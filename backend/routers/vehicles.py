from fastapi import APIRouter
from db import query, get_db
from models import Vehicle, OdometerEntry

router = APIRouter(prefix="/api/v1/vehicles", tags=["vehicles"])


@router.get("", response_model=list[Vehicle])
def get_vehicles():
    rows = query("SELECT * FROM vehicles")
    return [dict(row) for row in rows]


@router.get("/{vin}/odometer", response_model=list[OdometerEntry])
def get_odometer_history(vin: str):
    rows = query(
        "SELECT * FROM odometer_history WHERE vin = ? ORDER BY inspection_date DESC",
        (vin,)
    )
    return [dict(row) for row in rows]


@router.delete("")
def clear_vehicles():
    with get_db() as conn:
        conn.execute("DELETE FROM vehicles")
        conn.execute("DELETE FROM odometer_history")
    return {"status": "success", "message": "All vehicles cleared"}
