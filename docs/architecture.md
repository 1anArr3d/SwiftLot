# SwiftLot Backend Architecture

_Last updated: 2026-07-18_

---

## What we know (confirmed)

### Authentication
- `mp.autura.com` is fully auth-gated. Unauthenticated requests return null for all
  biddingInfo fields (auctionId, currentBid, status, expiry, etc.).
- Auth is two cookies: `user-session` and `selected-account-id`.
- Stored in `.env` as `AUTURA_SESSION` and `AUTURA_ACCOUNT_ID`.
- Session expires roughly monthly. Email + password are in `.env` for future auto-refresh.

### Authenticated feed (`/auctions?page=N`)
A single paginated crawl returns everything we need per listing:

| Field | Path in payload |
|---|---|
| VIN, year, make, model | `unitDetails.*` |
| Seller name | `sellerInfo.sellerName` |
| Seller city / state | `sellerInfo.city`, `sellerInfo.state` |
| Auction ID (Ably channel key) | `biddingInfo.auctionInfo.auctionId` |
| Auction status | `biddingInfo.biddingStatus` |
| Closes at | `biddingInfo.auctionInfo.biddingEndUtc` |
| Current winning bid (cents) | `biddingInfo.winningBid.amountCents` |
| Min bid (cents) | `biddingInfo.minBid.amountCents` |

`soldUnitListings` is returned on the same response pages — these feed directly into
`historical_sales` for average price calculations (the core value prop).

### Ably WebSocket (`public:auction:{auctionId}:updates`)
- Ably is a **dumb ping bus** — events arrive when the auction state changes but
  **the payload carries no bid amount or useful data**.
- Events observed: `NEW_BID`, `AUCTION_UPDATED` — both are notifications only.
- Rewind (`rewind=1`) returned nothing useful.
- Capability issued by `/ably-auth`: `{"*":["subscribe"]}` — subscribe only, no history.

**Consequence:** Ably tells us *when* to re-fetch, not *what* changed.
Every bid update still requires one HTTP request to get the new value.

---

## Design goals

1. **No bid spam** — same or fewer HTTP requests than current, never risk a ban.
2. **Near real-time bids** — fresh enough that a buyer can make a decision.
   Definition: ≤ 30 seconds stale during active bidding.
3. **Full vehicle data** — VIN, condition, seller state, inspection history.
4. **Historical avg price** — sold listings processed into `historical_sales`.

---

## Proposed architecture

### Startup (once on boot)
```
Authenticated feed scrape (all pages)
  → upsert vehicles table (full details)
  → upsert auctions table (seller state/city, status, closes_at)
  → process soldUnitListings → historical_sales
  → collect all active auctionIds
  → subscribe Ably channel for each active auctionId
```

### Ably ping handler (event-driven)
```
Ping arrives on public:auction:{auctionId}:updates
  → debounce: skip if same auctionId pinged within last 15s
  → SELECT item_key FROM vehicles WHERE auction_id = X  (zero HTTP, from DB)
  → fetch /auctions/listings/{item_key}.data for each vehicle  (parallel, targeted)
  → parse biddingInfo.winningBid.amountCents from each response
  → UPDATE vehicles SET current_bid, bid_expiration WHERE item_key = X
  → broadcast SSE snapshot to watching clients
```

**No N-page scrape on pings.** The feed (`/auctions?page=N`) is only hit during
startup and the 2-hour reconciler. On a ping, we only fetch the specific vehicles
we already know about for that auction — one HTTP request per vehicle, fired in
parallel, scoped entirely to that auction.

Debounce window: **15 seconds**. During a bidding war, pings can arrive several
times per minute. Without debounce, each ping triggers a batch of fetches.
With 15s debounce, a 10-ping burst becomes a single batch.

Typical auction size: 15–40 vehicles. A ping costs 15–40 lightweight `.data`
requests in parallel, resolving in roughly the time of one serial request.

### Periodic reconciliation (every 2 hours)
```
Full authenticated feed scrape (same as startup)
  → catches new listings that appeared between pings
  → catches auctions that ended without firing an AUCTION_UPDATED
  → diffs active auctionIds vs DB: subscribe to new, unsubscribe dead
  → re-processes soldUnitListings for any newly sold vehicles
```

### Auction ended detection
```
Reconciler sees auctionId no longer in active feed
  → harvest: move final sold price into historical_sales
  → UPDATE auctions SET auction_status = 'completed', ended_at = NOW()
  → broadcast SSE { type: "ended" } to clients watching that auction
  → unsubscribe Ably channel
```

---

## HTTP request budget

| Trigger | Requests | Frequency |
|---|---|---|
| Startup | N feed pages (~5–10) | Once |
| Periodic reconciler | N feed pages | Every 2h |
| Ably ping (debounced) | M detail pages (M = vehicles in that auction) | At most 1 batch per 15s per auction |
| Ably ping, old approach | N seller feed pages | Every ping |

**Old worst case:** 4 pings/min × 5 seller pages = 20 req/min, re-scraping vehicles
that didn't change.

**New worst case:** 1 debounced batch per 15s × 30 vehicle detail pages = 30 req
per 15s per auction, but each request is scoped to exactly one vehicle that may
have changed. No cross-auction bleed.

---

## File structure (proposed)

```
backend/
  feed_scraper.py        # replaces auction_scraper.py + auction_discovery.py
                         # single pass: vehicles + auctions + historical_sales
  auction_listener.py    # Ably subscriptions + debounced ping handler
  historical_harvester.py  # unchanged — processes sold listings into historical_sales
  inspection_scraper.py    # unchanged
  autura_api.py            # unchanged — HTTP client
  config.py                # unchanged
  db.py                    # unchanged
```

`auction_scraper.py` and `auction_discovery.py` merge into `feed_scraper.py`.
The single-pass approach eliminates the awkward two-step where discovery runs
separately from the vehicle upsert.

---

## Open questions

1. **`AUCTION_UPDATED` payload** — does it carry `biddingStatus` in the message data,
   or is it a bare ping? If it carries status, we can handle PRE_BID→ACTIVE→ENDED
   transitions without any HTTP. Needs a live test to confirm.

2. **`bid_amount` in `NEW_BID`** — the payload *may* carry the bid amount even though
   we haven't confirmed it. Worth logging raw message.data on first live event.
   If it does, NEW_BID becomes zero-HTTP: update DB directly from payload.

3. **Debounce window** — 15s is a starting point. If auctions close in sub-15s
   intervals, we may miss a final bid. Could tighten to 5s during the last minute
   of an auction (bid_expiration is in DB, so we can check).

4. **Session expiry** — current session expires ~2026-08-17. Before then, add an
   auto-refresh flow: POST to `/auth/login` with AUTURA_EMAIL + AUTURA_PASSWORD,
   capture new cookies, update .env and in-memory config.

---

## What stays the same

- Ably subscription management (subscribe_auction, unsubscribe_auction, sync_with_db)
- SSE broadcast format (`{ type: "update", auction_id, vehicles: [...] }`)
- `historical_sales` table and harvest logic
- Inspection scraper (TX odometer history)
- Frontend — no changes needed if SSE format is preserved
