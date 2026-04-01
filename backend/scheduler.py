import threading
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from db import query, get_db
import auction_discovery as discovery
import auction_scraper as scraper
import inspection_scraper as inspection
import historical_harvester as harvester


def scheduled_discovery_and_scrape():
    print("[scheduler] Running scheduled discovery...")
    discovery.run_discovery()

    with get_db() as conn:
        # Update final bid for vehicles already saved in any user's garage
        conn.execute("""
            UPDATE garage
            SET current_bid = (
                SELECT v.current_bid FROM vehicles v WHERE v.vin = garage.vin
            )
            WHERE vin IN (
                SELECT v.vin FROM vehicles v
                JOIN auctions a ON v.auction_id = a.auction_id
                WHERE a.auction_status = 'completed'
            )
        """)

        # Copy all vehicles from completed auctions into garage for users who saved those auctions
        rows = conn.execute("""
            SELECT sa.user_id,
                   v.vin, v.year, v.make, v.model, v.body_type, v.color, v.key_status,
                   v.catalytic_converter, v.start_status, v.engine_type, v.drivetrain,
                   v.fuel_type, v.num_cylinders, v.documentation_type, v.auction_id,
                   v.region_id, v.seller_id, v.item_id, v.item_key, v.current_bid,
                   v.bid_expiration, v.reserve_price, v.fee_price, v.images,
                   v.images_count, v.last_recorded_odo
            FROM saved_auctions sa
            JOIN auctions a ON sa.auction_id = a.auction_id
            JOIN vehicles v ON v.auction_id = a.auction_id
            WHERE a.auction_status = 'completed'
        """).fetchall()
        for row in rows:
            conn.execute('''
                INSERT OR IGNORE INTO garage (
                    vin, user_id, year, make, model, body_type, color, key_status,
                    catalytic_converter, start_status, engine_type, drivetrain, fuel_type,
                    num_cylinders, documentation_type, auction_id, region_id, seller_id,
                    item_id, item_key, current_bid, bid_expiration, reserve_price, fee_price,
                    images, images_count, last_recorded_odo, liked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ''', (
                row['vin'], row['user_id'], row['year'], row['make'], row['model'],
                row['body_type'], row['color'], row['key_status'], row['catalytic_converter'],
                row['start_status'], row['engine_type'], row['drivetrain'], row['fuel_type'],
                row['num_cylinders'], row['documentation_type'], row['auction_id'], row['region_id'],
                row['seller_id'], row['item_id'], row['item_key'], row['current_bid'],
                row['bid_expiration'], row['reserve_price'], row['fee_price'],
                row['images'], row['images_count'], row['last_recorded_odo']
            ))

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
    print("[live-refresh] Refreshing all published vehicle bids...")
    counts = scraper.scrape_all_published()
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
