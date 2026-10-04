"""
Auction update listener — mp.autura.com via Ably WebSocket.

Subscribes to public:auction:{auctionId}:updates channels.
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
_clients:       dict[str, list]   = {}   # auction_id → list[asyncio.Queue]
_subscriptions: dict[str, object] = {}   # auction_id → Ably channel
_ably: AblyRealtime | None = None
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
        "subscribed_auctions": list(_subscriptions.keys()),
        "active_clients":      {aid: len(qs) for aid, qs in _clients.items() if qs},
        "ably_connected":      _ably is not None and str(_ably.connection.state) == "ConnectionState.CONNECTED",
        "ably_connection_state": str(_ably.connection.state) if _ably else None,
        "timestamp":           datetime.now(timezone.utc).isoformat(),
    }


def _ably_auth_headers() -> dict:
    """
    ably-auth is session-gated on Autura's side — the Ably SDK's own request to
    auth_url doesn't carry our scraping session's cookies unless forwarded
    explicitly, so without this every subscribe silently fails auth (connection
    goes to FAILED, never raises anywhere visible). Captured once per process;
    if the Autura session rotates (~monthly) while this process stays up, this
    goes stale and needs a restart — acceptable for now, not auto-refreshed.
    """
    from .autura_api import _get_session
    sess = _get_session()
    cookie_str = "; ".join(f"{k}={v}" for k, v in dict(sess.cookies).items())
    return {"Cookie": cookie_str}


def _channel_name(auction_id: str) -> str:
    return f"{CHANNEL_PREFIX}{auction_id}{CHANNEL_SUFFIX}"


def _vehicle_snapshot(auction_id: str) -> dict:
    rows = query(
        "SELECT item_key, current_bid, bid_expiration FROM vehicles WHERE auction_id = %s",
        (auction_id,),
    )
    return {
        "type":       "update",
        "auction_id": auction_id,
        "vehicles": [
            {
                "item_key":       r["item_key"],
                "current_bid":    r["current_bid"],
                "bid_expiration": r["bid_expiration"],
            }
            for r in rows
        ],
    }


async def _on_update(auction_id: str, message):
    try:
        raw = getattr(message, 'data', None)
        if not raw:
            return
        data = json.loads(raw) if isinstance(raw, str) else raw

        bid = data.get('bid', {})
        bid_cents = bid.get('bid_amount')
        bid_expiration = (bid.get('auction') or {}).get('bidding_end_at')

        if bid_cents is None:
            return

        bid_amount = bid_cents / 100  # stored as dollars to match feed_scraper convention

        with get_db() as conn:
            conn.execute(
                """UPDATE vehicles
                   SET current_bid    = %s,
                       bid_expiration = COALESCE(%s, bid_expiration)
                   WHERE auction_id = %s""",
                (bid_amount, bid_expiration, auction_id),
            )

        _broadcast(auction_id, _vehicle_snapshot(auction_id))
        logger.info("auction %s: bid → $%.2f", auction_id, bid_amount)
    except Exception:
        logger.exception("Error handling NEW_BID for auction %s", auction_id)


async def _subscribe_async(auction_id: str):
    global _ably
    if _ably is None:
        _ably = AblyRealtime(auth_url=ABLY_AUTH_URL, auth_headers=_ably_auth_headers())
    ch = _ably.channels.get(_channel_name(auction_id))
    await ch.subscribe(lambda msg: asyncio.ensure_future(_on_update(auction_id, msg)))
    with _lock:
        _subscriptions[auction_id] = ch
    logger.info("Subscribed to auction %s", auction_id)


def subscribe_auction(auction_id: str):
    if auction_id in _subscriptions or not _event_loop:
        return
    future = asyncio.run_coroutine_threadsafe(_subscribe_async(auction_id), _event_loop)
    # run_coroutine_threadsafe swallows exceptions unless the future is checked —
    # this is exactly how the ably-auth 403 (session cookies not forwarded) went
    # unnoticed: every subscribe failed silently, health() still looked "connected".
    future.add_done_callback(
        lambda f: f.exception() and logger.error("Subscribe failed for auction %s: %s", auction_id, f.exception())
    )


async def _unsubscribe_async(auction_id: str):
    ch = _subscriptions.pop(auction_id, None)
    if ch:
        await ch.unsubscribe()
        logger.info("Unsubscribed from auction %s", auction_id)


def unsubscribe_auction(auction_id: str):
    if _event_loop and auction_id in _subscriptions:
        asyncio.run_coroutine_threadsafe(_unsubscribe_async(auction_id), _event_loop)


def sync_subscriptions():
    """
    Safety-net poll — re-subscribes any auction_id that currently has a
    connected SSE client but no live Ably subscription (e.g. a subscribe
    silently failed, or the connection dropped and channels weren't
    re-attached). Scoped to actual viewers, not the whole inventory: Autura's
    Ably setup has a hard ceiling around 200 channels per connection
    (confirmed by testing — attaches start failing past ~200 with no
    reason), so subscribing to every active auction_id up front doesn't scale
    once inventory passes that size. Subscribe-on-view / unsubscribe-on-last-
    disconnect (add_client/remove_client below) keeps concurrent channel
    usage bounded by how many vehicles people are actually watching right
    now, which in practice is nowhere near the ceiling.
    """
    for auction_id, queues in list(_clients.items()):
        if queues:
            subscribe_auction(auction_id)


def start_watchdog(interval: int = 900):
    """Safety-net poll (default 15 min) for sync_subscriptions() — see its docstring."""
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
        del _clients[auction_id]
        unsubscribe_auction(auction_id)
