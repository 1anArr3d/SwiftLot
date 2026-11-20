// Shared helpers. D is filled from the API by each page before it mounts (see adapt.js).
export const D = { auction: null, vehicles: [], auctions: [] };
export const SL = (() => {
  const money = n => n == null ? '—' : '$' + Math.round(n).toLocaleString();
  const miles = n => n == null ? '—' : Math.round(n).toLocaleString() + ' mi';
  const title = v => `${v.year} ${v.make} ${v.model}`;
  // What the buyer pays if the current bid wins, by Autura's own PriceBreakdownModel (verified against 300+ real bids):
  // platform fee = bid x rate (12.5% unless the lot/seller sets one), clamped to min/max ($950 default cap);
  // card processing = 3% of bid + platform + extra fees, rounded up. Key/storage/doc fees are inside the bid.
  const fees = (v, amount = v.current_bid) => {
    if (amount == null) return null;
    const bid = Math.round(amount * 100), extra = Math.round((v.extra_fees || 0) * 100);
    let plat = Math.round(bid * (v.platform_fee_rate ?? 0.125));
    if (v.platform_fee_min != null) plat = Math.max(plat, Math.round(v.platform_fee_min * 100));
    plat = Math.min(plat, Math.round((v.platform_fee_max ?? 950) * 100));
    const card = Math.ceil((bid + plat + extra) * (v.card_fee_rate ?? 0.03));
    return { bid: bid / 100, platform: plat / 100, extra: extra / 100, card: card / 100, total: (bid + plat + extra + card) / 100 };
  };
  const allIn = (v, amount) => fees(v, amount)?.total ?? null;
  // Plain-language notes about how this lot is selling, from fields Autura sends with every listing
  const lotNotes = v => [
    v.reserve_met === false && "Reserve not met: the yard can turn down the top bid.",
    ['BIDDING', 'ENDING_SOON'].includes(v.bidding_status) ? 'Live bidding now.'
      : v.bidding_status === 'PRE_BID' && new Date(v.bidding_start) > Date.now() && `Pre-bidding. Live bidding opens in ${timeLeft(v.bidding_start)}.`,
    v.run_number > 1 && `Relisted: this is its ${v.run_number === 2 ? 'second' : v.run_number === 3 ? 'third' : v.run_number + 'th'} time up for auction.`,
  ].filter(Boolean);
  const allInText = (v, amount) => allIn(v, amount) == null ? '—' : '$' + allIn(v, amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  // Smallest bid Autura will take next: the starting price, or the current bid plus Autura's increment
  // (their "CURRENT" scheme; every lot uses it). Mirrors pa()/fa() in Autura's shared bundle.
  const STEPS = [[250, 10], [500, 25], [2000, 50], [10000, 100], [20000, 200], [Infinity, 250]];
  const step = d => STEPS.find(([t]) => d < t)[1];
  const nextBid = v => {
    if (v.current_bid == null) return v.min_bid ?? null;
    let d = v.current_bid + step(v.current_bid);
    STEPS.forEach(() => { d = Math.ceil(d / step(d)) * step(d); });
    return d;
  };

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

  return { D, money, miles, title, fees, allIn, allInText, nextBid, lotNotes, timeLeft, verdict, bar, sparkSVG };
})();
