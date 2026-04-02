import threading
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
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
        t = threading.Thread(target=inspection.run_inspection_batch, args=(vins,))
        t.start()
        t.join()

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
    # Skip auctions already covered by the RTDB listener (they get real-time updates)
    covered = listener.active_auction_ids()
    print(f"[live-refresh] Refreshing bids (listener covers {len(covered)} auctions)...")
    counts = scraper.scrape_all_published(skip_auction_ids=covered)
    with get_db() as conn:
        for auction_id, count in counts.items():
            conn.execute(
                "UPDATE auctions SET vehicles_listed = ?, last_scraped_at = datetime('now') WHERE auction_id = ?",
                (count, auction_id)
            )
    print(f"[live-refresh] Done — {sum(counts.values())} vehicles updated")


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="America/Chicago")
    scheduler.add_job(
        scheduled_discovery_and_scrape,
        CronTrigger(hour="8,12,16,20,0", timezone="America/Chicago")
    )
    scheduler.add_job(
        scheduled_live_refresh,
        IntervalTrigger(minutes=15)
    )
    return scheduler
