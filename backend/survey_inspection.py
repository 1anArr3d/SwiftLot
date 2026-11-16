"""
Survey mytxcar for ~100 TX VINs from historical_sales.csv: dump every search page and
every detail page, then summarize what each holds and where the time goes. No DB writes.
Run from backend/: python survey_inspection.py [n_vins] [skip] [out_dir]

Fetches every detail page once, then replays two row-picking strategies offline:
  current: first 10 rows, one per year (year used up even if no odometer), stop at 5
  smart:   emissions rows first, one per year; "Safety Only" only for years still
           uncovered; stop at 5 readings
"""
import csv
import html as htmllib
import os
import re
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from scrapers.autura.inspection_scraper import _get_session, _extract_hidden, _LinkParser, SEARCH_URL, HISTORY_URL
from dump_inspection import pick_vins


def text_tokens(page):
    page = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    return [htmllib.unescape(t).strip() for t in re.split(r"<[^>]+>", page) if t.strip()]


def detail_fields(page):
    """'Label:' token followed by a value token -> {label: value}."""
    toks, out = text_tokens(page), {}
    for a, b in zip(toks, toks[1:]):
        if a.endswith(":") and not b.endswith(":"):
            out[a[:-1]] = b
    return out


def search_rows(page):
    """One list of cell texts per result row (rows holding a DoSelect link)."""
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, flags=re.S):
        if "DoSelect" in tr:
            rows.append([" ".join(text_tokens(td)) for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)])
    return rows


def year_of(row):
    return row["date"].split("/")[-1].split(" ")[0][:4]


def strategy_current(rows):
    readings, seen, fetched = [], set(), 0
    for row in rows[:10]:
        if year_of(row) in seen or len(readings) >= 5:
            continue
        seen.add(year_of(row))
        fetched += 1
        if row["odo"]:
            readings.append(row)
    return fetched, readings


def strategy_smart(rows):
    readings, seen, fetched = [], set(), 0
    ordered = [r for r in rows if r["type"] != "Safety Only"] + [r for r in rows if r["type"] == "Safety Only"]
    for row in ordered:
        if len(readings) >= 5:
            break
        if year_of(row) in seen:
            continue
        fetched += 1
        if row["odo"]:
            seen.add(year_of(row))
            readings.append(row)
    return fetched, readings


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    skip = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    out = sys.argv[3] if len(sys.argv) > 3 else "inspection_survey"
    os.makedirs(out, exist_ok=True)
    session = _get_session()

    timings = defaultdict(list)
    results_per_vin, odo_by_type, missing_by_type = [], Counter(), Counter()
    bad_vin = 0
    first_row_cells = None
    strat = {"current": [0, 0, 0], "smart": [0, 0, 0]}  # detail requests, readings, newest-reading misses
    t_all = time.perf_counter()

    with open(os.path.join(out, "details.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["vin", "row", "date", "test_type", "odometer", "vin_ok", "detail_ms"])

        for k, r in enumerate(pick_vins(skip + n)[skip:]):
            vin = r["vin"]
            t = time.perf_counter()
            hidden = _extract_hidden(session.get(SEARCH_URL, timeout=15).text)
            timings["get"].append(time.perf_counter() - t)

            t = time.perf_counter()
            search = session.post(SEARCH_URL, data={**hidden, "txtVin": vin, "btnSearch": "Search"}, timeout=15).text
            timings["search"].append(time.perf_counter() - t)
            ok = "Search For VIN" in search and vin in search
            if not ok:
                print(f"{vin}: search failed")
                continue
            hidden = _extract_hidden(search)
            open(os.path.join(out, f"{vin}_search.html"), "w", encoding="utf-8").write(search)

            links = _LinkParser()
            links.feed(search)
            rows = search_rows(search)
            first_row_cells = first_row_cells or (rows[0] if rows else None)
            results_per_vin.append(len(links.links))
            vin_rows = []

            for i, link in enumerate(links.links):
                test_type = next((c for c in (rows[i] if i < len(rows) else []) if "Emission" in c or "Safety" in c), "?")
                t = time.perf_counter()
                detail = session.post(HISTORY_URL, data={
                    **hidden,
                    "hidAction": "SelectSearch",
                    "hidSearchType": link["search_type"],
                    "hidCode": link["vin"],
                    "hidSelectedRow": link["row_id"],
                    "hidTasId": link.get("tas_id", ""),
                }, timeout=15).text
                ms = (time.perf_counter() - t) * 1000
                timings["detail"].append(ms / 1000)
                open(os.path.join(out, f"{vin}_{i}_detail.html"), "w", encoding="utf-8").write(detail)
                fields = detail_fields(detail)
                odo = fields.get("Odometer") or fields.get("Odometer Reading", "")  # Safety Only pages use "Odometer Reading"
                vin_ok = fields.get("VIN") == vin
                bad_vin += not vin_ok
                (odo_by_type if odo.isdigit() else missing_by_type)[test_type] += 1
                w.writerow([vin, i, link["date"], test_type, odo, vin_ok, round(ms)])
                vin_rows.append({"date": link["date"], "type": test_type, "odo": odo.isdigit()})

            newest = next((row for row in vin_rows if row["odo"]), None)
            for name, fn in (("current", strategy_current), ("smart", strategy_smart)):
                fetched, readings = fn(vin_rows)
                strat[name][0] += fetched
                strat[name][1] += len(readings)
                strat[name][2] += bool(newest) and newest not in readings

            print(f"[{k + 1}/{n}] {vin}: {len(links.links)} inspections")

    total = time.perf_counter() - t_all
    print("\n== Summary ==")
    print(f"Total {total:.0f}s for {len(results_per_vin)} VINs ({total / max(len(results_per_vin), 1):.1f}s per VIN)")
    for name, ts in timings.items():
        print(f"  {name:7s} {len(ts):5d} requests, avg {sum(ts) / len(ts) * 1000:.0f} ms")
    c = Counter(results_per_vin)
    print(f"Inspections per VIN: min {min(results_per_vin)}, max {max(results_per_vin)}, "
          f"avg {sum(results_per_vin) / len(results_per_vin):.1f}, zero-result VINs {c[0]}")
    print("Strategy replay (detail requests / readings kept / VINs missing their newest reading):")
    for name, (fetched, kept, miss) in strat.items():
        print(f"  {name:8s} {fetched:5d} / {kept:5d} / {miss}  ({kept / max(fetched, 1):.0%} of requests useful)")
    print(f"Detail pages with wrong VIN: {bad_vin}")
    print("Odometer present / missing by test type:")
    for tt in sorted(set(odo_by_type) | set(missing_by_type)):
        print(f"  {tt:40s} {odo_by_type[tt]:5d} / {missing_by_type[tt]}")
    print(f"Search row columns (first row): {first_row_cells}")
    print(f"Files + details.csv in {os.path.abspath(out)}")


if __name__ == "__main__":
    main()
