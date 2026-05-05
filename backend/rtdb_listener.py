"""
RTDB SSE Listener — subscribes to Firebase RTDB at the region/auction level.

One thread per region for auction lifecycle:
  - auction thread: watches /{region}/auctions for status/ended changes

One thread per active auction for bids:
  - results thread: watches /{region}/results/{auction_id} for bid updates

Event-driven triggers (after initial dump):
  - Unknown auction_id in auction stream  → discover + scrape
  - Unknown item_key in results stream    → rescrape that auction
  - next_retry_at due in auctions table   → rescrape (checked every 5 min)
"""
import json
import threading
import time
import requests
from db import query, get_db
import autura_api
import historical_harvester as harvester

_RTDB = "https://digital-auction.firebaseio.com"

# region_id -> {"auction": Thread, "stop": Event}
_region_subscriptions: dict = {}
_region_lock = threading.Lock()

# auction_id -> {"thread": Thread, "stop": Event, "region_id": str}
_auction_result_subscriptions: dict = {}
_auction_result_lock = threading.Lock()

# Per-auction SSE client queues for zero-latency fan-out
_queues: dict = {}  # auction_id -> set of asyncio.Queue
_queues_lock = threading.Lock()
_loop = None

# Tracks which regions have finished their initial dump (safe to trigger events after)
_auctions_ready: set = set()

# Prevents concurrent scrapes of the same auction
_scraping: set = set()
_scraping_lock = threading.Lock()


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
    to garage, then remove vehicles. Called when ended signal arrives from RTDB.
    """
    print(f"[listener] {auction_id} ended — running snapshot")

    # Brief wait so the results thread can flush any in-flight final bids before we read current_bid
    time.sleep(2)
    harvester.harvest_auction(region_id, auction_id)

    unsubscribe_auction_results(auction_id)

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


# ── Event-driven scrape triggers ───────────────────────────────────────────────

def _trigger_scrape(auction_id: str, region_id: str):
    """Scrape a single auction. Caller must add auction_id to _scraping before calling."""
    import auction_scraper as scraper
    import inspection_scraper as inspection

    try:
        count = scraper.scrape_data(auction_id, region_id)
        with get_db() as conn:
            if count == 0:
                conn.execute(
                    "UPDATE auctions SET next_retry_at = NOW() + INTERVAL '15 minutes' WHERE auction_id = %s",
                    (auction_id,)
                )
                print(f"[listener] {auction_id} has 0 vehicles — retry in 15 min")
            else:
                conn.execute(
                    "UPDATE auctions SET vehicles_listed = %s, last_scraped_at = NOW(), next_retry_at = NULL WHERE auction_id = %s",
                    (count, auction_id)
                )
                if region_id and region_id.endswith('-TX'):
                    rows = query(
                        "SELECT vin FROM vehicles WHERE auction_id = %s AND last_recorded_odo IS NULL",
                        (auction_id,)
                    )
                    vins = [r["vin"] for r in rows]
                    if vins:
                        print(f"[listener] Firing TX inspection for {len(vins)} VINs in {auction_id}")
                        threading.Thread(
                            target=inspection.run_inspection_batch,
                            args=(vins,), daemon=True
                        ).start()
    except Exception as e:
        print(f"[listener] scrape error for {auction_id}: {e}")
    finally:
        with _scraping_lock:
            _scraping.discard(auction_id)


def _trigger_discover_and_scrape(region_id: str, auction_id: str):
    """Discover all auctions in a region then scrape the new one."""
    import auction_discovery as discovery

    try:
        discovery.discover_region(region_id)
        row = query("SELECT auction_id FROM auctions WHERE auction_id = %s", (auction_id,), one=True)
        if row:
            with _scraping_lock:
                if auction_id in _scraping:
                    return
                _scraping.add(auction_id)
            _trigger_scrape(auction_id, region_id)
    except Exception as e:
        print(f"[listener] discover+scrape error for {region_id}/{auction_id}: {e}")


# ── Region-level SSE stream handlers ──────────────────────────────────────────

def _process_auction_update(auction_id: str, region_id: str, auction_data: dict):
    """Process a single auction's state dict from the RTDB auction node."""
    if not isinstance(auction_data, dict):
        return
    ended = auction_data.get("ended", False)
    start_item = auction_data.get("startItem")
    paused = auction_data.get("paused")

    if ended:
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
        subscribe_auction_results(region_id, auction_id)
    else:
        with get_db() as conn:
            conn.execute(
                "UPDATE auctions SET auction_status = 'active' WHERE auction_id = %s AND auction_status NOT IN ('completed')",
                (auction_id,)
            )
        _broadcast(auction_id, {"type": "status", "auction_status": "active"})
        subscribe_auction_results(region_id, auction_id)


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
                        # Initial full dump — sync state, mark region ready
                        for auction_id, auction_data in inner.items():
                            _process_auction_update(auction_id, region_id, auction_data)
                        _auctions_ready.add(region_id)
                    elif len(parts) == 1:
                        auction_id = parts[0]
                        # After initial dump: check for brand new auctions
                        if region_id in _auctions_ready and isinstance(inner, dict):
                            row = query("SELECT auction_id FROM auctions WHERE auction_id = %s", (auction_id,), one=True)
                            if not row:
                                print(f"[listener] New auction detected: {region_id}/{auction_id}")
                                threading.Thread(
                                    target=_trigger_discover_and_scrape,
                                    args=(region_id, auction_id),
                                    daemon=True
                                ).start()
                        _process_auction_update(auction_id, region_id, inner if isinstance(inner, dict) else {})
                    elif len(parts) == 2:
                        _process_auction_update(parts[0], region_id, {parts[1]: inner})

        except Exception as e:
            if stop.is_set():
                return
            print(f"[listener] auction region error {region_id}: {e} — reconnecting in 5s")
            time.sleep(5)


def _stream_auction_results(region_id: str, auction_id: str, stop: threading.Event):
    """Watch /{region}/results/{auction_id} for bid updates on a single auction."""
    url = f"{_RTDB}/{region_id}/results/{auction_id}.json"
    while not stop.is_set():
        is_initial = True  # reset on every (re)connect so reconnect dump doesn't trigger rescrapes
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
                    updates = []  # (item_key, amount, expiration)

                    if len(parts) == 0 and isinstance(inner, dict):
                        # Initial dump: {item_key: {amount: N, ...}}
                        for item_key, result in inner.items():
                            if not isinstance(result, dict):
                                continue
                            amount = result.get("amount")
                            if amount is not None:
                                updates.append((item_key, amount, result.get("expiration")))
                    elif len(parts) == 1 and isinstance(inner, dict):
                        # Item-level update: {amount: N, ...}
                        item_key = parts[0]
                        amount = inner.get("amount")
                        if amount is not None:
                            updates.append((item_key, amount, inner.get("expiration")))
                    elif len(parts) == 2:
                        # Field-level update: amount scalar
                        item_key, field = parts[0], parts[1]
                        if field == "amount" and inner is not None:
                            updates.append((item_key, inner, None))

                    if updates:
                        print(f"[listener] {auction_id} bid update — {len(updates)} item(s): {[(k, a) for k, a, _ in updates[:5]]}")
                        with get_db() as conn:
                            for item_key, amount, expiration in updates:
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
                        for item_key, amount, expiration in updates:
                            _broadcast(auction_id, {"type": "bid", "item_key": item_key, "amount": amount, "expires": expiration})

                        # After initial dump: unknown item_key means a new vehicle was added mid-auction
                        if not is_initial:
                            for item_key, _, _ in updates:
                                if item_key:
                                    row = query("SELECT vin FROM vehicles WHERE item_key = %s", (item_key,), one=True)
                                    if not row:
                                        with _scraping_lock:
                                            if auction_id in _scraping:
                                                break
                                            _scraping.add(auction_id)
                                        print(f"[listener] Unknown item_key {item_key} in {auction_id} — triggering rescrape")
                                        threading.Thread(
                                            target=_trigger_scrape,
                                            args=(auction_id, region_id),
                                            daemon=True
                                        ).start()
                                        break

                        is_initial = False

        except Exception as e:
            if stop.is_set():
                return
            print(f"[listener] results error {auction_id}: {e} — reconnecting in 5s")
            time.sleep(5)


def subscribe_auction_results(region_id: str, auction_id: str):
    """Start a per-auction results SSE thread. No-op if already subscribed."""
    with _auction_result_lock:
        if auction_id in _auction_result_subscriptions:
            return
        stop = threading.Event()
        t = threading.Thread(
            target=_stream_auction_results,
            args=(region_id, auction_id, stop),
            daemon=True,
            name=f"rtdb-results-{auction_id}",
        )
        _auction_result_subscriptions[auction_id] = {"thread": t, "stop": stop, "region_id": region_id}
        t.start()
        print(f"[listener] subscribed results for {auction_id}")


def unsubscribe_auction_results(auction_id: str):
    """Stop the results SSE thread for a specific auction."""
    with _auction_result_lock:
        sub = _auction_result_subscriptions.pop(auction_id, None)
    if sub:
        sub["stop"].set()
        print(f"[listener] unsubscribed results for {auction_id}")


# ── Public API ─────────────────────────────────────────────────────────────────

def subscribe_region(region_id: str):
    """Subscribe to RTDB SSE auction lifecycle for a region. No-op if already subscribed."""
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
        _region_subscriptions[region_id] = {
            "auction": t_auction,
            "stop": stop,
        }
        t_auction.start()
        print(f"[listener] subscribed region {region_id}")


def unsubscribe_region(region_id: str):
    """Stop SSE threads for a region and all its auction result threads."""
    with _region_lock:
        sub = _region_subscriptions.pop(region_id, None)
    if sub:
        sub["stop"].set()
        _auctions_ready.discard(region_id)
        print(f"[listener] unsubscribed region {region_id}")
    # Stop per-auction result threads that belong to this region
    with _auction_result_lock:
        to_stop = [aid for aid, s in _auction_result_subscriptions.items() if s["region_id"] == region_id]
        for aid in to_stop:
            _auction_result_subscriptions.pop(aid)["stop"].set()
    if to_stop:
        print(f"[listener] unsubscribed results for {len(to_stop)} auctions in {region_id}")


def active_regions() -> set:
    with _region_lock:
        return set(_region_subscriptions.keys())


def sync_with_db():
    """
    Subscribe to all regions/auctions that are active; unsubscribe from any that
    are completed. Safe to call repeatedly (idempotent).
    """
    rows = query(
        "SELECT auction_id, region_id FROM auctions WHERE auction_status != 'completed'"
    )
    db_auctions = {row["auction_id"]: row["region_id"] for row in rows}
    db_regions = set(db_auctions.values())

    for region_id in db_regions:
        if region_id not in active_regions():
            subscribe_region(region_id)

    for region_id in list(active_regions()):
        if region_id not in db_regions:
            unsubscribe_region(region_id)

    for auction_id, region_id in db_auctions.items():
        subscribe_auction_results(region_id, auction_id)

    with _auction_result_lock:
        stale = [aid for aid in _auction_result_subscriptions if aid not in db_auctions]
        for aid in stale:
            _auction_result_subscriptions.pop(aid)["stop"].set()

    print(f"[listener] sync complete — {len(active_regions())} regions, {len(db_auctions)} auction result streams")


def health() -> dict:
    """Return listener health snapshot for the /health endpoint."""
    with _region_lock:
        region_subs = list(_region_subscriptions.items())
    with _auction_result_lock:
        auction_subs = list(_auction_result_subscriptions.items())
    dead_regions = [rid for rid, s in region_subs if not s["auction"].is_alive()]
    dead_auctions = [aid for aid, s in auction_subs if not s["thread"].is_alive()]
    return {
        "region_subscriptions": len(region_subs),
        "auction_result_streams": len(auction_subs),
        "dead_regions": dead_regions,
        "dead_auction_streams": dead_auctions,
        "healthy": not dead_regions and not dead_auctions,
    }


def _watchdog(interval: int = 30):
    """Restart dead SSE threads for any active region or auction subscription."""
    while True:
        time.sleep(interval)
        with _region_lock:
            region_subs = list(_region_subscriptions.items())
        for region_id, sub in region_subs:
            stop = sub["stop"]
            if stop.is_set():
                continue
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
                print(f"[watchdog] restarted auction thread for region {region_id}")

        with _auction_result_lock:
            auction_subs = list(_auction_result_subscriptions.items())
        for auction_id, sub in auction_subs:
            stop = sub["stop"]
            if stop.is_set():
                continue
            if not sub["thread"].is_alive():
                t = threading.Thread(
                    target=_stream_auction_results,
                    args=(sub["region_id"], auction_id, stop),
                    daemon=True,
                    name=f"rtdb-results-{auction_id}",
                )
                t.start()
                with _auction_result_lock:
                    if auction_id in _auction_result_subscriptions:
                        _auction_result_subscriptions[auction_id]["thread"] = t
                print(f"[watchdog] restarted results thread for {auction_id}")


def start_watchdog(interval: int = 30):
    """Start the watchdog daemon thread. Call once on app startup."""
    t = threading.Thread(target=_watchdog, args=(interval,), daemon=True, name="rtdb-watchdog")
    t.start()
    print(f"[watchdog] started — checking every {interval}s")


def _retry_checker():
    """Every 5 min, rescrape auctions whose next_retry_at has passed."""
    while True:
        time.sleep(300)
        try:
            rows = query(
                "SELECT auction_id, region_id FROM auctions WHERE next_retry_at <= NOW() AND auction_status != 'completed'"
            )
            for row in rows:
                auction_id = row["auction_id"]
                with _scraping_lock:
                    if auction_id in _scraping:
                        continue
                    _scraping.add(auction_id)
                print(f"[retry] Retrying scrape for {auction_id}")
                threading.Thread(
                    target=_trigger_scrape,
                    args=(auction_id, row["region_id"]),
                    daemon=True
                ).start()
        except Exception as e:
            print(f"[retry] Error: {e}")


def start_retry_checker():
    """Start the scrape retry checker. Call once on app startup."""
    t = threading.Thread(target=_retry_checker, daemon=True, name="scrape-retry")
    t.start()
    print("[retry] Scrape retry checker started — checking every 5 min")
