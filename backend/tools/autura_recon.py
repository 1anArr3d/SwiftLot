"""
Autura recon: drive mp.autura.com in a headless browser as our account and record what its frontend talks to,
so we can map their backend without anyone clicking around with devtools open.

  python tools/autura_recon.py                  # home, auction list, a few lots, live messages for 60s
  python tools/autura_recon.py --lots 5 --listen 300 --headed

Writes backend/recon/<timestamp>/ (gitignored):
  endpoints.md     every distinct endpoint: method, status, type, sample keys
  responses/       one redacted sample body per endpoint
  live.jsonl       websocket frames (Ably), redacted
  bundles.md       JS bundle lines mentioning fees/bids/totals, to find the fee math
  pages/           screenshot of each page visited

Read-only by construction: every non-GET request except login and the Ably token is aborted before it leaves,
so nothing can place a bid; the tool also never clicks or types. Bidder/user PII is redacted before anything touches disk.
"""
import argparse, json, os, re, sys, time
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.chdir(Path(__file__).resolve().parents[1])
for line in open('.env', encoding='utf8'):
    if '=' in line and not line.lstrip().startswith('#'):
        k, v = line.strip().split('=', 1); os.environ.setdefault(k, v.strip().strip('"'))

from playwright.sync_api import sync_playwright
from scrapers.autura.autura_api import BASE_URL, _get_session, _fetch_flat, _decode

PII_KEYS = re.compile(r'(email|phone|first_?name|last_?name|full_?name|^name$|username|address|street|zip|postal|'
                      r'license|dob|birth|ssn|card|token|password|secret|cookie|ip_?addr)', re.I)
EMAIL = re.compile(r'[\w.+-]+@[\w-]+\.[\w.]+')
FEE_WORDS = re.compile(r'(platform_?fee|processing_?fee|buyer_?fee|fee_?config|feeConfig|total_amount|estTotal|'
                       r'est\.? total|percent|bid_increment|increment)', re.I)
ALLOWED_WRITES = (  # anything with 'bid' in it is refused even if listed
    '/signin', '/ably-auth', '/requestToken')  # login + Ably token exchange only


def redact(o):
    if isinstance(o, dict):
        return {k: ('[redacted]' if PII_KEYS.search(k) and not isinstance(v, (dict, list)) else redact(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [redact(x) for x in o[:5]] + ([f'... {len(o) - 5} more'] if len(o) > 5 else [])
    if isinstance(o, str):
        return EMAIL.sub('[email]', o)[:500]
    return o


def keys_of(o, depth=0):
    if isinstance(o, list) and o: return keys_of(o[0], depth)
    if not isinstance(o, dict) or depth > 1: return []
    return [k if depth == 0 else f'  .{k}' for k in o] if depth else [x for k, v in o.items() for x in [k] + [f'{k}.{s.strip(". ")}' for s in keys_of(v, 1)]]


def endpoint_key(method, url):
    p = urlparse(url)
    path = re.sub(r'/[0-9a-f-]{8,}|/\d{3,}', '/{id}', p.path)  # collapse ids so lots share one entry
    return f'{method} {p.netloc}{path}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lots', type=int, default=3, help='lot pages to open')
    ap.add_argument('--listen', type=int, default=60, help='seconds to sit on the last lot recording live messages')
    ap.add_argument('--headed', action='store_true')
    a = ap.parse_args()

    out = Path('recon') / time.strftime('%Y%m%d-%H%M%S')
    (out / 'responses').mkdir(parents=True); (out / 'pages').mkdir()
    seen, bundles, blocked = {}, {}, []
    live = open(out / 'live.jsonl', 'w', encoding='utf8')

    sess = _get_session()
    cookies = [{'name': c.name, 'value': c.value, 'domain': c.domain or 'mp.autura.com', 'path': c.path or '/'} for c in sess.cookies.jar]
    if not any(c['name'] == 'user-session' for c in cookies): sys.exit('Autura login failed; check AUTURA_EMAIL/PASSWORD in .env')
    flat = _fetch_flat(f'{BASE_URL}/auctions.data?distance=2000&zipCode=67901&page=1')
    route = (_decode(flat, flat[0]).get('pages/auctionsRoute/AuctionsRoute') or {}).get('data') or {}
    items = (route.get('data') or {}).get('unitListings') or []
    lots = [(i.get('unitDetails') or {}).get('unitListingId') for i in items][:a.lots]

    def on_response(r):
        req = r.request
        if req.resource_type not in ('xhr', 'fetch', 'document', 'script', 'other'): return
        url = r.url
        if not re.search(r'autura|ably', urlparse(url).netloc): return  # skip analytics/cookie banners
        if req.resource_type == 'script':
            if 'autura' in url and url not in bundles:
                try: bundles[url] = r.text()
                except Exception: pass
            return
        k = endpoint_key(req.method, url)
        if k in seen: seen[k]['hits'] += 1; return
        ctype = r.headers.get('content-type', '')
        entry = seen[k] = {'hits': 1, 'status': r.status, 'type': ctype.split(';')[0], 'example': url.split('?')[0] + ('?…' if '?' in url else ''), 'keys': []}
        if 'json' in ctype or url.endswith('.data'):
            try:
                body = r.json() if 'json' in ctype else json.loads(r.text())
                entry['keys'] = keys_of(body)[:40]
                fn = re.sub(r'[^\w.-]+', '_', k)[:120] + '.json'
                (out / 'responses' / fn).write_text(json.dumps(redact(body), indent=1)[:200_000], encoding='utf8')
                entry['file'] = fn
            except Exception: pass

    def on_ws(ws):
        def frame(payload, way):
            try: d = json.loads(payload)
            except Exception: d = str(payload)[:300]
            live.write(json.dumps({'t': time.time(), 'dir': way, 'url': ws.url.split('?')[0], 'data': redact(d)}) + '\n'); live.flush()
        ws.on('framereceived', lambda p: frame(p, 'in'))
        ws.on('framesent', lambda p: frame(p, 'out'))

    def guard(route):
        r = route.request
        if r.method in ('GET', 'HEAD', 'OPTIONS') or (any(w in r.url for w in ALLOWED_WRITES) and 'bid' not in r.url.lower()): return route.continue_()
        if re.search(r'autura|ably', urlparse(r.url).netloc) and '/metrics' not in r.url and '/-/' not in r.url: blocked.append(f'{r.method} {r.url.split("?")[0]}  body: {(r.post_data or "")[:200]}')
        route.abort()

    with sync_playwright() as p:
        br = p.chromium.launch(headless=not a.headed)
        ctx = br.new_context(viewport={'width': 1400, 'height': 1000})
        ctx.add_cookies(cookies)
        ctx.route('**/*', guard)
        page = ctx.new_page()
        page.on('response', on_response); page.on('websocket', on_ws)

        def visit(name, url):
            print('->', name, url, flush=True)
            try: page.goto(url, wait_until='networkidle', timeout=45_000)
            except Exception as e: print('   ', str(e)[:120])
            page.screenshot(path=str(out / 'pages' / f'{name}.png'))

        visit('home', BASE_URL)
        visit('auctions', f'{BASE_URL}/auctions')
        for i, key in enumerate(lots):
            visit(f'lot{i}', f'{BASE_URL}/auctions/listings/{key}')
            # never click or type here: their Bid button submits place-bid.data straight away (guard() blocks it, but don't rely on one wall)
            page.screenshot(path=str(out / 'pages' / f'lot{i}-full.png'))
            (out / 'pages' / f'lot{i}-text.txt').write_text(EMAIL.sub('[email]', page.inner_text('body'))[:20_000], encoding='utf8')
        if a.listen: print(f'listening {a.listen}s', flush=True); page.wait_for_timeout(a.listen * 1000)
        br.close()
    live.close()

    with open(out / 'endpoints.md', 'w', encoding='utf8') as f:
        f.write(f'# Autura endpoints seen {time.strftime("%Y-%m-%d %H:%M")}\n\n')
        for k, e in sorted(seen.items()):
            f.write(f'## {k}\n{e["status"]} {e["type"]} x{e["hits"]}  e.g. {e["example"]}\n')
            if e.get('file'): f.write(f'sample: responses/{e["file"]}\n')
            if e['keys']: f.write('keys: ' + ', '.join(e['keys']) + '\n')
            f.write('\n')
        if blocked: f.write('# Blocked writes (would have been sent)\n' + '\n'.join(blocked) + '\n')
    with open(out / 'bundles.md', 'w', encoding='utf8') as f:
        for url, src in bundles.items():
            hits = [m for m in re.finditer(FEE_WORDS, src)]
            if not hits: continue
            f.write(f'## {url}\n')
            last = -1
            for m in hits[:60]:
                if m.start() < last: continue
                s = max(0, m.start() - 200); last = m.end() + 200
                f.write('```\n' + src[s:last].replace('\n', ' ') + '\n```\n')
    print(f'done: {len(seen)} endpoints, {len(bundles)} bundles, {len(blocked)} writes blocked -> {out}')


if __name__ == '__main__':
    main()
