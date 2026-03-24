from fastapi import APIRouter, HTTPException, BackgroundTasks
from db import query, get_db
from models import JobStatus
from config import DB_PATH
from state import scrape_status, discovery_status
import scraper
import inspectionscrape
import discovery
import sqlite3

router = APIRouter(prefix="/api/v1", tags=["scraping"])


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


@router.post("/scrape/{auction_id}")
def start_scrape(auction_id: str, background_tasks: BackgroundTasks):
    row = query("SELECT region_id FROM auctions WHERE auction_id = ?", (auction_id,), one=True)
    if not row:
        raise HTTPException(status_code=404, detail="Auction not found")
    if scrape_status.get(auction_id) == "running":
        raise HTTPException(status_code=409, detail="Scrape already in progress")
    background_tasks.add_task(_run_scrape, auction_id, row["region_id"])
    return {"status": "started", "auction_id": auction_id}


@router.get("/scrape/{auction_id}/status", response_model=JobStatus)
def get_scrape_status(auction_id: str):
    status = scrape_status.get(auction_id)
    if status is None:
        raise HTTPException(status_code=404, detail="No scrape job found")
    return {"id": auction_id, "status": status}


@router.post("/inspectionscrape/{vin}")
def start_inspection(vin: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(inspectionscrape.run_inspection_scrape, vin)
    return {"status": "started", "vin": vin}


@router.post("/discovery/run")
def start_discovery(background_tasks: BackgroundTasks, state: str = "TX", region: str = None):
    key = region or state
    if discovery_status.get(key) == "running":
        raise HTTPException(status_code=409, detail="Discovery already in progress")
    background_tasks.add_task(_run_discovery, key, state, region)
    return {"status": "started", "key": key}


@router.get("/discovery/status", response_model=JobStatus)
def get_discovery_status(state: str = "TX", region: str = None):
    key = region or state
    status = discovery_status.get(key)
    if status is None:
        raise HTTPException(status_code=404, detail="No discovery job found")
    return {"id": key, "status": status}
