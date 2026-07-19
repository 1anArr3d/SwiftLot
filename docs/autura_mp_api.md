# Autura Marketplace API — Structure Reference

Discovered: 2026-07-16  
New platform: `https://mp.autura.com`  
Old platform: `https://autura.com` (Cloud Run microservices + Firebase RTDB — dead)

---

## Platform Overview

The new platform is a **React Router v7 SSR app** (Remix-style) served from `mp.autura.com`.
There are no more separate auction pages — all active inventory is a single unified listing feed.
Each vehicle listing carries its own auction context (dates, bid info, seller info).

**Key changes from old platform:**
- No Firebase RTDB, no Cloud Run microservices
- No more `auction-XXXXX` numeric IDs — everything uses **ULIDs**
- No more `regionId` grouping — replaced by `accountId` (seller account)
- Images moved from Firestore → **Amazon CloudFront**
- Firebase anonymous auth — unknown if still needed; no token seen in page HTML
- Auth for our own users (Firebase Auth on SwiftLot side) — unaffected

---

## Inventory Feed

### Page URL
```
GET https://mp.autura.com/auctions?page=N
```
- Page data is **server-rendered and embedded** in the HTML as a turbo-stream payload
- No separate API call needed — fetch the HTML, parse the stream
- `perPage: 12`, `total` varies (189 observed on 2026-07-16)
- Pages: `?page=1`, `?page=2`, ... up to `ceil(total / 12)`

### Parsing the Payload
The data lives in an inline `<script>` block:
```js
window.__reactRouterContext.streamController.enqueue("...")
```
- The enqueued value is a **JSON string** containing a flat array
- The array uses integer-index references: `{_50: 1192}` means "key at index 50, value at index 1192"
- Negative indices are sentinels: `-7` = null/undefined
- Decode by walking the array and resolving references recursively

### Pagination structure in decoded data
```json
{
  "unitListings": [...],
  "soldUnitListings": [...],
  "total": 189,
  "page": 1,
  "perPage": 12
}
```

---

## Vehicle Listing Structure (`unitListing`)

Each item in `unitListings` decodes to:

```json
{
  "title": "2010 Ford Focus",
  "status": "PUBLISHED",
  "publicUrl": "/auctions/listings/01kxghfew787b0gj73z3c9z2n0",

  "unitDetails": {
    "unitId": "01kxghfevz472fjv04vfqdqvzh",
    "unitListingId": "01kxghfew787b0gj73z3c9z2n0",
    "externalId": "Unknown",
    "vin": "1FAHP3GN0AW174009",
    "odometer": "Unknown mileage",
    "year": "2010",
    "color": "Red",
    "keys": "Has key",
    "engine": "4-Cylinder",
    "fuelType": "Gasoline",
    "catalyticConverter": "Unknown",
    "startStatus": "Does Not Start",
    "transmission": "Unknown",
    "drivetrain": "Front",
    "make": "Ford",
    "model": "Focus",
    "body": "Sedan/Saloon",
    "documentationType": "Parts only",
    "notes": null
  },

  "sellerInfo": {
    "sellerName": "Roberts Heavy Duty Towing"
    // NOTE: city/state/address are NOT present in anonymous requests.
    // They appear only in authenticated responses (see Seller Address Data section).
  },

  "biddingInfo": {
    "accessType": "PUBLIC",
    "biddingStatus": "PRE_BID",
    "isWinning": false,
    "isOutbid": false,
    "isReserveMet": true,
    "minBid": { "amountCents": 35000, "amountFormatted": "$350" },
    "startingPrice": { "amountCents": 35000, "amountFormatted": "$350" },
    "reservePrice": null,
    "winningBid": null,
    "sellerFees": {
      "keyFeeCents": null,
      "storageFeeCents": null,
      "docFeeCents": null
    },
    "platformFeeConfig": {
      "platformFeeRate": null,
      "minPlatformFeeAmount": null,
      "maxPlatformFeeAmount": null
    },
    "paymentProcessingConfig": {
      "isAchEnabled": null,
      "paymentProcessingFeeCardRate": 0.03
    },
    "auctionInfo": {
      "auctionId": "01kxk90naqckezda0drz9hng5f",
      "biddingStartUtc": "2026-07-17T14:00:00.000000Z",
      "biddingEndUtc": "2026-07-17T15:00:00.000000Z",
      "isHybrid": false,
      "pausedAt": null
    },
    "priceBreakdown": null
  },

  "media": {
    "allPhotos": [
      {
        "id": "01kxk8abjv62nw6gwncmwyx717",
        "desktopUrl": "https://d18rmcc9h5m005.cloudfront.net/{accountId}/{unitListingId}/{mediaGroupId}/IMAGE_DESKTOP/{timestamp}",
        "mobileUrl":  "https://d18rmcc9h5m005.cloudfront.net/{accountId}/{unitListingId}/{mediaGroupId}/IMAGE_MOBILE/{timestamp}",
        "thumbUrl":   "https://d18rmcc9h5m005.cloudfront.net/{accountId}/{unitListingId}/{mediaGroupId}/IMAGE_THUMBNAIL/{timestamp}",
        "status": "LOADED",
        "description": "FRONT_DRIVER_SIDE",
        "placeholderType": "FRONT_DRIVER_SIDE",
        "fileName": "IMG_5598.jpg",
        "mediaGroupId": "01KXK8ABJ64589KPX3X21YHT7F"
      }
    ],
    "allVideos": [],
    "photosByPlaceholderType": {
      "FRONT_DRIVER_SIDE": { "desktopUrl": "...", "thumbUrl": "..." },
      "REAR_DRIVER_SIDE":  { "desktopUrl": "...", "thumbUrl": "..." },
      "FRONT_PASSENGER_SIDE": { "desktopUrl": "...", "thumbUrl": "..." },
      "REAR_PASSENGER_SIDE":  { "desktopUrl": "...", "thumbUrl": "..." },
      "INTERIOR_DRIVER_SIDE": { "desktopUrl": "...", "thumbUrl": "..." },
      "INTERIOR_BACK_SEAT":   { "desktopUrl": "...", "thumbUrl": "..." },
      "INTERIOR_ENGINE":      { "desktopUrl": "...", "thumbUrl": "..." },
      "KEYS":                 { "desktopUrl": "...", "thumbUrl": "..." }
    }
  },

  "accountId": "01kxd6228kfsppbqfede4pnvck",
  "runNumber": 1,
  "maxRuns": 3,
  "runsLeft": 0,
  "updatedAt": "2026-07-15T16:16:02.000Z",
  "favoriteId": null,
  "pickUpStatus": null,
  "orderId": null
}
```

---

## Image URL Pattern

```
https://d18rmcc9h5m005.cloudfront.net/{accountId}/{unitListingId}/{mediaGroupId}/{FORMAT}/{timestamp}
```

Formats: `IMAGE_DESKTOP`, `IMAGE_MOBILE`, `IMAGE_THUMBNAIL`

**Photo types (placeholderType):**
`FRONT_DRIVER_SIDE`, `REAR_DRIVER_SIDE`, `FRONT_PASSENGER_SIDE`, `REAR_PASSENGER_SIDE`,
`INTERIOR_DRIVER_SIDE`, `INTERIOR_BACK_SEAT`, `INTERIOR_ENGINE`, `KEYS`

---

## ID Types

| Field | Example | Notes |
|---|---|---|
| `accountId` | `01kxd6228kfsppbqfede4pnvck` | Seller account (replaces `regionId`) |
| `unitId` | `01kxghfevz472fjv04vfqdqvzh` | The physical vehicle unit |
| `unitListingId` | `01kxghfew787b0gj73z3c9z2n0` | The listing (vehicle in an auction) |
| `auctionId` | `01kxk90naqckezda0drz9hng5f` | The auction event |
| `mediaGroupId` | `01KXK8ABJ64589KPX3X21YHT7F` | Photo group (uppercase ULID) |

All IDs are **ULIDs** — sortable by creation time.

---

## Bidding Status Values

`biddingStatus`: `PRE_BID`, `ACTIVE` (likely), `ENDED` (likely)  
`status` (listing): `PUBLISHED`, `SOLD` (likely for soldUnitListings)

---

## Live Bid Updates (SSE — TO BE EXPLORED)

Found in JS bundle (`Auctions-D4ohsonG.js`):
```
/sse/multi-bid-progress?multiBidId={id}
```
- Standard Server-Sent Events endpoint on `mp.autura.com`
- `multiBidId` likely comes from placing a bid — need to observe from devtools
- Format of SSE events: **unknown — needs capture**

Also found:
```
/zip-code?longitude={lon}&latitude={lat}
```
Used for location/nearest seller sorting.

---

## Routes Found in JS Bundle

| Route constant | Purpose |
|---|---|
| `PLACE_BID` | Single bid placement |
| `PLACE_MULTI_BID` | Multi-bid (auto-bid?) |
| `SAVED_SEARCH` | Save/update/delete search filters |
| `SIGNUP` / `SIGNIN` | User auth |

---

## DB Schema Mapping (old → new)

| Old field | New field | Notes |
|---|---|---|
| `auction_id` (e.g. `auction-109070`) | `auctionId` (ULID) | Schema change needed |
| `region_id` (e.g. `SBC-CA`) | `accountId` (ULID) | Replaces regionId |
| `seller_name` | `sellerInfo.sellerName` | Same concept |
| `closes_at` | `biddingInfo.auctionInfo.biddingEndUtc` | ISO timestamp |
| `current_bid` | `biddingInfo.winningBid.amountCents / 100` | Cents in new API |
| `bid_expiration` | `biddingInfo.auctionInfo.biddingEndUtc` | Same as closes_at |
| `reserve_price` | `biddingInfo.reservePrice` | |
| `images` | `media.allPhotos[].desktopUrl` (JSON array) | CloudFront URLs |
| `item_id` | `unitDetails.unitId` | |
| `item_key` | `unitDetails.unitListingId` | |
| `seller_id` | `accountId` | |

---

## Files Rewritten for New Platform

| File | Status | Notes |
|---|---|---|
| `autura_api.py` | Blank stub | Was: Firebase auth + Cloud Run client |
| `auction_discovery.py` | Blank stub | Was: region/auction discovery via Cloud Run |
| `auction_scraper.py` | Blank stub | Was: inventory scraper via items-http |
| `historical_harvester.py` | Blank stub | Was: completed auction harvester |
| `rtdb_listener.py` | Blank stub | Was: Firebase RTDB SSE listener |

Originals archived in `backend/legacy/`.

---

## Seller Address Data — Auth Requirement (investigated 2026-07-17)

### Summary

Structured city/state/address in `sellerDisclosure` is **server-side enriched only for authenticated sessions** where the user has a saved zip code in their profile. Anonymous requests never include these fields, regardless of URL params.

### Two separate systems

| Mechanism | Effect |
|---|---|
| `?zipCode=78202&distance=50` URL params | Client-side distance sorting/filtering only — reduces result count, does NOT add address fields |
| Session JWT with saved `userLocation.zipCode` | Server injects `city`, `state`, `address`, `zipcode` into every `sellerDisclosure` in the turbo-stream |

### sellerDisclosure structure (authenticated)

```json
"sellerDisclosure": {
  "sellerDisclosureId": "01kxj0qnf93h96ssx6j96pxp6a",
  "accountId": "01kxd60vmsnb3c2xcw38x1xe6m",
  "address": "422 Steves Ave, San Antonio, TX 78204",
  "locationName": "Txtow Corp",
  "city": "San Antonio",
  "state": "TX",
  "zipcode": "78204",
  "timezone": null
}
```

### sellerDisclosure structure (anonymous)

Same object — but `address`, `city`, `state`, `zipcode` fields are **completely absent** from the flat array (not null, not present at all).

### Anonymous vs authenticated feed

| | Anonymous | Authenticated |
|---|---|---|
| `perPage` | 12 | 48 |
| `city`/`state` in sellerDisclosure | absent | present |
| `sellerInfo` | null (buyer account sees null) | present with sellerName |
| `userLocation` in stream | absent | `{"zipCode": "78211"}` (saved profile zip) |

### What was tried

- `?zipCode=78202&distance=50` anonymous → no address fields (flat array len 753 vs 803, both `has_city=False`)
- Authenticated buyer request to `/auctions` → routes to MyAutura dashboard, `unitListings: []`
- `sellerInfo` is null for buyer accounts — sellers only see their own seller profile
- `/seller-disclosures/{id}` → 404
- `/sellers/{accountId}` profile page → 404 anonymous
- `.data` endpoints with auth → 202 Cloudflare challenge

The only working path: authenticated request to `/auctions` (not `.data`) with a `user-session` cookie belonging to an account that has a saved home zip code — this returns the full feed with all seller addresses.

---

## Seller Registry — /sellers.data

```
GET https://mp.autura.com/sellers.data?_routes=routes%2Fsellers
```

Returns a flat turbo-stream array (not HTML). Decodes to:
```json
{
  "routes/sellers": {
    "data": {
      "sellers": [
        { "accountId": "01kxd60vmsnb3c2xcw38x1xe6m", "accountName": "Txtow Corp" },
        ...
      ]
    }
  }
}
```

- Works **unauthenticated** — no session required
- Returns all registered sellers (name + accountId)
- Seller `accountId` values are **stable** — sellers register once and their ID never changes
- Used to backfill `seller_name` for any auction whose name is null

---

## Seller Location Strategy

Because seller IDs are stable (registered accounts, not ephemeral), city/state can be treated as permanent once populated:

1. **Normal scraper runs** operate anonymously — `seller_city`/`seller_state` will be null for new sellers
2. **Backfill runs** set `AUTURA_SESSION` env var to a valid `user-session` JWT and run the scraper — the authenticated feed includes city/state in every `sellerDisclosure`, which `upsert_auction` saves via `COALESCE` (never overwrites an existing value)
3. **Trigger condition**: run a backfill whenever `SELECT COUNT(*) FROM auctions WHERE seller_city IS NULL AND seller_state IS NULL` returns > 0 after a normal scrape
4. The session cookie expires ~1 hour after login; refresh from browser DevTools → Application → Cookies → `user-session`

---

## Current Implementation Status (as of 2026-07-17)

| File | Status |
|---|---|
| `autura_api.py` | Full — HTML fetch, turbo-stream decode, all feed/seller endpoints, optional `cookies` param |
| `auction_scraper.py` | Full — vehicles + auctions upsert, ended-auction harvester, `AUTURA_SESSION` env var support |
| `auction_discovery.py` | Full — auction upsert from listings, `sync_seller_names` from seller registry |
| `historical_harvester.py` | Full — harvests sold listings into `historical_sales` on auction end |
| `bid_listener.py` | Full — Ably SSE listener for live bid updates |
| `periodic_scraper.py` | Full — scheduled scraper runs |
