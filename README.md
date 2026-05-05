# SwiftLot

A full-stack auction intelligence platform built to give buyers a real edge at salvage vehicle auctions. It reverse-engineers the Autura Marketplace API to automatically discover active auctions across all regions nationwide, scrapes full vehicle listings, and enriches every Texas vehicle with real odometer history pulled from the state inspection database. The entire pipeline is event-driven — new auctions and vehicles are detected and scraped the moment they appear in Firebase.

Built for the first-time auction buyer who walks in blind and leaves with a bad deal, and turns that experience into something data-driven and repeatable.

Live at [swift-lot.com](https://swift-lot.com)

## Features

- **Real-time bid streaming** — backend subscribes to Firebase RTDB via SSE at the region level (2 threads per region); bid updates propagate to the frontend the instant they happen, no polling
- **Instant auction lifecycle detection** — detects `ended: true` from Firebase the moment an auction closes and runs harvest immediately, capturing final sale prices within seconds
- **LIVE badge** — auctions show a live indicator when a vehicle is actively on the block
- **Fully event-driven pipeline** — new auctions detected via RTDB stream trigger discovery + scrape automatically; new vehicles added mid-auction trigger a rescrape; zero-vehicle auctions are retried every 15 minutes via a DB-column-based retry queue
- Discovers active auctions across all active regions nationwide (no hardcoded state list)
- Fetches full vehicle details: VIN, year, make, model, color, condition, images, current bid
- Solves Cloudflare Turnstile on the TX state inspection site via Playwright, then batch-fetches odometer history for every VIN via authenticated HTTP
- Captures final sale prices from completed auctions and surfaces historical average sale prices per year/make/model
- Firebase Auth — per-user garage (saved vehicles with auction snapshots) and saved auctions
- Garage snapshots preserve final bid prices after an auction closes so saved vehicles are never lost
- Filterable UI by year range, make, model, start status, engine, drivetrain, odometer range

## Stack

- **Backend** — Python, FastAPI, Playwright, curl_cffi, PostgreSQL
- **Frontend** — React 19, Vite, React Router
- **Auth** — Firebase Authentication
- **Realtime** — Firebase RTDB (SSE), FastAPI StreamingResponse
- **Infra** — Hetzner (backend + nginx), Cloudflare Pages (frontend), Cloudflare DNS/CDN

## Project Structure

```
backend/
  main.py               # FastAPI app entry point
  config.py             # Environment config (.env loader)
  db.py                 # PostgreSQL connection pool and query helpers
  models.py             # Pydantic response models
  state.py              # Shared in-memory job status tracking (admin endpoints)
  autura_api.py         # Autura Marketplace API client (auth + Cloud Run calls)
  auction_scraper.py    # Fetches vehicles per auction via API
  auction_discovery.py  # Discovers active auctions across all regions via API
  inspection_scraper.py # Playwright session + HTTP batch fetch for TX odometer history
  historical_harvester.py # Captures final sale prices from completed auctions
  routes.py             # All API route handlers (includes SSE /stream/auction/:id)
  rtdb_listener.py      # Firebase RTDB SSE listener — real-time bid + lifecycle updates,
                        #   event-driven scrape triggers, watchdog, retry checker

frontend/
  src/
    App.jsx                        # Router and top nav
    api.js                         # API base URL (env-aware)
    AuthContext.jsx                 # Firebase auth context
    pages/
      AuctionsPage.jsx             # /auctions — auction card grid grouped by state (LIVE badge)
      AuctionDetailPage.jsx        # /auctions/:id — vehicle table with live bid updates
      WatchlistPage.jsx            # /watchlist — saved vehicles with live bid streaming
      SavedAuctionsPage.jsx        # /saved — saved auctions
      LoginPage.jsx                # /login
      AboutPage.jsx                # /about
    components/
      FilterSection.jsx
      ChecklistFilter.jsx
      ImageCycler.jsx
```

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

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App at `http://localhost:5173`

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/auctions` | All active auctions |
| GET | `/api/v1/auctions/:id` | Single auction |
| GET | `/api/v1/auctions/:id/vehicles` | Vehicles for a specific auction |
| GET | `/api/v1/historical/stats` | Avg sale price by make/model/year |
| GET | `/api/v1/historical/search` | Search historical sales |
| GET | `/api/v1/vehicles/:vin/history` | Sale history for a VIN |
| GET | `/api/v1/vehicles/:vin/odometer` | Odometer history for a VIN |
| GET | `/api/v1/garage` | Saved vehicles (auth required) |
| POST | `/api/v1/garage/:vin` | Add vehicle to garage (auth required) |
| DELETE | `/api/v1/garage/:vin` | Remove vehicle from garage (auth required) |
| GET | `/api/v1/saved-auctions` | Saved auctions (auth required) |
| POST | `/api/v1/saved-auctions/:id` | Save an auction (auth required) |
| DELETE | `/api/v1/saved-auctions/:id` | Remove saved auction (auth required) |
| GET | `/api/v1/stream/auction/:id` | SSE stream of live bid updates for an auction |
| GET | `/api/v1/health` | Listener health — active subscriptions and dead threads |
| POST | `/api/v1/discovery/run` | Run auction discovery (admin only) |
| POST | `/api/v1/scrape/:id` | Manually trigger auction scrape (admin only) |
| POST | `/api/v1/inspectionscrape/:vin` | Manually trigger TX inspection for a VIN (admin only) |
| POST | `/api/v1/pipeline/run` | Run full discovery pass (admin only) |

## Deployment

**Backend** runs on Hetzner at `/opt/swiftlot/`. The systemd service starts uvicorn with `xvfb-run --auto-servernum` so the inspection scraper's headed Playwright session works on a headless Linux server.

**Frontend** is deployed via Cloudflare Pages, connected directly to the GitHub repo. Pushing to `main` triggers an automatic build and deploy — no server involvement needed.

## Notes

- Inspection scraper uses Playwright with `headless=False` to bypass Cloudflare Turnstile on mytxcar.org, then reuses the acquired session for all subsequent VIN lookups via HTTP
- The systemd service uses `xvfb-run --auto-servernum` — no manual Xvfb setup needed
- RTDB listener subscribes at the region level (2 threads per region) rather than per-auction, keeping thread count bounded regardless of how many auctions are active
