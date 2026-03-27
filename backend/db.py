import sqlite3
from config import DB_PATH

# Bump this when the schema changes to trigger a migration
SCHEMA_VERSION = 3


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def query(sql: str, args: tuple = (), one: bool = False):
    with get_db() as conn:
        cur = conn.execute(sql, args)
        rv = cur.fetchall()
        return (rv[0] if rv else None) if one else rv


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        if current < SCHEMA_VERSION:
            # Schema changed — drop and recreate (preserves odometer_history)
            conn.execute("DROP TABLE IF EXISTS watchlist")
            conn.execute("DROP TABLE IF EXISTS vehicles")
            conn.execute("DROP TABLE IF EXISTS auctions")

        conn.execute('''CREATE TABLE IF NOT EXISTS auctions (
            auction_id         TEXT PRIMARY KEY,
            region_id          TEXT,
            seller_name        TEXT,
            auction_status     TEXT,
            vehicles_listed    INTEGER,
            last_discovered    TEXT,
            last_scraped_count INTEGER,
            last_scraped_at    TEXT,
            series_key         TEXT,
            minimum_bid        REAL,
            sales_tax          REAL,
            ended_at           TEXT
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS vehicles (
            vin                TEXT PRIMARY KEY,
            year               INTEGER,
            make               TEXT,
            model              TEXT,
            body_type          TEXT,
            color              TEXT,
            key_status         TEXT,
            catalytic_converter TEXT,
            start_status       TEXT,
            engine_type        TEXT,
            drivetrain         TEXT,
            fuel_type          TEXT,
            num_cylinders      TEXT,
            documentation_type TEXT,
            auction_id         TEXT,
            region_id          TEXT,
            seller_id          TEXT,
            item_id            TEXT,
            item_key           TEXT,
            current_bid        REAL,
            bid_expiration     TEXT,
            reserve_price      REAL,
            fee_price          REAL,
            seller_notes       TEXT,
            images             TEXT,
            images_count       INTEGER,
            published_at       TEXT,
            last_recorded_odo  TEXT
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS odometer_history (
            row_id         TEXT PRIMARY KEY,
            vin            TEXT,
            inspection_date TEXT,
            mileage        INTEGER
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS watchlist (
            vin                TEXT PRIMARY KEY,
            year               INTEGER,
            make               TEXT,
            model              TEXT,
            body_type          TEXT,
            color              TEXT,
            key_status         TEXT,
            catalytic_converter TEXT,
            start_status       TEXT,
            engine_type        TEXT,
            drivetrain         TEXT,
            fuel_type          TEXT,
            num_cylinders      TEXT,
            documentation_type TEXT,
            auction_id         TEXT,
            region_id          TEXT,
            seller_id          TEXT,
            item_id            TEXT,
            item_key           TEXT,
            current_bid        REAL,
            bid_expiration     TEXT,
            reserve_price      REAL,
            fee_price          REAL,
            images             TEXT,
            images_count       INTEGER,
            last_recorded_odo  TEXT,
            liked_at           TEXT
        )''')

        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
