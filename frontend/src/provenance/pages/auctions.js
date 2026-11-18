// Auctions page, ported from design/provenance/auctions.html. mount() builds the page inside root.
import { D } from '../sl.js';
import { PAT } from '../patterns.js';
import { HOLO } from '../holo.js';
import { every } from '../life.js';
import './auctions.css';

const MARKUP = `<main class="wrap">
 <section class="band tk"><div class="main"><div id="g"></div><h1 class="pg">Notices of sale</h1><p class="lede">Every live tow-yard sale. Texas yards are marked <b>Odometer records</b>: their cars come with state inspection mileage.</p>
  <div class="pills" id="pills" role="group" aria-label="Filter by state (pick any number)"></div></div>
  <div class="stub"><b id="tn"></b><small>Live sales</small><i id="ts"></i></div></section>
 <div class="finder" role="search"><input type="search" id="fq" placeholder="Yard or city: Walnut Hill, Dallas" aria-label="Search sales by yard or city">
  <button type="button" class="lchip" id="fodo" aria-pressed="false">Odometer records</button><button type="button" class="lchip" id="fsoon" aria-pressed="false">Closing within a day</button><button type="button" class="lchip" id="fopen" aria-pressed="true">Hide closed</button>
  <select id="fsort" aria-label="Sort sales"><option value="close">Closing soonest</option><option value="lots">Most lots</option><option value="name">Yard name</option></select>
  <span class="cnt"><span id="fcount" aria-live="polite"></span><button type="button" id="fclr" hidden>Clear</button></span></div>
 <div id="out"></div>
</main>`;

export function mount(root) {
  root.innerHTML = MARKUP;
  const $ = id => root.querySelector('#' + id);
  const [g, tn, ts, pills, fq, fodo, fsoon, fopen, fsort, fcount, fclr, out] = ['g', 'tn', 'ts', 'pills', 'fq', 'fodo', 'fsoon', 'fopen', 'fsort', 'fcount', 'fclr', 'out'].map($);
  const tot = document.getElementById('navr');

g.innerHTML=`<div class="guil">${PAT.waves('#8796c0')}</div>`;
const A=D.auctions;tn.textContent=A.length;ts.textContent=`${A.reduce((s,a)=>s+a.vehicles_count,0)} lots`;if(tot)tot.textContent=`${A.length} sales · ${A.reduce((s,a)=>s+a.vehicles_count,0)} lots`;
const left=iso=>{const ms=new Date(iso)-Date.now();if(!(ms>0))return 'Closed';const h=ms/36e5;return h<24?`${Math.floor(h)}h ${Math.floor(ms%36e5/6e4)}m`:`${Math.floor(h/24)}d ${Math.floor(h%24)}h`};
const states=[...new Set(A.map(a=>a.state))].sort(),pick=new Set();
const card=(a,i)=>{const soon=new Date(a.closes_at)-Date.now()<864e5;return `<a class="notice ${new Date(a.closes_at)<=Date.now()?'closed':''}" href="/auctions/${a.id}"> <div class="hd"><span>NOTICE OF SALE · ${a.state}</span><b>NO. ${String(i+1).padStart(3,'0')}</b></div><h3>${a.name}</h3><div class="city">${a.city}, ${a.state}</div>${a.state==='TX'?'<span class="tx">Odometer records</span>':''}
 <div class="ft"><div><b>${a.vehicles_count}</b><small>${a.vehicles_count===1?'Lot':'Lots'}</small></div><div class="cl"><small>Closes in</small><b class="${soon?'soon':''}" data-close="${a.closes_at}">${left(a.closes_at)}</b></div></div></a>`};
const on=b=>b.getAttribute('aria-pressed')==='true';
// everything except the state choice, so each state ticket can show how many sales it would add
const base=a=>{const ms=new Date(a.closes_at)-Date.now(),t=fq.value.trim().toLowerCase();
 return (!t||`${a.name} ${a.city} ${a.state}`.toLowerCase().includes(t))&&(!on(fodo)||a.state==='TX')&&(!on(fsoon)||ms>0&&ms<864e5)&&(!on(fopen)||ms>0)};
function render(){const pool=A.filter(base);
 pills.innerHTML=[['All',pool.length,!pick.size],...states.map(s=>[s,pool.filter(a=>a.state===s).length,pick.has(s)])].map(([s,n,p])=>`<button aria-pressed="${p}" data-s="${s}" aria-label="${s}, ${n} ${n===1?'sale':'sales'}" ${!n&&!p&&s!=='All'?'style="opacity:.45"':''}><b>${s}</b><small>${n}</small></button>`).join('');
 const l=pool.filter(a=>!pick.size||pick.has(a.state)).sort({close:(a,b)=>new Date(a.closes_at)-new Date(b.closes_at),lots:(a,b)=>b.vehicles_count-a.vehicles_count,name:(a,b)=>a.name.localeCompare(b.name)}[fsort.value]),now=Date.now();
 const lots=l.reduce((s,a)=>s+a.vehicles_count,0);fcount.textContent=`${l.length} ${l.length===1?'sale':'sales'} · ${lots} lots`;
 fclr.hidden=!(pick.size||fq.value||on(fodo)||on(fsoon)||!on(fopen));
 const ms=a=>new Date(a.closes_at)-now,gs=fsort.value!=='close'?[['',l]]:[['Closing within a day',l.filter(a=>ms(a)>0&&ms(a)<864e5)],['Closing later',l.filter(a=>ms(a)>=864e5)],['Closed',l.filter(a=>ms(a)<=0)]].filter(x=>x[1].length);
 out.innerHTML=l.length?gs.map(([h,x])=>`${h?`<div class="group ${h==='Closed'?'closed':''}"><span>${h}</span></div>`:'<div style="height:22px"></div>'}<div class="cards">${x.map(a=>card(a,A.indexOf(a))).join('')}</div>`).join(''):'<p class="empty">No sales match. Try another state or clear the filters.</p>';
 out.querySelectorAll('.notice').forEach(n=>HOLO.track(n,{tilt:0}))}
pills.onclick=e=>{const b=e.target.closest('button');if(!b)return;const s=b.dataset.s;s==='All'?pick.clear():pick.has(s)?pick.delete(s):pick.add(s);render();pills.querySelector(`[data-s="${s}"]`).focus()};
[fodo,fsoon,fopen].forEach(b=>b.onclick=()=>{b.setAttribute('aria-pressed',!on(b));render()});
fq.oninput=render;fsort.oninput=render;
fclr.onclick=()=>{pick.clear();fq.value='';fodo.setAttribute('aria-pressed',false);fsoon.setAttribute('aria-pressed',false);fopen.setAttribute('aria-pressed',true);render()};
render();
// timers tick: hh:mm:ss under a day, d h above
const tick=iso=>{const s=(new Date(iso)-Date.now())/1e3|0;if(s<=0)return 'Closed';const p=n=>String(n).padStart(2,'0');return s<86400?`${p(s/3600|0)}:${p(s%3600/60|0)}:${p(s%60)}`:left(iso)};
every(()=>out.querySelectorAll('[data-close]').forEach(b=>b.textContent=tick(b.dataset.close)),1000);

}
