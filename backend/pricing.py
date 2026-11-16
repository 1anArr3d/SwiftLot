"""
Price ranges from historical_sales, with make/model name merging.

Levels (first with MIN_SALES sales wins): same year -> within +/-2 years -> any year.
Range = 25th-75th percentile of final_sale at that level.
"""
import re
import statistics
import threading
import time
from collections import Counter, defaultdict

from db import query

MIN_SALES = 5
NEAR_YEARS = 2
_TTL = 3600  # historical_sales only grows when sold listings are harvested

MAKE_ALIASES = {"MERCEDES-BENZ": "MERCEDES", "CHEVY": "CHEVROLET", "VW": "VOLKSWAGEN"}

_lock = threading.Lock()
_index = None      # (make_key, model_key) -> list[(year, price)]
_prefix_map = {}   # truncated make -> full make, e.g. CHEVROL -> CHEVROLET
_loaded_at = 0.0


def model_key(model: str) -> str:
    """'F - 150', 'F-150', 'F150' -> 'F150'. Trims (e.g. 2500HD) stay distinct."""
    return re.sub(r"[^A-Z0-9]", "", (model or "").upper())


def make_key(make: str) -> str:
    m = (make or "").upper().strip()
    m = MAKE_ALIASES.get(m, m)
    return _prefix_map.get(m, m)


def build_prefix_map(make_counts: Counter) -> dict:
    """Map a truncated make (4+ chars) to the most common make it is a prefix of."""
    out = {}
    for short in make_counts:
        if len(short) < 4:
            continue
        longer = [m for m in make_counts if m != short and m.startswith(short) and make_counts[m] > make_counts[short]]
        if longer:
            out[short] = max(longer, key=make_counts.__getitem__)
    return out


def build_index(rows):
    """rows: iterable of (make, model, year, price). Returns (index, prefix_map)."""
    rows = list(rows)
    counts = Counter(MAKE_ALIASES.get(r[0].upper().strip(), r[0].upper().strip()) for r in rows if r[0])
    prefix = build_prefix_map(counts)
    index = defaultdict(list)
    for make, model, year, price in rows:
        if not make or not model or year is None or price is None:
            continue
        m = MAKE_ALIASES.get(make.upper().strip(), make.upper().strip())
        index[(prefix.get(m, m), model_key(model))].append((int(year), float(price)))
    return index, prefix


def range_from(index, make: str, model: str, year: int):
    sales = index.get((make_key(make), model_key(model)), [])
    levels = (
        ("year", [p for y, p in sales if y == year]),
        ("near", [p for y, p in sales if abs(y - year) <= NEAR_YEARS]),
        ("all",  [p for _, p in sales]),
    )
    for level, prices in levels:
        if len(prices) >= MIN_SALES:
            q1, median, q3 = statistics.quantiles(prices, n=4, method="inclusive")
            return {"count": len(prices), "level": level,
                    "low": round(q1), "median": round(median), "high": round(q3)}
    return None


def _ensure_loaded():
    global _index, _prefix_map, _loaded_at
    with _lock:
        if _index is None or time.time() - _loaded_at > _TTL:
            rows = query("SELECT make, model, year, final_sale FROM historical_sales WHERE final_sale IS NOT NULL")
            _index, _prefix_map = build_index((r["make"], r["model"], r["year"], r["final_sale"]) for r in rows)
            _loaded_at = time.time()
        return _index


def price_range(make: str, model: str, year: int):
    return range_from(_ensure_loaded(), make, model, int(year))
