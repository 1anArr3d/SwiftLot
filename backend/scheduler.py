from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from db import query, get_db
import auction_discovery as discovery
import auction_scraper as scraper
import inspection_scraper as inspection
import historical_harvester as harvester
import rtdb_listener as listener


def scheduled_discovery_and_scrape():
    print("[scheduler] Running scheduled discovery...")
    discovery.run_discovery()

    # Snapshot any completed auctions not already handled by the listener
    completed = query("""
        SELECT auction_id, region_id FROM auctions
        WHERE auction_status = 'completed'
          AND auction_id IN (SELECT DISTINCT auction_id FROM vehicles)
    """)
    for row in completed:
        listener.handle_auction_completed(row["auction_id"], row["region_id"])

    # Sync listener subscriptions after discovery (picks up newly published auctions)
    listener.sync_with_db()

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
        inspection.run_inspection_batch(vins)

    # Recover any completed auctions missed by the listener (e.g. server was down)
    # harvest_api() skips auctions already marked harvested=1
    harvester.harvest_api()

    print("[scheduler] ✓ Pipeline complete.")


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="America/Chicago")
    scheduler.add_job(
        scheduled_discovery_and_scrape,
        CronTrigger(hour="8,12,16,20,0", timezone="America/Chicago")
    )
    return scheduler
