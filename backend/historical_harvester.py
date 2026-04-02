"""
Historical sales harvester.

Three entry points:
  seed_from_json()       — one-time import of historical_sales.json
  harvest_api()          — pull all ended auctions still available via API
  harvest_auction(...)   — capture a single just-completed auction
"""
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed

import autura_api
from config import DB_PATH

_JSON_PATH = os.path.join(os.path.dirname(__file__), "historical_sales.json")


def _insert_batch(conn: sqlite3.Connection, rows: list[dict], source: str):
    """Insert a batch of sale records, skipping duplicates."""
    inserted = 0
    for row in rows:
        try:
            conn.execute(
                """INSERT OR IGNORE INTO historical_sales
                   (vin, year, make, model, color, key_status,
                    region_id, auction_id, final_sale, fees_total, sold_at, source)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    row.get("vin"),
                    row.get("year"),
                    row.get("make"),
                    row.get("model"),
                    row.get("color"),
                    row.get("key_status"),
                    row.get("region_id"),
                    row.get("auction_id"),
                    row.get("final_sale"),
                    row.get("fees_total"),
                    row.get("sold_at"),
                    source,
                ),
            )
            if conn.execute("SELECT changes()").fetchone()[0]:
                inserted += 1
        except Exception as e:
            print(f"[historical] insert error for {row.get('vin')}: {e}")
    return inserted


def seed_from_json():
    """Import historical_sales.json into the DB. Skips duplicates."""
    if not os.path.exists(_JSON_PATH):
        print("[historical] JSON file not found, skipping seed")
        return

    with open(_JSON_PATH, "r") as f:
        records = json.load(f)

    rows = []
    for r in records:
        rows.append({
            "vin":        r.get("vin"),
            "year":       r.get("year"),
            "make":       r.get("make"),
            "model":      r.get("model"),
            "color":      r.get("color"),
            "key_status": r.get("key_status"),
            "region_id":  r.get("region"),
            "auction_id": r.get("auction_id"),
            "final_sale": r.get("final_sale"),
            "fees_total": r.get("fees"),
            "sold_at":    r.get("expiration"),
        })

    with sqlite3.connect(DB_PATH) as conn:
        inserted = _insert_batch(conn, rows, source="json")
        conn.commit()

    print(f"[historical] JSON seed: {inserted} new records from {len(records)} total")


def _harvest_one(region_id: str, auction_id: str) -> list[dict]:
    """Fetch and parse sold items from a single completed auction."""
    items = autura_api.get_inventory(region_id, auction_id)
    rows = []
    for item in items:
        info = item.get("info") or {}
        result = item.get("result") or item.get("currentResult") or {}
        vin = info.get("vin")
        if not vin or not result.get("ended"):
            continue
        fees = result.get("fees") or {}
        rows.append({
            "vin":        vin,
            "year":       info.get("year"),
            "make":       info.get("make"),
            "model":      info.get("model"),
            "color":      info.get("exteriorColor"),
            "key_status": info.get("keyStatus"),
            "region_id":  region_id,
            "auction_id": auction_id,
            "final_sale": result.get("amount"),
            "fees_total": fees.get("total"),
            "sold_at":    result.get("expiration"),
        })
    return rows


def harvest_auction(region_id: str, auction_id: str):
    """
    Capture a just-completed auction directly from the vehicles table (fast path).
    Must be called before vehicles are deleted from the DB.
    Only marks harvested=1 if rows were actually inserted.
    """
    with sqlite3.connect(DB_PATH) as conn:
        vehicle_rows = conn.execute("""
            SELECT vin, year, make, model, color, key_status,
                   region_id, auction_id, current_bid, fee_price, bid_expiration
            FROM vehicles WHERE auction_id = ?
        """, (auction_id,)).fetchall()
        inserted = 0
        for r in vehicle_rows:
            conn.execute("""
                INSERT OR IGNORE INTO historical_sales
                    (vin, year, make, model, color, key_status, region_id, auction_id,
                     final_sale, fees_total, sold_at, source)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,'listener')
            """, r)
            if conn.execute("SELECT changes()").fetchone()[0]:
                inserted += 1
        if inserted > 0:
            conn.execute("UPDATE auctions SET harvested = 1 WHERE auction_id = ?", (auction_id,))
        conn.commit()
    print(f"[historical] {auction_id}: {inserted}/{len(vehicle_rows)} records captured")


def harvest_api():
    """Pull all ended auctions still available via API. Skips already-harvested ones."""
    region_ids = autura_api.get_active_region_ids()

    ended = []
    for region_id in region_ids:
        for series in autura_api.get_auction_series(region_id):
            for auction in series.get("auctions", []):
                if auction.get("ended"):
                    ended.append((region_id, auction["auctionId"]))

    if not ended:
        print("[historical] No ended auctions found")
        return

    # Skip auctions already present in historical_sales or marked harvested
    with sqlite3.connect(DB_PATH) as conn:
        harvested_ids = {
            row[0] for row in conn.execute(
                "SELECT DISTINCT auction_id FROM historical_sales WHERE source = 'api'"
            ).fetchall()
        }
        harvested_ids |= {
            row[0] for row in conn.execute(
                "SELECT auction_id FROM auctions WHERE harvested = 1"
            ).fetchall()
        }

    to_harvest = [(r, a) for r, a in ended if a not in harvested_ids]
    print(f"[historical] API harvest: {len(to_harvest)} auctions to process ({len(ended) - len(to_harvest)} already done)")

    def _process(region_id, auction_id):
        rows = _harvest_one(region_id, auction_id)
        return auction_id, rows

    all_rows = []
    harvested_auction_ids = []

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_process, r, a): (r, a) for r, a in to_harvest}
        for future in as_completed(futures):
            try:
                auction_id, rows = future.result()
                all_rows.extend(rows)
                harvested_auction_ids.append(auction_id)
            except Exception as e:
                r, a = futures[future]
                print(f"[historical] skipped {a}: {e}")

    with sqlite3.connect(DB_PATH) as conn:
        inserted = _insert_batch(conn, all_rows, source="api")
        for auction_id in harvested_auction_ids:
            conn.execute(
                "UPDATE auctions SET harvested = 1 WHERE auction_id = ?", (auction_id,)
            )
        conn.commit()

    print(f"[historical] API harvest complete: {inserted} new records from {len(harvested_auction_ids)} auctions")
