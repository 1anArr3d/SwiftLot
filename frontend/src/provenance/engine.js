import { SL } from './sl.js';
// Shared behaviour for the automotive concepts: deal ranking, persistent sliding rows, selection, simulated live bids.
export const ENG = (() => {
  const { D, money } = SL;
  const deal = v => v.price && v.current_bid != null ? (v.price.median - v.current_bid) / v.price.median : null;
  const tone = v => { const d = deal(v); return d == null ? 'none' : d >= 0 ? 'below' : 'above'; };
  const gap = v => deal(v) == null ? null : v.current_bid - v.price.median;           // negative = under median
  const gapText = v => { const g = gap(v); if (g == null) return v.current_bid == null ? 'No bids yet' : 'No price data';
    return `${money(Math.abs(g))} ${g <= 0 ? 'under' : 'over'} median`; };
  const urgency = iso => Math.min(1, Math.max(0, 1 - (new Date(iso) - Date.now()) / 36e5 / 72));  // 0 = 3+ days, 1 = closing
  const ranked = () => [...D.vehicles].sort((a, b) => (deal(b) ?? -9) - (deal(a) ?? -9));
  const lot = v => String(D.vehicles.indexOf(v) + 1).padStart(3, '0');
  const pad = n => String(n).padStart(2, '0');
  const clock = iso => { const s = Math.max(0, (new Date(iso) - Date.now()) / 1000 | 0);
    return `${Math.floor(s / 86400)}d ${pad(Math.floor(s % 86400 / 3600))}:${pad(Math.floor(s % 3600 / 60))}:${pad(s % 60)}`; };

  // rowsEl gets one persistent child per car; row(v, ctx) returns its inner HTML.
  function run({ rowsEl, rowH, row, hero, reveal = () => window.scrollTo({ top: 0, behavior: 'smooth' }), rowClass = 'row', keep = () => true, cmp = () => null }) {
    // a link can open a specific car: auction.html?vin=...
    const want = new URLSearchParams(location.search).get('vin');
    let sel = D.vehicles.find(v => v.vin === want) || D.vehicles[0];
    rowsEl.style.position = 'relative';
    rowsEl.style.height = D.vehicles.length * rowH + 'px';
    const els = new Map(D.vehicles.map(v => {
      const el = document.createElement('div'); el.className = rowClass; el.tabIndex = 0;
      Object.assign(el.style, { position: 'absolute', left: 0, right: 0 });
      el.onclick = () => { sel = v; paint(); hero(v); history.replaceState(history.state, '', `?vin=${v.vin}`); reveal(v, el); };
      el.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); el.click(); } };
      rowsEl.append(el); return [v, el];
    }));
    function paint() {
      const c = cmp(), all = c ? [...D.vehicles].sort(c) : ranked(), order = all.filter(keep), pole = order.find(v => deal(v) != null);
      all.forEach(v => { els.get(v).hidden = !order.includes(v); });
      rowsEl.style.height = order.length * rowH + 'px';
      order.forEach((v, i) => {
        const el = els.get(v); el.classList.toggle('rb', !!v.odo_rollback);
        const was = el.dataset.i; el.dataset.i = i; el.style.zIndex = was != null && +was !== i ? 2 : 1; // moving row passes over the others, not through them
        el.style.transform = `translateY(${i * rowH}px)`;
        el.classList.toggle('sel', v === sel); el.classList.toggle('pole', v === pole);
        el.dataset.tone = v === pole ? 'pole' : tone(v);
        el.innerHTML = row(v, { pos: i + 1, pole: v === pole, sel: v === sel, tone: tone(v) });
      });
      return order;
    }
    paint(); hero(sel);
    // A live bid from the SSE feed: update the car, re-rank, flash its row
    function bid(itemKey, amount, expires) {
      const v = D.vehicles.find(x => x.item_key === itemKey); if (!v || amount == null) return;
      if (v.current_bid === amount && (!expires || v.bid_expiration === expires)) return;
      const before = ranked().indexOf(v);
      v.current_bid = amount; if (expires) v.bid_expiration = expires;
      const order = paint(), el = els.get(v); if (el.hidden) return;
      el.classList.remove('flash', 'up'); void el.offsetWidth; el.classList.add('flash');
      if (order.indexOf(v) < before) el.classList.add('up');
      if (v === sel) hero(v);
    }
    return { paint, bid };
  }
  // Paint at an old value, then let CSS transition to the new one on the next frame.
  const settle = fn => requestAnimationFrame(() => requestAnimationFrame(fn));
  return { deal, tone, gap, gapText, urgency, ranked, lot, clock, run, settle };
})();
