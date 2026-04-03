"""
One-time migration: copy all data from swiftlot.db (SQLite) to Postgres.

Usage on Hetzner:
    cd /opt/swiftlot
    python migrate_sqlite_to_pg.py

Requires DATABASE_URL to be set in .env (pointing at the new Postgres DB).
The Postgres tables must already exist (run the app once so init_db() runs,
or just let this script call init_db() first).
"""
import sqlite3
import sys
import os

# Allow running from /opt/swiftlot directly
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

import psycopg2
import psycopg2.extras
from config import DATABASE_URL
from db import init_db

SQLITE_PATH = os.path.join(os.path.dirname(__file__), "swiftlot.db")


def _rows(sqlite_conn, table: str) -> list[dict]:
    sqlite_conn.row_factory = sqlite3.Row
    cur = sqlite_conn.execute(f"SELECT * FROM {table}")
    return [dict(r) for r in cur.fetchall()]


def _pg_conn():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


def migrate_table(sqlite_conn, pg_conn, table: str, columns: list[str], on_conflict: str = "DO NOTHING"):
    rows = _rows(sqlite_conn, table)
    if not rows:
        print(f"  {table}: 0 rows — skipping")
        return

    placeholders = ", ".join(["%s"] * len(columns))
    cols = ", ".join(columns)
    sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) ON CONFLICT {on_conflict}"

    cur = pg_conn.cursor()
    inserted = 0
    for row in rows:
        values = tuple(row.get(c) for c in columns)
        cur.execute(sql, values)
        if cur.rowcount:
            inserted += 1

    pg_conn.commit()
    print(f"  {table}: {inserted}/{len(rows)} rows migrated")


def main():
    if not os.path.exists(SQLITE_PATH):
        print(f"SQLite DB not found at {SQLITE_PATH}")
        sys.exit(1)

    print(f"Source: {SQLITE_PATH}")
    print(f"Target: {DATABASE_URL}\n")

    print("Initialising Postgres schema...")
    init_db()

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    pg_conn = _pg_conn()

    print("Migrating tables...")

    migrate_table(sqlite_conn, pg_conn, "auctions", [
        "auction_id", "region_id", "seller_name", "auction_status",
        "vehicles_listed", "last_discovered", "last_scraped_count", "last_scraped_at",
        "series_key", "minimum_bid", "sales_tax", "ended_at", "closes_at", "harvested",
    ])

    migrate_table(sqlite_conn, pg_conn, "vehicles", [
        "vin", "year", "make", "model", "body_type", "color", "key_status",
        "catalytic_converter", "start_status", "engine_type", "drivetrain",
        "fuel_type", "num_cylinders", "documentation_type",
        "auction_id", "region_id", "seller_id", "item_id", "item_key",
        "current_bid", "bid_expiration", "reserve_price", "fee_price",
        "seller_notes", "images", "images_count", "published_at", "last_recorded_odo",
    ])

    migrate_table(sqlite_conn, pg_conn, "odometer_history", [
        "row_id", "vin", "inspection_date", "mileage",
    ])

    migrate_table(sqlite_conn, pg_conn, "garage", [
        "vin", "user_id", "year", "make", "model", "body_type", "color", "key_status",
        "catalytic_converter", "start_status", "engine_type", "drivetrain",
        "fuel_type", "num_cylinders", "documentation_type",
        "auction_id", "region_id", "seller_id", "item_id", "item_key",
        "current_bid", "bid_expiration", "reserve_price", "fee_price",
        "images", "images_count", "last_recorded_odo", "liked_at",
    ])

    migrate_table(sqlite_conn, pg_conn, "historical_sales", [
        "vin", "year", "make", "model", "color", "key_status",
        "region_id", "auction_id", "final_sale", "fees_total", "sold_at", "source",
    ])

    migrate_table(sqlite_conn, pg_conn, "saved_auctions", [
        "auction_id", "user_id", "saved_at",
    ])

    sqlite_conn.close()
    pg_conn.close()
    print("\nMigration complete.")


if __name__ == "__main__":
    main()
