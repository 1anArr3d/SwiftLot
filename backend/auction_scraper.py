"""
Auction scraper — mp.autura.com.

Fetches unitListings from the HTML inventory feed and upserts vehicle
and auction records to the DB. Also triggers auction discovery.

See docs/autura_mp_api.md for full structure reference.
"""
import json
from db import get_db, query
from autura_api import get_all_feed, get_all_listings
from auction_discovery import discover_and_upsert


def _parse_odo(val) -> str | None:
    """Return None for non-numeric odometer values like 'Unknown mileage'."""
    if val is None:
        return None
    try:
        int(str(val).replace(",", "").strip())
        return str(val)
    except (ValueError, TypeError):
        return None


def _extract_cylinders(engine_str: str | None) -> str | None:
    if engine_str and "-Cylinder" in engine_str:
        return engine_str.split("-")[0]
    return None


def _listing_to_row(listing: dict) -> dict:
    """Map a decoded unitListing to the vehicles table columns."""
    details = listing.get("unitDetails") or {}
    seller = listing.get("sellerInfo") or {}
    bidding = listing.get("biddingInfo") or {}
    info = bidding.get("auctionInfo") or {}
    media = listing.get("media") or {}
    photos = media.get("allPhotos") or []

    winning = bidding.get("winningBid") or {}
    reserve = bidding.get("reservePrice") or {}
    min_bid = bidding.get("minBid") or {}

    thumb_urls = [p.get("desktopUrl") or p["thumbUrl"] for p in photos if p.get("desktopUrl") or p.get("thumbUrl")]

    year_raw = details.get("year")
    try:
        year = int(year_raw) if year_raw else None
    except (ValueError, TypeError):
        year = None

    current_bid_cents = winning.get("amountCents")
    current_bid = current_bid_cents / 100 if current_bid_cents is not None else None

    reserve_cents = reserve.get("amountCents")
    reserve_price = reserve_cents / 100 if reserve_cents is not None else None

    min_bid_cents = min_bid.get("amountCents")
    fee_price = min_bid_cents / 100 if min_bid_cents is not None else None

    return {
        "vin": details.get("vin"),
        "year": year,
        "make": details.get("make"),
        "model": details.get("model"),
        "body_type": details.get("body"),
        "color": details.get("color"),
        "key_status": details.get("keys"),
        "catalytic_converter": details.get("catalyticConverter"),
        "start_status": details.get("startStatus"),
        "engine_type": details.get("engine"),
        "drivetrain": details.get("drivetrain"),
        "fuel_type": details.get("fuelType"),
        "num_cylinders": _extract_cylinders(details.get("engine")),
        "documentation_type": details.get("documentationType"),
        "auction_id": info.get("auctionId") or listing.get("accountId"),
        "region_id": listing.get("accountId"),
        "seller_id": listing.get("accountId"),
        "item_id": details.get("unitId"),
        "item_key": details.get("unitListingId"),
        "current_bid": current_bid,
        "bid_expiration": info.get("biddingEndUtc"),
        "reserve_price": reserve_price,
        "fee_price": fee_price,
        "seller_notes": details.get("notes"),
        "images": json.dumps(thumb_urls),
        "images_count": len(thumb_urls),
        "published_at": listing.get("updatedAt"),
        "last_recorded_odo": _parse_odo(details.get("odometer")),
    }


def upsert_vehicle(conn, listing: dict):
    """
    Write a decoded unitListing to the vehicles table.
    """
    row = _listing_to_row(listing)
    if not row.get("vin"):
        return
    conn.execute(
        """
        INSERT INTO vehicles
            (vin, year, make, model, body_type, color, key_status, catalytic_converter,
             start_status, engine_type, drivetrain, fuel_type, num_cylinders,
             documentation_type, auction_id, region_id, seller_id, item_id, item_key,
             current_bid, bid_expiration, reserve_price, fee_price, seller_notes,
             images, images_count, published_at, last_recorded_odo)
        VALUES
            (%(vin)s, %(year)s, %(make)s, %(model)s, %(body_type)s, %(color)s,
             %(key_status)s, %(catalytic_converter)s, %(start_status)s, %(engine_type)s,
             %(drivetrain)s, %(fuel_type)s, %(num_cylinders)s, %(documentation_type)s,
             %(auction_id)s, %(region_id)s, %(seller_id)s, %(item_id)s, %(item_key)s,
             %(current_bid)s, %(bid_expiration)s, %(reserve_price)s, %(fee_price)s,
             %(seller_notes)s, %(images)s, %(images_count)s, %(published_at)s,
             %(last_recorded_odo)s)
        ON CONFLICT (vin) DO UPDATE SET
            auction_id      = EXCLUDED.auction_id,
            current_bid     = EXCLUDED.current_bid,
            bid_expiration  = EXCLUDED.bid_expiration,
            reserve_price   = EXCLUDED.reserve_price,
            images          = EXCLUDED.images,
            images_count    = EXCLUDED.images_count,
            published_at    = EXCLUDED.published_at,
            item_key        = EXCLUDED.item_key,
            item_id         = EXCLUDED.item_id,
            seller_id       = EXCLUDED.seller_id,
            region_id       = EXCLUDED.region_id,
            fee_price       = EXCLUDED.fee_price,
            seller_notes    = EXCLUDED.seller_notes
        """,
        row,
    )


def scrape_all():
    """
    Fetch all inventory pages, upsert vehicles + auctions, then harvest any
    auctions that have disappeared from the feed (i.e. ended).
    """
    active, sold = get_all_feed()
    discover_and_upsert(active)
    from auction_discovery import sync_seller_names
    sync_seller_names()

    with get_db() as conn:
        for listing in active:
            upsert_vehicle(conn, listing)

    active_ids = {
        (l.get("biddingInfo") or {}).get("auctionInfo", {}).get("auctionId") or l.get("accountId")
        for l in active
        if (l.get("biddingInfo") or {}).get("auctionInfo", {}).get("auctionId") or l.get("accountId")
    }
    _close_ended_auctions(active_ids, sold)

    with get_db() as conn:
        conn.execute("""
            UPDATE auctions a
            SET vehicles_listed = (
                SELECT COUNT(*) FROM vehicles v WHERE v.auction_id = a.auction_id
            )
        """)


def _close_ended_auctions(active_ids: set[str], sold_listings: list[dict]):
    """
    Any open auction no longer present in the active feed is considered ended.
    Harvest its sold vehicles into historical_sales, mark it completed, and
    notify SSE clients.
    """
    from historical_harvester import harvest_from_listings
    import bid_listener as listener

    open_rows = query(
        "SELECT auction_id FROM auctions WHERE auction_status NOT IN ('completed', 'ENDED')"
    )
    ended = [r["auction_id"] for r in open_rows if r["auction_id"] not in active_ids]
    if not ended:
        return

    ended_set = set(ended)
    relevant_sold = [
        l for l in sold_listings
        if (l.get("biddingInfo") or {}).get("auctionInfo", {}).get("auctionId") in ended_set
    ]
    harvest_from_listings(relevant_sold)

    with get_db() as conn:
        for auction_id in ended:
            conn.execute(
                "UPDATE auctions SET auction_status = 'completed', ended_at = NOW() WHERE auction_id = %s",
                (auction_id,),
            )
    for auction_id in ended:
        listener._broadcast(auction_id, {"type": "ended"})

    print(f"[scraper] Closed {len(ended)} ended auction(s): {ended}")


def scrape_auction(auction_id: str) -> int:
    """
    Re-scrape vehicles for a specific auctionId (called on Ably ping).
    Uses the ?seller= endpoint for speed — fetches only that seller's pages.
    Returns the count of active vehicles found for this auction.
    """
    from autura_api import get_seller_listings
    row = query("SELECT region_id FROM auctions WHERE auction_id = %s", (auction_id,), one=True)
    if row and row["region_id"]:
        active, _ = get_seller_listings(row["region_id"])
    else:
        active = get_all_listings()

    filtered = [
        l for l in active
        if (l.get("biddingInfo") or {}).get("auctionInfo", {}).get("auctionId") == auction_id
    ]
    with get_db() as conn:
        for listing in filtered:
            upsert_vehicle(conn, listing)
    return len(filtered)
