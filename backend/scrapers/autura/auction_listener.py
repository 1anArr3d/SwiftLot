"""
Auction update listener — mp.autura.com via Ably WebSocket.

Subscribes to public:auction:{auctionId}:updates for EVERY live lot, so current_bid stays live
on every page (Home, Search, Garage), not only while someone has the auction open.
Autura's Ably setup fails attaches past ~200 channels per connection, so channels are spread
over a pool of connections, CHANNELS_PER_CONNECTION each.
NEW_BID messages carry the full bid payload — parse directly, no API call needed.
"""
import asyncio
import json
import threading
import logging
from datetime import datetime, timezone

from ably import AblyRealtime
from db import get_db, query

logger = logging.getLogger(__name__)

ABLY_AUTH_URL  = "https://mp.autura.com/ably-auth"
CHANNEL_PREFIX = "public:auction:"
CHANNEL_SUFFIX = ":updates"

_event_loop: asyncio.AbstractEventLoop | None = None
CHANNELS_PER_CONNECTION = 150  # headroom under the ~200 per-connection ceiling

_clients:       dict[str, list]  = {}   # auction_id → list[asyncio.Queue]
_subscriptions: dict[str, tuple] = {}   # auction_id → (Ably channel, its pool entry)
_pending:       set[str]         = set()
_pool:          list[dict]       = []   # [{"rt": AblyRealtime, "n": channels on it}]
_lock = threading.Lock()


def set_event_loop(loop: asyncio.AbstractEventLoop):
    global _event_loop
    _event_loop = loop


def _broadcast(auction_id: str, event: dict):
    if not _event_loop:
        return
    for q in _clients.get(auction_id, []):
        asyncio.run_coroutine_threadsafe(q.put(event), _event_loop)


def health() -> dict:
    return {
        "subscribed_count":    len(_subscriptions),
        "active_clients":      {aid: len(qs) for aid, qs in _clients.items() if qs},
        "connections":         [{"channels": c["n"], "state": str(c["rt"].connection.state)} for c in _pool],
        "ably_connected":      bool(_pool) and all(str(c["rt"].connection.state) == "ConnectionState.CONNECTED" for c in _pool),
        "timestamp":           datetime.now(timezone.utc).isoformat(),
    }


async def _ably_auth_callback(token_params):
    """
    ably-auth is session-gated on Autura's side — the Ably SDK's own request to
    auth_url doesn't carry our scraping session's cookies unless forwarded
    explicitly, so without this every subscribe silently fails auth (connection
    goes to FAILED, never raises anywhere visible).

    Using auth_callback instead of a static auth_url + auth_headers: Ably calls
    this fresh every time it needs a token (initial connect + each periodic
    renewal before the previous token's TTL expires), so it always goes through
    _authed_get() — which already re-authenticates on session expiry — instead
    of a cookie string captured once at process start. A static auth_headers
    dict would go stale whenever Autura's session rotates (~monthly) without
    ever raising anywhere, the same invisible-failure shape as the original bug.
    """
    import json
    from .autura_api import _authed_get
    resp = await asyncio.to_thread(_authed_get, ABLY_AUTH_URL, timeout=20)
    resp.raise_for_status()
    return json.loads(resp.text)


def _channel_name(auction_id: str) -> str:
    return f"{CHANNEL_PREFIX}{auction_id}{CHANNEL_SUFFIX}"


def _vehicle_snapshot(auction_id: str) -> dict:
    rows = query(
        "SELECT item_key, current_bid, buyer_total, bid_expiration FROM vehicles WHERE auction_id = %s",
        (auction_id,),
    )
    return {
        "type":       "update",
        "auction_id": auction_id,
        "vehicles": [
            {
                "item_key":       r["item_key"],
                "current_bid":    r["current_bid"],
                "buyer_total":    r["buyer_total"],
                "bid_expiration": r["bid_expiration"],
            }
            for r in rows
        ],
    }


def parse_bid(data: dict):
    """NEW_BID payload -> (current bid $, buyer total $ or None, bidding_end_at or None), or None.
    `bid` is the bid just placed, which a proxy (max) bid may beat in the same instant; the two
    NEW_BIDs can then land in either order, so the standing bid comes from inventory.winningBid.
    Amounts are cents (verified 2026-11-18 against live bids: 40000 = $400, platform_fee 5000 = $50)."""
    bid = data.get('bid') or {}
    winning = (data.get('inventory') or {}).get('winningBid') or bid
    cents, total = winning.get('bid_amount'), winning.get('total_amount')
    if cents is None:
        return None
    return cents / 100, (total / 100 if total is not None else None), (bid.get('auction') or {}).get('bidding_end_at')


async def _on_update(auction_id: str, message):
    try:
        raw = getattr(message, 'data', None)
        if not raw:
            return
        data = json.loads(raw) if isinstance(raw, str) else raw

        parsed = parse_bid(data)
        if not parsed:
            return
        bid_amount, buyer_total, bid_expiration = parsed

        with get_db() as conn:
            conn.execute(
                """UPDATE vehicles
                   SET current_bid    = %s,
                       buyer_total    = %s,
                       bid_expiration = COALESCE(%s, bid_expiration)
                   WHERE auction_id = %s""",
                (bid_amount, buyer_total, bid_expiration, auction_id),
            )

        _broadcast(auction_id, _vehicle_snapshot(auction_id))
        logger.info("auction %s: bid → $%.2f (buyer pays $%s)", auction_id, bid_amount, buyer_total)
    except Exception:
        logger.exception("Error handling NEW_BID for auction %s", auction_id)


async def _subscribe_async(auction_id: str):
    with _lock:
        if auction_id in _subscriptions or auction_id in _pending:
            return
        _pending.add(auction_id)
        conn = next((c for c in _pool if c["n"] < CHANNELS_PER_CONNECTION), None)
        if conn is None:
            conn = {"rt": AblyRealtime(auth_callback=_ably_auth_callback), "n": 0}
            _pool.append(conn)
            logger.info("Opened Ably connection #%d", len(_pool))
        conn["n"] += 1
    try:
        ch = conn["rt"].channels.get(_channel_name(auction_id))
        await ch.subscribe(lambda msg: asyncio.ensure_future(_on_update(auction_id, msg)))
        with _lock:
            _subscriptions[auction_id] = (ch, conn)
    except BaseException:
        with _lock:
            conn["n"] -= 1
        raise
    finally:
        with _lock:
            _pending.discard(auction_id)


def subscribe_auction(auction_id: str):
    if auction_id in _subscriptions or auction_id in _pending or not _event_loop:
        return
    future = asyncio.run_coroutine_threadsafe(_subscribe_async(auction_id), _event_loop)
    # run_coroutine_threadsafe swallows exceptions unless the future is checked —
    # this is exactly how the ably-auth 403 (session cookies not forwarded) went
    # unnoticed: every subscribe failed silently, health() still looked "connected".
    future.add_done_callback(
        lambda f: f.exception() and logger.error("Subscribe failed for auction %s: %s", auction_id, f.exception())
    )


async def _unsubscribe_async(auction_id: str):
    with _lock:
        entry = _subscriptions.pop(auction_id, None)
    if entry:
        ch, conn = entry
        # unsubscribe() only drops listeners (and is sync in ably 2.x); without detach+release
        # the channel stays attached and counts against the per-connection ceiling.
        ch.unsubscribe()
        await ch.detach()
        conn["rt"].channels.release(ch.name)
        with _lock:
            conn["n"] -= 1
        logger.info("Unsubscribed from auction %s", auction_id)


def unsubscribe_auction(auction_id: str):
    if _event_loop and auction_id in _subscriptions:
        future = asyncio.run_coroutine_threadsafe(_unsubscribe_async(auction_id), _event_loop)
        future.add_done_callback(
            lambda f: f.exception() and logger.error("Unsubscribe failed for auction %s: %s", auction_id, f.exception())
        )


def sync_subscriptions():
    """
    Subscribe every live lot (every auction_id still in vehicles) and drop lots that have ended.
    Runs after each full feed scrape and on the watchdog, which also re-attaches anything whose
    subscribe failed or whose connection dropped.
    """
    live = {r["auction_id"] for r in query("SELECT DISTINCT auction_id FROM vehicles WHERE auction_id IS NOT NULL")}
    live |= {aid for aid, qs in _clients.items() if qs}
    for auction_id in live - set(_subscriptions):
        subscribe_auction(auction_id)
    for auction_id in set(_subscriptions) - live:
        unsubscribe_auction(auction_id)


def start_watchdog(interval: int = 300):
    """Runs sync_subscriptions() every `interval` seconds (default 5 min) — see its docstring."""
    def _run():
        while True:
            try:
                sync_subscriptions()
            except Exception:
                logger.exception("Watchdog sync_subscriptions failed")
            threading.Event().wait(interval)
    threading.Thread(target=_run, daemon=True, name="update-watchdog").start()


def start_periodic_scraper(interval: int = 7200):
    """Full feed rescrape every N seconds."""
    def _run():
        while True:
            threading.Event().wait(interval)
            try:
                from .feed_scraper import run_full_feed
                run_full_feed()
                logger.info("Periodic scraper: full feed rescrape complete")
            except Exception:
                logger.exception("Periodic scraper failed")

            try:
                from .inspection_scraper import run_inspection_batch
                rows = query(
                    "SELECT v.vin FROM vehicles v "
                    "JOIN sellers s ON s.region_id = v.region_id "
                    "WHERE (v.last_recorded_odo IS NULL OR v.last_recorded_odo = 'N/A') AND s.seller_state = 'TX'"
                )
                vins = [r["vin"] for r in rows]
                if vins:
                    logger.info("Inspection batch: %d unchecked TX vehicles", len(vins))
                    run_inspection_batch(vins)
                    logger.info("Inspection batch complete")
            except Exception:
                logger.exception("Inspection batch failed")

    threading.Thread(target=_run, daemon=True, name="periodic-scraper").start()



def add_client(auction_id: str, queue):
    _clients.setdefault(auction_id, []).append(queue)
    subscribe_auction(auction_id)


def remove_client(auction_id: str, queue):
    if auction_id not in _clients:
        return
    try:
        _clients[auction_id].remove(queue)
    except ValueError:
        pass
    if not _clients[auction_id]:
        # stay subscribed: every live lot is followed whether or not anyone is watching
        del _clients[auction_id]
