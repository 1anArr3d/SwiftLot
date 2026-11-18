// Search page, ported from design/provenance/search.html. mount() builds the page inside root.
import { D, SL } from '../sl.js';
import { ENG } from '../engine.js';
import { PAT } from '../patterns.js';
import { HOLO } from '../holo.js';
import { LEDGER } from '../ledger.js';
import './search.css';

const MARKUP = `<main class="wrap">
 <section class="band tk"><div class="main"><div id="g"></div><h1 class="pg">Search every lot</h1><p class="lede">Each card is a value certificate. The seal on each photo gives the verdict: green under median, blue over, red when the odometer went backwards.</p></div>
  <div class="stub"><b id="tn"></b><small>Lots</small><i id="ts"></i></div></section>
 <div class="layout">
  <aside class="filters" aria-label="Filters"><div class="fstub"><h3>Search</h3><input type="search" id="q" placeholder="2019 civic, f-150, or a VIN" aria-describedby="qh"><p class="hint" id="qh">Matches every word against year, make, model and VIN.</p></div><div class="perf" aria-hidden="true"></div>
   <div class="ldg" id="ldg"></div></aside>
  <section><div class="bar"><p id="count"></p><select id="sort" aria-label="Sort"><option value="deal">Best value first</option><option value="low">Lowest bid</option><option value="close">Closing soonest</option><option value="miles">Lowest miles</option><option value="new">Newest year</option></select></div>
   <div class="cards" id="grid"></div></section>
 </div>
</main>`;

export function mount(root) {
  root.innerHTML = MARKUP;
  const $ = id => root.querySelector('#' + id);
  const [g, tn, ts, q, ldg, count, sort, grid] = ['g', 'tn', 'ts', 'q', 'ldg', 'count', 'sort', 'grid'].map($);

const {money,title,timeLeft}=SL,{gap,gapText,deal,lot}=ENG;
g.innerHTML=`<div class="guil">${PAT.waves('#8796c0')}</div>`;tn.textContent=D.vehicles.length;ts.textContent=`${D.vehicles.filter(v=>v.odo_rollback).length} flagged`;
const card=v=>{const g=gap(v);return `<a class="mc" href="/auctions/${v.region_id}?vin=${v.vin}">${PAT.photo(v,g)}<small>SL-${lot(v)}</small><h3>${title(v)}</h3>
 <div class="row"><b class="${g==null?'':g<=0?'u':'o'}">${money(v.current_bid)}</b><span>${gapText(v)}</span></div>${v.odo_rollback?'<div class="flag">Odometer not actual</div>':''}
 <div class="meta"><span>${v.odometer[0]?Math.round(v.odometer[0].miles/1000)+'k mi':'No TX miles'}</span><span>${timeLeft(v.bid_expiration)} left</span></div></a>`};
const mi=v=>v.odometer[0]?.miles;
const words=v=>{const t=q.value.trim().toLowerCase().split(/\s+/).filter(Boolean),hay=`${v.year} ${v.make} ${v.model} ${v.vin}`.toLowerCase();return t.every(w=>hay.includes(w))};
const L=LEDGER.mount(ldg,{vehicles:D.vehicles,gap,pre:words,onChange:()=>render()});
function render(){const l=D.vehicles.filter(v=>words(v)&&L.match(v));
 l.sort({deal:(a,b)=>(deal(b)??-9)-(deal(a)??-9),low:(a,b)=>(a.current_bid??1e9)-(b.current_bid??1e9),close:(a,b)=>new Date(a.bid_expiration)-new Date(b.bid_expiration),miles:(a,b)=>(mi(a)??1e9)-(mi(b)??1e9),new:(a,b)=>b.year-a.year}[sort.value]);
 count.textContent=`${l.length} of ${D.vehicles.length} lots`;
 grid.innerHTML=l.map(card).join('')||'<p class="empty">No lots match. Try clearing a filter.</p>';
 grid.querySelectorAll('.mc').forEach(c=>HOLO.track(c,{tilt:0}))}
q.oninput=()=>{L.refresh();render()};sort.oninput=render;
render();

}
