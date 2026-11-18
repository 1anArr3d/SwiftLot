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
    Returns list of dicts with accountId, accountName and sellingConfig (platform fee overrides, may be empty).
    """
    flat = _fetch_flat(f"{BASE_URL}/sellers.data?_routes=routes%2Fsellers")
    root = _decode(flat, flat[0])
    data = (root.get("routes/sellers") or {}).get("data") or {}
    sellers_raw = data.get("sellers") or []
    return [
        {"accountId": s["accountId"], "accountName": s["accountName"], "sellingConfig": s.get("sellingConfig") or {}}
        for s in sellers_raw
        if s and s.get("accountId") and s.get("accountName")
    ]


def get_all_listings() -> list[dict]:
    """Fetch and return all active unitListings across all pages."""
    active, _ = get_all_feed()
    return active


def get_all_feed(**filters) -> tuple[list[dict], list[dict]]:
    """
    Fetch all US listings using a central zip code with a large radius.
    One call covers the entire continental US. `filters` are Autura's own search params,
    e.g. auction_status="LIVE_BIDDING" for only the lots in their live hour.
    """
    # Liberal, KS — geographic center of the contiguous US
    base = f"{BASE_URL}/auctions.data?distance=2000&zipCode=67901" + "".join(f"&{k}={v}" for k, v in filters.items())

    first_flat = _fetch_flat(f"{base}&page=1")
    first_root = _decode(first_flat, first_flat[0])
    first_route = (first_root.get("pages/auctionsRoute/AuctionsRoute") or {}).get("data") or {}
    first = first_route.get("data") or {}

    total    = first.get("total") or 0
    per_page = first.get("perPage") or 12
    active   = list(first.get("unitListings") or [])
    sold     = list(first.get("soldUnitListings") or [])

    total_pages = math.ceil(total / per_page) if per_page else 1
    print(f"[autura] {total} total listings across {total_pages} pages")

    for p in range(2, total_pages + 1):
        page_data_flat = _fetch_flat(f"{base}&page={p}")
        page_root = _decode(page_data_flat, page_data_flat[0])
        page_route = (page_root.get("pages/auctionsRoute/AuctionsRoute") or {}).get("data") or {}
        page = page_route.get("data") or {}
        active.extend(page.get("unitListings") or [])
        sold.extend(page.get("soldUnitListings") or [])

    return active, sold



def get_lot(unit_listing_id: str) -> dict | None:
    """One listing as its lot page loads it (same shape as a feed listing), or None if Autura no longer serves it."""
    route = "pages/bidderViewUnitListing/BidderViewUnitListing"
    flat = _fetch_flat(f"{BASE_URL}/auctions/listings/{unit_listing_id}.data?_routes={route}")
    return (((_decode(flat, flat[0]).get(route) or {}).get("data")) or {}).get("unitListing")


def get_bids(seller_account_id: str, auction_id: str, per_page: int = 100) -> dict:
    """Bid history for one lot: {"bids": [...], "total": n}. Amounts in cents. Contains bidder initials/email hints."""
    resp = _authed_get(f"{BASE_URL}/bids-history?unit_account_id={seller_account_id}&auction_id={auction_id}&page=1&per_page={per_page}", timeout=20)
    resp.raise_for_status()
    return resp.json()
