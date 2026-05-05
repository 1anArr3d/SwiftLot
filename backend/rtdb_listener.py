"""
RTDB SSE Listener — subscribes to Firebase RTDB at the region level.

Two threads per region (instead of two per auction):
  - auction thread: watches /{region}/auctions for all status/ended changes
  - results thread: watches /{region}/results for all bid updates
"""
import json
import threading
import time
import requests
from db import query, get_db
import autura_api
import historical_harvester as harvester

_RTDB = "https://digital-auction.firebaseio.com"

# region_id -> {"auction": Thread, "results": Thread, "stop": Event}
_region_subscriptions: dict = {}
_region_lock = threading.Lock()

# Per-auction SSE client queues for zero-latency fan-out
_queues: dict = {}  # auction_id -> set of asyncio.Queue
_queues_lock = threading.Lock()
_loop = None  # set once on startup via set_event_loop()


def set_event_loop(loop):
    global _loop
    _loop = loop


def subscribe_queue(auction_id: str, queue):
    with _queues_lock:
        if auction_id not in _queues:
            _queues[auction_id] = set()
        _queues[auction_id].add(queue)


def unsubscribe_queue(auction_id: str, queue):
    with _queues_lock:
        if auction_id in _queues:
            _queues[auction_id].discard(queue)


def _broadcast(auction_id: str, event: dict):
    if _loop is None:
        return
    with _queues_lock:
        queues = set(_queues.get(auction_id, set()))
    for q in queues:
        _loop.call_soon_threadsafe(q.put_nowait, event)


# ── Snapshot + cleanup ─────────────────────────────────────────────────────────

def handle_auction_completed(auction_id: str, region_id: str):
    """
    Run the end-of-auction snapshot: harvest from vehicles table, sync final bids
    to garage, then remove vehicles. Called by both listener and scheduler.
    """
    print(f"[listener] {auction_id} ended — running snapshot")

    harvester.harvest_auction(region_id, auction_id)

    with get_db() as conn:
        conn.execute("""
            UPDATE garage
            SET current_bid = (
                SELECT v.current_bid FROM vehicles v WHERE v.vin = garage.vin
            )
            WHERE vin IN (
                SELECT v.vin FROM vehicles v WHERE v.auction_id = %s
            )
        """, (auction_id,))
        conn.execute("DELETE FROM saved_auctions WHERE auction_id = %s", (auction_id,))
        conn.execute(
            "UPDATE auctions SET auction_status = 'completed' WHERE auction_id = %s",
            (auction_id,)
        )
        conn.execute("DELETE FROM vehicles WHERE auction_id = %s", (auction_id,))


# ── Region-level SSE stream handlers ──────────────────────────────────────────

def _process_auction_update(auction_id: str, region_id: str, auction_data: dict):
    """Process a single auction's state dict from the RTDB auction node."""
    if not isinstance(auction_data, dict):
        return
    ended = auction_data.get("ended", False)
    start_item = auction_data.get("startItem")
    paused = auction_data.get("paused")

    if ended:
        # Guard against reprocessing already-completed auctions (e.g. initial dump)
        row = query("SELECT auction_status FROM auctions WHERE auction_id = %s", (auction_id,), one=True)
        if row and row["auction_status"] != "completed":
            _broadcast(auction_id, {"type": "ended"})
            handle_auction_completed(auction_id, region_id)
    elif start_item:
        status = "paused" if paused == "paused" else "live"
        with get_db() as conn:
            conn.execute(
                "UPDATE auctions SET auction_status = %s WHERE auction_id = %s",
                (status, auction_id)
            )
        _broadcast(auction_id, {"type": "status", "auction_status": status})
    else:
        with get_db() as conn:
            conn.execute(
                "UPDATE auctions SET auction_status = 'active' WHERE auction_id = %s AND auction_status NOT IN ('completed')",
                (auction_id,)
            )
        _broadcast(auction_id, {"type": "status", "auction_status": "active"})


def _stream_region_auctions(region_id: str, stop: threading.Event):
    """Watch /{region}/auctions for all auction status changes in this region."""
    url = f"{_RTDB}/{region_id}/auctions.json"
    while not stop.is_set():
        token = autura_api.get_token()
        try:
            with requests.get(
                url,
                params={"auth": token},
                headers={"Accept": "text/event-stream"},
                stream=True,
                timeout=300,
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

                    path = data.get("path", "/")
                    inner = data.get("data")
                    parts = [p for p in path.split("/") if p]

                    if len(parts) == 0 and isinstance(inner, dict):
                        # Initial full dump: {auction_id: {ended, startItem, ...}}
                        for auction_id, auction_data in inner.items():
                            _process_auction_update(auction_id, region_id, auction_data)
                    elif len(parts) == 1:
                        # Single auction replaced entirely
                        _process_auction_update(parts[0], region_id, inner if isinstance(inner, dict) else {})
                    elif len(parts) == 2:
                        # Single field update: /auction_id/field = value
                        _process_auction_update(parts[0], region_id, {parts[1]: inner})

        except Exception as e:
            if stop.is_set():
                return
            print(f"[listener] auction region error {region_id}: {e} — reconnecting in 5s")
            time.sleep(5)


def _stream_region_results(region_id: str, stop: threading.Event):
    """Watch /{region}/results for all bid updates in this region."""
    url = f"{_RTDB}/{region_id}/results.json"
    while not stop.is_set():
        token = autura_api.get_token()
        try:
            with requests.get(
                url,
                params={"auth": token},
                headers={"Accept": "text/event-stream"},
                stream=True,
                timeout=300,
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

                    path = data.get("path", "/")
                    inner = data.get("data")
                    parts = [p for p in path.split("/") if p]
                    updates = []  # (auction_id, item_key, amount, expiration)

                    if len(parts) == 0 and isinstance(inner, dict):
                        # Initial full dump: {auction_id: {item_key: {amount, expiration}}}
                        for auction_id, items in inner.items():
                            if not isinstance(items, dict):
                                continue
                            for item_key, result in items.items():
                                if not isinstance(result, dict):
                                    continue
                                amount = result.get("amount")
                                if amount is not None:
                                    updates.append((auction_id, item_key, amount, result.get("expiration")))
                    elif len(parts) == 1 and isinstance(inner, dict):
                        # All items for one auction: {item_key: {amount, expiration}}
                        auction_id = parts[0]
                        for item_key, result in inner.items():
                            if not isinstance(result, dict):
                                continue
                            amount = result.get("amount")
                            if amount is not None:
                                updates.append((auction_id, item_key, amount, result.get("expiration")))
                    elif len(parts) == 2 and isinstance(inner, dict):
                        # Single item update: /auction_id/item_key = {amount, expiration}
                        auction_id, item_key = parts[0], parts[1]
                        amount = inner.get("amount")
                        if amount is not None:
                            updates.append((auction_id, item_key, amount, inner.get("expiration")))
                    elif len(parts) == 3:
                        # Field-level patch: /auction_id/item_key/field = value
                        auction_id, item_key, field = parts[0], parts[1], parts[2]
                        if field == "amount" and inner is not None:
                            updates.append((auction_id, item_key, inner, None))

                    if updates:
                        print(f"[listener] {region_id} bid update — {len(updates)} item(s): {[(k, a) for _, k, a, _ in updates[:5]]}")
                        with get_db() as conn:
                            for auction_id, item_key, amount, expiration in updates:
                                if expiration is not None:
                                    conn.execute(
                                        "UPDATE vehicles SET current_bid = %s, bid_expiration = %s WHERE item_key = %s",
                                        (amount, expiration, item_key)
                                    )
                                else:
                                    conn.execute(
                                        "UPDATE vehicles SET current_bid = %s WHERE item_key = %s",
                                        (amount, item_key)
                                    )
                        for auction_id, item_key, amount, expiration in updates:
                            _broadcast(auction_id, {"type": "bid", "item_key": item_key, "amount": amount, "expires": expiration})

        except Exception as e:
            if stop.is_set():
                return
            print(f"[listener] results region error {region_id}: {e} — reconnecting in 5s")
            time.sleep(5)


# ── Public API ─────────────────────────────────────────────────────────────────

def subscribe_region(region_id: str):
    """Subscribe to RTDB SSE for an entire region. No-op if already subscribed."""
    with _region_lock:
        if region_id in _region_subscriptions:
            return
        stop = threading.Event()
        t_auction = threading.Thread(
            target=_stream_region_auctions,
            args=(region_id, stop),
            daemon=True,
            name=f"rtdb-auction-{region_id}",
        )
        t_results = threading.Thread(
            target=_stream_region_results,
            args=(region_id, stop),
            daemon=True,
            name=f"rtdb-results-{region_id}",
        )
        _region_subscriptions[region_id] = {
            "auction": t_auction,
            "results": t_results,
            "stop": stop,
        }
        t_auction.start()
        t_results.start()
        print(f"[listener] subscribed region {region_id}")


def unsubscribe_region(region_id: str):
    """Stop SSE threads for a region."""
    with _region_lock:
        sub = _region_subscriptions.pop(region_id, None)
    if sub:
        sub["stop"].set()
        print(f"[listener] unsubscribed region {region_id}")


def active_regions() -> set:
    with _region_lock:
        return set(_region_subscriptions.keys())


def sync_with_db():
    """
    Subscribe to all regions that have active auctions; unsubscribe from any
    that no longer have active auctions. Safe to call repeatedly (idempotent).
    """
    rows = query(
        "SELECT DISTINCT region_id FROM auctions WHERE auction_status != 'completed'"
    )
    db_regions = {row["region_id"] for row in rows}

    for region_id in db_regions:
        if region_id not in active_regions():
            subscribe_region(region_id)

    for region_id in list(active_regions()):
        if region_id not in db_regions:
            unsubscribe_region(region_id)

    print(f"[listener] sync complete — {len(active_regions())} region subscriptions")


def health() -> dict:
    """Return listener health snapshot for the /health endpoint."""
    with _region_lock:
        subs = list(_region_subscriptions.items())
    dead = []
    for region_id, sub in subs:
        if not sub["auction"].is_alive() or not sub["results"].is_alive():
            dead.append(region_id)
    return {
        "subscriptions": len(subs),
        "dead_threads": dead,
        "healthy": len(dead) == 0,
    }


def _watchdog(interval: int = 30):
    """Restart dead SSE threads for any active region subscription."""
    while True:
        time.sleep(interval)
        with _region_lock:
            subs = list(_region_subscriptions.items())
        for region_id, sub in subs:
            stop = sub["stop"]
            if stop.is_set():
                continue
            restarted = []
            if not sub["auction"].is_alive():
                t = threading.Thread(
                    target=_stream_region_auctions,
                    args=(region_id, stop),
                    daemon=True,
                    name=f"rtdb-auction-{region_id}",
                )
                t.start()
                with _region_lock:
                    if region_id in _region_subscriptions:
                        _region_subscriptions[region_id]["auction"] = t
                restarted.append("auction")
            if not sub["results"].is_alive():
                t = threading.Thread(
                    target=_stream_region_results,
                    args=(region_id, stop),
                    daemon=True,
                    name=f"rtdb-results-{region_id}",
                )
                t.start()
                with _region_lock:
                    if region_id in _region_subscriptions:
                        _region_subscriptions[region_id]["results"] = t
                restarted.append("results")
            if restarted:
                print(f"[watchdog] restarted {restarted} thread(s) for region {region_id}")


def start_watchdog(interval: int = 30):
    """Start the watchdog daemon thread. Call once on app startup."""
    t = threading.Thread(target=_watchdog, args=(interval,), daemon=True, name="rtdb-watchdog")
    t.start()
    print(f"[watchdog] started — checking every {interval}s")
