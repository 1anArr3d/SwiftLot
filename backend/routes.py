from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from auth import get_current_user
from db import query, get_db
from pricing import price_range
from models import Auction, Vehicle, GarageVehicle
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
    # "Auction" in the UI means seller/sale event. Autura's real auction_id is
    # per-vehicle (each lot has its own closing time), so vehicles_count and
    # closes_at are computed live from vehicles rather than stored separately —
    # a seller with zero live vehicles just drops out of the JOIN.
    rows = query("""
        SELECT
            s.region_id                AS id,
            s.region_id,
            'autura'                   AS source,
            s.seller_name              AS name,
            s.seller_city              AS city,
            s.seller_state             AS state,
            COUNT(v.vin)               AS vehicles_count,
            MIN(v.bid_expiration)      AS closes_at
        FROM sellers s
        JOIN vehicles v ON v.region_id = s.region_id
        WHERE s.source = 'autura'
        GROUP BY s.region_id, s.seller_name, s.seller_city, s.seller_state
        ORDER BY closes_at NULLS LAST
    """)
    return [dict(row) for row in rows]


@router.get("/auctions/{auction_id}", response_model=Auction, tags=["auctions"])
def get_auction(auction_id: str):
    row = query("""
        SELECT s.region_id            AS auction_id,
               s.region_id,
               s.seller_name          AS seller_name,
               'ACTIVE'                AS auction_status,
               MIN(v.bid_expiration)  AS closes_at,
               s.last_discovered,
               s.seller_city,
               s.seller_state,
               COUNT(v.vin)           AS vehicles_listed
        FROM sellers s
        LEFT JOIN vehicles v ON v.region_id = s.region_id
        WHERE s.region_id = %s AND s.source = 'autura'
        GROUP BY s.region_id, s.seller_name, s.last_discovered, s.seller_city, s.seller_state
    """, (auction_id,), one=True)
    if not row:
        raise HTTPException(status_code=404, detail="Auction not found")
    return dict(row)


@router.get("/auctions/{auction_id}/vehicles", response_model=list[Vehicle], tags=["auctions"])
def get_auction_vehicles(auction_id: str, limit: int = 1000, offset: int = 0):
    # Ended vehicles are deleted from the table on scrape, so no status filter needed.
    rows = query(
        """SELECT v.* FROM vehicles v
           WHERE v.region_id = %s
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
    # Ended vehicles are deleted from the table on scrape, so no status filter needed.
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
        f"""SELECT v.*, s.seller_name, v.bid_expiration AS closes_at
            FROM vehicles v
            LEFT JOIN sellers s ON v.region_id = s.region_id
            {where} ORDER BY v.year DESC, v.make, v.model {limit_clause}""",
        tuple(args),
    )
    return [dict(row) for row in rows]


# ── Historical Sales ──────────────────────────────────────────────────────────

_bids_cache: dict[str, tuple[float, dict]] = {}  # vin -> (fetched at, result)


@router.get("/vehicles/{vin}/bids", tags=["vehicles"])
def vehicle_bids(vin: str):
    """
    A lot's bid history from Autura, oldest first: [{amount, at}] in dollars. Only amounts and times
    leave this function; Autura's rows also carry bidder ids, initials and email hints, which we never pass on.
    Cached 30s so a busy lot page doesn't turn into one Autura request per viewer.
    """
    import time
    from scrapers.autura.autura_api import get_bids
    hit = _bids_cache.get(vin)
    if hit and time.time() - hit[0] < 30:
        return hit[1]
    v = query("SELECT seller_id, auction_id FROM vehicles WHERE vin = %s", (vin,), one=True)
    if not v or not v["seller_id"] or not v["auction_id"]:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    try:
        raw = get_bids(v["seller_id"], v["auction_id"])
    except Exception:
        raise HTTPException(status_code=502, detail="Autura bid history unavailable")
    bids = sorted(({"amount": b["bidAmount"] / 100, "at": b["createdAt"]} for b in raw.get("bids") or [] if b.get("bidAmount") is not None),
                  key=lambda b: b["at"])
    result = {"total": raw.get("total", len(bids)), "bids": bids}
    if len(_bids_cache) > 2000:
        _bids_cache.clear()
    _bids_cache[vin] = (time.time(), result)
    return result


@router.post("/historical/stats/batch", tags=["historical"])
def get_historical_stats_batch(combos: list[dict]):
    results = {}
    for c in combos:
        make, model, year = c.get("make"), c.get("model"), c.get("year")
        if not make or not model or not year:
            continue
        r = price_range(make, model, year)
        if r:
            results[f"{make}|{model}|{year}"] = r
    return results


# ── Garage ────────────────────────────────────────────────────────────────────

@router.get("/garage", response_model=list[GarageVehicle], tags=["garage"])
def get_garage(user_id: str = Depends(get_current_user)):
    rows = query("""
        SELECT v.vin, v.year, v.make, v.model, v.body_type, v.color, v.key_status,
               v.catalytic_converter, v.start_status, v.engine_type, v.drivetrain,
               v.fuel_type, v.num_cylinders, v.documentation_type, v.auction_id,
               v.region_id, v.seller_id, v.item_id, v.item_key, v.current_bid,
               v.bid_expiration, v.min_bid, v.reserve_met, v.bidding_status, v.bidding_start,
               v.run_number, v.platform_fee_rate, v.platform_fee_min, v.platform_fee_max,
               v.card_fee_rate, v.extra_fees, v.seller_notes,
               v.images, v.images_count, v.published_at, v.last_recorded_odo,
               v.odo_rollback, w.liked_at
        FROM garage w
        JOIN vehicles v ON v.vin = w.vin
        WHERE w.user_id = %s

        UNION ALL

        SELECT w.vin, w.year, w.make, w.model, w.body_type, w.color, w.key_status,
               w.catalytic_converter, w.start_status, w.engine_type, w.drivetrain,
               w.fuel_type, w.num_cylinders, w.documentation_type, w.auction_id,
               w.region_id, w.seller_id, w.item_id, w.item_key, w.current_bid,
               w.bid_expiration, w.min_bid, NULL, NULL, NULL,
               NULL, NULL, NULL, NULL,
               NULL, NULL, NULL,
               w.images, w.images_count, NULL, w.last_recorded_odo,
               FALSE, w.liked_at
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
                current_bid, bid_expiration, min_bid,
                images, images_count, last_recorded_odo, liked_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
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
            vehicle["min_bid"],
            vehicle["images"], vehicle["images_count"], vehicle["last_recorded_odo"],
        ))
    return {"status": "added", "vin": vin}


@router.delete("/garage/{vin}", tags=["garage"])
def remove_from_garage(vin: str, user_id: str = Depends(get_current_user)):
    with get_db() as conn:
        conn.execute("DELETE FROM garage WHERE vin = %s AND user_id = %s", (vin, user_id))
    return {"status": "removed", "vin": vin}


# ── Live Bids ─────────────────────────────────────────────────────────────────

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

    # Existence in vehicles IS the "active" signal — ended vehicles are deleted on scrape.
    active_rows = query(
        "SELECT DISTINCT auction_id FROM vehicles WHERE auction_id = ANY(%s)",
        (auction_ids,)
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
