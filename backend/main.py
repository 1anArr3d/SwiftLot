import sqlite3
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import scraper
import inspectionscrape

DB_PATH = 'swiftlot.db'

# Tracks in-progress and completed scrape jobs: auction_id -> "running" | "done" | "failed"
scrape_status: dict[str, str] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    scraper.init_db()
    yield

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

def query_db(query, args=(), one=False):
    """Helper to handle boilerplate SQLite logic."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(query, args)
        rv = cur.fetchall()
        return (rv[0] if rv else None) if one else rv

# api routes

@app.get("/vehicles")
def get_vehicles():
    rows = query_db("SELECT * FROM vehicles")
    return [dict(row) for row in rows]

@app.get("/odometer/{vin}")
def get_odometer_history(vin: str):
    rows = query_db("SELECT * FROM odometer_history WHERE vin = ? ORDER BY inspection_date DESC", (vin,))
    return [dict(row) for row in rows]

def _run_scrape(auction_id: str, city: str = "SA-TX"):
    try:
        scrape_status[auction_id] = "running"
        scraper.scrape_data(auction_id, city)
        scrape_status[auction_id] = "done"
    except Exception:
        scrape_status[auction_id] = "failed"

@app.post("/scrape/{auction_id}")
async def start_scrape(auction_id: str, background_tasks: BackgroundTasks, city: str = "SA-TX"):
    if scrape_status.get(auction_id) == "running":
        raise HTTPException(status_code=409, detail="Scrape already in progress for this auction")
    background_tasks.add_task(_run_scrape, auction_id, city)
    return {"status": "started", "auction_id": auction_id, "city": city}

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


@app.delete("/vehicles")
def clear_database():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM vehicles")
        conn.execute("DELETE FROM odometer_history")
    return {"status": "success", "message": "All data cleared"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)