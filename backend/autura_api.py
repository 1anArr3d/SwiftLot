"""
Autura Marketplace API client — mp.autura.com.

Fetches HTML pages from the inventory feed, extracts the embedded
React Router turbo-stream payload, and decodes it into plain dicts.
No separate API calls needed — all data is server-rendered.

See docs/autura_mp_api.md for full structure reference.
"""
import json
import math
from curl_cffi import requests as cffi_requests

BASE_URL = "https://mp.autura.com"


def _fetch_html(url: str) -> str:
    resp = cffi_requests.get(url, impersonate="chrome120", timeout=30)
    resp.raise_for_status()
    return resp.text


def _fetch_flat(url: str) -> list:
    """Fetch a .data endpoint that returns a turbo-stream JSON array directly."""
    resp = cffi_requests.get(url, impersonate="chrome120", timeout=30)
    resp.raise_for_status()
    return json.loads(resp.text)


def get_all_sellers() -> list[dict]:
    """
    Fetch the full seller registry from /sellers.data.
    Returns list of dicts with accountId and accountName.
    """
    flat = _fetch_flat(f"{BASE_URL}/sellers.data?_routes=routes%2Fsellers")
    root = _decode(flat, flat[0])
    data = (root.get("routes/sellers") or {}).get("data") or {}
    sellers_raw = data.get("sellers") or []
    return [
        {"accountId": s["accountId"], "accountName": s["accountName"]}
        for s in sellers_raw
        if s and s.get("accountId") and s.get("accountName")
    ]


def _decode(flat: list, val) -> any:
    """Recursively decode one turbo-stream value from the flat array."""
    if isinstance(val, bool):
        return val
    if isinstance(val, int):
        return None if val < 0 else val
    if isinstance(val, (float, str)) or val is None:
        return val
    if isinstance(val, dict):
        result = {}
        for k, v in val.items():
            if not k.startswith("_"):
                continue
            key = flat[int(k[1:])]
            result[key] = None if (isinstance(v, int) and v < 0) else _decode(flat, flat[v])
        return result
    if isinstance(val, list):
        return [
            None if (isinstance(i, int) and i < 0) else _decode(flat, flat[i])
            for i in val
        ]
    return val


def _parse_auctions_page(html: str) -> dict:
    """Extract and decode the auctions page loader data from page HTML."""
    idx = html.find("streamController.enqueue(")
    if idx == -1:
        raise ValueError("turbo-stream enqueue not found in page HTML")
    rest = html[idx + len("streamController.enqueue("):]
    raw_json_str, _ = json.JSONDecoder().raw_decode(rest.strip())
    flat = json.loads(raw_json_str)
    root = _decode(flat, flat[0])
    loader = root.get("loaderData") or {}
    return loader.get("pages/auctions/Auctions") or {}


def get_listings_page(page: int = 1, seller: str = None, zip_code: str = None) -> dict:
    """
    Fetch one page of active inventory from mp.autura.com/auctions.
    Returns decoded dict with keys: unitListings, soldUnitListings, total, page, perPage.
    Pass seller=accountId to filter to a single seller.
    Pass zip_code to include structured city/state in sellerDisclosure.
    """
    url = f"{BASE_URL}/auctions?page={page}"
    if seller:
        url += f"&seller={seller}"
    if zip_code:
        url += f"&zipCode={zip_code}&distance=50"
    html = _fetch_html(url)
    return _parse_auctions_page(html)


def get_all_listings() -> list[dict]:
    """
    Fetch and return all active unitListings across all pages.
    """
    active, _ = get_all_feed()
    return active


def get_all_feed() -> tuple[list[dict], list[dict]]:
    """
    Fetch all pages once and return (active_listings, sold_listings).
    Prefer this over get_all_listings() when you also need sold data.
    """
    first = get_listings_page(1)
    total = first.get("total") or 0
    per_page = first.get("perPage") or 12
    active = list(first.get("unitListings") or [])
    sold = list(first.get("soldUnitListings") or [])

    total_pages = math.ceil(total / per_page) if per_page else 1
    for p in range(2, total_pages + 1):
        page_data = get_listings_page(p)
        active.extend(page_data.get("unitListings") or [])
        sold.extend(page_data.get("soldUnitListings") or [])

    return active, sold


def get_seller_listings(account_id: str) -> tuple[list[dict], list[dict]]:
    """
    Fetch active + sold listings for a single seller via ?seller= filter.
    Much faster than fetching all 16 pages when we only need one seller.
    Returns (active_listings, sold_listings).
    """
    first = get_listings_page(1, seller=account_id)
    total = first.get("total") or 0
    per_page = first.get("perPage") or 12
    active = list(first.get("unitListings") or [])
    sold = list(first.get("soldUnitListings") or [])

    total_pages = math.ceil(total / per_page) if per_page else 1
    for p in range(2, total_pages + 1):
        page_data = get_listings_page(p, seller=account_id)
        active.extend(page_data.get("unitListings") or [])
        sold.extend(page_data.get("soldUnitListings") or [])

    return active, sold


def get_sold_listings(page: int = 1) -> list[dict]:
    """
    Return soldUnitListings from a single page of the inventory feed.
    """
    data = get_listings_page(page)
    return data.get("soldUnitListings") or []


def get_listing_detail(unit_listing_id: str) -> dict:
    """
    Fetch a single listing detail page from /auctions/listings/{unit_listing_id}.
    Returns the decoded loader data dict (structure TBD from devtools).
    """
    html = _fetch_html(f"{BASE_URL}/auctions/listings/{unit_listing_id}")
    idx = html.find("streamController.enqueue(")
    if idx == -1:
        raise ValueError("turbo-stream enqueue not found in detail page HTML")
    rest = html[idx + len("streamController.enqueue("):]
    raw_json_str, _ = json.JSONDecoder().raw_decode(rest.strip())
    flat = json.loads(raw_json_str)
    root = _decode(flat, flat[0])
    return root.get("loaderData") or {}
