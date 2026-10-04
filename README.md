# SwiftLot

A full-stack auction intelligence platform built to give buyers a real edge at salvage vehicle auctions. It reverse-engineers the Autura Marketplace API to discover active auctions nationwide, scrapes full vehicle listings in a single feed pass, and enriches every Texas vehicle with real odometer history pulled from the state inspection database.

Built for the first-time auction buyer who walks in blind and leaves with a bad deal, and turns that experience into something data-driven and repeatable.

Live at [swift-lot.com](https://swift-lot.com)

## Features

- **Real-time bid streaming** — backend subscribes to Autura's Ably WebSocket feed per vehicle lot; `NEW_BID` events carry the bid amount directly, so updates reach the frontend with zero extra HTTP calls. Subscriptions are lazy (subscribe only while someone's actually watching, unsubscribe when the last viewer leaves) since Autura's Ably connection caps out around 200 concurrent channels
- **Single-pass feed scrape** — one paginated crawl of `mp.autura.com/auctions.data` returns vehicle details, bidding info, and seller info together; no per-auction or per-vehicle follow-up calls needed
- **VIN-based lifecycle tracking** — a vehicle whose VIN drops out of the active feed is harvested (final sale price captured) and removed outright, instead of being flagged and left to accumulate
- Discovers active auctions across all active sellers nationwide (no hardcoded state list)
- Solves Cloudflare Turnstile on the TX state inspection site via Playwright, then batch-fetches odometer history for every VIN via authenticated HTTP
- Captures final sale prices from completed auctions and surfaces historical average sale prices per year/make/model
- Firebase Auth — per-user garage (saved vehicles) and saved auctions (saved sellers)
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
  import_historical.py         # One-off: load historical_sales.csv into Postgres
  test_inspection.py           # Manual test script for the inspection scraper
  scrapers/autura/
    autura_api.py              # HTTP client — login, turbo-stream decoding, feed/seller pagination
    feed_scraper.py            # Single-pass feed scrape: upserts vehicles + sellers,
                                #   detects ended vehicles (VIN diff), harvests sold prices
    auction_listener.py        # Ably subscriptions (lazy, per-vehicle), SSE broadcast,
                                #   watchdog resync against connected clients
    inspection_scraper.py       # Playwright session + HTTP batch fetch for TX odometer history

frontend/
  src/
    App.jsx                        # Router and top nav
    api.js                         # API base URL (env-aware)
    AuthContext.jsx                 # Firebase auth context
    pages/
      HomePage.jsx                 # / — rotating vehicle carousel
      AuctionsPage.jsx             # /auctions — seller card grid
      AuctionDetailPage.jsx        # /auctions/:id — vehicle table with live bid updates
      SearchPage.jsx               # /search — full live inventory with filters
      WatchlistPage.jsx            # /watchlist — saved vehicles with live bid streaming
      SavedAuctionsPage.jsx        # /saved — saved sellers
      LoginPage.jsx                # /login
      AboutPage.jsx                # /about
    components/
      FilterSection.jsx
      ChecklistFilter.jsx
      ImageCycler.jsx
```

## Data model

"Auction" in the UI means a seller's sale event, but Autura's own `auction_id` is per-vehicle lot (each listing gets its own id and closing time, staggered seconds apart in a run). So:

- **`sellers`** — static-ish metadata per seller (name, city, state, region_id). No status or bidding fields.
- **`vehicles`** — one row per VIN, carrying its own `auction_id`, `current_bid`, `bid_expiration`. This is the source of truth for what's live; `vehicles_count` and `closes_at` shown per seller are computed live by aggregating this table, not stored separately.
- **`historical_sales`** — final sale prices, independent of whether the vehicle row still exists.
- **`garage`** / **`saved_auctions`** — per-user saved vehicles/sellers; garage keeps its own copy of a vehicle's last-known fields so a saved vehicle still displays after it's gone from `vehicles`.

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
- On startup it runs a full feed scrape in the background, plus a periodic rescrape every 2 hours and a weekly sold-listing sweep

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
| GET | `/api/v1/vehicles/:vin/history` | Sale history for a VIN |
| GET | `/api/v1/vehicles/:vin/odometer` | Odometer history for a VIN |
| GET | `/api/v1/historical/stats` | Avg sale price by make/model/year |
| POST | `/api/v1/historical/stats/batch` | Avg sale price for multiple make/model/year combos |
| GET | `/api/v1/historical/search` | Search historical sales |
| GET | `/api/v1/garage` | Saved vehicles (auth required) |
| POST | `/api/v1/garage/:vin` | Add vehicle to garage (auth required) |
| DELETE | `/api/v1/garage/:vin` | Remove vehicle from garage (auth required) |
| GET | `/api/v1/saved-auctions` | Saved sellers (auth required) |
| GET | `/api/v1/saved-auctions/check/:region_id` | Whether a seller is saved (auth required) |
| POST | `/api/v1/saved-auctions/:region_id` | Save a seller (auth required) |
| DELETE | `/api/v1/saved-auctions/:region_id` | Remove a saved seller (auth required) |
| GET | `/api/v1/stream/auction/:auction_id` | SSE stream of live bid updates for one vehicle lot |
| GET | `/api/v1/stream/multi?auctions=id1,id2` | Single SSE connection for multiple vehicle lots (watchlist/detail pages) |
| GET | `/api/v1/health` | Ably connection state, active SSE clients, live subscriptions |

## Deployment

**Backend** runs on Hetzner at `/opt/swiftlot/`. The systemd service starts uvicorn with `xvfb-run --auto-servernum` so the inspection scraper's headed Playwright session works on a headless Linux server.

**Frontend** is deployed via Cloudflare Pages, connected directly to the GitHub repo. Pushing to `main` triggers an automatic build and deploy — no server involvement needed.

## Notes

- Inspection scraper uses Playwright with `headless=False` to bypass Cloudflare Turnstile on mytxcar.org, then reuses the acquired session for all subsequent VIN lookups via HTTP
- The systemd service uses `xvfb-run --auto-servernum` — no manual Xvfb setup needed
- Ably's `auth_url` requires the same session cookies as the scraping client (Autura gates `/ably-auth`), so the realtime client forwards them explicitly — a fresh/unauthenticated request to `auth_url` gets a 403
- Sold-listing harvest runs sequentially, deliberately not parallelized — Neon's serverless Postgres drops connections under a burst of concurrent new ones
