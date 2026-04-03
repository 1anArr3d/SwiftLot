"""
Autura API client — Firebase auth + Cloud Run microservice calls.
Token is cached and refreshed automatically (expires every ~1 hour).
"""
import json
import os
import time
import urllib.request
import urllib.error
from dotenv import load_dotenv

load_dotenv()

EMAIL    = os.getenv("AUTURA_EMAIL")
PASSWORD = os.getenv("AUTURA_PASSWORD")
_API_KEY = "AIzaSyCT8xhncpOmizPFVFTvdbv3k434fbhLoH4"

_ITEMS_HTTP    = "https://items-http-duoqjfx26q-uc.a.run.app/api/internal/items-http"
_AUCTIONS_HTTP = "https://auctions-http-duoqjfx26q-uc.a.run.app/api/internal/auctions-http"
_SEARCH_HTTP   = "https://search-http-duoqjfx26q-uc.a.run.app/api/internal/search-http"

_token: str | None = None
_token_expiry: float = 0
_token_lock = __import__('threading').Lock()


def _login() -> dict:
    # Try email/password first; fall back to anonymous auth for RTDB-only access
    if EMAIL and PASSWORD:
        try:
            url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={_API_KEY}"
            payload = json.dumps({"email": EMAIL, "password": PASSWORD, "returnSecureToken": True}).encode()
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read())
        except Exception:
            pass
    # Anonymous auth — works for RTDB reads (public auction data)
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={_API_KEY}"
    payload = json.dumps({"returnSecureToken": True}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def get_token() -> str:
    global _token, _token_expiry
    if _token and time.time() < _token_expiry - 60:
        return _token
    with _token_lock:
        if _token and time.time() < _token_expiry - 60:
            return _token
        data = _login()
        _token = data["idToken"]
        _token_expiry = time.time() + int(data.get("expiresIn", 3600))
        print("[autura_api] Refreshed auth token")
        return _token


def _post(base_url: str, fn_name: str, inner: dict) -> dict:
    token = get_token()
    url = f"{base_url}/{fn_name}"
    body = json.dumps({"data": inner}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def get_inventory(region_id: str, auction_id: str) -> list[dict]:
    """
    Fetch all items for an auction.

    Each item dict contains:
      item["info"]          – vin, year, make, model, exteriorColor, keyStatus,
                               fuelType, engineType, startCode, catalyticConverter,
                               drivetrain, body, numCylinders, ...
      item["currentResult"] – amount (current bid $), expiration (ISO), fees, uid, ...
                               (absent or minimal when no bids placed yet)
      item["image"]         – full_4x3, thumb_200, original — keyed by index str
      item["itemId"]        – e.g. "JS-225-50499"
      item["key"]           – Firestore document key
      item["sellerId"]      – e.g. "JS-225"
      item["status"]        – "published" etc.
    """
    full_id = auction_id if auction_id.startswith("auction-") else f"auction-{auction_id}"
    result = _post(_ITEMS_HTTP, "item-getInventoryItemsForAuction", {
        "regionId": region_id,
        "auctionId": full_id,
    })
    return result.get("result", [])


_FIRESTORE = "https://firestore.googleapis.com/v1/projects/digital-auction/databases/(default)/documents"


def get_item_images(item_key: str) -> list[str]:
    """
    Fetch all full_4x3 image URLs for an item from Firestore.
    Returns a list of URLs ordered by image index.
    """
    token = get_token()
    url = f"{_FIRESTORE}/items/{item_key}/images/full_4x3"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            doc = json.loads(r.read())
        fields = doc.get("fields", {})
        urls = []
        for idx in sorted(fields.keys(), key=lambda x: int(x) if x.isdigit() else 999):
            url_val = (
                fields[idx]
                .get("mapValue", {})
                .get("fields", {})
                .get("url", {})
                .get("stringValue")
            )
            if url_val:
                urls.append(url_val)
        return urls
    except Exception:
        return []


def get_active_region_ids() -> list[str]:
    """
    Return all region IDs that currently have published vehicles.
    Covers the entire platform nationwide — no hardcoding required.
    """
    result = _post(_SEARCH_HTTP, "searchEngine-getPublishedVehiclesForFilters", {"limit": 2000})
    data = result.get("result", {})
    vehicles = data.get("vehicles", []) if isinstance(data, dict) else []
    seen = []
    for v in vehicles:
        rid = v.get("regionId")
        if rid and rid not in seen:
            seen.append(rid)
    return seen


def get_auction_series(region_id: str) -> list[dict]:
    """
    Fetch all auction series for a region.

    Each series dict contains:
      series["id"]      – numeric series ID
      series["key"]     – Firebase RTDB key
      series["name"]    – seller / series name
      series["regionId"]
      series["auctions"] – list of auction objects:
          auction["auctionId"]  – e.g. "auction-109070"
          auction["ended"]      – bool
          auction["endedAt"]    – epoch ms (if ended)
          auction["sellers"]    – {"JS-225": true, ...}
          auction["regionId"]
    """
    result = _post(_AUCTIONS_HTTP, "auction-getAuctionSeries", {"regionId": region_id})
    return result.get("result", [])
