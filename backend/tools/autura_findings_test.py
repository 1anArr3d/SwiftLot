"""
Re-checks what we learned about Autura against the live site. Read-only (GETs + Ably subscribe), no PII kept.

  python tools/autura_findings_test.py               # data checks, ~1 min
  python tools/autura_findings_test.py --listen 600  # also listen to live-phase lots for AUCTION_UPDATED / UNIT_LISTING_UPDATES

Each check prints PASS / FAIL / SKIP with the evidence. Exit code 1 if anything failed.
"""
import argparse, asyncio, json, math, os, sys, time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.chdir(Path(__file__).resolve().parents[1])
for line in open('.env', encoding='utf8'):
    if '=' in line and not line.lstrip().startswith('#'):
        k, v = line.strip().split('=', 1); os.environ.setdefault(k, v.strip().strip('"'))

from scrapers.autura.autura_api import BASE_URL, _authed_get, _fetch_flat, _decode

DEFAULT_RATE, DEFAULT_MAX, CARD_RATE = 0.125, 95000, 0.03
results = []


def report(name, ok, detail=''):
    tag = {True: 'PASS', False: 'FAIL', None: 'SKIP'}[ok]
    results.append(ok); print(f'[{tag}] {name}' + (f'\n       {detail}' if detail else ''), flush=True)


def js_round(x): return math.floor(x + 0.5)  # JS Math.round, not Python's banker's rounding


def platform_fee(bid, cfg):
    """Autura PriceBreakdownModel.calculatePlatformFee, cents. cfg = first non-null of lot → seller config."""
    rate = cfg.get('platformFeeRate'); rate = DEFAULT_RATE if rate is None else rate
    fee = js_round(bid * rate)
    if cfg.get('minPlatformFeeAmount') is not None: fee = max(fee, cfg['minPlatformFeeAmount'])
    mx = cfg.get('maxPlatformFeeAmount'); return min(fee, DEFAULT_MAX if mx is None else mx)


def est_total(bid, cfg, custom=0, card_rate=CARD_RATE):
    plat = platform_fee(bid, cfg)
    return bid + plat + custom + math.ceil((bid + plat + custom) * card_rate)


def route(path, route_id):
    f = _fetch_flat(f'{BASE_URL}{path}{"&" if "?" in path else "?"}_routes={route_id}')
    return _decode(f, f[0])[route_id]['data']


def feed(page=1, **filters):
    q = '&'.join(f'{k}={v}' for k, v in filters.items())
    f = _fetch_flat(f'{BASE_URL}/auctions.data?distance=2000&zipCode=67901&page={page}' + (f'&{q}' if q else ''))
    return _decode(f, f[0])['pages/auctionsRoute/AuctionsRoute']['data']['data']


def merged_cfg(lot, sellers):
    lc = lot['biddingInfo'].get('platformFeeConfig') or {}
    sc = (sellers.get(lot['accountId']) or {}).get('sellingConfig') or {}
    return {k: lc.get(k) if lc.get(k) is not None else sc.get(k) for k in ('platformFeeRate', 'minPlatformFeeAmount', 'maxPlatformFeeAmount')}


def bids_history(lot, per_page=100):
    a = lot['biddingInfo']['auctionInfo']['auctionId']
    r = _authed_get(f'{BASE_URL}/bids-history?unit_account_id={lot["accountId"]}&auction_id={a}&page=1&per_page={per_page}', timeout=20)
    return r.json()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--listen', type=int, default=0); ap.add_argument('--lots', type=int, default=40)
    a = ap.parse_args()

    # 1. The formula reproduces the screenshot exactly
    report('fee formula: $325 bid -> $376.60 (Autura screenshot)', est_total(32500, {}) == 37660, f'got {est_total(32500, {}) / 100}')

    # 2. Seller overrides exist
    sellers = {s['accountId']: s for s in route('/sellers.data', 'routes/sellers')['sellers']}
    ov = {k: s for k, s in sellers.items() if any((s.get('sellingConfig') or {}).get(f) is not None for f in ('platformFeeRate', 'minPlatformFeeAmount', 'maxPlatformFeeAmount'))}
    report('/sellers lists per-seller platform fee overrides', len(sellers) > 50 and len(ov) > 0, f'{len(sellers)} sellers, {len(ov)} override')

    lots = []
    for p in range(1, 12):
        lots += [l for l in feed(p)['unitListings'] if l.get('biddingInfo')]  # some lots come with no bidding info
        if len(lots) >= 130: break
    bid_lots = [l for l in lots if l['biddingInfo'].get('winningBid')]
    # half from sellers with their own fee rate, half on the default, so both paths are tested
    half = a.lots // 2
    bid_lots = [l for l in bid_lots if l['accountId'] in ov][:half] + [l for l in bid_lots if l['accountId'] not in ov][:a.lots - half]
    rates = Counter()

    # 3. Every historical bid's platform fee and total match our formula (incl. seller overrides)
    checked = bad = 0; ov_checked = 0; samples = []
    count_mismatch, count_gaps = [], []
    for lot in bid_lots[:a.lots]:
        h = bids_history(lot); cfg = merged_cfg(lot, sellers); rates[str(cfg['platformFeeRate'] if cfg['platformFeeRate'] is not None else DEFAULT_RATE)] += len(h['bids'])
        for b in h['bids']:
            exp = platform_fee(b['bidAmount'], cfg); checked += 1; ov_checked += lot['accountId'] in ov
            tot = b['bidAmount'] + b['platformFee'] + (b.get('sellerExtraFixedFeeAmount') or 0)
            if b['platformFee'] != exp or b['totalAmount'] != tot:
                bad += 1; samples.append((sellers.get(lot['accountId'], {}).get('accountName'), b['bidAmount'], b['platformFee'], exp, b['totalAmount'], tot))
        # 4. active-bid-count agrees with history
        c = _authed_get(f'{BASE_URL}/auction-active-bid-count?unit_account_id={lot["accountId"]}&auction_id={lot["biddingInfo"]["auctionInfo"]["auctionId"]}', timeout=20).json()
        if c.get('total') != h.get('total'): count_gaps.append((c.get('total'), h.get('total')))
        # 5. winningBid in feed is the top of history
        top = max((b['bidAmount'] for b in h['bids']), default=None)
        if top != lot['biddingInfo']['winningBid']['amountCents']: count_mismatch.append(('top', top, lot['biddingInfo']['winningBid']['amountCents']))
        time.sleep(0.3)  # be gentle
    report(f'bids-history platform fee + total match formula ({checked} bids on {min(len(bid_lots), a.lots)} lots, {ov_checked} on override sellers)',
           checked > 0 and bad == 0, f'bids per rate {dict(rates)}' + (f'; mismatches (seller, bid, fee, expected, total, expected): {samples[:5]}' if bad else ''))
    report('feed winningBid == top bid in bids-history', not count_mismatch, f'mismatches: {count_mismatch[:5]}' if count_mismatch else '')
    print(f'       info: active-bid-count differs from history total on {len(count_gaps)} lots (active vs all bids): {count_gaps[:5]}')

    # 6. Fields we don't use yet are populated
    c = Counter()
    for l in lots:
        b = l['biddingInfo']
        c['biddingStatus=' + str(b.get('biddingStatus'))] += 1
        c['isReserveMet=' + str(b.get('isReserveMet'))] += 1
        c['reservePrice set'] += b.get('reservePrice') is not None
        c['runNumber>1'] += (l.get('runNumber') or 0) > 1
        c['has biddingEndUtc'] += bool(b['auctionInfo'].get('biddingEndUtc'))
        c['lot platformFeeConfig set'] += any(v is not None for v in (b.get('platformFeeConfig') or {}).values())
        c['customFees set'] += bool(b.get('customFees'))
        c['sellerFees set'] += any(v for v in (b.get('sellerFees') or {}).values())
    report(f'feed carries reserve / phase / run fields ({len(lots)} lots)', c['has biddingEndUtc'] == len(lots), dict(sorted(c.items())))

    # 7. Server-side phase filter works
    live = feed(1, auction_status='LIVE_BIDDING'); pre = feed(1, auction_status='PRE_BIDDING'); allf = feed(1)
    phases = Counter(l['biddingInfo'].get('biddingStatus') for l in live['unitListings'])
    ok = live['total'] + pre['total'] <= allf['total'] + 5 and live['total'] != allf['total'] and (not live['unitListings'] or set(phases) <= {'BIDDING', 'ENDING_SOON'})
    report('auction_status=LIVE_BIDDING / PRE_BIDDING filters server-side', ok,
           f'live {live["total"]} (phases {dict(phases)}), pre {pre["total"]}, all {allf["total"]}')
    for name, val in (('NO_RESERVE', 'NO_RESERVE'), ('RESERVE_NOT_MET', 'RESERVE_NOT_MET')):
        r = feed(1, reserve_status=val)
        print(f'       reserve_status={name}: {r["total"]} lots')

    # 8. Dictionary gives canonical makes
    makes = route('/dictionary.data?code=MAKE', 'routeComponents/dictionary/Dictionary')['values']
    report('/dictionary?code=MAKE returns canonical makes', len(makes) > 50, f'{len(makes)} makes, e.g. {[m["translationValue"] for m in makes[:4]]}')

    # 9. bids-history on lots past their end time (sold-price source?)
    now = datetime.now(timezone.utc).isoformat()
    ended = [l for l in lots if (l['biddingInfo']['auctionInfo'].get('biddingEndUtc') or 'z') < now or l.get('status') != 'PUBLISHED']
    if ended:
        h = bids_history(ended[0]); report('bids-history works after a lot ends', 'bids' in h, f'status {ended[0]["status"]}, {h.get("total")} bids')
    else:
        report('bids-history works after a lot ends', None, 'no ended lots in the feed right now; rerun just after a live window closes')

    if a.listen: asyncio.run(listen(a.listen))
    sys.exit(1 if False in results else 0)


async def listen(secs):
    from ably import AblyRealtime
    lots = []
    for phase in ('LIVE_BIDDING', 'PRE_BIDDING'):
        for p in range(1, 4):
            lots += [l for l in feed(p, auction_status=phase)['unitListings'] if l.get('biddingInfo')]
            if len(lots) >= 90: break
        if len(lots) >= 90: break
    # live lots first, then the pre-bid lots whose live hour starts soonest (feed order isn't by time)
    lots.sort(key=lambda l: (l['biddingInfo'].get('biddingStatus') == 'PRE_BID', l['biddingInfo']['auctionInfo'].get('biddingStartUtc') or 'z'))
    lots = lots[:90]
    print(f'listening {secs}s on {len(lots)} lots (live first), auction + listing channels', flush=True)
    seen, shapes = Counter(), {}

    async def auth(_): return json.loads((await asyncio.to_thread(_authed_get, f'{BASE_URL}/ably-auth', timeout=20)).text)
    rt = AblyRealtime(auth_callback=auth)
    for l in lots:
        for ch in (f"public:auction:{l['biddingInfo']['auctionInfo']['auctionId']}:updates", f"public:listing:{l['unitDetails']['unitListingId']}:updates"):
            def h(m, kind=ch.split(':')[1]):
                d = m.data if isinstance(m.data, dict) else json.loads(m.data) if m.data else {}
                k = f'{kind}/{m.name}'; seen[k] += 1
                shapes.setdefault(k, sorted(d) if isinstance(d, dict) else type(d).__name__)
            await rt.channels.get(ch).subscribe(h)
    await asyncio.sleep(secs); await rt.close()
    for k, n in seen.items(): print(f'       {k} x{n}: keys {shapes[k]}')
    report('AUCTION_UPDATED seen on auction channel', 'auction/AUCTION_UPDATED' in seen or None, 'none arrived' if 'auction/AUCTION_UPDATED' not in seen else '')
    report('UNIT_LISTING_UPDATES seen on listing channel', any(k.startswith('listing/') for k in seen) or None, '' if any(k.startswith('listing/') for k in seen) else 'none arrived')


if __name__ == '__main__':
    main()
