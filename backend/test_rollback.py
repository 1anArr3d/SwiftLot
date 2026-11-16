"""
Self-check for is_rollback using real TX readings (newest first). No network or DB.
Run from backend/: python test_rollback.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from scrapers.autura.inspection_scraper import is_rollback


def r(*miles):
    return [{"odometer": m} for m in miles]


CASES = [
    # (label, readings newest-first, expected)
    ("Tahoe: real drop",           r(154739, 191919, 165646, 149501), True),
    ("Camry: real drop",           r(143045, 132135, 100528, 274344, 259539), True),
    ("Aerio: single low typo",     r(180959, 97283, 175224, 168977, 158359), False),
    ("Accord: single high typo",   r(147690, 135925, 211892, 109764, 102374), False),
    ("Altima: repeated old value", r(225941, 211987, 158022, 173594, 158022), False),
    ("Fusion: -502 noise",         r(49303, 49805, 48322, 47518, 46498), False),
    ("Van: -177 noise",            r(147650, 145281, 145458, 143623, 142075), False),
    ("Corolla: -1,863 noise",      r(218819, 189344, 191207), False),
    ("Normal climb",               r(119783, 112569, 104315, 88203, 73864), False),
    ("One reading",                r(50000), False),
    ("No readings",                [], False),
]

if __name__ == "__main__":
    for label, readings, expected in CASES:
        assert is_rollback(readings) == expected, label
    print(f"ok: {len(CASES)} cases")
