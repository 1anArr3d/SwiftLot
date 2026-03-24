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
