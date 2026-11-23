# SwiftLot

SwiftLot helps first-time buyers at tow-yard and salvage auctions avoid overpaying. For every live lot on the Autura Marketplace it shows what similar cars actually sold for, what you'd really pay once fees are added, and, for Texas cars, whether the odometer was rolled back.

Live at [swift-lot.com](https://swift-lot.com)

![Home page: the best-value lot shown as a certificate of lot value](docs/screenshots/home.jpg)

## What it does

**Is it a good price?** Every lot is compared with final sale prices of the same year, make and model. The lot shows a typical price range (25th to 75th percentile). If there are fewer than 5 matching sales, it widens to ±2 years, then to any year. The green, blue or red seal on each photo gives the verdict at a glance.

**What will I actually pay?** "If you win now" is the all-in price at the next bid Autura will accept: the bid, plus the platform fee (12.5% unless the seller sets their own rate), plus 3% card processing. The fee formula and the bid increments come from Autura's own frontend code, and the total matches Autura's checkout to the cent. A dropdown breaks the total down the way Autura does.

![Lot certificate with the fee breakdown open](docs/screenshots/auction-fees.jpg)

**Was the odometer rolled back?** For Texas cars, SwiftLot pulls up to 5 years of state inspection readings for the VIN. A drop of more than 2,000 miles flags a possible rollback. A single reading that's out of line with its neighbours is treated as an inspector typo, so it doesn't flag an honest car. If the seller lists a mileage on Autura, it's added to the history, dated the day we first saw it.

![Odometer certificate: Texas inspection readings plus the seller-listed mileage](docs/screenshots/auction-odometer.jpg)

**Live bids, no refresh.** An open auction page updates bids, all-in prices and countdowns as they happen. Lots that sell drop off within seconds. Each lot also shows its bid history as a chart, plus plain-language notes: reserve not met, pre-bidding or live, relisted for the Nth time.

**Every lot in one place.** Search and filter all ~600 live lots by value, make, model, year, price, odometer and condition. Browse sales by state, or by how soon they close. Signed-in users can save cars to a garage, and a saved car stays visible after it sells.

<p>
  <img src="docs/screenshots/auctions.jpg" alt="Notices of sale: every live tow-yard sale, filterable by state" width="49%">
  <img src="docs/screenshots/search.jpg" alt="Search every lot with filters and value seals" width="49%">
</p>

<p align="center"><img src="docs/screenshots/mobile.jpg" alt="Lot certificate on a phone" width="300"></p>

## How it works

```
Autura feed (every 30 min) ─┐
Autura Ably (live bids)  ───┼─▶ FastAPI + Postgres ──REST + SSE──▶ React site (Cloudflare Pages)
TX inspection site       ───┘
```

- **Feed scrape:** one paginated crawl of `mp.autura.com/auctions.data` returns vehicle, bidding and seller details together, with no per-lot follow-up calls. It runs on startup and every 30 minutes. Lots in their live hour are re-read every 3 minutes.
- **Live bids:** the backend subscribes to Autura's Ably channels for lots that are live, or within 3 hours of their live hour, plus any lot someone has open. Autura's Ably refuses more than about 200 channels per connection, so channels are spread over a pool of connections, 150 each. Each `NEW_BID` carries the standing bid. The backend forwards a snapshot to open pages over Server-Sent Events.
- **Ended lots:** Autura's `AUCTION_UPDATED` ping makes the backend re-read that lot. Once the lot page is gone, the final price is read from Autura's bid history (which outlives the listing) into `historical_sales`, and the lot is removed. The 30-minute scrape catches anything the ping missed.
- **Fees:** each lot stores its seller's platform fee settings (`platform_fee_rate/min/max`), the card rate and any extra fees. The frontend computes the all-in price from the live bid, so it never goes stale.
- **Odometer:** Playwright solves Cloudflare Turnstile on the Texas inspection site once. Lookups then reuse that session over plain HTTP, one VIN at a time (see Notes).

## Stack

- **Backend:** Python, FastAPI, PostgreSQL (Neon), Playwright, curl_cffi, Ably
- **Frontend:** React 19, Vite, React Router, with hand-written HTML/CSS for the certificate design
- **Auth:** Firebase Authentication
- **Infra:** Hetzner (backend, systemd), Cloudflare Pages (frontend), Cloudflare DNS/CDN

## Project structure

```
backend/
  main.py                    # App entry: startup scrape, background threads (30-min scrape, 3-min live refresh, Ably watchdog)
  routes.py                  # All API routes, incl. the SSE stream and bid history
  db.py                      # Connection pool, schema + migrations (run on startup)
  models.py, auth.py, config.py
  pricing.py                 # Price ranges and make/model name merging (CHEVROL → Chevrolet, F - 150 → F150)
  scrapers/autura/
    autura_api.py            # Autura client: login, turbo-stream decoding, feed, sellers, lot, bid history
    feed_scraper.py          # Feed upsert, fee settings, ended lots, final price from bid history
    auction_listener.py      # Ably connection pool, SSE broadcast, AUCTION_UPDATED handling
    inspection_scraper.py    # Texas inspection odometer history and rollback check
  tools/
    autura_findings_test.py  # Re-checks the fee formula, feed fields and Ably events against the live site
    autura_recon.py          # Headless browser that records what Autura's site calls (read-only, never bids)
  test_*.py                  # Self-checks: listener, pricing, rollback, inspection

frontend/src/
  pages/                     # Thin React pages: fetch data, then mount a certificate page
  provenance/                # The certificate design: shared CSS, nav, gallery, filters, fee math (sl.js)
    adapt.js                 # API rows → page data (photo sizes, odometer history, escaping)
    pages/                   # One mount() + scoped CSS per page
  hooks.js                   # Shared data loading, live-bid stream, garage

docs/                        # Autura API notes, architecture notes, screenshots
```

## Data model

In the UI an "auction" is a seller's sale event. Autura's own `auction_id` is per lot: each car gets its own id and closing time.

- **`vehicles`:** one row per live VIN, with its bid, closing time, phase, reserve status, fee settings, photos, and odometer fields. `last_recorded_odo` holds the Texas history and `autura_odo`/`autura_odo_at` the seller-listed mileage. A row is deleted when the lot ends, so this table is exactly what's live.
- **`sellers`:** name, city and state per seller.
- **`historical_sales`:** final sale prices, which drive the price ranges.
- **`odometer_history`:** Texas inspection readings per VIN.
- **`garage`:** each user's saved cars, with a copy of the car's last-known details so it still shows after the lot ends.

## Local setup

Prerequisites: Python 3.10+, Node.js 20+, PostgreSQL.

```bash
cd backend
pip install -r requirements.txt
playwright install chromium
```

Create `backend/.env`:

```
DATABASE_URL=postgresql://swiftlot:swiftlot@localhost:5432/swiftlot
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:5174
FIREBASE_CREDENTIALS=your-firebase-adminsdk.json
AUTURA_EMAIL=your@email.com
AUTURA_PASSWORD=yourpassword
ADMIN_UID=your_firebase_uid
```

```bash
python main.py          # API at http://127.0.0.1:8000, docs at /docs, hot reload on
```

The schema is created or migrated on startup, followed by a full feed scrape in the background.

```bash
cd frontend
npm install
npm run dev             # http://localhost:5173 (talks to 127.0.0.1:8000 in dev)
```

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/auctions` | Sellers with at least one live lot |
| GET | `/api/v1/auctions/:region_id` | One seller's summary |
| GET | `/api/v1/auctions/:region_id/vehicles` | That seller's live lots |
| GET | `/api/v1/vehicles` | All live lots (make/model/year/region filters) |
| GET | `/api/v1/vehicles/:vin/bids` | Bid history: amount and time only, no bidder details (cached 30s) |
| GET | `/api/v1/historical/stats/live` | Price ranges for every live make/model/year (served from memory, refreshed every 5 min) |
| POST | `/api/v1/historical/stats/batch` | Price ranges for a list of make/model/year combos |
| GET / POST / DELETE | `/api/v1/garage[/:vin]` | Saved cars (sign-in required) |
| GET | `/api/v1/stream/multi?auctions=id1,id2` | SSE stream of live bid snapshots and "ended" events |
| GET | `/api/v1/health` | Ably connections, subscribed lot count, open streams |

## Deployment

- **Frontend:** Cloudflare Pages builds and deploys on every push to `main`.
- **Backend:** runs on Hetzner at `/opt/swiftlot/` as the `swiftlot` systemd service. That's uvicorn on port 8002 under `xvfb-run`, so the inspection scraper's headed Playwright works on a headless server. To deploy:

```bash
cd /opt/swiftlot && git fetch && git reset --hard origin/main && systemctl restart swiftlot
```

## Notes

- **Inspection lookups run one at a time, on purpose.** The Texas inspection site keeps each session's last search on the server, and its detail page only asks for "row N of my last search". In parallel, lookups got answers from each other's searches and saved the wrong car's mileage: 6 of 8 VINs wrong, reproduced by `dump_inspection.py`. Lookups are now sequential (about 0.5 s per VIN), and every page is checked for the searched VIN before saving.
- **Autura gates its Ably tokens behind our login,** so the realtime client sends the scraper's session cookies to `/ably-auth`.
- **Photos come from Autura's CDN in three sizes:** 320 px, 1280 px and 1920 px. Lists use the smallest, cards and the gallery the middle size, and only the full-screen viewer loads full size.
- **Bidder privacy:** Autura's bid payloads include bidder names and emails. SwiftLot never stores or forwards them; only amounts and times leave the backend.
