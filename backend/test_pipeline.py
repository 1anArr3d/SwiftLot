"""
Pipeline tester — run stages individually to verify each layer.

Usage:
    python backend/test_pipeline.py feed          # fetch page 1 (no DB)
    python backend/test_pipeline.py detail        # fetch one vehicle detail page (no DB)
    python backend/test_pipeline.py scrape        # full feed → DB (needs Postgres)
    python backend/test_pipeline.py ping          # simulate Ably ping on first DB auction (needs Postgres)
    python backend/test_pipeline.py sellers       # fetch seller registry (no DB)
    python backend/test_pipeline.py ably          # test Ably auth + channel enumeration
    python backend/test_pipeline.py rewind        # subscribe with rewind=1
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))


# ── HTTP-only stages (no DB) ──────────────────────────────────────────────────

def test_feed():
    """Fetch page 1 of the authenticated feed and show key fields on the first listing."""
    import json
    print("\n── Feed (page 1) ─────────────────────────────")
    from autura_api import get_listings_page
    page     = get_listings_page(1)
    total    = page.get("total", 0)
    per_page = page.get("perPage", 0)
    active   = page.get("unitListings") or []
    sold     = page.get("soldUnitListings") or []
    print(f"  total={total}  perPage={per_page}  active_on_p1={len(active)}  sold_on_p1={len(sold)}")

    if not active:
        print("  no active listings — check auth cookies")
        return

    s       = active[0]
    bidding = s.get("biddingInfo") or {}
    info    = bidding.get("auctionInfo") or {}
    seller  = s.get("sellerInfo") or {}
    details = s.get("unitDetails") or {}

    print(f"\n  first listing:")
    print(f"    item_key:    {details.get('unitListingId', '—')}")
    print(f"    vin:         {details.get('vin', '—')}")
    print(f"    auction_id:  {info.get('auctionId', '—')}")
    print(f"    status:      {bidding.get('biddingStatus', '—')}")
    print(f"    closes_at:   {info.get('biddingEndUtc', '—')}")
    print(f"    current_bid: {(bidding.get('winningBid') or {}).get('amountFormatted', '—')}")
    print(f"    seller_name: {seller.get('sellerName', '—')}")
    print(f"    seller_city: {seller.get('city', '—')}")
    print(f"    seller_state:{seller.get('state', '—')}")


def test_detail():
    """
    Fetch the detail page for the first active listing and show its biddingInfo.
    This is the endpoint called on every Ably ping per vehicle.
    """
    import json
    print("\n── Listing detail (single vehicle) ──────────")
    from autura_api import get_listings_page, get_listing_detail

    page = get_listings_page(1)
    listings = page.get("unitListings") or []
    if not listings:
        print("  no active listings on page 1")
        return

    s        = listings[0]
    details  = s.get("unitDetails") or {}
    item_key = details.get("unitListingId")
    vin      = details.get("vin", "—")
    print(f"  item_key: {item_key}  vin: {vin}")

    if not item_key:
        print("  no unitListingId — cannot fetch detail")
        return

    result = get_listing_detail(item_key)
    print(f"\n  get_listing_detail result:")
    print(f"    current_bid:    {result['current_bid']}")
    print(f"    bid_expiration: {result['bid_expiration']}")
    print(f"    status:         {result['status']}")

    if result["current_bid"] is None and result["status"] is None:
        print("\n  ⚠ both fields null — detail page may need auth or the route key changed")
        print("  falling back to raw HTML inspection...")
        from autura_api import _fetch_html, _decode
        html = _fetch_html(f"https://mp.autura.com/auctions/listings/{item_key}")
        idx  = html.find("streamController.enqueue(")
        if idx == -1:
            print("  no turbo-stream enqueue found in detail HTML")
            return
        rest = html[idx + len("streamController.enqueue("):]
        import json as _json
        raw, _ = _json.JSONDecoder().raw_decode(rest.strip())
        flat   = _json.loads(raw)
        root   = _decode(flat, flat[0])
        loader = root.get("loaderData") or {}
        print(f"  loaderData keys: {list(loader.keys())}")
        for k, v in loader.items():
            if isinstance(v, dict):
                ul      = v.get("unitListing") or {}
                bidding = ul.get("biddingInfo") or {}
                if bidding:
                    print(f"  [{k}] biddingInfo keys: {list(bidding.keys())}")
                    ai = bidding.get("auctionInfo") or {}
                    print(f"    auctionId:    {ai.get('auctionId', '—')}")
                    print(f"    biddingEndUtc:{ai.get('biddingEndUtc', '—')}")
                    winning = bidding.get("winningBid") or {}
                    print(f"    amountCents:  {winning.get('amountCents', '—')}")
                else:
                    print(f"  [{k}] keys: {list(v.keys())}")


def test_sellers():
    """Fetch seller registry — shows account names but no location data."""
    print("\n── Sellers ───────────────────────────────────")
    from autura_api import get_all_sellers
    sellers = get_all_sellers()
    print(f"  {len(sellers)} sellers in registry")
    for s in sellers[:5]:
        print(f"  {s['accountId']}  {s['accountName']}")
    if len(sellers) > 5:
        print(f"  ... and {len(sellers) - 5} more")


# ── DB-dependent stages ───────────────────────────────────────────────────────

def test_scrape():
    """Full feed scrape → DB. Populates vehicles, auctions, historical_sales."""
    print("\n── Full feed scrape → DB ─────────────────────")
    from db import init_db
    init_db()
    from feed_scraper import run_full_feed
    result = run_full_feed()
    print(f"  vehicles={result['vehicles']}  auctions={result['auctions']}  sold={result['sold']}")

    from db import query
    a      = query("SELECT COUNT(*) AS n FROM auctions")[0]["n"]
    v      = query("SELECT COUNT(*) AS n FROM vehicles")[0]["n"]
    hs     = query("SELECT COUNT(*) AS n FROM historical_sales")[0]["n"]
    no_loc = query("SELECT COUNT(*) AS n FROM auctions WHERE seller_city IS NULL")[0]["n"]
    print(f"\n  DB totals: auctions={a}  vehicles={v}  historical_sales={hs}")
    print(f"  auctions missing seller_city: {no_loc}")

    # sample one auction with location
    sample = query("""
        SELECT auction_id, seller_name, seller_city, seller_state, auction_status
        FROM auctions WHERE seller_city IS NOT NULL LIMIT 1
    """)
    if sample:
        r = sample[0]
        print(f"\n  sample auction with location:")
        print(f"    {r['seller_name']} — {r['seller_city']}, {r['seller_state']} ({r['auction_status']})")


def test_ping():
    """
    Simulate an Ably ping on the first active auction in DB.
    Calls the same handler that fires on a real Ably ping.
    """
    import asyncio
    print("\n── Ping simulation ───────────────────────────")
    from db import query
    rows = query(
        "SELECT auction_id FROM auctions WHERE auction_status IN ('ACTIVE', 'PRE_BID') LIMIT 1"
    )
    if not rows:
        print("  no active auctions in DB — run scrape first")
        return

    auction_id = rows[0]["auction_id"]
    print(f"  simulating ping for auction_id: {auction_id}")

    vehicles = query(
        "SELECT item_key, current_bid FROM vehicles WHERE auction_id = %s AND item_key IS NOT NULL",
        (auction_id,),
    )
    print(f"  {len(vehicles)} vehicle(s) in DB for this auction")
    if not vehicles:
        print("  no vehicles with item_key — cannot fetch details")
        return

    # Run the actual ping handler directly
    import auction_listener as listener
    import asyncio

    async def _run():
        # bypass debounce by clearing it first
        listener._debounce.pop(auction_id, None)

        class FakeMsg:
            name = "PING_SIM"
            data = None

        await listener._on_update(auction_id, FakeMsg())

    asyncio.run(_run())

    # Show updated values
    after = query(
        "SELECT item_key, current_bid, bid_expiration FROM vehicles WHERE auction_id = %s AND item_key IS NOT NULL",
        (auction_id,),
    )
    print(f"\n  post-ping vehicle bids:")
    for r in after[:10]:
        print(f"    {r['item_key']}  bid={r['current_bid']}  exp={r['bid_expiration']}")


# ── Ably stages ───────────────────────────────────────────────────────────────

def test_ably():
    """Test Ably token auth and show channel capabilities."""
    from curl_cffi import requests as cffi_requests
    print("\n── Ably auth ─────────────────────────────────")
    auth = cffi_requests.get("https://mp.autura.com/ably-auth", impersonate="chrome120", timeout=10)
    print(f"  /ably-auth status: {auth.status_code}")
    tr = auth.json()
    key_name = tr.get("keyName", "")
    print(f"  keyName:    {key_name}")
    print(f"  capability: {tr.get('capability')}")
    print(f"  ttl:        {tr.get('ttl')}")

    import requests as std_requests
    ex = std_requests.post(
        f"https://rest.ably.io/keys/{key_name}/requestToken",
        json=tr, timeout=10
    )
    print(f"\n  token exchange: {ex.status_code}")
    if ex.status_code in (200, 201):
        token = ex.json().get("token", "")
        print(f"  token: {token[:40]}...")


def test_rewind():
    """Subscribe with rewind=1 on the first active auction to check for recent messages."""
    import json, asyncio
    from curl_cffi import requests as cffi_requests
    print("\n── Ably rewind ───────────────────────────────")

    from autura_api import get_listings_page
    page     = get_listings_page(1)
    listings = page.get("unitListings") or []
    if not listings:
        print("  no active listings")
        return
    s        = listings[0]
    bidding  = s.get("biddingInfo") or {}
    info     = bidding.get("auctionInfo") or {}
    auction_id = info.get("auctionId")
    item_key   = (s.get("unitDetails") or {}).get("unitListingId")
    print(f"  auction_id: {auction_id}")
    print(f"  item_key:   {item_key}")

    tr = cffi_requests.get("https://mp.autura.com/ably-auth", impersonate="chrome120", timeout=10).json()
    key_name = tr.get("keyName", "")

    import requests as std_requests
    ex = std_requests.post(
        f"https://rest.ably.io/keys/{key_name}/requestToken",
        json=tr, timeout=10
    )
    if ex.status_code not in (200, 201):
        print(f"  token exchange failed: {ex.status_code}")
        return
    token = ex.json().get("token")

    from ably import AblyRealtime

    async def _subscribe(channel_name):
        client = AblyRealtime(token=token)
        received = []
        print(f"\n  subscribing: {channel_name}")
        ch = client.channels.get(channel_name, {"params": {"rewind": "1"}})

        async def _on_msg(msg):
            received.append(msg)
            print(f"  ← name={msg.name}  data={json.dumps(msg.data, default=str)[:300]}")

        await ch.subscribe(_on_msg)
        await asyncio.sleep(5)
        await client.close()
        if not received:
            print(f"  no messages received (no rewind history)")

    async def _run():
        if auction_id:
            await _subscribe(f"public:auction:{auction_id}:updates")

    asyncio.run(_run())


# ── Stage registry ────────────────────────────────────────────────────────────

STAGES = {
    # HTTP-only (no DB needed)
    "feed":    test_feed,
    "detail":  test_detail,
    "sellers": test_sellers,
    "ably":    test_ably,
    "rewind":  test_rewind,
    # DB-dependent
    "scrape":  test_scrape,
    "ping":    test_ping,
}

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("Stages available:", list(STAGES.keys()))
        print("Usage: python backend/test_pipeline.py <stage> [stage...]")
        sys.exit(0)

    unknown = [a for a in args if a not in STAGES]
    if unknown:
        print(f"Unknown stage(s): {unknown}")
        print(f"Available: {list(STAGES.keys())}")
        sys.exit(1)

    for name in args:
        try:
            STAGES[name]()
        except Exception as e:
            import traceback
            print(f"\n  ERROR in {name}: {e}")
            traceback.print_exc()
    print()
