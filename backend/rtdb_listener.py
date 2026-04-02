"""
RTDB SSE Listener — subscribes to Firebase RTDB auction + results nodes
for all active auctions and processes events in real-time.

Two threads per auction:
  - auction thread: watches /{region}/auctions/{id} for startItem (LIVE), ended
  - results thread: watches /{region}/results/{id} for bid updates
"""
import json
import threading
import time
import requests
from db import query, get_db
import autura_api
import historical_harvester as harvester

_RTDB = "https://digital-auction.firebaseio.com"

# auction_id -> {"auction": Thread, "results": Thread, "stop": Event, "region_id": str}
_subscriptions: dict = {}
_lock = threading.Lock()


# ── Snapshot + cleanup (shared with scheduler) ─────────────────────────────────

def handle_auction_completed(auction_id: str, region_id: str):
    """
    Run the end-of-auction snapshot: archive vehicles to garage for users who
    saved the auction, update final bids, then remove from vehicles table.
    Fires harvest immediately. Called by both listener and scheduler.
    """
    print(f"[listener] {auction_id} ended — running snapshot")
    with get_db() as conn:
        # Update final bid for vehicles already in any user's garage
        conn.execute("""
            UPDATE garage
            SET current_bid = (
                SELECT v.current_bid FROM vehicles v WHERE v.vin = garage.vin
            )
            WHERE vin IN (
                SELECT v.vin FROM vehicles v WHERE v.auction_id = ?
            )
        """, (auction_id,))

        # Copy vehicles into garage for users who saved this auction
        rows = conn.execute("""
            SELECT sa.user_id,
                   v.vin, v.year, v.make, v.model, v.body_type, v.color, v.key_status,
                   v.catalytic_converter, v.start_status, v.engine_type, v.drivetrain,
                   v.fuel_type, v.num_cylinders, v.documentation_type, v.auction_id,
                   v.region_id, v.seller_id, v.item_id, v.item_key, v.current_bid,
                   v.bid_expiration, v.reserve_price, v.fee_price, v.images,
                   v.images_count, v.last_recorded_odo
            FROM saved_auctions sa
            JOIN vehicles v ON v.auction_id = sa.auction_id
            WHERE sa.auction_id = ?
        """, (auction_id,)).fetchall()

        for row in rows:
            conn.execute('''
                INSERT OR IGNORE INTO garage (
                    vin, user_id, year, make, model, body_type, color, key_status,
                    catalytic_converter, start_status, engine_type, drivetrain, fuel_type,
                    num_cylinders, documentation_type, auction_id, region_id, seller_id,
                    item_id, item_key, current_bid, bid_expiration, reserve_price, fee_price,
                    images, images_count, last_recorded_odo, liked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ''', (
                row['vin'], row['user_id'], row['year'], row['make'], row['model'],
                row['body_type'], row['color'], row['key_status'], row['catalytic_converter'],
                row['start_status'], row['engine_type'], row['drivetrain'], row['fuel_type'],
                row['num_cylinders'], row['documentation_type'], row['auction_id'], row['region_id'],
                row['seller_id'], row['item_id'], row['item_key'], row['current_bid'],
                row['bid_expiration'], row['reserve_price'], row['fee_price'],
                row['images'], row['images_count'], row['last_recorded_odo']
            ))

        # Mark completed and delete vehicles
        conn.execute(
            "UPDATE auctions SET auction_status = 'completed' WHERE auction_id = ?",
            (auction_id,)
        )
        conn.execute("DELETE FROM vehicles WHERE auction_id = ?", (auction_id,))

    # Harvest in background
    threading.Thread(
        target=harvester.harvest_auction,
        args=(region_id, auction_id),
        daemon=True
    ).start()


# ── Per-auction SSE stream handlers ────────────────────────────────────────────

def _stream_auction_node(region_id: str, auction_id: str, stop: threading.Event):
    """Watch /{region}/auctions/{auction_id} for live/ended state changes."""
    url = f"{_RTDB}/{region_id}/auctions/{auction_id}.json"
    while not stop.is_set():
        token = autura_api.get_token()
        try:
            with requests.get(
                url,
                params={"auth": token},
                headers={"Accept": "text/event-stream"},
                stream=True,
                timeout=90,
            ) as resp:
                for raw in resp.iter_lines():
                    if stop.is_set():
                        return
                    if not raw:
                        continue
                    line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if not payload or payload == "null":
                        continue
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue

                    if not isinstance(data, dict):
                        continue

                    auction_data = data.get("data") or data

                    ended = auction_data.get("ended", False)
                    start_item = auction_data.get("startItem")
                    paused = auction_data.get("paused")

                    if ended:
                        # Update DB status and fire snapshot
                        with get_db() as conn:
                            conn.execute(
                                "UPDATE auctions SET auction_status = 'completed' WHERE auction_id = ?",
                                (auction_id,)
                            )
                        handle_auction_completed(auction_id, region_id)
                        unsubscribe(auction_id)
                        return
                    elif start_item:
                        status = "paused" if paused == "paused" else "live"
                        with get_db() as conn:
                            conn.execute(
                                "UPDATE auctions SET auction_status = ? WHERE auction_id = ?",
                                (status, auction_id)
                            )
                    else:
                        # startItem gone but not ended — between vehicles or pre-live
                        with get_db() as conn:
                            conn.execute(
                                "UPDATE auctions SET auction_status = 'active' WHERE auction_id = ? AND auction_status NOT IN ('completed')",
                                (auction_id,)
                            )

        except Exception as e:
            if stop.is_set():
                return
            print(f"[listener] auction node error {auction_id}: {e} — reconnecting in 5s")
            time.sleep(5)


def _stream_results_node(region_id: str, auction_id: str, stop: threading.Event):
    """Watch /{region}/results/{auction_id} for bid updates."""
    url = f"{_RTDB}/{region_id}/results/{auction_id}.json"
    while not stop.is_set():
        token = autura_api.get_token()
        try:
            with requests.get(
                url,
                params={"auth": token},
                headers={"Accept": "text/event-stream"},
                stream=True,
                timeout=90,
            ) as resp:
                for raw in resp.iter_lines():
                    if stop.is_set():
                        return
                    if not raw:
                        continue
                    line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if not payload or payload == "null":
                        continue
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue

                    # data may be {"path": "/", "data": {itemKey: {amount, expiration, ...}}}
                    # or directly the results dict on initial "put"
                    results = data.get("data") if isinstance(data, dict) else None
                    if not isinstance(results, dict):
                        continue

                    # Results keyed by itemKey
                    for item_key, result in results.items():
                        if not isinstance(result, dict):
                            continue
                        amount = result.get("amount")
                        expiration = result.get("expiration")
                        if amount is None:
                            continue
                        with get_db() as conn:
                            conn.execute(
                                "UPDATE vehicles SET current_bid = ?, bid_expiration = ? WHERE item_key = ?",
                                (amount, expiration, item_key)
                            )
                            conn.execute(
                                "UPDATE garage SET current_bid = ? WHERE item_key = ?",
                                (amount, item_key)
                            )

        except Exception as e:
            if stop.is_set():
                return
            print(f"[listener] results node error {auction_id}: {e} — reconnecting in 5s")
            time.sleep(5)


# ── Public API ──────────────────────────────────────────────────────────────────

def subscribe(region_id: str, auction_id: str):
    """Subscribe to RTDB SSE for an auction. No-op if already subscribed."""
    with _lock:
        if auction_id in _subscriptions:
            return
        stop = threading.Event()
        t_auction = threading.Thread(
            target=_stream_auction_node,
            args=(region_id, auction_id, stop),
            daemon=True,
            name=f"rtdb-auction-{auction_id}",
        )
        t_results = threading.Thread(
            target=_stream_results_node,
            args=(region_id, auction_id, stop),
            daemon=True,
            name=f"rtdb-results-{auction_id}",
        )
        _subscriptions[auction_id] = {
            "auction": t_auction,
            "results": t_results,
            "stop": stop,
            "region_id": region_id,
        }
        t_auction.start()
        t_results.start()
        print(f"[listener] subscribed {region_id}/{auction_id}")


def unsubscribe(auction_id: str):
    """Stop SSE threads for an auction."""
    with _lock:
        sub = _subscriptions.pop(auction_id, None)
    if sub:
        sub["stop"].set()
        print(f"[listener] unsubscribed {auction_id}")


def active_auction_ids() -> set:
    """Return set of auction IDs currently subscribed."""
    with _lock:
        return set(_subscriptions.keys())


def sync_with_db():
    """
    Subscribe to all active auctions in DB, unsubscribe from completed ones.
    Safe to call repeatedly (idempotent).
    """
    rows = query(
        "SELECT auction_id, region_id FROM auctions WHERE auction_status != 'completed'"
    )
    db_active = {row["auction_id"]: row["region_id"] for row in rows}

    # Subscribe to new ones
    for auction_id, region_id in db_active.items():
        if auction_id not in active_auction_ids():
            subscribe(region_id, auction_id)

    # Unsubscribe from any that are now completed
    for auction_id in list(active_auction_ids()):
        if auction_id not in db_active:
            unsubscribe(auction_id)

    print(f"[listener] sync complete — {len(active_auction_ids())} active subscriptions")
