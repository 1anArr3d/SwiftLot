"""
Feed scraper — mp.autura.com single-pass inventory fetch.

One call to run_full_feed() fetches all pages and upserts vehicles,
auctions, and historical_sales in one pass. Replaces auction_scraper.py
and auction_discovery.py.
"""
import json
import re
from datetime import date, datetime, timezone
from db import get_db, query
from .autura_api import get_all_feed, get_all_sellers, get_lot, get_bids


# ── Parsing helpers ───────────────────────────────────────────────────────────

def _parse_odo(val) -> int | None:
    """Autura sends "154,494 miles" or "Unknown mileage"."""
    m = re.match(r"\s*([\d,]+)", str(val or ""))
    return int(m.group(1).replace(",", "")) if m else None


def _extract_cylinders(engine_str: str | None) -> str | None:
    if engine_str and "-Cylinder" in engine_str:
        return engine_str.split("-")[0]
    return None


def _cents(obj: dict, key: str = "amountCents") -> float | None:
    c = obj.get(key)
    return c / 100 if c is not None else None


FEE_KEYS = ("platformFeeRate", "minPlatformFeeAmount", "maxPlatformFeeAmount")


def _fee_config(bidding: dict, seller_cfg: dict) -> dict:
    """Autura's lookup order for the platform fee: the lot's own config, then the seller's. None = Autura's default."""
    lot = bidding.get("platformFeeConfig") or {}
    return {k: lot.get(k) if lot.get(k) is not None else seller_cfg.get(k) for k in FEE_KEYS}


def _listing_to_vehicle_row(listing: dict, seller_cfg: dict | None = None) -> dict:
    details = listing.get("unitDetails") or {}
    bidding = listing.get("biddingInfo") or {}
    fees    = _fee_config(bidding, seller_cfg or {})
    card    = (bidding.get("paymentProcessingConfig") or {}).get("paymentProcessingFeeCardRate")
    extra   = sum((f.get("amountCents") or f.get("amount") or 0) for f in (bidding.get("customFees") or []))
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
        "min_bid":            _cents(bidding.get("minBid") or {}),
        "reserve_met":        bidding.get("isReserveMet"),
        "bidding_status":     bidding.get("biddingStatus"),
        "bidding_start":      info.get("biddingStartUtc"),
        "run_number":         listing.get("runNumber"),
        # fee inputs; the frontend works out the buyer's total from these + the live bid (Autura's PriceBreakdownModel)
        "platform_fee_rate":  fees["platformFeeRate"],
        "platform_fee_min":   fees["minPlatformFeeAmount"] / 100 if fees["minPlatformFeeAmount"] is not None else None,
        "platform_fee_max":   fees["maxPlatformFeeAmount"] / 100 if fees["maxPlatformFeeAmount"] is not None else None,
        "card_fee_rate":      card,
        "extra_fees":         extra / 100 if extra else None,
        "seller_notes":       details.get("notes"),
        "images":             json.dumps(thumb_urls),
        "images_count":       len(thumb_urls),
        "published_at":       listing.get("updatedAt"),
        "autura_odo":         _parse_odo(details.get("odometer")),
        "autura_odo_at":      date.today().isoformat(),
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

def _upsert_vehicle(conn, listing: dict, seller_cfg: dict | None = None):
    row = _listing_to_vehicle_row(listing, seller_cfg)
    if not row.get("vin"):
        return
    conn.execute(
        """
        INSERT INTO vehicles
            (vin, year, make, model, body_type, color, key_status, catalytic_converter,
             start_status, engine_type, drivetrain, fuel_type, num_cylinders,
             documentation_type, auction_id, region_id, seller_id, item_id, item_key,
             current_bid, bid_expiration, min_bid, reserve_met, bidding_status, bidding_start,
             run_number, platform_fee_rate, platform_fee_min, platform_fee_max, card_fee_rate,
             extra_fees, seller_notes, images, images_count, published_at, autura_odo, autura_odo_at)
        VALUES
            (%(vin)s, %(year)s, %(make)s, %(model)s, %(body_type)s, %(color)s,
             %(key_status)s, %(catalytic_converter)s, %(start_status)s, %(engine_type)s,
             %(drivetrain)s, %(fuel_type)s, %(num_cylinders)s, %(documentation_type)s,
             %(auction_id)s, %(region_id)s, %(seller_id)s, %(item_id)s, %(item_key)s,
             %(current_bid)s, %(bid_expiration)s, %(min_bid)s, %(reserve_met)s,
             %(bidding_status)s, %(bidding_start)s, %(run_number)s, %(platform_fee_rate)s,
             %(platform_fee_min)s, %(platform_fee_max)s, %(card_fee_rate)s, %(extra_fees)s,
             %(seller_notes)s, %(images)s, %(images_count)s, %(published_at)s,
             %(autura_odo)s, %(autura_odo_at)s)
        ON CONFLICT (vin) DO UPDATE SET
            auction_id      = EXCLUDED.auction_id,
            current_bid     = EXCLUDED.current_bid,
            bid_expiration  = EXCLUDED.bid_expiration,
            min_bid         = EXCLUDED.min_bid,
            reserve_met     = EXCLUDED.reserve_met,
            bidding_status  = EXCLUDED.bidding_status,
            bidding_start   = EXCLUDED.bidding_start,
            run_number      = EXCLUDED.run_number,
            platform_fee_rate = EXCLUDED.platform_fee_rate,
            platform_fee_min  = EXCLUDED.platform_fee_min,
            platform_fee_max  = EXCLUDED.platform_fee_max,
            card_fee_rate   = EXCLUDED.card_fee_rate,
            extra_fees      = EXCLUDED.extra_fees,
            images          = EXCLUDED.images,
            images_count    = EXCLUDED.images_count,
            published_at    = EXCLUDED.published_at,
            item_key        = EXCLUDED.item_key,
            item_id         = EXCLUDED.item_id,
            seller_id       = EXCLUDED.seller_id,
            region_id       = EXCLUDED.region_id,
            seller_notes    = EXCLUDED.seller_notes,
            -- dated the day we first saw this reading, so it slots into the odometer history
            autura_odo_at   = CASE WHEN vehicles.autura_odo IS DISTINCT FROM EXCLUDED.autura_odo
                                   THEN EXCLUDED.autura_odo_at ELSE vehicles.autura_odo_at END,
            autura_odo      = EXCLUDED.autura_odo
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
    try:
        _seller_cfgs.update({s["accountId"]: s["sellingConfig"] for s in get_all_sellers()})
    except Exception as e:  # keep the last known configs (or Autura's defaults on a cold start)
        print(f"[feed] seller fee configs unavailable: {e}")

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
                _upsert_vehicle(conn, listing, _seller_cfg(listing.get("accountId")))

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

    _handle_ended_vehicles(active_vins)

    # follow live bids on every lot now in the table (new lots in, ended lots out)
    from scrapers.autura import auction_listener as listener
    listener.sync_subscriptions()

    print(f"[feed] Done: {len(all_active)} vehicles, {len(seen_sellers)} sellers, {len(all_sold)} sold")
    return {"vehicles": len(all_active), "sellers": len(seen_sellers), "sold": len(all_sold)}


# Alias for callers that still use scrape_all()
scrape_all = run_full_feed


# ── Support functions ─────────────────────────────────────────────────────────

def _handle_ended_vehicles(active_vins: set[str]):
    """
    A vehicle whose VIN no longer appears in the active feed has either sold
    or been pulled. Fetch final sold data for its seller (the global feed's
    soldUnitListings doesn't always carry every just-ended vehicle), broadcast
    "ended" + unsubscribe its Ably channel, then drop the row — vehicles has
    no separate "completed" flag that can drift out of sync with reality.
    """
    gone = query(f"SELECT {_ENDED_COLS} FROM vehicles WHERE NOT (vin = ANY(%s))", (list(active_vins),))
    if not gone:
        return
    print(f"[feed] {len(gone)} vehicle(s) no longer in feed — recording final bids + removing")
    for row in gone:
        _record_final_bid(row)
    _remove_vehicles(gone)
    print(f"[feed] Removed {len(gone)} ended vehicle(s)")


_ENDED_COLS = "vin, auction_id, region_id, seller_id, year, make, model, color, key_status, reserve_met"


def _record_final_bid(row):
    """
    Ended lots vanish from Autura's feed and lot page, but /bids-history still answers: its top bid is the sale price.
    Only kept when the reserve was met (otherwise the lot went unsold). Replaces the old weekly per-seller sold sweep.
    """
    if not row["seller_id"] or not row["auction_id"] or row["reserve_met"] is False:
        return
    try:
        bids = get_bids(row["seller_id"], row["auction_id"]).get("bids") or []
    except Exception as e:
        print(f"[feed] bid history unavailable for {row['vin']}: {e}")
        return
    top = max(bids, key=lambda b: b.get("bidAmount") or 0, default=None)
    if not top or not top.get("bidAmount"):
        return
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO historical_sales
                (vin, year, make, model, color, key_status, region_id, auction_id, final_sale, fees_total, sold_at, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'autura_mp')
            ON CONFLICT (vin, auction_id) DO NOTHING
            """,
            (row["vin"], row["year"], row["make"], row["model"], row["color"], row["key_status"], row["region_id"],
             row["auction_id"], top["bidAmount"] / 100, (top.get("totalAmount") or 0) / 100 or None, top.get("createdAt")),
        )


def _remove_vehicles(rows):
    """Drop ended lots, tell open pages, stop following their bids."""
    from scrapers.autura import auction_listener as listener
    with get_db() as conn:
        for row in rows:
            conn.execute("DELETE FROM vehicles WHERE vin = %s", (row["vin"],))
    for row in rows:
        if row["auction_id"]:
            listener._broadcast(row["auction_id"], {"type": "ended", "auction_id": row["auction_id"]})
            listener.unsubscribe_auction(row["auction_id"])


def refresh_lot(auction_id: str):
    """
    Re-read one lot from Autura (triggered by its AUCTION_UPDATED message). Still for sale: update the row.
    Sold or pulled: record the sale and remove it now instead of at the next full scrape.
    """
    row = query(f"SELECT {_ENDED_COLS}, item_key FROM vehicles WHERE auction_id = %s", (auction_id,), one=True)
    if not row or not row["item_key"]:
        return
    lot = get_lot(row["item_key"])
    if not lot:  # Autura drops a lot's page as soon as it ends
        _record_final_bid(row)
        _remove_vehicles([row])
        print(f"[feed] {row['vin']} ended (page gone), removed")
        return
    if lot.get("status") == "PUBLISHED":
        with get_db() as conn:
            _upsert_vehicle(conn, lot, _seller_cfg(lot.get("accountId")))
        return
    with get_db() as conn:
        _insert_sold(conn, lot)  # no-op without a winning bid (unsold / pulled)
    _remove_vehicles([row])
    print(f"[feed] {row['vin']} ended ({lot.get('status')}), removed")


def refresh_live_lots() -> int:
    """Re-read only the lots in their live bidding hour: reserve status, phase and end time move fastest there."""
    live, _ = get_all_feed(auction_status="LIVE_BIDDING")
    with get_db() as conn:
        for listing in live:
            _upsert_vehicle(conn, listing, _seller_cfg(listing.get("accountId")))
    return len(live)


_seller_cfgs: dict = {}  # accountId -> sellingConfig, refreshed by each full scrape


def _seller_cfg(account_id):
    return _seller_cfgs.get(account_id)


