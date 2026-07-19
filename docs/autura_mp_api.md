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
    "sellerName": "Roberts Heavy Duty Towing",
    "locationName": "Roberts Heavy Duty Towing (757 E 7th St, Lexington, KY 40505)",
    "address": "757 E 7th St, Lexington, KY 40505",
    "city": "Lexington",
    "state": "KY",
    "zipcode": "40505",
    "timezone": null
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

## Next Steps

1. **Inventory scraper** (`auction_scraper.py`) — fetch all pages from `/auctions?page=N`, parse turbo-stream, write to DB
2. **Discovery** (`auction_discovery.py`) — derive from inventory feed (group by `auctionId`)
3. **Live bid listener** (`rtdb_listener.py`) — reverse engineer SSE endpoint from devtools
4. **Historical harvester** (`historical_harvester.py`) — needs `soldUnitListings` capture strategy
5. **DB schema** — `auction_id` and `region_id` column types/values will change
