"""
Import historical_sales.csv into Neon.
Run from backend/: python import_historical.py
"""
import sys
import os
import csv
sys.path.insert(0, os.path.dirname(__file__))

from db import init_db, get_db

CSV_PATH = os.path.join(os.path.dirname(__file__), '..', 'historical_sales.csv')

def main():
    init_db()

    with open(CSV_PATH, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Importing {len(rows)} rows...")

    inserted = 0
    with get_db() as conn:
        for row in rows:
            conn.execute(
                """INSERT INTO historical_sales
                       (vin, year, make, model, color, key_status, region_id, auction_id,
                        final_sale, fees_total, sold_at, source)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT DO NOTHING""",
                (
                    row['vin'],
                    int(row['year']) if row['year'] else None,
                    row['make'] or None,
                    row['model'] or None,
                    row['color'] or None,
                    row['key_status'] or None,
                    row['region_id'] or None,
                    row['auction_id'] or None,
                    float(row['final_sale']) if row['final_sale'] else None,
                    float(row['fees_total']) if row['fees_total'] else None,
                    row['sold_at'] or None,
                    row['source'] or None,
                )
            )
            inserted += 1
            if inserted % 1000 == 0:
                print(f"  {inserted}/{len(rows)}...")

    print(f"Done: {inserted} rows imported.")

if __name__ == '__main__':
    main()
