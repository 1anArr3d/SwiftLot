"""
RTDB SSE Listener — subscribes to Firebase RTDB at the region/auction level.

One thread per region for auction lifecycle:
  - auction thread: watches /{region}/auctions for status/ended changes

Two threads per active auction for bids:
  - results thread: watches /{region}/results/{auction_id} — timed/pre-auction bids
  - items thread:   watches /{region}/items/{auction_id}   — live auctioneer bids

Both bid streams update the DB and broadcast to SSE clients. The items stream
skips its initial dump (results stream already provides current state) and only
processes incremental currentResult/amount updates from the live auctioneer phase.

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

# auction_id -> {"thread": Thread, "stop": Event, "region_id": str}
_auction_items_subscriptions: dict = {}
_auction_items_lock = threading.Lock()

# Per-auction SSE client queues for zero-latency fan-out
_queues: dict = {}  # auction_id -> set of asyncio.Queue
_queues_lock = threading.Lock()
_loop = None
_pending_broadcasts: list = []  # [(auction_id, event)] buffered until event loop is ready
_pending_broadcasts_lock = threading.Lock()

# Tracks which regions have finished their initial dump (safe to trigger events after)
_auctions_ready: set = set()
_auctions_ready_lock = threading.Lock()

# Prevents concurrent scrapes of the same auction
_scraping: set = set()
_scraping_lock = threading.Lock()

# (auction_id, item_key) pairs that have already triggered a rescrape; pruned on auction completion
_rescrape_attempted: set = set()


def set_event_loop(loop):
    global _loop
    _loop = loop
    with _pending_broadcasts_lock:
        pending = list(_pending_broadcasts)
        _pending_broadcasts.clear()
    for auction_id, event in pending:
        with _queues_lock:
            queues = set(_queues.get(auction_id, set()))
        for q in queues:
            _loop.call_soon_threadsafe(q.put_nowait, event)


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
        with _pending_broadcasts_lock:
            _pending_broadcasts.append((auction_id, event))
        return
    with _queues_lock:
        queues = set(_queues.get(auction_id, set()))
    for q in queues:
        _loop.call_soon_threadsafe(q.put_nowait, event)


def _iter_sse(resp):
    """Yield (event_type, payload) pairs from a Firebase REST SSE response.

    Tracks event: lines so callers can detect auth_revoked and cancel.
    Defaults to "put" when no event: line precedes a data: line.
    """
    current_event = "put"
    for raw in resp.iter_lines():
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if line.startswith("event:"):
            current_event = line[6:].strip()
        elif line.startswith("data:"):
            payload = line[5:].strip()
            yield current_event, payload
            current_event = "put"


# ── Snapshot + cleanup ─────────────────────────────────────────────────────────

def handle_auction_completed(auction_id: str, region_id: str):
    """
    Run the end-of-auction snapshot: harvest from vehicles table, sync final bids
    to garage, then remove vehicles. Called when ended signal arrives from RTDB.
    """
    vehicle_count = query(
        "SELECT COUNT(*) AS cnt FROM vehicles WHERE auction_id = %s", (auction_id,), one=True
    )
    if not vehicle_count or vehicle_count["cnt"] == 0:
        print(f"[listener] {auction_id} ended signal ignored — no vehicles scraped, likely premature")
        return

    print(f"[listener] {auction_id} ended — running snapshot")

    unsubscribe_auction_results(auction_id)
    unsubscribe_auction_items(auction_id)
    _rescrape_attempted.difference_update({k for k in _rescrape_attempted if k[0] == auction_id})
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


# ── Event-driven scrape triggers ───────────────────────────────────────────────

def _trigger_scrape(auction_id: str, region_id: str):
    """Scrape a single auction. Caller must add auction_id to _scraping before calling."""
    import auction_scraper as scraper
    import inspection_scraper as inspection

    try:
        count = scraper.scrape_data(auction_id, region_id)
        with get_db() as conn:
            if count == 0:
                # Exponential backoff: 15m, 30m, 1h, 2h, 4h, then stop after 4h interval
                row = query(
                    "SELECT next_retry_at, last_scraped_at FROM auctions WHERE auction_id = %s",
                    (auction_id,), one=True
                )
                # Estimate attempt count from how long we've been retrying (rough but no counter column needed)
                import math
                prev_interval_minutes = 15
                if row and row["last_scraped_at"] and row["next_retry_at"]:
                    delta = (row["next_retry_at"] - row["last_scraped_at"]).total_seconds() / 60
                    prev_interval_minutes = max(15, min(int(delta), 240))
                next_interval_minutes = min(prev_interval_minutes * 2, 240)
                if prev_interval_minutes >= 240:
                    conn.execute(
                        "UPDATE auctions SET next_retry_at = NULL, last_scraped_at = NOW() WHERE auction_id = %s",
                        (auction_id,)
                    )
                    print(f"[listener] {auction_id} has 0 vehicles — giving up after max retries")
                else:
                    conn.execute(
                        "UPDATE auctions SET next_retry_at = NOW() + (%s * INTERVAL '1 minute'), last_scraped_at = NOW() WHERE auction_id = %s",
                        (next_interval_minutes, auction_id)
                    )
                    print(f"[listener] {auction_id} has 0 vehicles — retry in {next_interval_minutes} min")
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


def _discover_and_scrape_unknown(region_id: str, auction_ids: list):
    """Discover a region then scrape any auctions that were missing from our DB."""
    import auction_discovery as discovery

    try:
        discovery.discover_region(region_id)
        for auction_id in auction_ids:
            row = query("SELECT auction_id FROM auctions WHERE auction_id = %s", (auction_id,), one=True)
            if not row:
                continue
            with _scraping_lock:
                if auction_id in _scraping:
                    continue
                _scraping.add(auction_id)
            _trigger_scrape(auction_id, region_id)
    except Exception as e:
        print(f"[listener] discover unknown error {region_id}: {e}")


# ── Region-level SSE stream handlers ──────────────────────────────────────────

def _process_auction_update(auction_id: str, region_id: str, auction_data: dict):
    """Process a single auction's state dict from the RTDB auction node."""
    if not isinstance(auction_data, dict):
        return
    ended = auction_data.get("ended", False)

    if ended:
        row = query("SELECT auction_status FROM auctions WHERE auction_id = %s", (auction_id,), one=True)
        if row and row["auction_status"] != "completed":
            _broadcast(auction_id, {"type": "ended"})
            handle_auction_completed(auction_id, region_id)
    else:
        with get_db() as conn:
            conn.execute(
                "UPDATE auctions SET auction_status = 'active' WHERE auction_id = %s AND auction_status NOT IN ('completed')",
                (auction_id,)
            )
        _broadcast(auction_id, {"type": "status", "auction_status": "active"})
        subscribe_auction_results(region_id, auction_id)
        subscribe_auction_items(region_id, auction_id)


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
                for event_type, payload in _iter_sse(resp):
                    if stop.is_set():
                        return
                    if event_type in ("auth_revoked", "cancel"):
                        print(f"[listener] auctions {region_id}: {event_type} — reconnecting")
                        break
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
                        with _auctions_ready_lock:
                            _auctions_ready.add(region_id)
                        # Discover auctions present in RTDB but missing from our DB
                        unknown = [
                            aid for aid, adata in inner.items()
                            if isinstance(adata, dict) and not adata.get("ended", False)
                            and not query("SELECT 1 FROM auctions WHERE auction_id = %s", (aid,), one=True)
                        ]
                        if unknown:
                            print(f"[listener] {len(unknown)} unknown auction(s) in {region_id} at initial dump — triggering discovery")
                            threading.Thread(
                                target=_discover_and_scrape_unknown,
                                args=(region_id, unknown),
                                daemon=True
                            ).start()
                    elif len(parts) == 1:
                        auction_id = parts[0]
                        # After initial dump: check for brand new auctions
                        with _auctions_ready_lock:
                            ready = region_id in _auctions_ready
                        if ready and isinstance(inner, dict):
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
                for event_type, payload in _iter_sse(resp):
                    if stop.is_set():
                        return
                    if event_type in ("auth_revoked", "cancel"):
                        print(f"[listener] results {auction_id}: {event_type} — reconnecting")
                        break
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
                        if inner.get("ended") and not is_initial:
                            _broadcast(auction_id, {"type": "sold", "item_key": item_key})
                    elif len(parts) == 2:
                        item_key, field = parts[0], parts[1]
                        if field == "amount" and inner is not None:
                            updates.append((item_key, inner, None))
                        elif field == "expiration" and inner is not None:
                            updates.append((item_key, None, inner))

                    if updates:
                        print(f"[listener] {auction_id} bid update — {len(updates)} item(s): {[(k, a) for k, a, _ in updates if a is not None][:5]}")
                        for item_key, amount, expiration in updates:
                            if amount is not None:
                                _broadcast(auction_id, {"type": "bid", "item_key": item_key, "amount": amount, "expires": expiration})
                        with get_db() as conn:
                            for item_key, amount, expiration in updates:
                                if amount is not None and expiration is not None:
                                    conn.execute(
                                        "UPDATE vehicles SET current_bid = %s, bid_expiration = %s WHERE item_key = %s",
                                        (amount, expiration, item_key)
                                    )
                                elif amount is not None:
                                    conn.execute(
                                        "UPDATE vehicles SET current_bid = %s WHERE item_key = %s",
                                        (amount, item_key)
                                    )
                                elif expiration is not None:
                                    conn.execute(
                                        "UPDATE vehicles SET bid_expiration = %s WHERE item_key = %s",
                                        (expiration, item_key)
                                    )

                        # After initial dump: unknown item_key means a new vehicle was added mid-auction
                        if not is_initial:
                            for item_key, _, _ in updates:
                                if item_key and (auction_id, item_key) not in _rescrape_attempted:
                                    row = query("SELECT vin FROM vehicles WHERE item_key = %s", (item_key,), one=True)
                                    if not row:
                                        # Mark before _scraping check so skipped items aren't retried next round
                                        _rescrape_attempted.add((auction_id, item_key))
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


def _stream_auction_items(region_id: str, auction_id: str, stop: threading.Event):
    """Watch /{region}/items/{auction_id} for live auctioneer bid updates.

    The items path carries currentResult/amount updates during the live auctioneer
    phase. The initial dump is skipped (results stream provides current state);
    only incremental updates are processed.
    """
    url = f"{_RTDB}/{region_id}/items/{auction_id}.json"
    while not stop.is_set():
        is_initial = True
        token = autura_api.get_token()
        try:
            with requests.get(
                url,
                params={"auth": token},
                headers={"Accept": "text/event-stream"},
                stream=True,
                timeout=300,
            ) as resp:
                for event_type, payload in _iter_sse(resp):
                    if stop.is_set():
                        return
                    if event_type in ("auth_revoked", "cancel"):
                        print(f"[listener] items {auction_id}: {event_type} — reconnecting")
                        break
                    if not payload or payload == "null":
                        continue
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(data, dict):
                        continue

                    if is_initial:
                        is_initial = False
                        continue  # skip large initial dump; results stream has current state

                    path = data.get("path", "/")
                    inner = data.get("data")
                    parts = [p for p in path.split("/") if p]
                    updates = []  # (item_key, amount, expiration)

                    if len(parts) == 1 and isinstance(inner, dict):
                        # item-level update: {currentResult: {amount: N, ...}, info: {...}, ...}
                        item_key = parts[0]
                        result = inner.get("currentResult")
                        if isinstance(result, dict):
                            amount = result.get("amount")
                            if amount is not None:
                                updates.append((item_key, amount, result.get("expiration")))
                    elif len(parts) == 2 and parts[1] == "currentResult" and isinstance(inner, dict):
                        # currentResult-level update: {amount: N, expiration: ..., ...}
                        item_key = parts[0]
                        amount = inner.get("amount")
                        if amount is not None:
                            updates.append((item_key, amount, inner.get("expiration")))
                    elif len(parts) >= 3 and parts[1] == "currentResult" and parts[2] == "amount":
                        # amount field update: N
                        item_key = parts[0]
                        if inner is not None:
                            updates.append((item_key, inner, None))

                    if updates:
                        print(f"[listener] {auction_id} live bid — {len(updates)} item(s): {[(k, a) for k, a, _ in updates[:5]]}")
                        for item_key, amount, expiration in updates:
                            _broadcast(auction_id, {"type": "bid", "item_key": item_key, "amount": amount, "expires": expiration})
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

        except Exception as e:
            if stop.is_set():
                return
            print(f"[listener] items error {auction_id}: {e} — reconnecting in 5s")
            time.sleep(5)


def subscribe_auction_items(region_id: str, auction_id: str):
    """Start per-auction items SSE thread for live auctioneer bids. No-op if already subscribed."""
    with _auction_items_lock:
        if auction_id in _auction_items_subscriptions:
            return
        stop = threading.Event()
        t = threading.Thread(
            target=_stream_auction_items,
            args=(region_id, auction_id, stop),
            daemon=True,
            name=f"rtdb-items-{auction_id}",
        )
        _auction_items_subscriptions[auction_id] = {"thread": t, "stop": stop, "region_id": region_id}
        t.start()
        print(f"[listener] subscribed items for {auction_id}")


def unsubscribe_auction_items(auction_id: str):
    """Stop the items SSE thread for a specific auction."""
    with _auction_items_lock:
        sub = _auction_items_subscriptions.pop(auction_id, None)
    if sub:
        sub["stop"].set()
        print(f"[listener] unsubscribed items for {auction_id}")


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
        with _auctions_ready_lock:
            _auctions_ready.discard(region_id)
        print(f"[listener] unsubscribed region {region_id}")
    # Stop per-auction result and items threads that belong to this region
    with _auction_result_lock:
        to_stop = [aid for aid, s in _auction_result_subscriptions.items() if s["region_id"] == region_id]
        for aid in to_stop:
            _auction_result_subscriptions.pop(aid)["stop"].set()
    if to_stop:
        print(f"[listener] unsubscribed results for {len(to_stop)} auctions in {region_id}")
    with _auction_items_lock:
        to_stop_items = [aid for aid, s in _auction_items_subscriptions.items() if s["region_id"] == region_id]
        for aid in to_stop_items:
            _auction_items_subscriptions.pop(aid)["stop"].set()
    if to_stop_items:
        print(f"[listener] unsubscribed items for {len(to_stop_items)} auctions in {region_id}")


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
        subscribe_auction_items(region_id, auction_id)

    with _auction_result_lock:
        stale = [aid for aid in _auction_result_subscriptions if aid not in db_auctions]
        for aid in stale:
            _auction_result_subscriptions.pop(aid)["stop"].set()
    with _auction_items_lock:
        stale_items = [aid for aid in _auction_items_subscriptions if aid not in db_auctions]
        for aid in stale_items:
            _auction_items_subscriptions.pop(aid)["stop"].set()

    print(f"[listener] sync complete — {len(active_regions())} regions, {len(db_auctions)} result+items streams")


def health() -> dict:
    """Return listener health snapshot for the /health endpoint."""
    with _region_lock:
        region_subs = list(_region_subscriptions.items())
    with _auction_result_lock:
        result_subs = list(_auction_result_subscriptions.items())
    with _auction_items_lock:
        items_subs = list(_auction_items_subscriptions.items())
    dead_regions = [rid for rid, s in region_subs if not s["auction"].is_alive()]
    dead_results = [aid for aid, s in result_subs if not s["thread"].is_alive()]
    dead_items = [aid for aid, s in items_subs if not s["thread"].is_alive()]
    return {
        "region_subscriptions": len(region_subs),
        "auction_result_streams": len(result_subs),
        "auction_items_streams": len(items_subs),
        "dead_regions": dead_regions,
        "dead_result_streams": dead_results,
        "dead_items_streams": dead_items,
        "healthy": not dead_regions and not dead_results and not dead_items,
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

        with _auction_items_lock:
            items_subs = list(_auction_items_subscriptions.items())
        for auction_id, sub in items_subs:
            stop = sub["stop"]
            if stop.is_set():
                continue
            if not sub["thread"].is_alive():
                t = threading.Thread(
                    target=_stream_auction_items,
                    args=(sub["region_id"], auction_id, stop),
                    daemon=True,
                    name=f"rtdb-items-{auction_id}",
                )
                t.start()
                with _auction_items_lock:
                    if auction_id in _auction_items_subscriptions:
                        _auction_items_subscriptions[auction_id]["thread"] = t
                print(f"[watchdog] restarted items thread for {auction_id}")


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
