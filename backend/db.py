import psycopg2
import psycopg2.extras
import psycopg2.pool
from config import DATABASE_URL

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2, maxconn=20, dsn=DATABASE_URL
        )
    return _pool


class _Conn:
    """Thin wrapper so callers can do conn.execute(sql, args) like sqlite3."""

    def __init__(self, raw: psycopg2.extensions.connection):
        self._raw = raw

    def execute(self, sql: str, args: tuple = ()):
        cur = self._raw.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, args or None)
        return cur


class _ConnCtx:
    """Context manager: borrows a connection, commits or rolls back, returns it."""

    def __enter__(self) -> _Conn:
        self._raw = _get_pool().getconn()
        self._raw.autocommit = False
        return _Conn(self._raw)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self._raw.rollback()
        else:
            self._raw.commit()
        _get_pool().putconn(self._raw)


def get_db() -> _ConnCtx:
    """Use as: `with get_db() as conn: conn.execute(...)`"""
    return _ConnCtx()


def query(sql: str, args: tuple = (), one: bool = False):
    """Run a SELECT and return all rows (or one). Rows are dict-like."""
    raw = _get_pool().getconn()
    try:
        with raw.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, args or None)
            rows = cur.fetchall()
            return (rows[0] if rows else None) if one else rows
    finally:
        raw.rollback()  # no-op for reads; releases any implicit txn
        _get_pool().putconn(raw)


def init_db():
    with get_db() as conn:
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
            minimum_bid        DOUBLE PRECISION,
            sales_tax          DOUBLE PRECISION,
            ended_at           TEXT,
            closes_at          TEXT,
            harvested          INTEGER DEFAULT 0
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
            current_bid        DOUBLE PRECISION,
            bid_expiration     TEXT,
            reserve_price      DOUBLE PRECISION,
            fee_price          DOUBLE PRECISION,
            seller_notes       TEXT,
            images             TEXT,
            images_count       INTEGER,
            published_at       TEXT,
            last_recorded_odo  TEXT
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS odometer_history (
            row_id          TEXT PRIMARY KEY,
            vin             TEXT,
            inspection_date TEXT,
            mileage         INTEGER
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS garage (
            vin                TEXT,
            user_id            TEXT,
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
            current_bid        DOUBLE PRECISION,
            bid_expiration     TEXT,
            reserve_price      DOUBLE PRECISION,
            fee_price          DOUBLE PRECISION,
            images             TEXT,
            images_count       INTEGER,
            last_recorded_odo  TEXT,
            liked_at           TEXT,
            PRIMARY KEY (vin, user_id)
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS historical_sales (
            id          SERIAL PRIMARY KEY,
            vin         TEXT,
            year        INTEGER,
            make        TEXT,
            model       TEXT,
            color       TEXT,
            key_status  TEXT,
            region_id   TEXT,
            auction_id  TEXT,
            final_sale  DOUBLE PRECISION,
            fees_total  DOUBLE PRECISION,
            sold_at     TEXT,
            source      TEXT,
            UNIQUE (vin, auction_id)
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS saved_auctions (
            auction_id  TEXT,
            user_id     TEXT,
            saved_at    TEXT,
            PRIMARY KEY (auction_id, user_id)
        )''')

    print("[db] Schema ready.")
