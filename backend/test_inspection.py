"""
Quick test for the inspection scraper.
Run from backend/: python test_inspection.py

Pulls up to 3 unchecked TX vehicles from DB, runs the inspection batch,
and prints results.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from db import init_db, query
from scrapers.autura.inspection_scraper import run_inspection_batch

def main():
    init_db()

    rows = query("""
        SELECT v.vin, v.year, v.make, v.model, a.seller_state
        FROM vehicles v
        JOIN auctions a ON a.auction_id = v.auction_id
        WHERE (v.last_recorded_odo IS NULL OR v.last_recorded_odo = 'N/A')
          AND a.seller_state = 'TX'
    """)

    if not rows:
        print("No unchecked TX vehicles found.")
        print("Checking if any TX auctions exist at all...")
        tx = query("SELECT COUNT(*) as n FROM auctions WHERE seller_state = 'TX'")
        print(f"  TX auctions in DB: {tx[0]['n']}")
        unchecked = query("SELECT COUNT(*) as n FROM vehicles WHERE last_recorded_odo IS NULL")
        print(f"  Unchecked vehicles total: {unchecked['n'] if isinstance(unchecked, dict) else unchecked[0]['n']}")
        return

    vins = [r["vin"] for r in rows]
    print(f"Testing {len(vins)} VIN(s):")
    for r in rows:
        print(f"  {r['vin']} — {r['year']} {r['make']} {r['model']} (state={r['seller_state']})")

    print("\nRunning inspection batch...")
    run_inspection_batch(vins)

    done = query("SELECT COUNT(*) as n FROM vehicles WHERE last_recorded_odo IS NOT NULL AND last_recorded_odo != 'N/A' AND vin = ANY(%s)", (vins,))
    print(f"\nDone: {done[0]['n']}/{len(vins)} VINs have odometer records")

if __name__ == "__main__":
    main()
