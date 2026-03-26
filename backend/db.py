import sqlite3
from config import DB_PATH


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
        conn.execute('''CREATE TABLE IF NOT EXISTS auctions (
            auction_id        TEXT PRIMARY KEY,
            region_id         TEXT,
            seller_name       TEXT,
            auction_status    TEXT,
            vehicles_listed   INTEGER,
            last_discovered   TEXT,
            last_scraped_count INTEGER
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS vehicles (
            vin TEXT PRIMARY KEY, year TEXT, make TEXT, model TEXT, color TEXT,
            key_status TEXT, catalytic_converter TEXT, start_status TEXT,
            engine_type TEXT, transmission TEXT, auction_id TEXT, city TEXT,
            last_recorded_odo TEXT, images TEXT, vehicle_id TEXT, fuel_type TEXT
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS odometer_history (
            row_id TEXT PRIMARY KEY, vin TEXT, inspection_date TEXT, mileage INTEGER
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS watchlist (
            vin TEXT PRIMARY KEY, year TEXT, make TEXT, model TEXT, color TEXT,
            key_status TEXT, catalytic_converter TEXT, start_status TEXT,
            engine_type TEXT, transmission TEXT, auction_id TEXT, city TEXT,
            last_recorded_odo TEXT, images TEXT, liked_at TEXT
        )''')
