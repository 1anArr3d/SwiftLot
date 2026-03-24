from fastapi import APIRouter, HTTPException
from db import query, get_db
from models import WatchlistVehicle

router = APIRouter(prefix="/api/v1/watchlist", tags=["watchlist"])


@router.get("", response_model=list[WatchlistVehicle])
def get_watchlist():
    rows = query("SELECT * FROM watchlist ORDER BY liked_at DESC")
    return [dict(row) for row in rows]


@router.post("/{vin}")
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


@router.delete("/{vin}")
def remove_from_watchlist(vin: str):
    with get_db() as conn:
        conn.execute("DELETE FROM watchlist WHERE vin = ?", (vin,))
    return {"status": "removed", "vin": vin}
