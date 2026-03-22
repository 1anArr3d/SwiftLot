import sqlite3
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import scraper
import inspectionscrape
import discovery

DB_PATH = 'swiftlot.db'

# Tracks in-progress and completed jobs: id -> "running" | "done" | "failed"
scrape_status: dict[str, str] = {}
discovery_status: dict[str, str] = {}


def query_db(query, args=(), one=False):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(query, args)
        rv = cur.fetchall()
        return (rv[0] if rv else None) if one else rv


def _run_scrape(auction_id: str, city: str):
    try:
        scrape_status[auction_id] = "running"
        scraper.scrape_data(auction_id, city)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "UPDATE auctions SET last_scraped_count = vehicles_listed WHERE auction_id = ?",
                (auction_id,)
            )
        scrape_status[auction_id] = "done"
    except Exception:
        scrape_status[auction_id] = "failed"


def _run_discovery(key: str, state: str, region_id: str = None):
    try:
        discovery_status[key] = "running"
        discovery.run_discovery(state, region_id)
        discovery_status[key] = "done"
    except Exception:
        discovery_status[key] = "failed"


def scheduled_discovery_and_scrape():
    print("[scheduler] Running scheduled discovery...")
    discovery.run_discovery("TX")

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            DELETE FROM vehicles WHERE auction_id IN (
                SELECT auction_id FROM auctions WHERE auction_status = 'completed'
            )
        """)

    rows = query_db(
        """SELECT auction_id, region_id FROM auctions
           WHERE vehicles_listed > 0
             AND auction_status != 'completed'
             AND (last_scraped_count IS NULL OR last_scraped_count != vehicles_listed)"""
    )
    for row in rows:
        auction_id = row["auction_id"]
        if scrape_status.get(auction_id) != "running":
            print(f"[scheduler] Triggering scrape for {auction_id}")
            _run_scrape(auction_id, row["region_id"])

    print("[scheduler] Done.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scraper.init_db()
    discovery.init_db()

    scheduler = BackgroundScheduler(timezone="America/Chicago")
    scheduler.add_job(
        scheduled_discovery_and_scrape,
        CronTrigger(hour="8,14,22", timezone="America/Chicago")
    )
    scheduler.start()
    print("[scheduler] Started — jobs at 8am, 2pm, 10pm CT")

    yield

    scheduler.shutdown(wait=False)
    print("[scheduler] Stopped.")


app = FastAPI(lifespan=lifespan)

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# --- vehicles ---

@app.get("/vehicles")
def get_vehicles():
    rows = query_db("SELECT * FROM vehicles")
    return [dict(row) for row in rows]

@app.get("/odometer/{vin}")
def get_odometer_history(vin: str):
    rows = query_db("SELECT * FROM odometer_history WHERE vin = ? ORDER BY inspection_date DESC", (vin,))
    return [dict(row) for row in rows]

@app.delete("/vehicles")
def clear_database():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM vehicles")
        conn.execute("DELETE FROM odometer_history")
    return {"status": "success", "message": "All data cleared"}

# --- scraping ---

@app.post("/scrape/{auction_id}")
async def start_scrape(auction_id: str, background_tasks: BackgroundTasks):
    row = query_db("SELECT region_id FROM auctions WHERE auction_id = ?", (auction_id,), one=True)
    if not row:
        raise HTTPException(status_code=404, detail="Auction not found")
    if scrape_status.get(auction_id) == "running":
        raise HTTPException(status_code=409, detail="Scrape already in progress for this auction")
    background_tasks.add_task(_run_scrape, auction_id, row["region_id"])
    return {"status": "started", "auction_id": auction_id, "city": row["region_id"]}

@app.get("/scrape/{auction_id}/status")
def get_scrape_status(auction_id: str):
    status = scrape_status.get(auction_id)
    if status is None:
        raise HTTPException(status_code=404, detail="No scrape job found for this auction")
    return {"auction_id": auction_id, "status": status}

@app.post("/inspectionscrape/{vin}")
async def start_inspection(vin: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(inspectionscrape.run_inspection_scrape, vin)
    return {"status": "started", "vin": vin}

# --- watchlist ---

@app.get("/watchlist")
def get_watchlist():
    rows = query_db("SELECT * FROM watchlist ORDER BY liked_at DESC")
    return [dict(row) for row in rows]

@app.post("/watchlist/{vin}")
def add_to_watchlist(vin: str):
    vehicle = query_db("SELECT * FROM vehicles WHERE vin = ?", (vin,), one=True)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            INSERT OR IGNORE INTO watchlist
                (vin, year, make, model, color, key_status, catalytic_converter,
                 start_status, engine_type, transmission, auction_id, city,
                 last_recorded_odo, images, liked_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ''', (
            vehicle["vin"], vehicle["year"], vehicle["make"], vehicle["model"],
            vehicle["color"], vehicle["key_status"], vehicle["catalytic_converter"],
            vehicle["start_status"], vehicle["engine_type"], vehicle["transmission"],
            vehicle["auction_id"], vehicle["city"], vehicle["last_recorded_odo"],
            vehicle["images"]
        ))
    return {"status": "added", "vin": vin}

@app.delete("/watchlist/{vin}")
def remove_from_watchlist(vin: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM watchlist WHERE vin = ?", (vin,))
    return {"status": "removed", "vin": vin}

# --- auctions ---

@app.get("/auctions")
def get_auctions():
    rows = query_db("SELECT * FROM auctions ORDER BY auction_date")
    return [dict(row) for row in rows]

@app.post("/discovery/run")
async def start_discovery(background_tasks: BackgroundTasks, state: str = "TX", region: str = None):
    key = region or state
    if discovery_status.get(key) == "running":
        raise HTTPException(status_code=409, detail="Discovery already in progress")
    background_tasks.add_task(_run_discovery, key, state, region)
    return {"status": "started", "key": key}

@app.get("/discovery/status")
def get_discovery_status(state: str = "TX", region: str = None):
    key = region or state
    status = discovery_status.get(key)
    if status is None:
        raise HTTPException(status_code=404, detail="No discovery job found")
    return {"key": key, "status": status}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
