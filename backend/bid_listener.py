"""
Live bid listener — mp.autura.com via Ably WebSocket.

Architecture:
  - Subscribes to Ably channel per active auction:
      public:auction:{auctionId}:updates
  - Ably sends an empty "ping" (action=11) when anything changes in an auction
  - On ping: re-scrape that auction via HTTP feed, push updated listings to SSE clients
  - Token auth via https://mp.autura.com/ably-auth (unauthenticated request)

Ably App ID: OpkFyA
"""
import asyncio
import threading
import logging
from datetime import datetime, timezone

from ably import AblyRealtime
from db import get_db, query

logger = logging.getLogger(__name__)

ABLY_AUTH_URL = "https://mp.autura.com/ably-auth"
CHANNEL_PREFIX = "public:auction:"
CHANNEL_SUFFIX = ":updates"

_event_loop: asyncio.AbstractEventLoop | None = None
_clients: dict[str, list] = {}          # auction_id → list of asyncio.Queue
_subscriptions: dict[str, object] = {}  # auction_id → Ably channel
_ably: AblyRealtime | None = None
_lock = threading.Lock()


def set_event_loop(loop: asyncio.AbstractEventLoop):
    global _event_loop
    _event_loop = loop


def _broadcast(auction_id: str, event: dict):
    """Push a bid event to all SSE clients watching auction_id."""
    if not _event_loop:
        return
    queues = _clients.get(auction_id, [])
    for q in queues:
        asyncio.run_coroutine_threadsafe(q.put(event), _event_loop)


def health() -> dict:
    """Return listener health stats."""
    return {
        "subscribed_auctions": list(_subscriptions.keys()),
        "active_clients": {aid: len(qs) for aid, qs in _clients.items() if qs},
        "ably_connected": _ably is not None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _channel_name(auction_id: str) -> str:
    return f"{CHANNEL_PREFIX}{auction_id}{CHANNEL_SUFFIX}"


async def _on_update(auction_id: str, message):
    """Called by Ably on any update ping for an auction. Re-scrapes and broadcasts."""
    try:
        from auction_scraper import scrape_auction
        await asyncio.get_event_loop().run_in_executor(None, scrape_auction, auction_id)
        rows = query(
            "SELECT item_key, current_bid, bid_expiration FROM vehicles WHERE auction_id = %s",
            (auction_id,),
        )
        for r in rows:
            if r["item_key"] and r["current_bid"] is not None:
                _broadcast(auction_id, {
                    "type": "bid",
                    "item_key": r["item_key"],
                    "amount": r["current_bid"],
                    "expires": r["bid_expiration"],
                })
        logger.info("Re-scraped auction %s after Ably ping", auction_id)
    except Exception:
        logger.exception("Error re-scraping auction %s", auction_id)


async def _subscribe_async(auction_id: str):
    global _ably
    if _ably is None:
        _ably = AblyRealtime(auth_url=ABLY_AUTH_URL)

    ch = _ably.channels.get(_channel_name(auction_id))
    await ch.subscribe(lambda msg: asyncio.ensure_future(_on_update(auction_id, msg)))
    with _lock:
        _subscriptions[auction_id] = ch
    logger.info("Subscribed to Ably channel for auction %s", auction_id)


def subscribe_auction(auction_id: str):
    """Open a live bid Ably subscription for a single auction."""
    if auction_id in _subscriptions:
        return
    if _event_loop:
        asyncio.run_coroutine_threadsafe(_subscribe_async(auction_id), _event_loop)


async def _unsubscribe_async(auction_id: str):
    ch = _subscriptions.pop(auction_id, None)
    if ch:
        await ch.unsubscribe()
        logger.info("Unsubscribed from auction %s", auction_id)


def unsubscribe_auction(auction_id: str):
    """Close the Ably subscription for a single auction."""
    if _event_loop and auction_id in _subscriptions:
        asyncio.run_coroutine_threadsafe(_unsubscribe_async(auction_id), _event_loop)


def sync_with_db():
    """Subscribe to live bid streams for all active auctions in DB."""
    rows = query("SELECT auction_id FROM auctions WHERE auction_status IN ('PRE_BID', 'ACTIVE')")
    for row in rows:
        subscribe_auction(row["auction_id"])


def start_watchdog(interval: int = 30):
    """Periodically re-sync subscriptions with DB active auctions."""
    def _run():
        while True:
            try:
                sync_with_db()
            except Exception:
                logger.exception("Watchdog sync_with_db failed")
            threading.Event().wait(interval)

    t = threading.Thread(target=_run, daemon=True, name="ably-watchdog")
    t.start()


def start_retry_checker():
    """No-op — Ably SDK handles reconnection internally."""
    pass


def start_bid_reconciler(interval: int = 600):
    """
    Periodically re-scrape all active auctions as a fallback in case
    any Ably pings are missed.
    """
    def _run():
        while True:
            threading.Event().wait(interval)
            try:
                from auction_scraper import scrape_all
                scrape_all()
                logger.info("Bid reconciler: full rescrape complete")
            except Exception:
                logger.exception("Bid reconciler scrape failed")

    t = threading.Thread(target=_run, daemon=True, name="bid-reconciler")
    t.start()


def start_periodic_scraper(interval: int = 7200):
    """
    Full rescrape of all inventory every N seconds.
    Catches anything missed by the Ably listener.
    """
    def _run():
        while True:
            threading.Event().wait(interval)
            try:
                from auction_scraper import scrape_all
                scrape_all()
                sync_with_db()
                logger.info("Periodic scraper: full rescrape complete")
            except Exception:
                logger.exception("Periodic scraper failed")

    t = threading.Thread(target=_run, daemon=True, name="periodic-scraper")
    t.start()


def add_client(auction_id: str, queue):
    """Register a new SSE client for an auction."""
    _clients.setdefault(auction_id, []).append(queue)
    subscribe_auction(auction_id)


def remove_client(auction_id: str, queue):
    """Unregister an SSE client."""
    if auction_id in _clients:
        try:
            _clients[auction_id].remove(queue)
        except ValueError:
            pass
