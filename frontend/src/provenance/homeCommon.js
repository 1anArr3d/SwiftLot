import { pic } from './adapt.js';
import { SL } from './sl.js';
import { ENG } from './engine.js';
import { PAT } from './patterns.js';
import { HOLO } from './holo.js';
import { every } from './life.js';
// Shared content for the three Home directions: same hero certificate, deals and closing list; each page supplies its own card markup.
export const HOME = (() => {
  const { D, money, title, allIn, allInText, bar } = SL, { gap, gapText, ranked, deal, lot, clock } = ENG;
  const left = iso => { const ms = new Date(iso) - Date.now(), h = ms / 36e5; return h < 24 ? `${Math.floor(h)}h ${Math.floor(ms % 36e5 / 6e4)}m` : `${Math.floor(h / 24)}d ${Math.floor(h % 24)}h`; };
  const certHTML = v => { const b = bar(v); return `<article class="cert" id="heroCert">${(S=>`<div class="guil tile" style="background-image:${S.map(s=>s.img).join(',')};background-position:${S.map(s=>s.pos).join(',')};background-size:${S.map(s=>s.size).join(',')}"></div>`)(PAT.spots('#3f6b5c',v.vin,'value'))}${PAT.strip('value',v.vin,'VALUE')}
    <div class="c-head"><div><small>Certificate of lot value</small><h2>${title(v)}</h2></div><div class="no">Certificate no.<b>SL-${lot(v)}-${v.vin.slice(-6)}</b></div></div>
    <div class="c-body"><div class="photo"><img src="${pic(v.images[0], 'MOBILE')}" alt="${title(v)}" loading="lazy"></div>
     <div><div class="field"><small>Current bid</small><div class="big u">${money(v.current_bid)}</div><span style="font-size:13px">${gapText(v)}</span></div>
      ${b ? `<div class="bandbar"><i style="left:${b.lo}%;width:${b.hi - b.lo}%"></i><b style="left:${b.bid}%"></b></div><div class="vlab"><span>Typical ${money(v.price.low)}–${money(v.price.high)}</span><span>${v.price.count} sales</span></div>` : ''}
      <div class="field"><small>If you win now</small><b>${allInText(v)}</b></div></div></div>
    <div class="foot">${PAT.inkSeal('Market<br>value')}<a class="btn go" href="/auctions/${v.region_id}?vin=${v.vin}" style="display:inline-grid;place-items:center;text-decoration:none">Open certificate</a></div></article>`; };
  function render({ cert, trust, deals, ledger, tot, deal: dealCard, yard }) {
    const order = ranked().filter(v => deal(v) != null), A = D.auctions, lots = A.reduce((s, a) => s + a.vehicles_count, 0);
    if (tot) document.getElementById(tot).textContent = `${A.length} sales · ${lots} lots`;
    if (cert) { document.getElementById(cert).innerHTML = certHTML(order[0]); HOLO.track(document.getElementById('heroCert'), { tilt: 3 }); }
    if (trust) document.getElementById(trust).innerHTML = `<div><b>${A.length}</b><small>Live sales</small></div><div><b>${lots}</b><small>Lots</small></div><div><b>${D.vehicles.filter(v => v.odo_rollback).length}</b><small>Rollbacks caught here</small></div>`;
    if (deals) document.getElementById(deals).innerHTML = order.slice(0, 12).map(v => dealCard(v, { money, title, gapText, gap, allIn, bar })).join('');
    if (ledger) { // only sales still open; each timer ticks every second
      const open = [...A].filter(a => new Date(a.closes_at) > Date.now()).sort((a, b) => new Date(a.closes_at) - new Date(b.closes_at)).slice(0, 5), el = document.getElementById(ledger);
      el.innerHTML = open.map((a, i) => yard(a, i, `<span data-close="${a.closes_at}">${clock(a.closes_at)}</span>`, new Date(a.closes_at) - Date.now() < 864e5)).join('');
      every(() => el.querySelectorAll('[data-close]').forEach(s => s.textContent = clock(s.dataset.close)), 1000); }
    document.querySelectorAll('.foil:not(#heroCert .foil)').forEach(el => HOLO.track(el.parentElement, { tilt: 0 }));
  }
  return { render, lot, left };
})();
