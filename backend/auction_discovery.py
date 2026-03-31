"""
Auction discovery — pure API, no Playwright, nationwide coverage.

Pulls active region IDs from the search service, then fetches all auction
series per region via auctions-http. No hardcoded states or region IDs.
"""
import sqlite3
from datetime import datetime, timezone

import autura_api
from config import DB_PATH


def _epoch_ms_to_iso(epoch_ms) -> str | None:
    if not epoch_ms:
        return None
    try:
        return datetime.fromtimestamp(int(epoch_ms) / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return None


def upsert_auction(conn, record: dict):
    conn.execute('''
        INSERT INTO auctions (
            auction_id, region_id, seller_name, auction_status,
            vehicles_listed, last_discovered, series_key, minimum_bid, sales_tax, ended_at, closes_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(auction_id) DO UPDATE SET
            seller_name     = excluded.seller_name,
            auction_status  = excluded.auction_status,
            last_discovered = excluded.last_discovered,
            series_key      = excluded.series_key,
            minimum_bid     = excluded.minimum_bid,
            sales_tax       = excluded.sales_tax,
            ended_at        = excluded.ended_at,
            closes_at       = excluded.closes_at
    ''', (
        record["auction_id"],
        record["region_id"],
        record["seller_name"],
        record["auction_status"],
        record.get("vehicles_listed"),
        datetime.now(timezone.utc).isoformat(),
        record.get("series_key"),
        record.get("minimum_bid"),
        record.get("sales_tax"),
        record.get("ended_at"),
        record.get("closes_at"),
    ))


def mark_completed_auctions(conn, seen_ids: set):
    """Any active auction not seen in this run gets marked completed."""
    placeholders = ','.join('?' * len(seen_ids))
    conn.execute(
        f"UPDATE auctions SET auction_status='completed' WHERE auction_id NOT IN ({placeholders})",
        list(seen_ids)
    )


def _discover_region(region_id: str) -> list[dict]:
    series_list = autura_api.get_auction_series(region_id)
    auctions = []
    for series in series_list:
        seller_name  = series.get("name") or series.get("title") or ""
        series_key   = series.get("key")
        minimum_bid  = series.get("minimumBid")
        sales_tax    = series.get("salesTax")

        for auction in series.get("auctions") or []:
            auction_id = auction.get("auctionId") or auction.get("auction_id")
            if not auction_id:
                continue
            ended = bool(auction.get("ended"))
            settings = auction.get("settings") or {}
            auction_type = settings.get("auctionType", "")
            # SEQUENCE auctions close after a live start event; LISTING auctions have an expiration
            closes_at = settings.get("startEvent") if auction_type == "SEQUENCE" else settings.get("expiration")
            auctions.append({
                "auction_id":     auction_id,
                "region_id":      region_id,
                "seller_name":    seller_name,
                "auction_status": "completed" if ended else "active",
                "series_key":     series_key,
                "minimum_bid":    float(minimum_bid) if minimum_bid is not None else None,
                "sales_tax":      float(sales_tax) if sales_tax is not None else None,
                "ended_at":       _epoch_ms_to_iso(auction.get("endedAt")),
                "closes_at":      closes_at,
            })
    return auctions


def run_discovery():
    print("[discovery] Fetching active regions...")
    region_ids = autura_api.get_active_region_ids()
    print(f"[discovery] {len(region_ids)} active regions: {region_ids}")

    all_auctions = []
    for rid in region_ids:
        try:
            auctions = _discover_region(rid)
            print(f"[discovery] [{rid}] {len(auctions)} auctions")
            all_auctions.extend(auctions)
        except Exception as e:
            print(f"[discovery] [{rid}] Error: {e}")

    active = [a for a in all_auctions if a["auction_status"] != "completed"]
    print(f"[discovery] {len(all_auctions)} total, {len(active)} active")

    seen_ids = {a["auction_id"] for a in active}
    with sqlite3.connect(DB_PATH) as conn:
        # Only store active auctions — no point keeping completed ones
        for a in active:
            upsert_auction(conn, a)
        conn.commit()
        if seen_ids:
            mark_completed_auctions(conn, seen_ids)
        conn.commit()

    print(f"[discovery] Saved {len(all_auctions)} auctions. Done.")
