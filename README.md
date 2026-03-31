# SwiftLot

A data pipeline and inventory browser for vehicle auctions on the Autura Marketplace. Discovers upcoming auctions, scrapes listed vehicles, and enriches each VIN with Texas state inspection odometer history — all on a automated schedule.

## Features

- Scheduled pipeline runs 3x daily (8am, 2pm, 10pm CT) — no manual intervention needed
- Discovers active TX auctions and tracks vehicle count changes
- Scrapes full vehicle details: VIN, year, make, model, color, condition, images
- Auto-runs TX state odometer history lookup per VIN after each scrape
- Skips redundant scrapes — only re-scrapes auctions when vehicle count changes
- Watchlist — save vehicles across auctions, stored as independent snapshots
- Saved auctions — bookmark auctions for quick access
- Historical average sale prices per year/make/model to avoid overbidding
- Filterable UI by year range, make, model, start status, engine, transmission
- Firebase Auth — user accounts with saved auctions and watchlist

## Stack

- **Backend** — Python, FastAPI, APScheduler, Playwright, SQLite
- **Frontend** — React 19, Vite, React Router

## Project Structure

```
backend/
  main.py           # FastAPI app entry point
  config.py         # Environment config (.env loader)
  db.py             # SQLite connection and query helpers
  models.py         # Pydantic response models
  state.py             # Shared in-memory job status tracking
  scheduler.py            # APScheduler — 3x daily pipeline
  auction_scraper.py      # Async Playwright — scrapes vehicles per auction
  auction_discovery.py    # Async Playwright — discovers active auctions by state
  inspection_scraper.py   # Sync Playwright — TX state odometer history per VIN
  routes.py            # All API route handlers

frontend/
  src/
    App.jsx         # Router and top nav
    api.js          # API base URL
    pages/
      AuctionsPage.jsx       # /auctions — auction card grid
      AuctionDetailPage.jsx  # /auctions/:id — vehicle table with filters
      WatchlistPage.jsx      # /watchlist — saved vehicles
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
| GET | `/api/v1/auctions` | All discovered auctions |
| GET | `/api/v1/auctions/:id` | Single auction |
| GET | `/api/v1/auctions/:id/vehicles` | Vehicles for a specific auction |
| GET | `/api/v1/watchlist` | Saved watchlist vehicles |
| POST | `/api/v1/watchlist/:vin` | Add vehicle to watchlist |
| DELETE | `/api/v1/watchlist/:vin` | Remove vehicle from watchlist |
| POST | `/api/v1/scrape/:id` | Manually trigger auction scrape |
| GET | `/api/v1/scrape/:id/status` | Scrape job status |
| POST | `/api/v1/discovery/run` | Run auction discovery |
| POST | `/api/v1/pipeline/run` | Run full pipeline (discovery + scrape + inspection) |

## Manually trigger the pipeline

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8000/api/v1/pipeline/run -Method POST
```

Or use the Swagger UI at `http://127.0.0.1:8000/docs`.

## Notes

- Inspection scraper uses `headless=False` to bypass Cloudflare Turnstile on mytxcar.org. On a headless Linux server, run with Xvfb: `Xvfb :99 -screen 0 1280x720x24 & export DISPLAY=:99`
- SQLite is used for local development. PostgreSQL migration is planned for deployment.
- Multi-user auth via Firebase Authentication. Users can save auctions and watchlist vehicles tied to their account.
