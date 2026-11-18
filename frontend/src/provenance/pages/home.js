// Home page, ported from design/provenance/home.html. mount() builds the page inside root.
import { PAT } from '../patterns.js';
import { HOME } from '../homeCommon.js';
import { onStop } from '../life.js';
import './home.css';

const MARKUP = `<main class="wrap">
 <section class="band tk home"><div id="g"></div><div class="hero"><div><h1>Every lot,<br>certified.</h1>
  <p>Know what a tow-yard car is worth, what it'll cost with fees, and whether its odometer was rolled back, before you bid.</p>
  <a class="btn go" href="/auctions" style="display:inline-grid;place-items:center;text-decoration:none">Browse auctions</a>
  <div class="trust" id="trust"></div></div><div id="hc"></div></div></section>
 <div class="chead"><h2 class="s"><span>Best value right now</span></h2>
  <div class="cnav"><button class="btn" id="prev" aria-label="Previous cars">‹</button><button class="btn" id="next" aria-label="Next cars">›</button></div></div>
 <p class="sub">The bids furthest under what similar cars sold for.</p>
 <div class="deals" id="deals" tabindex="0" aria-label="Best value cars, scrollable"></div>
 <h2 class="s"><span>Closing soonest</span></h2><p class="sub">Sales that end first.</p><div class="ledger" id="ledger"></div>
</main>`;

export function mount(root) {
  root.innerHTML = MARKUP;
  const $ = id => root.querySelector('#' + id);
  const [g, deals, prev, next] = ['g', 'deals', 'prev', 'next'].map($);

g.innerHTML=`<div class="guil">${PAT.waves('#8796c0')}</div>`;
HOME.render({cert:'hc',trust:'trust',deals:'deals',ledger:'ledger',tot:'navr',
 deal:(v,{money,title,gapText,gap})=>`<a class="mc" href="/auctions/${v.region_id}?vin=${v.vin}">${PAT.photo(v,gap(v))}<small>SL-${HOME.lot(v)}</small><h3>${title(v)}</h3>
  <div class="row"><b class="${(gap(v)??1)<=0?'u':''}">${money(v.current_bid)}</b><span>${gapText(v)}</span></div>${v.odo_rollback?'<div class="flag">Odometer not actual</div>':''}</a>`,
 yard:(a,i,left,soon)=>`<a href="/auctions/${a.id}"><span class="n">${String(i+1).padStart(2,'0')}</span><span><b>${a.name}</b> <span>· ${a.city}, ${a.state}</span></span><span>${a.vehicles_count} lots</span><span class="t ${soon?'soon':''}">${left}</span></a>`});
// slow continuous drift (~40px/s); back to the first car at the end; pauses on hover/focus and briefly after arrow use
const SPEED=40;let hold=false,pauseTill=0,last=0,pos=0;
const page=d=>{pauseTill=performance.now()+4000;deals.style.scrollBehavior='smooth';deals.scrollBy({left:d*deals.clientWidth});setTimeout(()=>{pos=deals.scrollLeft;deals.style.scrollBehavior=''},700)};
prev.onclick=()=>page(-1);next.onclick=()=>page(1);
['mouseenter','focusin'].forEach(e=>deals.addEventListener(e,()=>hold=true));['mouseleave','focusout'].forEach(e=>deals.addEventListener(e,()=>{hold=false;pos=deals.scrollLeft}));
function drift(t){const dt=last?Math.min(t-last,100):0;last=t;
 if(!hold&&t>pauseTill&&!document.hidden){pos+=SPEED*dt/1000;if(pos>=deals.scrollWidth-deals.clientWidth-1){pos=0;pauseTill=t+1500}deals.scrollLeft=pos}
 raf=requestAnimationFrame(drift)}
let raf;onStop(()=>cancelAnimationFrame(raf));
if(!matchMedia('(prefers-reduced-motion: reduce)').matches)raf=requestAnimationFrame(drift);

}
