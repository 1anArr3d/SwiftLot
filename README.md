# SwiftLot

A self-running auction inventory pipeline for Texas salvage auctions. Automatically discovers upcoming auctions, scrapes listed vehicles, and enriches each VIN with Texas inspection odometer history. Built to replace manual research with a clean, searchable interface.

## Features

- Scheduled auction scraping 3x daily — no manual trigger needed
- Vehicle inventory with photos, specs, and odometer history
- TX state inspection history lookup per VIN (auto-runs after each scrape)
- Watchlist — save vehicles across auctions
- Filterable UI by year, make, model, condition, engine, transmission

## Stack

Python / FastAPI / APScheduler / Playwright / SQLite · React / Vite / React Router

## Setup

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

Run:

```bash
python main.py
```

API at `http://127.0.0.1:8000` — Swagger docs at `http://127.0.0.1:8000/docs`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App at `http://localhost:5173`

## Manually trigger the pipeline

POST to `/api/v1/pipeline/run` via Swagger or PowerShell to run discovery + scrape + inspection immediately without waiting for the scheduler.

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8000/api/v1/pipeline/run -Method POST
```

## Pages

- `/auctions` — All discovered auctions as cards
- `/auctions/:id` — Vehicles for a specific auction with filters and watchlist
- `/watchlist` — Saved vehicles across all auctions
