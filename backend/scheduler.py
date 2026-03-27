from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from db import query, get_db
from state import scrape_status
from routes import _run_scrape
import auction_discovery as discovery


def scheduled_discovery_and_scrape():
    print("[scheduler] Running scheduled discovery...")
    discovery.run_discovery()

    with get_db() as conn:
        conn.execute("""
            DELETE FROM vehicles WHERE auction_id IN (
                SELECT auction_id FROM auctions WHERE auction_status = 'completed'
            )
        """)

    rows = query("""
        SELECT auction_id, region_id FROM auctions
        WHERE auction_status != 'completed'
          AND (vehicles_listed IS NULL OR vehicles_listed > 0)
          AND (last_scraped_at IS NULL OR last_scraped_at < datetime('now', '-6 hours'))
    """)

    for row in rows:
        auction_id = row["auction_id"]
        if scrape_status.get(auction_id) != "running":
            print(f"[scheduler] Triggering scrape for {auction_id}")
            _run_scrape(auction_id, row["region_id"])

    print("[scheduler] ✓ Pipeline complete.")


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="America/Chicago")
    scheduler.add_job(
        scheduled_discovery_and_scrape,
        CronTrigger(hour="8,14,22", timezone="America/Chicago")
    )
    return scheduler
