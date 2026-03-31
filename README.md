# SwiftLot

A full-stack auction inventory platform for vehicle auctions on the Autura Marketplace. Reverse-engineers the marketplace API to discover active auctions, fetches vehicle listings, and enriches each VIN with Texas state inspection odometer history — all on an automated schedule.

Live at [swift-lot.com](https://swift-lot.com)

## Features

- Scheduled pipeline runs 3x daily (8am, 2pm, 10pm CT) — no manual intervention needed
- Discovers active auctions across 18 regions nationwide (400+ auctions)
- Fetches full vehicle details per auction: VIN, year, make, model, color, condition, images
- Solves Cloudflare Turnstile on the TX state inspection site via Playwright, then batch-fetches odometer history for every VIN via authenticated HTTP
- Skips redundant scrapes — only re-scrapes auctions when vehicle count changes
- Historical average sale prices per year/make/model to avoid overbidding
- Firebase Auth — per-user watchlist (saved vehicles) and saved auctions
- Filterable UI by year range, make, model, start status, engine, drivetrain

## Stack

- **Backend** — Python, FastAPI, APScheduler, Playwright, curl_cffi, SQLite
- **Frontend** — React 19, Vite, React Router
- **Auth** — Firebase Authentication
- **Infra** — Hetzner (backend + nginx), Cloudflare (DNS + CDN)

## Project Structure

```
backend/
  main.py               # FastAPI app entry point
  config.py             # Environment config (.env loader)
  db.py                 # SQLite connection and query helpers
  models.py             # Pydantic response models
  state.py              # Shared in-memory job status tracking
  scheduler.py          # APScheduler — 3x daily pipeline
  autura_api.py         # Autura Marketplace API client
  auction_scraper.py    # Fetches vehicles per auction via API
  auction_discovery.py  # Discovers active auctions across all regions via API
  inspection_scraper.py # Playwright session + HTTP batch fetch for TX odometer history
  routes.py             # All API route handlers

frontend/
  src/
    App.jsx                        # Router and top nav
    api.js                         # API base URL (env-aware)
    AuthContext.jsx                 # Firebase auth context
    pages/
      AuctionsPage.jsx             # /auctions — auction card grid grouped by state
      AuctionDetailPage.jsx        # /auctions/:id — vehicle table with filters
      WatchlistPage.jsx            # /watchlist — saved vehicles
      SavedAuctionsPage.jsx        # /saved — saved auctions
      LoginPage.jsx                # /login
    components/
      FilterSection.jsx
      ChecklistFilter.jsx
      ImageCycler.jsx
```

## Local Setup

### Prerequisites

- Python 3.10+
- Node.js 18+

### Backend

```bash
cd backend
pip install -r requirements.txt
playwright install chromium
```

Create `backend/.env`:

```
DB_PATH=swiftlot.db
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:5174
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
| GET | `/api/v1/watchlist` | Saved watchlist vehicles (auth required) |
| POST | `/api/v1/watchlist/:vin` | Add vehicle to watchlist (auth required) |
| DELETE | `/api/v1/watchlist/:vin` | Remove vehicle from watchlist (auth required) |
| GET | `/api/v1/saved-auctions` | Saved auctions (auth required) |
| POST | `/api/v1/saved-auctions/:id` | Save an auction (auth required) |
| DELETE | `/api/v1/saved-auctions/:id` | Remove saved auction (auth required) |
| POST | `/api/v1/pipeline/run` | Run full pipeline (admin only) |
| POST | `/api/v1/discovery/run` | Run auction discovery (admin only) |
| POST | `/api/v1/scrape/:id` | Manually trigger auction scrape (admin only) |

## Deployment

**Backend** runs on Hetzner at `/opt/swiftlot/`. The systemd service starts uvicorn with `xvfb-run --auto-servernum` so the inspection scraper's headed Playwright session works on a headless Linux server.

**Frontend** is built with `npm run build` and served via nginx from `/opt/swiftlot/frontend/dist`. To deploy frontend changes, push to `main` then pull and rebuild on the server.

## Notes

- Inspection scraper uses Playwright with `headless=False` to bypass Cloudflare Turnstile on mytxcar.org, then reuses the acquired session for all subsequent VIN lookups via HTTP
- The systemd service uses `xvfb-run --auto-servernum` — no manual Xvfb setup needed for scheduled runs
