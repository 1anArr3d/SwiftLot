"""
Historical sales harvester — mp.autura.com.

Sold vehicles appear in soldUnitListings on the inventory feed pages.
Final sale price is in biddingInfo.winningBid.amountCents (divide by 100).

See docs/autura_mp_api.md for full structure reference.
"""
from db import get_db


def harvest_listing(listing: dict):
    """
    Insert a single sold unitListing into historical_sales.
    Expects a fully decoded unitListing dict with biddingInfo.winningBid present.
    Skips if VIN+auction_id already recorded (unique constraint).
    """
    details = listing.get("unitDetails") or {}
    bidding = listing.get("biddingInfo") or {}
    info = bidding.get("auctionInfo") or {}
    winning = bidding.get("winningBid") or {}

    vin = details.get("vin")
    auction_id = info.get("auctionId")
    sale_cents = winning.get("amountCents")

    if not vin or not auction_id or sale_cents is None:
        return

    year_raw = details.get("year")
    try:
        year = int(year_raw) if year_raw else None
    except (ValueError, TypeError):
        year = None

    with get_db() as conn:
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
                "vin": vin,
                "year": year,
                "make": details.get("make"),
                "model": details.get("model"),
                "color": details.get("color"),
                "key_status": details.get("keys"),
                "region_id": listing.get("accountId"),
                "auction_id": auction_id,
                "final_sale": sale_cents / 100,
                "fees_total": None,
                "sold_at": listing.get("updatedAt"),
                "source": "autura_mp",
            },
        )


def harvest_from_listings(sold_listings: list[dict]):
    """
    Harvest an already-fetched list of soldUnitListings into historical_sales.
    Used by scrape_all() to avoid re-fetching the feed.
    """
    for listing in sold_listings:
        harvest_listing(listing)


def harvest_sold():
    """
    Fetch all inventory pages, extract soldUnitListings, and insert new records
    into historical_sales. Uses ON CONFLICT DO NOTHING to avoid duplicates.
    """
    from autura_api import get_all_feed
    _, sold = get_all_feed()
    harvest_from_listings(sold)
