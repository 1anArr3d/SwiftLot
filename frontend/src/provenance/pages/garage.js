// Garage page, ported from design/provenance/garage.html. mount() builds the page inside root.
import { D, SL } from '../sl.js';
import { ENG } from '../engine.js';
import { PAT } from '../patterns.js';
import { HOLO } from '../holo.js';
import './garage.css';

const MARKUP = `<main class="wrap">
 <section class="band tk"><div class="main"><div id="g"></div><h1 class="pg">Your garage</h1><p class="lede">Cars you're watching. Open one for its full certificate.</p></div>
  <div class="stub" id="stats"></div></section>
 <h2 class="s"><span>Watching</span></h2><p class="sub">Sorted by when bidding closes.</p><div class="cards" id="grid"></div>
</main>`;

// opts.onRemove(vin) resolves true once the server has removed it
export function mount(root, { onRemove = async () => true } = {}) {
  root.innerHTML = MARKUP;
  const $ = id => root.querySelector('#' + id);
  const [g, stats, grid] = ['g', 'stats', 'grid'].map($);

const {money,title,timeLeft}=SL,{gap,gapText,lot}=ENG;
g.innerHTML=`<div class="guil">${PAT.waves('#8796c0')}</div>`;
let saved=[...D.vehicles];
function render(){const s=[...saved].sort((a,b)=>new Date(a.bid_expiration)-new Date(b.bid_expiration));
 stats.innerHTML=`<b>${s.length}</b><small>Watching</small><i>${s.filter(v=>(gap(v)??1)<=0).length} under median<br>${s.filter(v=>v.odo_rollback).length} odometer flags</i>`;
 grid.innerHTML=s.map(v=>{const g=gap(v);return `<div class="slot"><a class="mc" href="/auctions/${v.region_id}?vin=${v.vin}">${PAT.photo(v,g)}<small>SL-${lot(v)}</small><h3>${title(v)}</h3>
  <div class="row"><b class="${g==null?'':g<=0?'u':'o'}">${money(v.current_bid)}</b><span>${gapText(v)}</span></div>${v.odo_rollback?'<div class="flag">Odometer not actual</div>':''}
  <div class="meta"><span>${v.seller_name||''}</span><span>${timeLeft(v.bid_expiration)} left</span></div></a>
  <button class="remove" data-vin="${v.vin}" aria-label="Stop watching ${title(v)}">✕</button></div>`}).join('')||'<div class="empty" style="grid-column:1/-1"><p>Your garage is empty.</p><a class="btn go" href="/search" style="display:inline-grid;place-items:center;text-decoration:none">Find a car</a></div>';
 grid.querySelectorAll('.remove').forEach(b=>b.onclick=async()=>{b.disabled=true;if(await onRemove(b.dataset.vin)){saved=saved.filter(v=>v.vin!==b.dataset.vin);render()}else b.disabled=false});
 grid.querySelectorAll('.mc').forEach(c=>HOLO.track(c,{tilt:0}))}
render();

}
