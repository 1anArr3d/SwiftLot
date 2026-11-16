"""
Self-check for pricing.py levels and name merging. No DB.
Run from backend/: python test_pricing.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import pricing

rows = (
    [("FORD", "F150", 2012, p) for p in (500, 600, 700, 800)]
    + [("FORD", "F - 150", 2012, 900)]                         # merges with F150 -> 5 same-year sales
    + [("CHEVROLET", "MALIBU", 2010, p) for p in (1000, 1100)]
    + [("CHEVROL", "MALIBU", 2011, p) for p in (1200, 1300, 1400)]  # truncated make merges
    + [("TOYOTA", "CAMRY", y, 2000) for y in (2001, 2005, 2009, 2013, 2017)]
    + [("CHEVROLET", "SILVERADO 2500HD", 2015, 5000)] * 5
)
index, prefix = pricing.build_index(rows)
pricing._prefix_map = prefix

assert prefix["CHEVROL"] == "CHEVROLET"
assert pricing.model_key("F - 150") == pricing.model_key("F-150") == "F150"

r = pricing.range_from(index, "Ford", "F-150", 2012)
assert r == {"count": 5, "level": "year", "low": 600, "median": 700, "high": 800}, r

r = pricing.range_from(index, "Chevrolet", "Malibu", 2010)
assert r["level"] == "near" and r["count"] == 5, r

r = pricing.range_from(index, "Toyota", "Camry", 2009)
assert r["level"] == "all" and r["count"] == 5, r

assert pricing.range_from(index, "Mercedes-Benz", "S550", 2010) is None
assert pricing.range_from(index, "Chevrolet", "Silverado", 2015) is None  # trims are not merged

print("ok")
