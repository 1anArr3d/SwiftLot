"""
Dump raw mytxcar responses for a few TX VINs from historical_sales.csv. No DB writes.
Run from backend/: python dump_inspection.py [n_vins] [out_dir]

Pass 1 (sequential) saves search + detail HTML per VIN.
Pass 2 (8 threads, one shared session, like run_inspection_batch) re-reads the same
VINs; any odometer that differs from pass 1 points at shared-session crosstalk.
"""
import csv
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(__file__))
from scrapers.autura.inspection_scraper import (
    _get_session, _extract_hidden, _LinkParser, _OdometerParser, SEARCH_URL, HISTORY_URL,
)

CSV = os.path.join(os.path.dirname(__file__), "..", "historical_sales.csv")


def pick_vins(n):
    with open(CSV, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["region_id"].endswith("-TX")]
    seen, out = set(), []
    for r in rows:
        if r["vin"] not in seen:
            seen.add(r["vin"])
            out.append(r)
        if len(out) == n:
            break
    return out


def fetch(session, vin):
    """Same requests as _lookup_vin, but returns raw HTML too. Only the first detail row."""
    r = session.get(SEARCH_URL, timeout=15)
    hidden = _extract_hidden(r.text)
    search = session.post(SEARCH_URL, data={**hidden, "txtVin": vin, "btnSearch": "Search"}, timeout=15).text
    links = _LinkParser()
    links.feed(search)
    if not links.links:
        return search, None, None, None
    link = links.links[0]
    detail = session.post(HISTORY_URL, data={
        **_extract_hidden(search),
        "hidAction": "SelectSearch",
        "hidSearchType": link["search_type"],
        "hidCode": link["vin"],
        "hidSelectedRow": link["row_id"],
        "hidTasId": link.get("tas_id", ""),
    }, timeout=15).text
    odo = _OdometerParser()
    odo.feed(detail)
    detail_vins = set(re.findall(r"\b[A-HJ-NPR-Z0-9]{17}\b", detail))
    return search, detail, odo.odometer, detail_vins


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    out = sys.argv[2] if len(sys.argv) > 2 else "inspection_dump"
    os.makedirs(out, exist_ok=True)
    rows = pick_vins(n)
    t0 = time.perf_counter()
    session = _get_session()
    print(f"Browser login: {time.perf_counter() - t0:.1f}s")

    print("== Pass 1: sequential ==")
    seq = {}
    t0 = time.perf_counter()
    for r in rows:
        vin = r["vin"]
        search, detail, odo, detail_vins = fetch(session, vin)
        open(os.path.join(out, f"{vin}_search.html"), "w", encoding="utf-8").write(search)
        if detail:
            open(os.path.join(out, f"{vin}_detail.html"), "w", encoding="utf-8").write(detail)
        seq[vin] = odo
        print(f"{vin} {r['year']} {r['make']} {r['model']}: odo={odo} vin_on_detail={vin in (detail_vins or ())} other_vins={sorted((detail_vins or set()) - {vin})}")
    t_seq = time.perf_counter() - t0
    print(f"Sequential: {t_seq:.1f}s ({t_seq / len(rows):.2f}s per VIN)")

    print("\n== Pass 2: 8 threads, shared session ==")
    t0 = time.perf_counter()
    with ThreadPoolExecutor(8) as pool:
        par = dict(zip(seq, pool.map(lambda v: fetch(session, v)[2], seq)))
    print(f"Parallel: {time.perf_counter() - t0:.1f}s")
    bad = 0
    for vin in seq:
        flag = "" if seq[vin] == par[vin] else "  <-- MISMATCH"
        bad += bool(flag)
        print(f"{vin}: seq={seq[vin]} par={par[vin]}{flag}")
    print(f"\n{bad}/{len(seq)} mismatched. HTML in {os.path.abspath(out)}")


if __name__ == "__main__":
    main()
