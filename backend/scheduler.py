import threading
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from db import query, get_db
from state import scrape_status
from routes import _run_scrape
import auction_discovery as discovery
import auction_scraper as scraper
import inspection_scraper as inspection
import historical_harvester as harvester


def scheduled_discovery_and_scrape():
    print("[scheduler] Running scheduled discovery...")
    discovery.run_discovery()

    with get_db() as conn:
        conn.execute("""
            DELETE FROM vehicles WHERE auction_id IN (
                SELECT auction_id FROM auctions WHERE auction_status = 'completed'
            )
        """)

    print("[scheduler] Scraping all published vehicles...")
    counts = scraper.scrape_all_published()

    with get_db() as conn:
        for auction_id, count in counts.items():
            conn.execute(
                "UPDATE auctions SET vehicles_listed = ?, last_scraped_at = datetime('now') WHERE auction_id = ?",
                (count, auction_id)
            )
        # Zero out auctions not seen in this scrape
        if counts:
            placeholders = ",".join("?" * len(counts))
            conn.execute(
                f"UPDATE auctions SET vehicles_listed = 0 WHERE auction_id NOT IN ({placeholders}) AND auction_status != 'completed'",
                list(counts.keys())
            )

    # Fire TX inspections for vehicles without odometer data
    rows = query("""
        SELECT vin FROM vehicles
        WHERE region_id LIKE '%-TX'
          AND last_recorded_odo IS NULL
    """)
    vins = [row["vin"] for row in rows]
    if vins:
        print(f"[scheduler] Firing inspection for {len(vins)} TX VINs")
        threading.Thread(target=inspection.run_inspection_batch, args=(vins,), daemon=True).start()

    # Harvest any completed auctions that haven't been captured yet
    unharvested = query("""
        SELECT auction_id, region_id FROM auctions
        WHERE auction_status = 'completed' AND (harvested IS NULL OR harvested = 0)
    """)
    for row in unharvested:
        threading.Thread(
            target=harvester.harvest_auction,
            args=(row["region_id"], row["auction_id"]),
            daemon=True
        ).start()

    print("[scheduler] ✓ Pipeline complete.")


def scheduled_live_refresh():
    rows = query("""
        SELECT auction_id, region_id FROM auctions
        WHERE auction_status = 'live-auction'
          AND (last_scraped_at IS NULL OR last_scraped_at < datetime('now', '-15 minutes'))
    """)
    for row in rows:
        auction_id = row["auction_id"]
        if scrape_status.get(auction_id) != "running":
            print(f"[live-refresh] Scraping {auction_id}")
            _run_scrape(auction_id, row["region_id"])


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="America/Chicago")
    scheduler.add_job(
        scheduled_discovery_and_scrape,
        CronTrigger(hour="8,14,22", timezone="America/Chicago")
    )
    scheduler.add_job(
        scheduled_live_refresh,
        IntervalTrigger(minutes=15)
    )
    return scheduler
