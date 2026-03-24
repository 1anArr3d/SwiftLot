from fastapi import APIRouter, HTTPException
from db import query, get_db
from models import Auction, Vehicle

router = APIRouter(prefix="/api/v1/auctions", tags=["auctions"])


@router.get("", response_model=list[Auction])
def get_auctions():
    rows = query("SELECT * FROM auctions ORDER BY auction_date")
    return [dict(row) for row in rows]


@router.delete("")
def clear_auctions():
    with get_db() as conn:
        conn.execute("DELETE FROM vehicles")
        conn.execute("DELETE FROM auctions")
    return {"status": "success", "message": "All auctions and vehicles cleared"}


@router.get("/{auction_id}/vehicles", response_model=list[Vehicle])
def get_auction_vehicles(auction_id: str):
    rows = query(
        "SELECT * FROM vehicles WHERE auction_id = ?",
        (auction_id,)
    )
    if rows is None:
        raise HTTPException(status_code=404, detail="Auction not found")
    return [dict(row) for row in rows]
