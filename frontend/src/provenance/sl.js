// Shared helpers. D is filled from the API by each page before it mounts (see adapt.js).
export const D = { auction: null, vehicles: [], auctions: [] };
export const SL = (() => {
  const money = n => n == null ? '—' : '$' + Math.round(n).toLocaleString();
  const miles = n => n == null ? '—' : Math.round(n).toLocaleString() + ' mi';
  const title = v => `${v.year} ${v.make} ${v.model}`;
  // what the buyer pays if the current bid wins: Autura's total from the live bid feed (bid + platform and yard fees)
  const allIn = v => v.buyer_total ?? null;
  const allInText = v => v.buyer_total != null ? money(v.buyer_total) : v.current_bid != null ? `${money(v.current_bid)} + fees` : '—';

  function timeLeft(iso) {
    const ms = new Date(iso) - Date.now();
    if (!(ms > 0)) return 'Closed';
    const h = Math.floor(ms / 36e5), m = Math.floor(ms % 36e5 / 6e4);
    return h >= 24 ? `${Math.floor(h / 24)}d ${h % 24}h` : `${h}h ${m}m`;
  }

  // Bid vs. typical range: 'under' | 'within' | 'over' | null
  function verdict(v) {
    const p = v.price, b = v.current_bid;
    if (!p || b == null) return null;
    return b < p.low ? 'under' : b > p.high ? 'over' : 'within';
  }

  // Positions (0-100%) for the range bar on a shared scale
  function bar(v) {
    const p = v.price; if (!p) return null;
    const max = Math.max(p.high * 1.5, (v.current_bid || 0) * 1.15, 1);
    const pct = x => Math.min(100, Math.max(0, x / max * 100));
    return { lo: pct(p.low), hi: pct(p.high), med: pct(p.median), bid: v.current_bid != null ? pct(v.current_bid) : null };
  }

  // SVG sparkline of odometer readings, oldest -> newest; drops > 2,000 mi drawn as rollback segments
  function spark(v, w = 160, h = 36, pad = 3) {
    const pts = [...v.odometer].reverse();
    if (pts.length < 2) return null;
    const lo = Math.min(...pts.map(p => p.miles)), hi = Math.max(...pts.map(p => p.miles));
    const xy = pts.map((p, i) => [pad + i * (w - 2 * pad) / (pts.length - 1),
                                   h - pad - (p.miles - lo) / Math.max(hi - lo, 1) * (h - 2 * pad)]);
    const segs = xy.slice(1).map((b, i) => ({ a: xy[i], b, drop: pts[i + 1].miles < pts[i].miles - 2000 }));
    return { w, h, xy, segs };
  }

  function sparkSVG(v, cls = 'spark', w, h) {
    const s = spark(v, w, h);
    if (!s) return `<span class="${cls}-empty">${v.odometer.length ? miles(v.odometer[0].miles) : 'No TX history'}</span>`;
    const lines = s.segs.map(g => `<line x1="${g.a[0]}" y1="${g.a[1]}" x2="${g.b[0]}" y2="${g.b[1]}" class="${g.drop ? 'drop' : 'ok'}"/>`).join('');
    const dots = s.xy.map((p, i) => `<circle cx="${p[0]}" cy="${p[1]}" r="${i === s.xy.length - 1 ? 2.6 : 1.6}"/>`).join('');
    return `<svg class="${cls}" viewBox="0 0 ${s.w} ${s.h}" width="${s.w}" height="${s.h}" role="img" aria-label="Odometer readings">${lines}${dots}</svg>`;
  }

  return { D, money, miles, title, allIn, allInText, timeLeft, verdict, bar, sparkSVG };
})();
