# SwiftLot

A full-stack auction intelligence platform built to give buyers a real edge at salvage vehicle auctions. It reverse-engineers the Autura Marketplace API to discover active auctions nationwide, scrapes full vehicle listings in a single feed pass, and enriches every Texas vehicle with real odometer history pulled from the state inspection database.

Built for the first-time auction buyer who walks in blind and leaves with a bad deal, and turns that experience into something data-driven and repeatable.

Live at [swift-lot.com](https://swift-lot.com)

## Features

- **Bid history** — `GET /api/v1/vehicles/{vin}/bids` returns a lot's bids (amount and time only, cached 30s) from Autura's bid history; the lot certificate plots it.
- **Lot status** — reserve met/not met, pre-bid vs live phase and relist count come from the feed (`reserve_met`, `bidding_status`, `bidding_start`, `run_number`). `backend/tools/autura_findings_test.py` re-checks these and the fee formula against the live site; `backend/tools/autura_recon.py` records what Autura's site talks to (read-only).
- **Real-time bid streaming** — backend subscribes to Autura's Ably WebSocket feed for every lot that is live or within 3 hours of its live hour (where nearly all bidding happens), so `current_bid` is live on every page, not just open auctions. `NEW_BID` events carry the standing bid (`inventory.winningBid`, in cents), so updates reach the frontend with zero extra HTTP calls. The buyer's all-in price is worked out in the frontend from that bid with Autura's own fee formula (platform fee per lot/seller from `/sellers`, 3% card processing), stored per lot as `platform_fee_*`, `card_fee_rate` and `extra_fees`. Autura's Ably fails attaches past ~200 channels per connection, so lots are spread over a pool of connections, 150 channels each (fewer than the ≈7 needed to cover all ~1,000 lots)
- **Single-pass feed scrape** — one paginated crawl of `mp.autura.com/auctions.data` returns vehicle details, bidding info, and seller info together; no per-auction or per-vehicle follow-up calls needed
- **VIN-based lifecycle tracking** — a vehicle whose VIN drops out of the active feed has its final price read from Autura's bid history (kept when the reserve was met) and is removed outright, instead of being flagged and left to accumulate
- Discovers active auctions across all active sellers nationwide (no hardcoded state list)
- Solves Cloudflare Turnstile on the TX state inspection site via Playwright, then fetches up to 5 years of odometer readings per VIN via authenticated HTTP
- **Odometer rollback detection** — flags a vehicle when a newer inspection records more than 2,000 fewer miles than an older one, ignoring single out-of-line readings (inspector typos); shown as a "Possible rollback" badge
- Captures final sale prices from completed auctions and shows a **price range** (25th–75th percentile) per vehicle from the closest match with 5+ sales: same year/make/model, then ±2 years, then any year. Truncated makes (`CHEVROL` → `CHEVROLET`) and punctuation variants (`F - 150` → `F150`) are merged; trims are not
- Firebase Auth — per-user garage (saved vehicles)
- Garage snapshots preserve a vehicle's last-known data after it sells or is pulled, so saved vehicles are never lost
- Filterable UI by year range, make, model, start status, engine, drivetrain, odometer range

## Stack

- **Backend** — Python, FastAPI, Playwright, curl_cffi, PostgreSQL (Neon)
- **Frontend** — React 19, Vite, React Router
- **Auth** — Firebase Authentication
- **Realtime** — Ably WebSocket (Autura's feed) in, FastAPI SSE (`StreamingResponse`) out
- **Infra** — Hetzner (backend + systemd), Cloudflare Pages (frontend), Cloudflare DNS/CDN

## Project Structure

```
backend/
  main.py                      # FastAPI app entry point, startup scrape + scheduler threads
  config.py                    # Environment config (.env loader)
  db.py                        # PostgreSQL connection pool, schema init/migration
  models.py                    # Pydantic response models
  auth.py                      # Firebase ID token verification
  routes.py                    # All API route handlers (incl. SSE /stream endpoints)
  pricing.py                   # Price ranges + make/model name merging (in-memory, hourly refresh)
  test_pricing.py              # Self-check for pricing levels and name merging
  import_historical.py         # One-off: load historical_sales.csv into Postgres
  test_inspection.py           # Manual test: inspection batch against the DB, with timing
  test_rollback.py             # Self-check for rollback detection on real readings
  dump_inspection.py           # Dumps raw mytxcar pages; reproduces the shared-session bug
  survey_inspection.py         # Surveys ~100 VINs: page contents, timings, row-picking strategies
  scrapers/autura/
    autura_api.py              # HTTP client — login, turbo-stream decoding, feed/seller pagination
    feed_scraper.py            # Single-pass feed scrape: upserts vehicles + sellers,
                                #   detects ended vehicles (VIN diff), records final bids
    auction_listener.py        # Ably subscriptions (lots live or about to be, pooled connections), SSE broadcast,
                                #   AUCTION_UPDATED -> lot re-read, 5-min resync, 3-min live-lot refresh
    inspection_scraper.py       # Playwright session + HTTP batch fetch for TX odometer history

frontend/
  src/
    App.jsx                        # Routes
    api.js                         # API base URL, getJSON / authFetch (throw on non-2xx)
    AuthContext.jsx                # Firebase auth context
    hooks.js                       # fetchPriceRanges, usePageData, useLiveBids, useGarage
    pages/                         # Thin React pages: fetch data, then mount a Provenance page
      HomePage.jsx                 # /
      AuctionsPage.jsx             # /auctions — notices of sale with state/finder filters
      AuctionDetailPage.jsx        # /auctions/:id?vin= — lot list + three-copy certificate, live bids
      SearchPage.jsx               # /search — every lot, Ledger filters
      GaragePage.jsx               # /garage — saved vehicles (sign-in required)
      LoginPage.jsx, AboutPage.jsx, NotFoundPage.jsx
    provenance/                    # The "Provenance" certificate design (ported from design/provenance)
      holo.css, banknote.css, shell.css
      Nav.jsx, Printing.jsx        # Nav bar with gilded logo; loading / could-not-load card
      Provenance.jsx               # Hosts a page's mount(), routes in-app links, stops timers on unmount
      adapt.js                     # API rows -> page data (parsed photos, odometer readings, price range; text escaped)
      sl.js, engine.js, patterns.js, ledger.js, gallery.js, holo.js, homeCommon.js, life.js
      pages/                       # One mount() + scoped CSS per page
```

## Data model

"Auction" in the UI means a seller's sale event, but Autura's own `auction_id` is per-vehicle lot (each listing gets its own id and closing time, staggered seconds apart in a run). So:

- **`sellers`** — static-ish metadata per seller (name, city, state, region_id). No status or bidding fields.
- **`vehicles`** — one row per VIN, carrying its own `auction_id`, `current_bid`, `bid_expiration`. This is the source of truth for what's live; `vehicles_count` and `closes_at` shown per seller are computed live by aggregating this table, not stored separately.
- **`historical_sales`** — final sale prices, independent of whether the vehicle row still exists.
- **`odometer_history`** — TX inspection readings per VIN (`row_id` = `{vin}_{n}`, `_0` newest). `vehicles.last_recorded_odo` holds a display copy and `vehicles.odo_rollback` the rollback flag.
- **`garage`** — per-user saved vehicles; keeps its own copy of a vehicle's last-known fields so a saved vehicle still displays after it's gone from `vehicles`.

## Local Setup

### Prerequisites

- Python 3.10+
- Node.js 20+
- PostgreSQL

### Backend

```bash
cd backend
pip install -r requirements.txt
playwright install chromium
```

Create `backend/.env`:

```
DATABASE_URL=postgresql://swiftlot:swiftlot@localhost:5432/swiftlot
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:5174
FIREBASE_CREDENTIALS=swiftlot-firebase-adminsdk-fbsvc-d64100172c.json
AUTURA_EMAIL=your@email.com
AUTURA_PASSWORD=yourpassword
ADMIN_UID=your_firebase_uid
```

Start the server:

```bash
python main.py
```

- API: `http://127.0.0.1:8000`
- Swagger docs: `http://127.0.0.1:8000/docs`
- Hot reload is enabled — no restart needed on code changes
- On startup it runs a full feed scrape in the background, then rescrapes every 30 minutes (new lots, pre-bid changes) and re-reads lots in their live hour every 3 minutes (reserve, phase, end time). The sale price of each ended lot comes from its bid history. Autura's `AUCTION_UPDATED` ping re-reads that one lot, so sold or pulled lots leave within seconds and their sale is recorded straight away. Ably subscriptions cover lots that are live or within 3 hours of their live hour, plus any lot someone has open

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App at `http://localhost:5173`

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|--------------|
| GET | `/api/v1/auctions` | All sellers with at least one live vehicle |
| GET | `/api/v1/auctions/:region_id` | Single seller summary |
| GET | `/api/v1/auctions/:region_id/vehicles` | Live vehicles for a seller |
| GET | `/api/v1/vehicles` | Search live inventory (make/model/year/region filters) |
| POST | `/api/v1/historical/stats/batch` | Price ranges for multiple make/model/year combos |
| GET | `/api/v1/garage` | Saved vehicles (auth required) |
| POST | `/api/v1/garage/:vin` | Add vehicle to garage (auth required) |
| DELETE | `/api/v1/garage/:vin` | Remove vehicle from garage (auth required) |
| GET | `/api/v1/stream/multi?auctions=id1,id2` | Single SSE connection for multiple vehicle lots (garage/detail pages) |
| GET | `/api/v1/health` | Ably connections (channels + state each), subscribed lot count, active SSE clients |

## Deployment

**Backend** runs on Hetzner at `/opt/swiftlot/`. The systemd service starts uvicorn with `xvfb-run --auto-servernum` so the inspection scraper's headed Playwright session works on a headless Linux server.

**Frontend** is deployed via Cloudflare Pages, connected directly to the GitHub repo. Pushing to `main` triggers an automatic build and deploy — no server involvement needed.

## Notes

- Inspection scraper uses Playwright with `headless=False` to bypass Cloudflare Turnstile on mytxcar.org, then reuses the acquired session for all subsequent VIN lookups via HTTP
- **Inspection lookups run on one worker, on purpose.** mytxcar is ASP.NET WebForms: the server keeps each session's last search, and the detail request only says "row N of my last search". With 8 threads sharing one session, a lookup's detail request was answered from another thread's search, saving other cars' mileage. `dump_inspection.py` reproduced it (6 of 8 VINs wrong in parallel, 0 sequentially). Lookups are now sequential (~0.5 s per VIN), every detail page is checked for the searched VIN before saving, and a VIN's old rows are cleared on each save
- "Safety Only" inspection pages label the reading `Odometer Reading` rather than `Odometer`; 97% of them have one, so they are not skipped
- The systemd service uses `xvfb-run --auto-servernum` — no manual Xvfb setup needed
- Ably's `auth_url` requires the same session cookies as the scraping client (Autura gates `/ably-auth`), so the realtime client forwards them explicitly — a fresh/unauthenticated request to `auth_url` gets a 403
