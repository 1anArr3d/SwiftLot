"""
API-based auction scraper — replaces Playwright scraping entirely.
Fetches vehicle inventory from the Autura items-http microservice.
"""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import autura_api
from config import DB_PATH


def _format_odo(raw_odo):
    if not raw_odo:
        return None
    numeric = ''.join(c for c in str(raw_odo).split('(')[0] if c.isdigit() or c == ',').replace(',', '').strip()
    if not numeric:
        return None
    return f"{date.today().strftime('%m/%d/%Y')}: {int(numeric):,}"


def _parse_images(image_dict: dict) -> tuple[str, int]:
    """
    Extract full_4x3 URLs from the nested image structure.
    Structure: image["full_4x3"] = {"0": {"url": ...}, "1": {"url": ...}, ...}
    """
    if not image_dict:
        return None, 0
    size = image_dict.get("full_4x3") or image_dict.get("thumbnail_4x3") or {}
    urls = []
    for idx in sorted(size.keys(), key=lambda x: int(x) if x.isdigit() else 0):
        entry = size[idx]
        if isinstance(entry, dict) and entry.get("url"):
            urls.append(entry["url"])
    return (json.dumps(urls) if urls else None), len(urls)


def _extract_fee(fees) -> float | None:
    """Extract buyer fee from the fees dict/value in currentResult."""
    if fees is None:
        return None
    if isinstance(fees, (int, float)):
        return float(fees)
    if isinstance(fees, dict):
        # feePrice shape: {"amount": N, ...}
        # fees shape from currentResult: {"buyerFee": N, "total": N, ...}
        for key in ("amount", "buyerFee", "buyer_fee", "fee", "total"):
            if key in fees and isinstance(fees[key], (int, float)):
                return float(fees[key])
        total = sum(v for v in fees.values() if isinstance(v, (int, float)))
        return float(total) if total else None
    return None


def _str_val(v) -> str | None:
    """Extract a string from a plain string or a {code, name} dict."""
    if v is None:
        return None
    if isinstance(v, str):
        return v or None
    if isinstance(v, dict):
        return v.get("name") or v.get("code") or None
    return str(v)


def _firestore_ts_to_iso(ts) -> str | None:
    """Convert Firestore {_seconds, _nanoseconds} dict or plain ISO string to ISO string."""
    if ts is None:
        return None
    if isinstance(ts, str):
        return ts
    if isinstance(ts, dict) and "_seconds" in ts:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(ts["_seconds"], tz=timezone.utc).isoformat()
    return None


def save_vehicle(conn, item: dict, auction_id: str, region_id: str):
    info = item.get("info") or {}
    result = item.get("currentResult") or {}

    override = item.get("_images_override")
    if override:
        images_json = json.dumps(override)
        images_count = len(override)
    else:
        images_json, images_count = _parse_images(item.get("image"))
        if item.get("imagesCount") is not None:
            images_count = int(item["imagesCount"])

    raw_odo = info.get("odometer") or info.get("mileage")
    listing_odo = _format_odo(raw_odo)

    try:
        year = int(info.get("year")) if info.get("year") else None
    except (ValueError, TypeError):
        year = None

    conn.execute('''
        INSERT INTO vehicles (
            vin, year, make, model, body_type, color, key_status,
            catalytic_converter, start_status, engine_type, drivetrain,
            fuel_type, num_cylinders, documentation_type,
            auction_id, region_id, seller_id, item_id, item_key,
            current_bid, bid_expiration, reserve_price, fee_price,
            seller_notes, images, images_count, published_at, last_recorded_odo
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?, ?
        )
        ON CONFLICT(vin) DO UPDATE SET
            year               = excluded.year,
            make               = excluded.make,
            model              = excluded.model,
            body_type          = excluded.body_type,
            color              = excluded.color,
            key_status         = excluded.key_status,
            catalytic_converter = excluded.catalytic_converter,
            start_status       = excluded.start_status,
            engine_type        = excluded.engine_type,
            drivetrain         = excluded.drivetrain,
            fuel_type          = excluded.fuel_type,
            num_cylinders      = excluded.num_cylinders,
            documentation_type = excluded.documentation_type,
            auction_id         = excluded.auction_id,
            region_id          = excluded.region_id,
            seller_id          = excluded.seller_id,
            item_id            = excluded.item_id,
            item_key           = excluded.item_key,
            current_bid        = excluded.current_bid,
            bid_expiration     = excluded.bid_expiration,
            reserve_price      = excluded.reserve_price,
            fee_price          = excluded.fee_price,
            seller_notes       = excluded.seller_notes,
            images             = excluded.images,
            images_count       = excluded.images_count,
            published_at       = excluded.published_at
    ''', (
        info.get("vin"),
        year,
        _str_val(info.get("make")),
        _str_val(info.get("model")),
        _str_val(info.get("body") or info.get("bodyType")),
        _str_val(info.get("exteriorColor") or info.get("color")),
        _str_val(info.get("keyStatus")),
        _str_val(info.get("catalyticConverter")),
        _str_val(info.get("startCode") or info.get("startStatus")),
        _str_val(info.get("engineType")),
        _str_val(info.get("drivetrain")),
        _str_val(info.get("fuelType")),
        str(info.get("numCylinders")) if info.get("numCylinders") is not None else None,
        _str_val(info.get("documentationType")),
        auction_id,
        region_id,
        item.get("sellerId"),
        item.get("itemId"),
        item.get("key"),
        float(result["amount"]) if result.get("amount") is not None else None,
        result.get("expiration"),
        float(item["reservePrice"]) if item.get("reservePrice") is not None else (
            float(result["reservePrice"]) if result.get("reservePrice") is not None else None
        ),
        _extract_fee(result.get("fees")) or _extract_fee(item.get("feePrice")),
        item.get("sellerNotes") or result.get("sellerNotes") or info.get("sellerNotes"),
        images_json,
        images_count,
        _firestore_ts_to_iso(item.get("publishedAt")),
        listing_odo,
    ))


def scrape_data(auction_id: str, region_id: str) -> int:
    """Fetch all vehicles for a single auction via API. Used for manual triggers."""
    full_id = auction_id if auction_id.startswith("auction-") else f"auction-{auction_id}"
    print(f"[scraper] Fetching inventory for {full_id} ({region_id})...")
    items = autura_api.get_inventory(region_id, full_id)
    valid = [item for item in items if (item.get("info") or {}).get("vin")]
    print(f"[scraper] Got {len(valid)} items with VINs")

    if not valid:
        return 0

    image_map: dict[str, list[str]] = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(autura_api.get_item_images, item["key"]): item["key"]
                   for item in valid if item.get("key")}
        for future in as_completed(futures):
            key = futures[future]
            image_map[key] = future.result()

    saved = 0
    with sqlite3.connect(DB_PATH) as conn:
        for item in valid:
            item_key = item.get("key")
            if item_key and image_map.get(item_key):
                item["_images_override"] = image_map[item_key]
            save_vehicle(conn, item, full_id, region_id)
            saved += 1
        conn.commit()

    print(f"[scraper] Saved {saved} vehicles for {full_id}")
    return saved


def scrape_all_published() -> dict[str, int]:
    """
    Fetch all published vehicles nationwide in one API call.
    Returns {auction_id: vehicle_count} for updating auctions table.
    """
    print("[scraper] Fetching all published vehicles...")
    result = autura_api._post(autura_api._SEARCH_HTTP, "searchEngine-getPublishedVehiclesForFilters", {"limit": 2000})
    all_items = result.get("result", {}).get("vehicles", [])
    valid = [item for item in all_items if (item.get("info") or {}).get("vin")]
    print(f"[scraper] Got {len(valid)} published vehicles with VINs")

    if not valid:
        return {}

    # Fetch full image sets in parallel
    image_map: dict[str, list[str]] = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(autura_api.get_item_images, item["key"]): item["key"]
                   for item in valid if item.get("key")}
        for future in as_completed(futures):
            key = futures[future]
            image_map[key] = future.result()

    counts: dict[str, int] = {}
    with sqlite3.connect(DB_PATH) as conn:
        for item in valid:
            auction_id = item.get("auctionId", "")
            region_id  = item.get("regionId", "")
            item_key   = item.get("key")
            if item_key and image_map.get(item_key):
                item["_images_override"] = image_map[item_key]
            save_vehicle(conn, item, auction_id, region_id)
            counts[auction_id] = counts.get(auction_id, 0) + 1
        conn.commit()

    print(f"[scraper] Saved {len(valid)} vehicles across {len(counts)} auctions")
    return counts
