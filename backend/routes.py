from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from auth import get_current_user, require_admin
from db import query, get_db
from models import Auction, Vehicle, OdometerEntry, WatchlistVehicle, SavedAuction, JobStatus
from config import DB_PATH
from state import scrape_status, discovery_status, inspection_status
import auction_scraper as scraper
import inspection_scraper as inspection
import auction_discovery as discovery
import sqlite3
import threading

router = APIRouter(prefix="/api/v1")


# ── Auctions ──────────────────────────────────────────────────────────────────

@router.get("/auctions", response_model=list[Auction], tags=["auctions"])
def get_auctions():
    rows = query("""
        SELECT * FROM auctions
        WHERE auction_status != 'completed'
          AND (vehicles_listed IS NULL OR vehicles_listed > 0)
        ORDER BY seller_name
    """)
    return [dict(row) for row in rows]


@router.get("/auctions/{auction_id}", response_model=Auction, tags=["auctions"])
def get_auction(auction_id: str):
    row = query("SELECT * FROM auctions WHERE auction_id = ?", (auction_id,), one=True)
    if not row:
        raise HTTPException(status_code=404, detail="Auction not found")
    return dict(row)


@router.delete("/auctions", tags=["auctions"])
def delete_auctions(user_id: str = Depends(require_admin)):
    with get_db() as conn:
        conn.execute("DELETE FROM vehicles")
        conn.execute("DELETE FROM auctions")
    return {"status": "cleared"}


@router.get("/auctions/{auction_id}/vehicles", response_model=list[Vehicle], tags=["auctions"])
def get_auction_vehicles(auction_id: str):
    rows = query("SELECT * FROM vehicles WHERE auction_id = ?", (auction_id,))
    return [dict(row) for row in rows]


# ── Historical Sales ──────────────────────────────────────────────────────────

@router.get("/vehicles/{vin}/history", tags=["vehicles"])
def get_vehicle_history(vin: str):
    rows = query(
        "SELECT * FROM historical_sales WHERE vin = ? ORDER BY sold_at DESC",
        (vin,)
    )
    return [dict(row) for row in rows]


@router.get("/historical/stats", tags=["historical"])
def get_historical_stats(make: str, model: str, year: int):
    row = query(
        """SELECT
               COUNT(*)        AS count,
               ROUND(AVG(final_sale), 0) AS avg_sale,
               MIN(final_sale) AS min_sale,
               MAX(final_sale) AS max_sale
           FROM historical_sales
           WHERE UPPER(make) = UPPER(?)
             AND UPPER(model) = UPPER(?)
             AND year = ?
             AND final_sale IS NOT NULL""",
        (make, model, year),
        one=True,
    )
    if not row or row["count"] < 3:
        return {"make": make, "model": model, "year": year, "count": 0}
    return {
        "make": make,
        "model": model,
        "year": year,
        "count": row["count"],
        "avg_sale": row["avg_sale"],
        "min_sale": row["min_sale"],
        "max_sale": row["max_sale"],
    }


@router.get("/historical/search", tags=["historical"])
def search_historical(make: str = None, model: str = None, year: int = None, region_id: str = None, limit: int = 50):
    filters, args = [], []
    if make:
        filters.append("UPPER(make) = UPPER(?)")
        args.append(make)
    if model:
        filters.append("UPPER(model) LIKE UPPER(?)")
        args.append(f"%{model}%")
    if year:
        filters.append("year = ?")
        args.append(year)
    if region_id:
        filters.append("region_id = ?")
        args.append(region_id)
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    args.append(limit)
    rows = query(
        f"SELECT * FROM historical_sales {where} ORDER BY sold_at DESC LIMIT ?",
        tuple(args)
    )
    return [dict(row) for row in rows]


# ── Vehicles ──────────────────────────────────────────────────────────────────


@router.get("/vehicles/{vin}/odometer", response_model=list[OdometerEntry], tags=["vehicles"])
def get_odometer_history(vin: str):
    rows = query("SELECT * FROM odometer_history WHERE vin = ? ORDER BY inspection_date DESC", (vin,))
    return [dict(row) for row in rows]


# ── Watchlist ─────────────────────────────────────────────────────────────────

@router.get("/watchlist", response_model=list[WatchlistVehicle], tags=["watchlist"])
def get_watchlist(user_id: str = Depends(get_current_user)):
    rows = query("SELECT * FROM watchlist WHERE user_id = ? ORDER BY liked_at DESC", (user_id,))
    return [dict(row) for row in rows]


@router.post("/watchlist/{vin}", tags=["watchlist"])
def add_to_watchlist(vin: str, user_id: str = Depends(get_current_user)):
    vehicle = query("SELECT * FROM vehicles WHERE vin = ?", (vin,), one=True)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    with get_db() as conn:
        conn.execute('''
            INSERT OR IGNORE INTO watchlist (
                vin, user_id, year, make, model, body_type, color, key_status, catalytic_converter,
                start_status, engine_type, drivetrain, fuel_type, num_cylinders,
                documentation_type, auction_id, region_id, seller_id, item_id, item_key,
                current_bid, bid_expiration, reserve_price, fee_price,
                images, images_count, last_recorded_odo, liked_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, datetime('now')
            )
        ''', (
            vehicle["vin"], user_id, vehicle["year"], vehicle["make"], vehicle["model"],
            vehicle["body_type"], vehicle["color"], vehicle["key_status"],
            vehicle["catalytic_converter"], vehicle["start_status"], vehicle["engine_type"],
            vehicle["drivetrain"], vehicle["fuel_type"], vehicle["num_cylinders"],
            vehicle["documentation_type"], vehicle["auction_id"], vehicle["region_id"],
            vehicle["seller_id"], vehicle["item_id"], vehicle["item_key"],
            vehicle["current_bid"], vehicle["bid_expiration"],
            vehicle["reserve_price"], vehicle["fee_price"],
            vehicle["images"], vehicle["images_count"], vehicle["last_recorded_odo"],
        ))
    return {"status": "added", "vin": vin}


@router.delete("/watchlist/{vin}", tags=["watchlist"])
def remove_from_watchlist(vin: str, user_id: str = Depends(get_current_user)):
    with get_db() as conn:
        conn.execute("DELETE FROM watchlist WHERE vin = ? AND user_id = ?", (vin, user_id))
    return {"status": "removed", "vin": vin}


# ── Saved Auctions ────────────────────────────────────────────────────────────

@router.get("/saved-auctions", response_model=list[SavedAuction], tags=["saved-auctions"])
def get_saved_auctions(user_id: str = Depends(get_current_user)):
    rows = query("""
        SELECT a.auction_id, a.region_id, a.seller_name, a.auction_status,
               a.vehicles_listed, s.saved_at
        FROM saved_auctions s
        JOIN auctions a ON s.auction_id = a.auction_id
        WHERE s.user_id = ?
        ORDER BY s.saved_at DESC
    """, (user_id,))
    return [dict(row) for row in rows]


@router.post("/saved-auctions/{auction_id}", tags=["saved-auctions"])
def save_auction(auction_id: str, user_id: str = Depends(get_current_user)):
    auction = query("SELECT auction_id FROM auctions WHERE auction_id = ?", (auction_id,), one=True)
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO saved_auctions (auction_id, user_id, saved_at) VALUES (?, ?, datetime('now'))",
            (auction_id, user_id)
        )
    return {"status": "saved", "auction_id": auction_id}


@router.delete("/saved-auctions/{auction_id}", tags=["saved-auctions"])
def unsave_auction(auction_id: str, user_id: str = Depends(get_current_user)):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM saved_auctions WHERE auction_id = ? AND user_id = ?",
            (auction_id, user_id)
        )
    return {"status": "removed", "auction_id": auction_id}


# ── Jobs ──────────────────────────────────────────────────────────────────────

def _run_scrape(auction_id: str, region_id: str):
    try:
        scrape_status[auction_id] = "running"
        count = scraper.scrape_data(auction_id, region_id)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "UPDATE auctions SET last_scraped_count = ?, vehicles_listed = ?, last_scraped_at = datetime('now') WHERE auction_id = ?",
                (count, count, auction_id)
            )
        scrape_status[auction_id] = "done"
        if region_id and region_id.endswith('-TX'):
            rows = query(
                "SELECT vin FROM vehicles WHERE auction_id = ? AND last_recorded_odo IS NULL",
                (auction_id,)
            )
            vins = [row["vin"] for row in rows]
            if vins:
                print(f"[scrape] Firing inspection for {len(vins)} VINs")
                threading.Thread(target=inspection.run_inspection_batch, args=(vins,), daemon=True).start()
    except Exception as e:
        print(f"[scrape] ERROR for {auction_id}: {e}")
        scrape_status[auction_id] = "failed"


def _run_inspection(vin: str):
    try:
        inspection_status[vin] = "running"
        inspection.run_inspection_batch([vin])
        inspection_status[vin] = "done"
    except Exception as e:
        print(f"[inspection] ERROR for {vin}: {e}")
        inspection_status[vin] = "failed"


def _run_discovery(key: str):
    try:
        discovery_status[key] = "running"
        discovery.run_discovery()
        discovery_status[key] = "done"
    except Exception as e:
        print(f"[discovery] ERROR: {e}")
        discovery_status[key] = "failed"


def _run_pipeline(state: str):
    from scheduler import scheduled_discovery_and_scrape
    scheduled_discovery_and_scrape()


@router.post("/scrape/{auction_id}", tags=["jobs"])
def start_scrape(auction_id: str, background_tasks: BackgroundTasks, user_id: str = Depends(require_admin)):
    row = query("SELECT region_id FROM auctions WHERE auction_id = ?", (auction_id,), one=True)
    if not row:
        raise HTTPException(status_code=404, detail="Auction not found")
    if scrape_status.get(auction_id) == "running":
        raise HTTPException(status_code=409, detail="Scrape already in progress")
    background_tasks.add_task(_run_scrape, auction_id, row["region_id"])
    return {"status": "started", "auction_id": auction_id}


@router.get("/scrape/{auction_id}/status", response_model=JobStatus, tags=["jobs"])
def get_scrape_status(auction_id: str, user_id: str = Depends(require_admin)):
    status = scrape_status.get(auction_id)
    if status is None:
        raise HTTPException(status_code=404, detail="No scrape job found")
    return {"id": auction_id, "status": status}


@router.post("/inspectionscrape/{vin}", tags=["jobs"])
def start_inspection(vin: str, background_tasks: BackgroundTasks, user_id: str = Depends(require_admin)):
    background_tasks.add_task(_run_inspection, vin)
    return {"status": "started", "vin": vin}


@router.get("/inspectionscrape/{vin}/status", response_model=JobStatus, tags=["jobs"])
def get_inspection_status(vin: str, user_id: str = Depends(require_admin)):
    status = inspection_status.get(vin)
    if status is None:
        raise HTTPException(status_code=404, detail="No inspection job found")
    return {"id": vin, "status": status}


@router.post("/discovery/run", tags=["jobs"])
def start_discovery(background_tasks: BackgroundTasks, user_id: str = Depends(require_admin)):
    if discovery_status.get("global") == "running":
        raise HTTPException(status_code=409, detail="Discovery already in progress")
    background_tasks.add_task(_run_discovery, "global")
    return {"status": "started"}


@router.get("/discovery/status", response_model=JobStatus, tags=["jobs"])
def get_discovery_status(user_id: str = Depends(require_admin)):
    status = discovery_status.get("global")
    if status is None:
        raise HTTPException(status_code=404, detail="No discovery job found")
    return {"id": "global", "status": status}


@router.post("/pipeline/run", tags=["jobs"])
def run_full_pipeline(background_tasks: BackgroundTasks, user_id: str = Depends(require_admin)):
    background_tasks.add_task(_run_pipeline, None)
    return {"status": "started"}
