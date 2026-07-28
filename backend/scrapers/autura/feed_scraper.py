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


def _listing_to_auction_record(listing: dict) -> dict | None:
    bidding = listing.get("biddingInfo") or {}
    info    = bidding.get("auctionInfo") or {}
    auction_id = info.get("auctionId") or listing.get("accountId")
    if not auction_id:
        return None

    seller = listing.get("sellerInfo") or {}
    disc   = listing.get("sellerDisclosure") or {}

    return {
        "auction_id":     auction_id,
        "region_id":      listing.get("accountId"),
        "seller_name":    seller.get("sellerName"),
        "auction_status": bidding.get("biddingStatus") or "PRE_BID",
        "closes_at":      info.get("biddingEndUtc"),
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


def _upsert_auction(conn, record: dict):
    conn.execute(
        """
        INSERT INTO auctions
            (auction_id, region_id, seller_name, auction_status, closes_at,
             last_discovered, seller_city, seller_state, source)
        VALUES
            (%(auction_id)s, %(region_id)s, %(seller_name)s,
             %(auction_status)s, %(closes_at)s, %(last_discovered)s,
             %(seller_city)s, %(seller_state)s, %(source)s)
        ON CONFLICT (auction_id) DO UPDATE SET
            auction_status  = EXCLUDED.auction_status,
            closes_at       = EXCLUDED.closes_at,
            last_discovered = EXCLUDED.last_discovered,
            seller_name     = COALESCE(EXCLUDED.seller_name, auctions.seller_name),
            seller_city     = COALESCE(EXCLUDED.seller_city, auctions.seller_city),
            seller_state    = COALESCE(EXCLUDED.seller_state, auctions.seller_state),
            source          = COALESCE(EXCLUDED.source, auctions.source)
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
    Full single-pass feed scrape. Fetches every page once and upserts
    vehicles, auctions, and historical_sales in one DB pass.
    Also detects ended auctions and runs inspection queuing.
    """
    print("[feed] Fetching all pages...")
    active, sold = get_all_feed()
    print(f"[feed] {len(active)} active, {len(sold)} sold listings fetched")

    seen_auctions: set[str] = set()
    active_ids:    set[str] = set()

    CHUNK = 100
    for i in range(0, len(active), CHUNK):
        chunk = active[i:i + CHUNK]
        with get_db() as conn:
            for listing in chunk:
                _upsert_vehicle(conn, listing)
                record = _listing_to_auction_record(listing)
                if record:
                    aid = record["auction_id"]
                    active_ids.add(aid)
                    if aid not in seen_auctions:
                        seen_auctions.add(aid)
                        _upsert_auction(conn, record)
        print(f"[feed] {min(i + CHUNK, len(active))}/{len(active)} vehicles written")

    with get_db() as conn:
        for listing in sold:
            _insert_sold(conn, listing)
        conn.execute("""
            UPDATE auctions a
            SET vehicles_listed = (
                SELECT COUNT(*) FROM vehicles v WHERE v.auction_id = a.auction_id
            )
        """)

    _handle_ended_auctions(active_ids, sold)

    print(f"[feed] Done: {len(active)} vehicles, {len(seen_auctions)} auctions, {len(sold)} sold")
    return {"vehicles": len(active), "auctions": len(seen_auctions), "sold": len(sold)}


# Alias for callers that still use scrape_all()
scrape_all = run_full_feed


def run_sold_backfill() -> dict:
    """
    Walk every seller and collect their sold listings into historical_sales.
    Sold listings are only visible via ?seller= filter, not the global feed.
    Runs independently of the main feed scrape; safe to call weekly.
    """
    sellers = get_all_sellers()
    print(f"[sold-backfill] {len(sellers)} sellers to check")
    inserted = skipped = errors = 0

    for s in sellers:
        try:
            _, sold = get_seller_listings(s["accountId"])
            if not sold:
                continue
            with get_db() as conn:
                for listing in sold:
                    details = listing.get("unitDetails") or {}
                    bidding = listing.get("biddingInfo") or {}
                    info    = bidding.get("auctionInfo") or {}
                    winning = bidding.get("winningBid") or {}
                    vin        = details.get("vin")
                    auction_id = info.get("auctionId")
                    sale_cents = winning.get("amountCents")
                    if not vin or not auction_id or sale_cents is None:
                        skipped += 1
                        continue
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
                            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (vin, auction_id) DO NOTHING
                        """,
                        (vin, year, details.get("make"), details.get("model"),
                         details.get("color"), details.get("keys"),
                         s["accountId"], auction_id, sale_cents / 100, None,
                         listing.get("updatedAt"), "autura_mp"),
                    )
                    inserted += 1
        except Exception:
            errors += 1
            print(f"[sold-backfill] Error on seller {s['accountName']}")

    print(f"[sold-backfill] Done: {inserted} inserted, {skipped} skipped, {errors} errors")
    return {"inserted": inserted, "skipped": skipped, "errors": errors}


# ── Support functions ─────────────────────────────────────────────────────────

def _handle_ended_auctions(active_ids: set[str], sold_listings: list[dict]):
    from scrapers.autura import auction_listener as listener

    open_rows = query(
        "SELECT auction_id FROM auctions WHERE auction_status NOT IN ('completed', 'ENDED') AND source = 'autura'"
    )
    ended = [r["auction_id"] for r in open_rows if r["auction_id"] not in active_ids]
    if not ended:
        return

    ended_set = set(ended)
    relevant_sold = [
        l for l in sold_listings
        if (l.get("biddingInfo") or {}).get("auctionInfo", {}).get("auctionId") in ended_set
    ]

    with get_db() as conn:
        for listing in relevant_sold:
            _insert_sold(conn, listing)
        for auction_id in ended:
            conn.execute(
                "UPDATE auctions SET auction_status = 'completed', ended_at = NOW() WHERE auction_id = %s",
                (auction_id,),
            )

    for auction_id in ended:
        listener._broadcast(auction_id, {"type": "ended"})

    print(f"[feed] Closed {len(ended)} ended auction(s): {ended}")


