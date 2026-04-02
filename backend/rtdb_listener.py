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
    Run the end-of-auction snapshot: harvest from vehicles table, sync final bids
    to garage, then remove vehicles. Called by both listener and scheduler.
    """
    print(f"[listener] {auction_id} ended — running snapshot")

    # Harvest first — reads from vehicles table before they are deleted
    harvester.harvest_auction(region_id, auction_id)

    with get_db() as conn:
        # Sync final bid into garage snapshots before vehicles are deleted
        conn.execute("""
            UPDATE garage
            SET current_bid = (
                SELECT v.current_bid FROM vehicles v WHERE v.vin = garage.vin
            )
            WHERE vin IN (
                SELECT v.vin FROM vehicles v WHERE v.auction_id = ?
            )
        """, (auction_id,))

        # Clean up saved auctions watchlist — auction is over
        conn.execute("DELETE FROM saved_auctions WHERE auction_id = ?", (auction_id,))

        # Mark completed and delete vehicles
        conn.execute(
            "UPDATE auctions SET auction_status = 'completed' WHERE auction_id = ?",
            (auction_id,)
        )
        conn.execute("DELETE FROM vehicles WHERE auction_id = ?", (auction_id,))


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

                    auction_data = data.get("data") or data
                    if not isinstance(auction_data, dict):
                        continue

                    ended = auction_data.get("ended", False)
                    start_item = auction_data.get("startItem")
                    paused = auction_data.get("paused")

                    if ended:
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
                    updates = []  # list of (item_key, amount, expiration)

                    if path == "/" and isinstance(inner, dict):
                        # put/patch at root: {itemKey: {amount, expiration, ...}}
                        for item_key, result in inner.items():
                            if not isinstance(result, dict):
                                continue
                            amount = result.get("amount")
                            if amount is not None:
                                updates.append((item_key, amount, result.get("expiration")))
                    elif path.count("/") == 1 and isinstance(inner, dict):
                        # patch at item level: path="/itemKey", data={amount, expiration, ...}
                        item_key = path.lstrip("/")
                        amount = inner.get("amount")
                        if item_key and amount is not None:
                            updates.append((item_key, amount, inner.get("expiration")))

                    if updates:
                        print(f"[listener] {auction_id} bid update — {len(updates)} item(s): {[(k, a) for k, a, _ in updates]}")
                        with get_db() as conn:
                            for item_key, amount, expiration in updates:
                                conn.execute(
                                    "UPDATE vehicles SET current_bid = ?, bid_expiration = ? WHERE item_key = ?",
                                    (amount, expiration, item_key)
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


def health() -> dict:
    """Return listener health snapshot for the /health endpoint."""
    with _lock:
        subs = list(_subscriptions.items())
    dead = []
    for auction_id, sub in subs:
        if not sub["auction"].is_alive() or not sub["results"].is_alive():
            dead.append(auction_id)
    return {
        "subscriptions": len(subs),
        "dead_threads": dead,
        "healthy": len(dead) == 0,
    }


def _watchdog(interval: int = 30):
    """Restart dead SSE threads for any active subscription."""
    while True:
        time.sleep(interval)
        with _lock:
            subs = list(_subscriptions.items())
        for auction_id, sub in subs:
            stop = sub["stop"]
            if stop.is_set():
                continue
            region_id = sub["region_id"]
            restarted = []
            if not sub["auction"].is_alive():
                t = threading.Thread(
                    target=_stream_auction_node,
                    args=(region_id, auction_id, stop),
                    daemon=True,
                    name=f"rtdb-auction-{auction_id}",
                )
                t.start()
                with _lock:
                    if auction_id in _subscriptions:
                        _subscriptions[auction_id]["auction"] = t
                restarted.append("auction")
            if not sub["results"].is_alive():
                t = threading.Thread(
                    target=_stream_results_node,
                    args=(region_id, auction_id, stop),
                    daemon=True,
                    name=f"rtdb-results-{auction_id}",
                )
                t.start()
                with _lock:
                    if auction_id in _subscriptions:
                        _subscriptions[auction_id]["results"] = t
                restarted.append("results")
            if restarted:
                print(f"[watchdog] restarted {restarted} thread(s) for {auction_id}")


def start_watchdog(interval: int = 30):
    """Start the watchdog daemon thread. Call once on app startup."""
    t = threading.Thread(target=_watchdog, args=(interval,), daemon=True, name="rtdb-watchdog")
    t.start()
    print(f"[watchdog] started — checking every {interval}s")
