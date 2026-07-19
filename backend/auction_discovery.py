"""
Auction discovery -- mp.autura.com.

Derives auction records from the inventory feed by grouping unitListings
by biddingInfo.auctionInfo.auctionId. No separate auction API exists.

See docs/autura_mp_api.md for full structure reference.
"""
import re
import html
from datetime import datetime, timezone
from db import get_db, query
from autura_api import get_all_listings


def upsert_auction(conn, record: dict):
    """
    Upsert a single auction record derived from a unitListing's biddingInfo.
    """
    conn.execute(
        """
        INSERT INTO auctions
            (auction_id, region_id, seller_name, auction_status, closes_at, last_discovered)
        VALUES
            (%(auction_id)s, %(region_id)s, %(seller_name)s,
             %(auction_status)s, %(closes_at)s, %(last_discovered)s)
        ON CONFLICT (auction_id) DO UPDATE SET
            auction_status  = EXCLUDED.auction_status,
            closes_at       = EXCLUDED.closes_at,
            last_discovered = EXCLUDED.last_discovered,
            seller_name     = COALESCE(EXCLUDED.seller_name, auctions.seller_name)
        """,
        record,
    )


def _listing_to_auction(listing: dict) -> dict | None:
    """Extract auction record fields from a decoded unitListing."""
    bidding = listing.get("biddingInfo") or {}
    info = bidding.get("auctionInfo") or {}
    auction_id = info.get("auctionId") or listing.get("accountId")
    if not auction_id:
        return None

    seller = listing.get("sellerInfo") or {}
    status = bidding.get("biddingStatus") or "PRE_BID"

    return {
        "auction_id": auction_id,
        "region_id": listing.get("accountId"),
        "seller_name": seller.get("sellerName"),
        "auction_status": status,
        "closes_at": info.get("biddingEndUtc"),
        "last_discovered": datetime.now(timezone.utc).isoformat(),
    }


def discover_and_upsert(unit_listings: list[dict]):
    """
    Derive and upsert auction records from an already-fetched list of unitListings.
    Used by the scraper to avoid double-fetching the feed.
    """
    seen: set[str] = set()
    with get_db() as conn:
        for listing in unit_listings:
            record = _listing_to_auction(listing)
            if record and record["auction_id"] not in seen:
                seen.add(record["auction_id"])
                upsert_auction(conn, record)


def _extract_location(all_disc_html: str) -> tuple[str | None, str | None]:
    """Return (city, state) from any disclosure HTML field."""
    m = re.search(r"<strong>([^<]+\b([A-Z]{2})\s+\d{5}[^<]*)</strong>", all_disc_html)
    if m:
        state = m.group(2)
        addr = html.unescape(m.group(1).strip())
        before_state = re.sub(r",?\s*[A-Z]{2}\s+\d{5}.*", "", addr)
        parts = [p.strip() for p in before_state.split(",")]
        city = parts[-1] if parts else None
        return city, state
    plain = re.sub(r"<[^>]+>", " ", all_disc_html)
    m = re.search(r"\b([A-Z]{2})\s+\d{5}", plain)
    if m:
        return None, m.group(1)
    return None, None


def sync_seller_names():
    """
    Fetch the full seller registry from /sellers.data and update seller_name
    for any auction whose region_id matches. One HTTP request total.
    """
    from autura_api import get_all_sellers
    try:
        sellers = get_all_sellers()
    except Exception as e:
        print(f"[discovery] fetch_sellers failed: {e}")
        return

    name_map = {s["accountId"]: s["accountName"] for s in sellers}
    rows = query("SELECT auction_id, region_id FROM auctions")
    updated = 0
    with get_db() as conn:
        for row in rows:
            name = name_map.get(row["region_id"])
            if name:
                conn.execute(
                    "UPDATE auctions SET seller_name = %s WHERE auction_id = %s",
                    (name, row["auction_id"]),
                )
                updated += 1
    print(f"[discovery] sync_seller_names: updated {updated} auction(s)")


def backfill_seller_location():
    """
    For auctions missing seller_state, fetch one listing detail page per seller
    and extract location from sellerDisclosure HTML.
    """
    from autura_api import get_listing_detail

    rows = query("""
        SELECT DISTINCT ON (a.auction_id) a.auction_id, v.item_key
        FROM auctions a
        JOIN vehicles v ON v.auction_id = a.auction_id AND v.item_key IS NOT NULL
        WHERE a.seller_state IS NULL
    """)

    seen: set[str] = set()
    for row in rows:
        auction_id = row["auction_id"]
        if auction_id in seen:
            continue
        seen.add(auction_id)
        try:
            detail = get_listing_detail(row["item_key"])
            unit_listing = (
                (detail.get("pages/bidderViewUnitListing/BidderViewUnitListing") or {})
                .get("unitListing") or {}
            )
            disc = unit_listing.get("sellerDisclosure") or {}
            all_disc_html = " ".join(
                (disc.get(k) or "").replace(" ", " ")
                for k in ["sellerPolicies", "pickupInstructions", "specialAnnouncements"]
            )
            city, state = _extract_location(all_disc_html)
            if not state:
                continue
            with get_db() as conn:
                conn.execute(
                    "UPDATE auctions SET seller_city = %s, seller_state = %s WHERE auction_id = %s",
                    (city, state, auction_id),
                )
            print(f"[discovery] location {auction_id}: {city}, {state}")
        except Exception as e:
            print(f"[discovery] location failed for {auction_id}: {e}")


def run_discovery():
    """
    Pull all pages of inventory, extract unique auctions, upsert to DB.
    """
    listings = get_all_listings()
    discover_and_upsert(listings)
