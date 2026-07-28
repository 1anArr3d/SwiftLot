"""
Autura Marketplace API client — mp.autura.com.

Fetches HTML pages from the inventory feed, extracts the embedded
React Router turbo-stream payload, and decodes it into plain dicts.

Session is acquired once via POST /signin and reused; re-auth on redirect
back to /signin (session expiry).
"""
import json
import math
import os
import threading

from curl_cffi import requests as cffi_requests

BASE_URL = "https://mp.autura.com"

_session: cffi_requests.Session | None = None
_session_lock = threading.Lock()


# ── Session ───────────────────────────────────────────────────────────────────

def _acquire_session() -> cffi_requests.Session:
    email = os.getenv("AUTURA_EMAIL", "")
    password = os.getenv("AUTURA_PASSWORD", "")

    sess = cffi_requests.Session(impersonate="chrome120")
    sess.headers.update({
        "accept-language": "en-US,en;q=0.9",
        "origin": BASE_URL,
        "referer": f"{BASE_URL}/signin",
    })

    if email and password:
        print("[autura] Logging in...")
        sess.get(f"{BASE_URL}/signin", timeout=20)
        sess.post(
            f"{BASE_URL}/signin",
            data={"email": email, "password": password},
            headers={"content-type": "application/x-www-form-urlencoded"},
            timeout=20,
        )
        if sess.cookies.get("user-session"):
            print("[autura] Logged in")
        else:
            print("[autura] Login failed — no user-session cookie received")
    else:
        print("[autura] No credentials — guest session only")

    return sess


def _get_session() -> cffi_requests.Session:
    global _session
    with _session_lock:
        if _session is None:
            _session = _acquire_session()
        return _session


def reset_session():
    global _session
    with _session_lock:
        _session = None


def _authed_get(url: str, **kwargs) -> cffi_requests.Response:
    sess = _get_session()
    resp = sess.get(url, **kwargs)
    if resp.url and "/signin" in str(resp.url) and resp.url != url:
        reset_session()
        sess = _get_session()
        resp = sess.get(url, **kwargs)
    return resp


# ── Turbo-stream decoder ───────────────────────────────────────────────────────

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


def _fetch_flat(url: str) -> list:
    """Fetch a .data endpoint that returns a turbo-stream JSON array directly."""
    resp = _authed_get(url, timeout=30, allow_redirects=True)
    resp.raise_for_status()
    return json.loads(resp.text)


# ── Endpoints ─────────────────────────────────────────────────────────────────

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


def get_listings_page(page: int = 1, seller: str = None) -> dict:
    """
    Fetch one page of active inventory from mp.autura.com/auctions.data.
    Returns decoded dict with keys: unitListings, soldUnitListings, total, page, perPage.
    Pass seller=accountId to filter to a single seller.
    """
    url = f"{BASE_URL}/auctions.data?page={page}"
    if seller:
        url += f"&seller={seller}"
    flat = _fetch_flat(url)
    root = _decode(flat, flat[0])
    page_data = root.get("pages/auctions/Auctions") or {}
    return page_data.get("data") or {}


def get_all_listings() -> list[dict]:
    """Fetch and return all active unitListings across all pages."""
    active, _ = get_all_feed()
    return active


def get_all_feed() -> tuple[list[dict], list[dict]]:
    """
    Fetch all pages and return (active_listings, sold_listings).
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
    Paginates until both lists stop growing (total=0 for sold-only sellers).
    Returns (active_listings, sold_listings).
    """
    first = get_listings_page(1, seller=account_id)
    per_page = first.get("perPage") or 12
    active = list(first.get("unitListings") or [])
    sold = list(first.get("soldUnitListings") or [])

    # Use total for active pages; fall back to response-size check for sold-only sellers
    total = first.get("total") or 0
    total_pages = max(1, math.ceil(total / per_page)) if per_page else 1

    seen_vins: set[str] = set()
    for lst in (active, sold):
        for l in lst:
            v = (l.get("unitDetails") or {}).get("vin")
            if v:
                seen_vins.add(v)

    p = 2
    while p <= max(total_pages, 1) + 1:
        page_data = get_listings_page(p, seller=account_id)
        new_active = page_data.get("unitListings") or []
        new_sold = page_data.get("soldUnitListings") or []
        if not new_active and not new_sold:
            break
        new_vins = {(l.get("unitDetails") or {}).get("vin") for l in new_active + new_sold} - {None}
        if new_vins and new_vins.issubset(seen_vins):
            break  # API cycling — same items returned again
        seen_vins.update(new_vins)
        active.extend(new_active)
        sold.extend(new_sold)
        p += 1

    return active, sold
