"""
Feed scraper — mp.autura.com single-pass inventory fetch.

One call to run_full_feed() fetches all pages and upserts vehicles,
auctions, and historical_sales in one pass. Replaces auction_scraper.py
and auction_discovery.py.
"""
import json
from datetime import datetime, timezone
from db import get_db, query
from .autura_api import get_all_feed, get_all_sellers, get_seller_listings


# ── Parsing helpers ───────────────────────────────────────────────────────────

def _parse_odo(val) -> str | None:
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


def _cents(obj: dict, key: str = "amountCents") -> float | None:
    c = obj.get(key)
    return c / 100 if c is not None else None


def _listing_to_vehicle_row(listing: dict) -> dict:
    details = listing.get("unitDetails") or {}
    bidding = listing.get("biddingInfo") or {}
    info    = bidding.get("auctionInfo") or {}
    media   = listing.get("media") or {}
    photos  = media.get("allPhotos") or []

    thumb_urls = [
        p.get("desktopUrl") or p["thumbUrl"]
        for p in photos
        if p.get("desktopUrl") or p.get("thumbUrl")
    ]

    year_raw = details.get("year")
    try:
        year = int(year_raw) if year_raw else None
    except (ValueError, TypeError):
        year = None

    return {
        "vin":                details.get("vin"),
        "year":               year,
        "make":               details.get("make"),
        "model":              details.get("model"),
        "body_type":          details.get("body"),
        "color":              details.get("color"),
        "key_status":         details.get("keys"),
        "catalytic_converter":details.get("catalyticConverter"),
        "start_status":       details.get("startStatus"),
        "engine_type":        details.get("engine"),
        "drivetrain":         details.get("drivetrain"),
        "fuel_type":          details.get("fuelType"),
        "num_cylinders":      _extract_cylinders(details.get("engine")),
        "documentation_type": details.get("documentationType"),
        "auction_id":         info.get("auctionId") or listing.get("accountId"),
        "region_id":          listing.get("accountId"),
        "seller_id":          listing.get("accountId"),
        "item_id":            details.get("unitId"),
        "item_key":           details.get("unitListingId"),
        "current_bid":        _cents(bidding.get("winningBid") or {}),
        "bid_expiration":     info.get("biddingEndUtc"),
        "reserve_price":      _cents(bidding.get("reservePrice") or {}),
        "fee_price":          _cents(bidding.get("minBid") or {}),
        "seller_notes":       details.get("notes"),
        "images":             json.dumps(thumb_urls),
        "images_count":       len(thumb_urls),
        "published_at":       listing.get("updatedAt"),
        "last_recorded_odo":  _parse_odo(details.get("odometer")),
    }


def _listing_to_seller_record(listing: dict) -> dict | None:
    region_id = listing.get("accountId")
    if not region_id:
        return None

    seller = listing.get("sellerInfo") or {}
    disc   = listing.get("sellerDisclosure") or {}

    return {
        "region_id":      region_id,
        "seller_name":    seller.get("sellerName"),
        "last_discovered":datetime.now(timezone.utc).isoformat(),
        "seller_city":    seller.get("city") or disc.get("city"),
        "seller_state":   seller.get("state") or disc.get("state"),
        "source":         "autura",
    }


# ── DB writes ─────────────────────────────────────────────────────────────────

def _upsert_vehicle(conn, listing: dict):
    row = _listing_to_vehicle_row(listing)
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


def _upsert_seller(conn, record: dict):
    conn.execute(
        """
        INSERT INTO sellers
            (region_id, seller_name, last_discovered, seller_city, seller_state, source)
        VALUES
            (%(region_id)s, %(seller_name)s, %(last_discovered)s,
             %(seller_city)s, %(seller_state)s, %(source)s)
        ON CONFLICT (region_id) DO UPDATE SET
            last_discovered = EXCLUDED.last_discovered,
            seller_name     = COALESCE(EXCLUDED.seller_name, sellers.seller_name),
            seller_city     = COALESCE(EXCLUDED.seller_city, sellers.seller_city),
            seller_state    = COALESCE(EXCLUDED.seller_state, sellers.seller_state),
            source          = COALESCE(EXCLUDED.source, sellers.source)
        """,
        record,
    )


def _insert_sold(conn, listing: dict):
    details = listing.get("unitDetails") or {}
    bidding = listing.get("biddingInfo") or {}
    info    = bidding.get("auctionInfo") or {}
    winning = bidding.get("winningBid") or {}

    vin        = details.get("vin")
    auction_id = info.get("auctionId")
    sale_cents = winning.get("amountCents")
    if not vin or not auction_id or sale_cents is None:
        return

    year_raw = details.get("year")
    try:
        year = int(year_raw) if year_raw else None
    except (ValueError, TypeError):
        year = None

    conn.execute(
        """
        INSERT INTO historical_sales
            (vin, year, make, model, color, key_status,
             region_id, auction_id, final_sale, fees_total, sold_at, source)
        VALUES
            (%(vin)s, %(year)s, %(make)s, %(model)s, %(color)s, %(key_status)s,
             %(region_id)s, %(auction_id)s, %(final_sale)s, %(fees_total)s,
             %(sold_at)s, %(source)s)
        ON CONFLICT (vin, auction_id) DO NOTHING
        """,
        {
            "vin":        vin,
            "year":       year,
            "make":       details.get("make"),
            "model":      details.get("model"),
            "color":      details.get("color"),
            "key_status": details.get("keys"),
            "region_id":  listing.get("accountId"),
            "auction_id": auction_id,
            "final_sale": sale_cents / 100,
            "fees_total": None,
            "sold_at":    listing.get("updatedAt"),
            "source":     "autura_mp",
        },
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def run_full_feed() -> dict:
    """
    Full single-pass feed scrape. Fetches listings for every seller and upserts
    vehicles, sellers, and historical_sales in one DB pass.
    Also detects ended vehicles (sold or pulled) and runs inspection queuing.

    Autura's auction_id is per-vehicle, not per-seller (each lot gets its own
    id and closing time, staggered ~15s apart in a run). The VIN is the only
    stable identity across scrapes, so ended-vehicle detection diffs on VIN,
    not auction_id.
    """
    all_active, all_sold = get_all_feed()

    seen_sellers: set[str] = set()
    active_vins:  set[str] = set()

    print(f"[feed] {len(all_active)} active, {len(all_sold)} sold listings fetched")
    CHUNK = 100
    for i in range(0, len(all_active), CHUNK):
        chunk = all_active[i:i + CHUNK]
        with get_db() as conn:
            for listing in chunk:
                vin = (listing.get("unitDetails") or {}).get("vin")
                if vin:
                    active_vins.add(vin)
                _upsert_vehicle(conn, listing)

                record = _listing_to_seller_record(listing)
                if record:
                    rid = record["region_id"]
                    if rid not in seen_sellers:
                        seen_sellers.add(rid)
                        _upsert_seller(conn, record)
        print(f"[feed] {min(i + CHUNK, len(all_active))}/{len(all_active)} vehicles written")

    with get_db() as conn:
        for listing in all_sold:
            _insert_sold(conn, listing)

    # Ably subscriptions are lazy (subscribe-on-view, see auction_listener.py)
    # and don't need reconciling against the full active set here — Autura's
    # Ably setup caps out around 200 channels per connection, so proactively
    # subscribing to the whole inventory doesn't scale.
    _handle_ended_vehicles(active_vins)

    print(f"[feed] Done: {len(all_active)} vehicles, {len(seen_sellers)} sellers, {len(all_sold)} sold")
    return {"vehicles": len(all_active), "sellers": len(seen_sellers), "sold": len(all_sold)}


# Alias for callers that still use scrape_all()
scrape_all = run_full_feed


def _harvest_sold_for_sellers(seller_ids: list[str]) -> dict:
    """
    Fetch + insert sold listings for the given sellers via get_seller_listings()
    (sold listings are only visible via ?seller= filter, not the global feed).
    Shared by the immediate per-ended-seller harvest in _handle_ended_vehicles()
    and the periodic full-sweep run_sold_backfill() — same job, same code path,
    just different scope and trigger.

    Deliberately sequential, not parallelized: a burst of concurrent fresh
    connections to Neon's serverless Postgres gets dropped/rejected (confirmed
    by testing — "server closed the connection unexpectedly" under ~6 concurrent
    getconn() calls). Slow is fine here; this only walks more than a couple
    sellers on the rare full backlog sweep, not on the normal per-cycle path.
    """
    inserted = errors = 0
    for seller_id in seller_ids:
        try:
            _, sold = get_seller_listings(seller_id)
            with get_db() as conn:
                for listing in sold:
                    _insert_sold(conn, listing)
                    inserted += 1
        except Exception as e:
            errors += 1
            print(f"[sold-harvest] Fetch failed for seller {seller_id}: {e}")
    return {"inserted": inserted, "errors": errors}


def run_sold_backfill() -> dict:
    """
    Walk every seller and collect their sold listings into historical_sales.
    Runs independently of the main feed scrape, in its own thread; safe to
    call periodically as a catch-all for anything the immediate per-ended-seller
    harvest missed.
    """
    sellers = get_all_sellers()
    print(f"[sold-backfill] {len(sellers)} sellers to check")
    result = _harvest_sold_for_sellers([s["accountId"] for s in sellers])
    print(f"[sold-backfill] Done: {result['inserted']} inserted, {result['errors']} seller error(s)")
    return result


# ── Support functions ─────────────────────────────────────────────────────────

def _handle_ended_vehicles(active_vins: set[str]):
    """
    A vehicle whose VIN no longer appears in the active feed has either sold
    or been pulled. Fetch final sold data for its seller (the global feed's
    soldUnitListings doesn't always carry every just-ended vehicle), broadcast
    "ended" + unsubscribe its Ably channel, then drop the row — vehicles has
    no separate "completed" flag that can drift out of sync with reality.
    """
    from scrapers.autura import auction_listener as listener

    gone = query(
        "SELECT vin, auction_id, region_id FROM vehicles WHERE NOT (vin = ANY(%s))",
        (list(active_vins),),
    )
    if not gone:
        return

    print(f"[feed] {len(gone)} vehicle(s) no longer in feed — harvesting + removing")

    seller_ids = list({r["region_id"] for r in gone if r["region_id"]})
    if seller_ids:
        result = _harvest_sold_for_sellers(seller_ids)
        print(f"[feed] Sold harvest: {result['inserted']} listing(s) for {len(seller_ids)} affected seller(s)")

    with get_db() as conn:
        for row in gone:
            conn.execute("DELETE FROM vehicles WHERE vin = %s", (row["vin"],))

    for row in gone:
        if row["auction_id"]:
            listener._broadcast(row["auction_id"], {"type": "ended"})
            listener.unsubscribe_auction(row["auction_id"])

    print(f"[feed] Removed {len(gone)} ended vehicle(s)")


