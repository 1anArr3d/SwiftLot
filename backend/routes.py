from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from auth import get_current_user
from db import query, get_db
from models import Auction, Vehicle, OdometerEntry, GarageVehicle, SavedAuction
from scrapers.autura import auction_listener as listener
import asyncio
import json

router = APIRouter(prefix="/api/v1")


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health", tags=["system"])
def get_health():
    return listener.health()


# ── Auctions ──────────────────────────────────────────────────────────────────

@router.get("/auctions", tags=["auctions"])
def get_auctions():
    rows = query("""
        SELECT
            region_id                               AS id,
            region_id,
            'autura'                                AS source,
            MAX(seller_name)                        AS name,
            MAX(seller_city)                        AS city,
            MAX(seller_state)                       AS state,
            SUM(COALESCE(vehicles_listed, 0))       AS vehicles_count,
            MIN(closes_at)                          AS closes_at
        FROM auctions
        WHERE source = 'autura'
          AND auction_status != 'completed'
        GROUP BY region_id
        ORDER BY closes_at NULLS LAST
    """)
    return [dict(row) for row in rows]


@router.get("/auctions/{auction_id}", response_model=Auction, tags=["auctions"])
def get_auction(auction_id: str):
    row = query("""
        SELECT region_id          AS auction_id,
               region_id,
               MAX(seller_name)   AS seller_name,
               'PRE_BID'          AS auction_status,
               MAX(closes_at)     AS closes_at,
               MAX(last_discovered) AS last_discovered,
               MAX(seller_city)   AS seller_city,
               MAX(seller_state)  AS seller_state,
               SUM(COALESCE(vehicles_listed, 0)) AS vehicles_listed
        FROM auctions
        WHERE region_id = %s AND source = 'autura'
        GROUP BY region_id
    """, (auction_id,), one=True)
    if not row:
        raise HTTPException(status_code=404, detail="Auction not found")
    return dict(row)


@router.get("/auctions/{auction_id}/vehicles", response_model=list[Vehicle], tags=["auctions"])
def get_auction_vehicles(auction_id: str, limit: int = 1000, offset: int = 0):
    rows = query(
        """SELECT v.* FROM vehicles v
           WHERE v.region_id = %s
             AND NOT EXISTS (
                 SELECT 1 FROM auctions a
                 WHERE a.auction_id = v.auction_id
                   AND a.auction_status = 'completed'
             )
           ORDER BY v.make, v.model, v.year LIMIT %s OFFSET %s""",
        (auction_id, limit, offset)
    )
    return [dict(row) for row in rows]


# ── Vehicle Search ───────────────────────────────────────────────────────────

@router.get("/vehicles", response_model=list[Vehicle], tags=["vehicles"])
def search_vehicles(
    make: str = None,
    model: str = None,
    year_min: int = None,
    year_max: int = None,
    region_id: str = None,
    limit: int = None,
):
    filters, args = ["v.make NOT IN ('OTHER', 'OTHER-NOT FOUND') AND v.year IS NOT NULL AND v.year < 9000"], []
    if make:
        filters.append("UPPER(make) = UPPER(%s)")
        args.append(make)
    if model:
        filters.append("UPPER(model) LIKE UPPER(%s)")
        args.append(f"%{model}%")
    if year_min:
        filters.append("year >= %s")
        args.append(year_min)
    if year_max:
        filters.append("year <= %s")
        args.append(year_max)
    if region_id:
        filters.append("region_id = %s")
        args.append(region_id)
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    limit_clause = f"LIMIT {int(limit)}" if limit else ""
    rows = query(
        f"""SELECT v.*, a.seller_name, a.closes_at
            FROM vehicles v
            LEFT JOIN auctions a ON v.auction_id = a.auction_id
            {where} ORDER BY v.year DESC, v.make, v.model {limit_clause}""",
        tuple(args),
    )
    return [dict(row) for row in rows]


# ── Historical Sales ──────────────────────────────────────────────────────────

@router.get("/vehicles/{vin}/history", tags=["vehicles"])
def get_vehicle_history(vin: str):
    rows = query(
        "SELECT * FROM historical_sales WHERE vin = %s ORDER BY sold_at DESC",
        (vin,)
    )
    return [dict(row) for row in rows]


@router.get("/historical/stats", tags=["historical"])
def get_historical_stats(make: str, model: str, year: int):
    _sql = """SELECT
               COUNT(*)                          AS count,
               ROUND(AVG(final_sale)::numeric, 0) AS avg_sale,
               MIN(final_sale)                   AS min_sale,
               MAX(final_sale)                   AS max_sale
           FROM historical_sales
           WHERE UPPER(make) = UPPER(%s)
             AND UPPER(model) = UPPER(%s)
             AND {year_clause}
             AND final_sale IS NOT NULL"""

    row = query(_sql.format(year_clause="year = %s"), (make, model, year), one=True)
    if row and row["count"] >= 3:
        return {"make": make, "model": model, "year": year, "count": row["count"],
                "avg_sale": row["avg_sale"], "min_sale": row["min_sale"], "max_sale": row["max_sale"]}

    # Fall back to ±2 year window
    row = query(_sql.format(year_clause="year BETWEEN %s AND %s"), (make, model, year - 2, year + 2), one=True)
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
        "approx": True,
    }


@router.post("/historical/stats/batch", tags=["historical"])
def get_historical_stats_batch(combos: list[dict]):
    _sql = """SELECT
               COUNT(*)                           AS count,
               ROUND(AVG(final_sale)::numeric, 0) AS avg_sale,
               MIN(final_sale)                    AS min_sale,
               MAX(final_sale)                    AS max_sale
           FROM historical_sales
           WHERE UPPER(make) = UPPER(%s)
             AND UPPER(model) = UPPER(%s)
             AND {year_clause}
             AND final_sale IS NOT NULL"""

    results = {}
    for c in combos:
        make, model, year = c.get("make"), c.get("model"), c.get("year")
        if not make or not model or not year:
            continue
        key = f"{make}|{model}|{year}"
        row = query(_sql.format(year_clause="year = %s"), (make, model, year), one=True)
        if row and row["count"] >= 3:
            results[key] = {"count": row["count"], "avg_sale": row["avg_sale"],
                            "min_sale": row["min_sale"], "max_sale": row["max_sale"]}
            continue
        row = query(_sql.format(year_clause="year BETWEEN %s AND %s"), (make, model, year - 2, year + 2), one=True)
        if row and row["count"] >= 3:
            results[key] = {"count": row["count"], "avg_sale": row["avg_sale"],
                            "min_sale": row["min_sale"], "max_sale": row["max_sale"], "approx": True}
    return results


@router.get("/historical/search", tags=["historical"])
def search_historical(make: str = None, model: str = None, year: int = None, region_id: str = None, limit: int = 50):
    filters, args = [], []
    if make:
        filters.append("UPPER(make) = UPPER(%s)")
        args.append(make)
    if model:
        filters.append("UPPER(model) LIKE UPPER(%s)")
        args.append(f"%{model}%")
    if year:
        filters.append("year = %s")
        args.append(year)
    if region_id:
        filters.append("region_id = %s")
        args.append(region_id)
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    args.append(limit)
    rows = query(
        f"SELECT * FROM historical_sales {where} ORDER BY sold_at DESC LIMIT %s",
        tuple(args)
    )
    return [dict(row) for row in rows]


# ── Vehicles ──────────────────────────────────────────────────────────────────


@router.get("/vehicles/{vin}/odometer", response_model=list[OdometerEntry], tags=["vehicles"])
def get_odometer_history(vin: str):
    rows = query("SELECT * FROM odometer_history WHERE vin = %s ORDER BY inspection_date DESC", (vin,))
    return [dict(row) for row in rows]


# ── Garage ────────────────────────────────────────────────────────────────────

@router.get("/garage", response_model=list[GarageVehicle], tags=["garage"])
def get_garage(user_id: str = Depends(get_current_user)):
    rows = query("""
        SELECT v.vin, v.year, v.make, v.model, v.body_type, v.color, v.key_status,
               v.catalytic_converter, v.start_status, v.engine_type, v.drivetrain,
               v.fuel_type, v.num_cylinders, v.documentation_type, v.auction_id,
               v.region_id, v.seller_id, v.item_id, v.item_key, v.current_bid,
               v.bid_expiration, v.reserve_price, v.fee_price, v.seller_notes,
               v.images, v.images_count, v.published_at, v.last_recorded_odo,
               w.liked_at
        FROM garage w
        JOIN vehicles v ON v.vin = w.vin
        WHERE w.user_id = %s

        UNION ALL

        SELECT w.vin, w.year, w.make, w.model, w.body_type, w.color, w.key_status,
               w.catalytic_converter, w.start_status, w.engine_type, w.drivetrain,
               w.fuel_type, w.num_cylinders, w.documentation_type, w.auction_id,
               w.region_id, w.seller_id, w.item_id, w.item_key, w.current_bid,
               w.bid_expiration, w.reserve_price, w.fee_price, NULL,
               w.images, w.images_count, NULL, w.last_recorded_odo,
               w.liked_at
        FROM garage w
        WHERE w.user_id = %s
          AND NOT EXISTS (SELECT 1 FROM vehicles v WHERE v.vin = w.vin)

        ORDER BY liked_at DESC
    """, (user_id, user_id))
    return [dict(row) for row in rows]


@router.post("/garage/{vin}", tags=["garage"])
def add_to_garage(vin: str, user_id: str = Depends(get_current_user)):
    vehicle = query("SELECT * FROM vehicles WHERE vin = %s", (vin,), one=True)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    with get_db() as conn:
        conn.execute('''
            INSERT INTO garage (
                vin, user_id, year, make, model, body_type, color, key_status, catalytic_converter,
                start_status, engine_type, drivetrain, fuel_type, num_cylinders,
                documentation_type, auction_id, region_id, seller_id, item_id, item_key,
                current_bid, bid_expiration, reserve_price, fee_price,
                images, images_count, last_recorded_odo, liked_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, NOW()
            )
            ON CONFLICT (vin, user_id) DO NOTHING
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


@router.delete("/garage/{vin}", tags=["garage"])
def remove_from_garage(vin: str, user_id: str = Depends(get_current_user)):
    with get_db() as conn:
        conn.execute("DELETE FROM garage WHERE vin = %s AND user_id = %s", (vin, user_id))
    return {"status": "removed", "vin": vin}


# ── Saved Auctions ────────────────────────────────────────────────────────────

@router.get("/saved-auctions", response_model=list[SavedAuction], tags=["saved-auctions"])
def get_saved_auctions(user_id: str = Depends(get_current_user)):
    rows = query("""
        SELECT s.auction_id AS region_id,
               MAX(a.seller_name) AS seller_name,
               MAX(a.seller_city) AS seller_city,
               MAX(a.seller_state) AS seller_state,
               'PRE_BID' AS auction_status,
               SUM(COALESCE(a.vehicles_listed, 0)) AS vehicles_listed,
               MIN(a.closes_at) AS closes_at,
               s.saved_at
        FROM saved_auctions s
        JOIN auctions a ON s.auction_id = a.region_id
        WHERE s.user_id = %s
        GROUP BY s.auction_id, s.saved_at
        ORDER BY s.saved_at DESC
    """, (user_id,))
    return [dict(row) for row in rows]


@router.get("/saved-auctions/check/{region_id}", tags=["saved-auctions"])
def check_saved_auction(region_id: str, user_id: str = Depends(get_current_user)):
    row = query("SELECT 1 FROM saved_auctions WHERE auction_id = %s AND user_id = %s", (region_id, user_id), one=True)
    return {"saved": row is not None}


@router.post("/saved-auctions/{region_id}", tags=["saved-auctions"])
def save_auction(region_id: str, user_id: str = Depends(get_current_user)):
    auction = query("SELECT 1 FROM auctions WHERE region_id = %s LIMIT 1", (region_id,), one=True)
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
    with get_db() as conn:
        conn.execute(
            "INSERT INTO saved_auctions (auction_id, user_id, saved_at) VALUES (%s, %s, NOW()) ON CONFLICT DO NOTHING",
            (region_id, user_id)
        )
    return {"status": "saved", "region_id": region_id}


@router.delete("/saved-auctions/{region_id}", tags=["saved-auctions"])
def unsave_auction(region_id: str, user_id: str = Depends(get_current_user)):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM saved_auctions WHERE auction_id = %s AND user_id = %s",
            (region_id, user_id)
        )
    return {"status": "removed", "region_id": region_id}


# ── SSE Stream ────────────────────────────────────────────────────────────────

@router.get("/stream/multi", tags=["stream"])
async def stream_multi_auctions(request: Request, auctions: str = ""):
    """
    SSE stream for live updates across multiple auctions.
    Query param: auctions=id1,id2,id3
    Emits: {"type":"update","auction_id":..,"vehicles":[{item_key,current_bid,bid_expiration},...]}
    Emits: {"type":"ended","auction_id":..}
    """
    auction_ids = [a.strip() for a in auctions.split(",") if a.strip()]
    if not auction_ids:
        async def _empty():
            yield f"data: {json.dumps({'type': 'no_active'})}\n\n"
        return StreamingResponse(_empty(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    placeholders = ",".join(["%s"] * len(auction_ids))
    active_rows = query(
        f"SELECT auction_id FROM auctions WHERE auction_id IN ({placeholders}) AND auction_status != 'completed'",
        tuple(auction_ids)
    )
    active_ids = [r["auction_id"] for r in active_rows]

    async def event_gen():
        if not active_ids:
            yield f"data: {json.dumps({'type': 'no_active'})}\n\n"
            return

        merged: asyncio.Queue = asyncio.Queue()
        per_auction_queues: dict[str, asyncio.Queue] = {}

        for aid in active_ids:
            q: asyncio.Queue = asyncio.Queue()
            per_auction_queues[aid] = q
            listener.add_client(aid, q)

        async def drain(aid, q):
            while True:
                event = await q.get()
                await merged.put(event)
                if event.get("type") == "ended":
                    break

        tasks = [asyncio.create_task(drain(aid, q)) for aid, q in per_auction_queues.items()]

        # Send one snapshot per auction on connect
        for aid in active_ids:
            yield f"data: {json.dumps(listener._vehicle_snapshot(aid))}\n\n"

        remaining = set(active_ids)
        try:
            while remaining:
                try:
                    event = await asyncio.wait_for(merged.get(), timeout=25)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") == "ended":
                        remaining.discard(event.get("auction_id"))
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            for task in tasks:
                task.cancel()
            for aid, q in per_auction_queues.items():
                listener.remove_client(aid, q)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/stream/auction/{auction_id}", tags=["stream"])
async def stream_auction_updates(auction_id: str):
    """
    SSE stream for live updates on a single auction.
    Emits: {"type":"update","auction_id":..,"vehicles":[{item_key,current_bid,bid_expiration},...]}
    Emits: {"type":"ended","auction_id":..}
    """
    async def event_gen():
        auction = query(
            "SELECT auction_status FROM auctions WHERE auction_id = %s",
            (auction_id,), one=True
        )
        if auction and auction["auction_status"] == "completed":
            yield f"data: {json.dumps({'type': 'ended', 'auction_id': auction_id})}\n\n"
            return

        queue = asyncio.Queue()
        listener.add_client(auction_id, queue)
        try:
            # Snapshot on connect
            yield f"data: {json.dumps(listener._vehicle_snapshot(auction_id))}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") == "ended":
                        break
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            listener.remove_client(auction_id, queue)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

