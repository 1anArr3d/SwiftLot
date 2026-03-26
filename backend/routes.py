from fastapi import APIRouter, HTTPException, BackgroundTasks
from concurrent.futures import ThreadPoolExecutor
from db import query, get_db
from models import Auction, Vehicle, OdometerEntry, WatchlistVehicle, JobStatus
from config import DB_PATH
from state import scrape_status, discovery_status, inspection_status
import scraper
import inspection
import discovery
import sqlite3
import threading

INSPECTION_WORKERS = 2

router = APIRouter(prefix="/api/v1")


# ── Auctions ──────────────────────────────────────────────────────────────────

@router.get("/auctions", response_model=list[Auction], tags=["auctions"])
def get_auctions():
    rows = query("SELECT * FROM auctions ORDER BY seller_name")
    return [dict(row) for row in rows]


@router.get("/auctions/{auction_id}", response_model=Auction, tags=["auctions"])
def get_auction(auction_id: str):
    row = query("SELECT * FROM auctions WHERE auction_id = ?", (auction_id,), one=True)
    if not row:
        raise HTTPException(status_code=404, detail="Auction not found")
    return dict(row)


@router.delete("/auctions", tags=["auctions"])
def delete_auctions():
    with get_db() as conn:
        conn.execute("DELETE FROM vehicles")
        conn.execute("DELETE FROM auctions")
    return {"status": "cleared"}


@router.get("/auctions/{auction_id}/vehicles", response_model=list[Vehicle], tags=["auctions"])
def get_auction_vehicles(auction_id: str):
    rows = query("SELECT * FROM vehicles WHERE auction_id = ?", (auction_id,))
    return [dict(row) for row in rows]


# ── Vehicles ──────────────────────────────────────────────────────────────────


@router.get("/vehicles/{vin}/odometer", response_model=list[OdometerEntry], tags=["vehicles"])
def get_odometer_history(vin: str):
    rows = query("SELECT * FROM odometer_history WHERE vin = ? ORDER BY inspection_date DESC", (vin,))
    return [dict(row) for row in rows]


# ── Watchlist ─────────────────────────────────────────────────────────────────

@router.get("/watchlist", response_model=list[WatchlistVehicle], tags=["watchlist"])
def get_watchlist():
    rows = query("SELECT * FROM watchlist ORDER BY liked_at DESC")
    return [dict(row) for row in rows]


@router.post("/watchlist/{vin}", tags=["watchlist"])
def add_to_watchlist(vin: str):
    vehicle = query("SELECT * FROM vehicles WHERE vin = ?", (vin,), one=True)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    with get_db() as conn:
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


@router.delete("/watchlist/{vin}", tags=["watchlist"])
def remove_from_watchlist(vin: str):
    with get_db() as conn:
        conn.execute("DELETE FROM watchlist WHERE vin = ?", (vin,))
    return {"status": "removed", "vin": vin}


# ── Jobs ──────────────────────────────────────────────────────────────────────

def _run_inspections(vins: list[str]):
    with ThreadPoolExecutor(max_workers=INSPECTION_WORKERS) as pool:
        pool.map(inspection.run_inspection_scrape, vins)


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
        if city and city.endswith('-TX'):
            rows = query(
                "SELECT vin FROM vehicles WHERE auction_id = ? AND last_recorded_odo IS NULL",
                (auction_id,)
            )
            vins = [row["vin"] for row in rows]
            if vins:
                print(f"[scrape] Firing inspection for {len(vins)} VINs")
                threading.Thread(target=_run_inspections, args=(vins,), daemon=True).start()
    except Exception as e:
        print(f"[scrape] ERROR for {auction_id}: {e}")
        scrape_status[auction_id] = "failed"


def _run_inspection(vin: str):
    try:
        inspection_status[vin] = "running"
        inspection.run_inspection_scrape(vin)
        inspection_status[vin] = "done"
    except Exception as e:
        print(f"[inspection] ERROR for {vin}: {e}")
        inspection_status[vin] = "failed"


def _run_discovery(key: str, state: str, region_id: str = None):
    try:
        discovery_status[key] = "running"
        discovery.run_discovery(state, region_id)
        discovery_status[key] = "done"
    except Exception as e:
        print(f"[discovery] ERROR: {e}")
        discovery_status[key] = "failed"


def _run_pipeline(state: str):
    from scheduler import scheduled_discovery_and_scrape
    scheduled_discovery_and_scrape()


@router.post("/scrape/{auction_id}", tags=["jobs"])
def start_scrape(auction_id: str, background_tasks: BackgroundTasks):
    row = query("SELECT region_id FROM auctions WHERE auction_id = ?", (auction_id,), one=True)
    if not row:
        raise HTTPException(status_code=404, detail="Auction not found")
    if scrape_status.get(auction_id) == "running":
        raise HTTPException(status_code=409, detail="Scrape already in progress")
    background_tasks.add_task(_run_scrape, auction_id, row["region_id"])
    return {"status": "started", "auction_id": auction_id}


@router.get("/scrape/{auction_id}/status", response_model=JobStatus, tags=["jobs"])
def get_scrape_status(auction_id: str):
    status = scrape_status.get(auction_id)
    if status is None:
        raise HTTPException(status_code=404, detail="No scrape job found")
    return {"id": auction_id, "status": status}


@router.post("/inspectionscrape/{vin}", tags=["jobs"])
def start_inspection(vin: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_inspection, vin)
    return {"status": "started", "vin": vin}


@router.get("/inspectionscrape/{vin}/status", response_model=JobStatus, tags=["jobs"])
def get_inspection_status(vin: str):
    status = inspection_status.get(vin)
    if status is None:
        raise HTTPException(status_code=404, detail="No inspection job found")
    return {"id": vin, "status": status}


@router.post("/discovery/run", tags=["jobs"])
def start_discovery(background_tasks: BackgroundTasks, state: str = "TX", region: str = None):
    key = region or state
    if discovery_status.get(key) == "running":
        raise HTTPException(status_code=409, detail="Discovery already in progress")
    background_tasks.add_task(_run_discovery, key, state, region)
    return {"status": "started", "key": key}


@router.get("/discovery/status", response_model=JobStatus, tags=["jobs"])
def get_discovery_status(state: str = "TX", region: str = None):
    key = region or state
    status = discovery_status.get(key)
    if status is None:
        raise HTTPException(status_code=404, detail="No discovery job found")
    return {"id": key, "status": status}


@router.post("/pipeline/run", tags=["jobs"])
def run_full_pipeline(background_tasks: BackgroundTasks, state: str = "TX"):
    background_tasks.add_task(_run_pipeline, state)
    return {"status": "started", "state": state}
