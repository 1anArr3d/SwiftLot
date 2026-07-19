"""
Auction update listener — mp.autura.com via Ably WebSocket.

Subscribes to public:auction:{auctionId}:updates channels.
Ably is a dumb ping bus — no bid data in the payload.

On ping:
  debounce 15s → fetch /auctions/listings/{item_key} for each vehicle
  in that auction (parallel) → update DB → push SSE snapshot.
"""
import asyncio
import threading
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from ably import AblyRealtime
from db import get_db, query

logger = logging.getLogger(__name__)

ABLY_AUTH_URL  = "https://mp.autura.com/ably-auth"
CHANNEL_PREFIX = "public:auction:"
CHANNEL_SUFFIX = ":updates"
DEBOUNCE_SECS  = 15

_event_loop: asyncio.AbstractEventLoop | None = None
_clients:       dict[str, list]   = {}   # auction_id → list[asyncio.Queue]
_subscriptions: dict[str, object] = {}   # auction_id → Ably channel
_debounce:      dict[str, float]  = {}   # auction_id → last handled monotonic time
_ably: AblyRealtime | None = None
_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=20, thread_name_prefix="detail-fetch")


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
        "ably_connected":      _ably is not None,
        "timestamp":           datetime.now(timezone.utc).isoformat(),
    }


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
    """
    Handle Ably ping for auction_id.
    Debounce → parallel detail fetches → DB update → SSE broadcast.
    """
    try:
        now = time.monotonic()
        if now - _debounce.get(auction_id, 0) < DEBOUNCE_SECS:
            return
        _debounce[auction_id] = now

        rows = query(
            "SELECT item_key FROM vehicles WHERE auction_id = %s AND item_key IS NOT NULL",
            (auction_id,),
        )
        if not rows:
            logger.debug("No vehicles in DB for auction %s — skipping detail fetch", auction_id)
            return

        item_keys = [r["item_key"] for r in rows]
        logger.info("Ping auction %s → fetching %d vehicle detail(s)", auction_id, len(item_keys))

        from autura_api import get_listing_detail
        loop = asyncio.get_event_loop()
        results = await asyncio.gather(
            *[loop.run_in_executor(_executor, get_listing_detail, ik) for ik in item_keys],
            return_exceptions=True,
        )

        updated = 0
        with get_db() as conn:
            for ik, result in zip(item_keys, results):
                if isinstance(result, Exception):
                    logger.warning("Detail fetch failed for %s: %s", ik, result)
                    continue
                conn.execute(
                    """UPDATE vehicles
                       SET current_bid    = %s,
                           bid_expiration = COALESCE(%s, bid_expiration)
                       WHERE item_key = %s""",
                    (result["current_bid"], result["bid_expiration"], ik),
                )
                updated += 1

        _broadcast(auction_id, _vehicle_snapshot(auction_id))
        logger.info("auction %s: updated %d/%d vehicle(s)", auction_id, updated, len(item_keys))
    except Exception:
        logger.exception("Error handling ping for auction %s", auction_id)


async def _subscribe_async(auction_id: str):
    global _ably
    if _ably is None:
        _ably = AblyRealtime(auth_url=ABLY_AUTH_URL)
    ch = _ably.channels.get(_channel_name(auction_id))
    await ch.subscribe(lambda msg: asyncio.ensure_future(_on_update(auction_id, msg)))
    with _lock:
        _subscriptions[auction_id] = ch
    logger.info("Subscribed to auction %s", auction_id)


def subscribe_auction(auction_id: str):
    if auction_id in _subscriptions or not _event_loop:
        return
    asyncio.run_coroutine_threadsafe(_subscribe_async(auction_id), _event_loop)


async def _unsubscribe_async(auction_id: str):
    ch = _subscriptions.pop(auction_id, None)
    if ch:
        await ch.unsubscribe()
        logger.info("Unsubscribed from auction %s", auction_id)


def unsubscribe_auction(auction_id: str):
    if _event_loop and auction_id in _subscriptions:
        asyncio.run_coroutine_threadsafe(_unsubscribe_async(auction_id), _event_loop)


def sync_with_db():
    """Subscribe to all active auctions in DB."""
    rows = query("SELECT auction_id FROM auctions WHERE auction_status IN ('PRE_BID', 'ACTIVE')")
    for row in rows:
        subscribe_auction(row["auction_id"])


def start_watchdog(interval: int = 30):
    """Periodically re-sync subscriptions with active auctions in DB."""
    def _run():
        while True:
            try:
                sync_with_db()
            except Exception:
                logger.exception("Watchdog sync_with_db failed")
            threading.Event().wait(interval)
    threading.Thread(target=_run, daemon=True, name="update-watchdog").start()


def start_periodic_scraper(interval: int = 7200):
    """Full feed rescrape every N seconds, then re-sync subscriptions."""
    def _run():
        while True:
            threading.Event().wait(interval)
            try:
                from feed_scraper import run_full_feed
                run_full_feed()
                sync_with_db()
                logger.info("Periodic scraper: full feed rescrape complete")
            except Exception:
                logger.exception("Periodic scraper failed")
    threading.Thread(target=_run, daemon=True, name="periodic-scraper").start()


def start_reconciler(interval: int = 600):
    """Fallback full rescrape for missed Ably pings."""
    def _run():
        while True:
            threading.Event().wait(interval)
            try:
                from feed_scraper import run_full_feed
                run_full_feed()
                logger.info("Reconciler: full rescrape complete")
            except Exception:
                logger.exception("Reconciler scrape failed")
    threading.Thread(target=_run, daemon=True, name="update-reconciler").start()


def start_retry_checker():
    """Placeholder — retry logic handled by reconciler."""
    pass


def add_client(auction_id: str, queue):
    _clients.setdefault(auction_id, []).append(queue)
    subscribe_auction(auction_id)


def remove_client(auction_id: str, queue):
    if auction_id in _clients:
        try:
            _clients[auction_id].remove(queue)
        except ValueError:
            pass
