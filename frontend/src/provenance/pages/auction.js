// Auction page, ported from design/provenance/auction.html. mount() builds the page inside root.
import { D, SL } from '../sl.js';
import { ENG } from '../engine.js';
import { PAT } from '../patterns.js';
import { HOLO } from '../holo.js';
import { LEDGER } from '../ledger.js';
import { GAL } from '../gallery.js';
import { every } from '../life.js';
import './auction.css';

const MARKUP = `<main class="page">
 <aside class="side"><div class="yticket">
  <div class="yt-top"><div><h1 id="seller"></h1><p id="where"></p></div><div class="yt-stub"><b id="nlots"></b><small>Lots</small></div></div>
  <div class="perf" aria-hidden="true"></div>
  <div class="lotfind"><input type="search" id="lq" placeholder="Find a lot: 2019 civic, f-150, VIN" aria-label="Find a lot">
   <div class="lrow"><select id="lsort" aria-label="Sort lots"><option value="deal">Best value first</option><option value="low">Lowest bid</option><option value="close">Closing soonest</option><option value="miles">Lowest miles</option><option value="new">Newest year</option></select>
    <button class="btn" id="ltog" aria-expanded="false" aria-controls="lpanel">Filters <span id="lnum"></span></button></div>
   <div class="lpanel" id="lpanel" hidden>
    <div class="ldg" id="ldg"></div></div>
   <p id="lcount" aria-live="polite"></p></div></div>
  <div id="rows"></div></aside>
 <section id="hero" aria-live="polite"></section>
</main>`;

// opts.onSave(vin) toggles the garage; opts.isSaved(vin) says whether it is saved.
// Returns { bid(itemKey, amount, expires), saved() } for live bids and garage changes.
export function mount(root, { onSave = () => {}, isSaved = () => false } = {}) {
  root.innerHTML = MARKUP;
  const navr = document.getElementById('navr');
  if (navr) navr.innerHTML = 'Sale closes in <span id="clock"></span>';
  const clock = navr ? navr.querySelector('#clock') : document.createElement('span');
  const $ = id => root.querySelector('#' + id);
  const [seller, where, nlots, hero, rows, lq, lsort, ltog, lpanel, ldg, lnum, lcount] = ['seller', 'where', 'nlots', 'hero', 'rows', 'lq', 'lsort', 'ltog', 'lpanel', 'ldg', 'lnum', 'lcount'].map($);
  const { money, miles, title, allIn, timeLeft, bar } = SL, { gap, gapText, lot, clock: clk, run } = ENG;

seller.textContent=D.auction.seller_name;where.textContent=`${D.auction.seller_city}, ${D.auction.seller_state}`;nlots.textContent=D.auction.vehicles_listed;
every(()=>clock.textContent=clk(D.auction.closes_at),1000);clock.textContent=clk(D.auction.closes_at);
const COPIES=[['value','Value'],['odometer','Odometer'],['vehicle','Vehicle']];
const MICRO='SWIFTLOT LOT CERTIFICATE · '.repeat(40);
const SEAL={value:()=>PAT.inkSeal('Market<br>value'),
 odometer:()=>PAT.odoSeal(),
 vehicle:v=>PAT.vinSeal(v.vin)};
let front='value',stop=null;
const chart=v=>{const p=[...v.odometer].reverse();if(p.length<2)return '';
 const W=560,H=190,L=58,R=14,T=22,B=30,t=p.map(q=>new Date(q.date).getTime()),t0=Math.min(...t),t1=Math.max(...t);
 const step=10**Math.floor(Math.log10(Math.max(...p.map(q=>q.miles))-Math.min(...p.map(q=>q.miles))||1e4)),lo=Math.floor(Math.min(...p.map(q=>q.miles))/step)*step,hi=Math.ceil(Math.max(...p.map(q=>q.miles))/step)*step||lo+step;
 const X=x=>L+(x-t0)/Math.max(t1-t0,1)*(W-L-R),Y=m=>T+(1-(m-lo)/Math.max(hi-lo,1))*(H-T-B),xy=p.map((q,i)=>[X(t[i]),Y(q.miles)]),f=n=>n.toFixed(1);
 const ticks=[0,1,2,3,4].map(k=>lo+(hi-lo)*k/4),yrs=[];for(let y=new Date(t0).getFullYear()+1;y<=new Date(t1).getFullYear();y++)yrs.push(y);
 const seg=xy.slice(1).map((b,i)=>({a:xy[i],b,bad:p[i+1].miles<p[i].miles-2000,d:p[i+1].miles-p[i].miles}));
 const line=pts=>pts.map((q,i)=>(i?'L':'M')+f(q[0])+' '+f(q[1])).join('');
 return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Odometer readings over time${v.odo_rollback?', with a rollback':''}">
  <defs><pattern id="hatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="4" stroke="currentColor" stroke-width=".6" opacity=".35"/></pattern>
   <pattern id="hatchR" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)"><line x1="0" y1="0" x2="0" y2="4" stroke="#a3132a" stroke-width=".8" opacity=".45"/></pattern></defs>
  <g class="grid">${ticks.map(m=>`<line x1="${L}" x2="${W-R}" y1="${f(Y(m))}" y2="${f(Y(m))}"/>`).join('')}${yrs.map(y=>`<line y1="${T}" y2="${H-B}" x1="${f(X(new Date(y,0,1)))}" x2="${f(X(new Date(y,0,1)))}"/>`).join('')}</g>
  ${ticks.map(m=>`<text class="ax" x="${L-8}" y="${f(Y(m)+3)}" text-anchor="end">${Math.round(m/1000)}k</text>`).join('')}
  ${yrs.map(y=>`<text class="yr" x="${f(X(new Date(y,0,1)))}" y="${H-10}" text-anchor="middle">${y}</text>`).join('')}
  <line class="base" x1="${L}" x2="${W-R}" y1="${H-B}" y2="${H-B}"/>
  <path d="${line(xy)}L${f(xy.at(-1)[0])} ${H-B}L${f(xy[0][0])} ${H-B}Z" fill="url(#hatch)" style="color:var(--ink)"/>
  ${seg.filter(s=>s.bad).map(s=>`<path class="badarea" d="M${f(s.a[0])} ${f(s.a[1])}L${f(s.b[0])} ${f(s.b[1])}L${f(s.b[0])} ${f(s.a[1])}Z"/>`).join('')}
  <path class="ln" d="${line(xy)}"/>${seg.filter(s=>s.bad).map(s=>`<path class="ln bad" d="M${f(s.a[0])} ${f(s.a[1])}L${f(s.b[0])} ${f(s.b[1])}"/>`).join('')}<path class="ln2" d="${line(xy)}"/>
  ${xy.map((q,i)=>{const r=seg[i-1]?.bad;return `<path class="mk ${i===xy.length-1?'last':''} ${r?'r':''}" d="M${f(q[0])} ${f(q[1]-5)}l5 5l-5 5l-5 -5Z"/>`}).join('')}
  ${seg.filter(s=>s.bad).map(s=>`<text class="drop" x="${f(s.b[0]+8)}" y="${f((s.a[1]+s.b[1])/2)}">${Math.round(s.d).toLocaleString()} mi</text>`).join('')}
  <text class="now" x="${f(xy.at(-1)[0])}" y="${f(xy.at(-1)[1]-10)}" text-anchor="end">${Math.round(p.at(-1).miles).toLocaleString()} mi</text></svg>`};
function place(){const ids=COPIES.map(c=>c[0]),i=ids.indexOf(front),o=[front,...ids.slice(i+1),...ids.slice(0,i)];
 hero.querySelectorAll('.stack .cert').forEach(c=>{const d=o.indexOf(c.dataset.copy);c.dataset.depth=d;c.style.zIndex=3-d});
 hero.querySelectorAll('.tabs button').forEach(b=>b.setAttribute('aria-selected',b.dataset.copy===front))}
function draw(v){const b=bar(v),g=gap(v),pts=[...v.odometer].reverse(),no=`SL-${lot(v)}-${v.vin.slice(-6)}`;
 const shell=(k,label,inner)=>`<article class="cert copy-${k}" data-copy="${k}">${(S=>`<div class="guil tile" style="background-image:${S.map(s=>s.img).join(',')};background-position:${S.map(s=>s.pos).join(',')};background-size:${S.map(s=>s.size).join(',')}"></div>`)(PAT.spots({value:'#3f6b5c',odometer:'#35507a',vehicle:'#7a3f45'}[k],v.vin,k))}<div class="micro">${MICRO}</div><div class="micro b">${MICRO}</div>
   ${PAT.strip(k,v.vin,label,k==='odometer'&&v.odo_rollback)}${k==='value'?'':`<div class="sealspot">${SEAL[k](v)}</div>`}
   <div class="c-head"><div><small>Certificate of lot ${label.toLowerCase()}</small><h2>${v.year} ${v.make} ${v.model}</h2></div><div class="no">Certificate no.<b>${no}</b>Copy: ${label}</div></div>${inner}</article>`;
 hero.innerHTML=`<div class="tabs" role="tablist">${COPIES.map(([k,l])=>`<button role="tab" data-copy="${k}">${l}</button>`).join('')}</div><div class="stack" id="stack">
  ${shell('value','Value',`<div class="c-body">${GAL.html(v.images,title(v))}
    <div><div class="field"><small>Held by</small><b style="font-size:15px">${D.auction.seller_name}, ${D.auction.seller_city}</b></div>
     <div class="value"><small>Current bid against comparable sales</small><div class="big ${g==null?'':g<=0?'u':'o'}">${money(v.current_bid)}</div><div style="font-size:13px">${gapText(v)}</div>
      ${b?`<div class="bandbar"><i style="left:${b.lo}%;width:${b.hi-b.lo}%"></i>${b.bid!=null?`<b style="left:${b.bid}%"></b>`:''}</div><div class="vlab"><span>Typical ${money(v.price.low)}–${money(v.price.high)}</span><span>${v.price.count} sales</span></div>`:''}</div>
     <div class="grid2"><div class="field"><small>If you win now</small><b>${money(allIn(v))}</b></div><div class="field"><small>Bidding closes in</small><b>${timeLeft(v.bid_expiration)}</b></div></div></div></div>
   <div class="foot">${SEAL.value(v)}<div style="display:flex;gap:10px"><button class="btn" data-save="${v.vin}" aria-pressed="${isSaved(v.vin)}">${isSaved(v.vin)?'Saved to garage':'Save to garage'}</button><a class="btn go" href="https://mp.autura.com/auctions/listings/${v.item_key}" target="_blank" rel="noreferrer" style="display:inline-grid;place-items:center;text-decoration:none">View listing on Autura</a></div></div>`)}
  ${shell('odometer','Odometer',`<div class="status"><span class="sc" style="font-size:13px;letter-spacing:.12em;color:var(--ink2)">Odometer status</span><label><i>${v.odometer.length&&!v.odo_rollback?'✓':''}</i>Actual</label><label><i>${v.odo_rollback?'✕':''}</i>Not actual</label></div>
   <div class="chart">${chart(v)}</div><div class="readings" style="max-width:520px">${pts.map((p,i)=>{const d=i?p.miles-pts[i-1].miles:null;return `<div class="${d!=null&&d<-2000?'bad':''}"><span>${p.date}</span><span>${miles(p.miles)}</span><span>${d==null?'':(d>=0?'+':'')+Math.round(d).toLocaleString()}</span></div>`}).join('')||'<div><span>No Texas records</span></div>'}</div>
   ${v.odo_rollback?'<div class="brand rb-stamp">Odometer<br>not actual<small>Texas inspection discrepancy</small></div>':''}`)}
  ${shell('vehicle','Vehicle',`<div class="c-body"><div><div class="grid2"><div class="field"><small>VIN</small><b style="font-size:14px">${v.vin}</b></div><div class="field"><small>Colour</small><b>${v.color||'—'}</b></div>
    <div class="field"><small>Engine</small><b>${v.engine_type||'—'}</b></div><div class="field"><small>Drive</small><b>${v.drivetrain||'—'}</b></div><div class="field"><small>Keys</small><b>${v.key_status||'—'}</b></div><div class="field"><small>Starts</small><b>${v.start_status||'—'}</b></div></div>
    <p style="margin-top:12px;font:italic 500 16px Cormorant;color:var(--ink2)">${v.seller_notes||'No notes from the yard.'}</p></div>
    ${GAL.html(v.images,title(v))}</div>`)}
 </div>`;
 place();
 hero.querySelectorAll('.tabs button').forEach(bt=>bt.onclick=()=>{front=bt.dataset.copy;place()});
 hero.querySelectorAll('.stack .cert').forEach(c=>c.addEventListener('click',e=>{if(c.dataset.depth!=='0'&&!e.target.closest('button')){front=c.dataset.copy;place()}}));
 GAL.bind(hero);
 hero.querySelector('[data-save]')?.addEventListener('click',e=>onSave(e.currentTarget.dataset.save));
 stop&&stop();stop=HOLO.track(document.getElementById('stack'),{tilt:3})}
const mi=v=>v.odometer[0]?.miles;
const words=v=>{const t=lq.value.trim().toLowerCase().split(/\s+/).filter(Boolean),hay=`${v.year} ${v.make} ${v.model} ${v.vin}`.toLowerCase();return t.every(w=>hay.includes(w))};
const keep=v=>words(v)&&L.match(v);
const cmp=()=>({deal:null,low:(a,b)=>(a.current_bid??1e9)-(b.current_bid??1e9),close:(a,b)=>new Date(a.bid_expiration)-new Date(b.bid_expiration),miles:(a,b)=>(mi(a)??1e9)-(mi(b)??1e9),new:(a,b)=>b.year-a.year})[lsort.value];
const closeL=()=>{lpanel.hidden=true;ltog.setAttribute('aria-expanded',false);ltog.focus()};
const L=LEDGER.mount(ldg,{vehicles:D.vehicles,gap,pre:words,onChange:()=>refilter(),onDone:closeL});
const list=run({keep,cmp,rowsEl:rows,rowH:106,rowClass:'mini',
 row:(v,c)=>{const b=bar(v),g=gap(v);return `<span class="stub">${PAT.lat(PAT.verdict(v,g))}<small>${c.pole?'Best':'Lot'}</small><b>${c.pos}</b></span><img src="${v.images[0]||''}" alt="">
  <span class="body"><b>${title(v)}</b><small class="${v.odo_rollback?'bad':''}">${v.odo_rollback?'Odometer not actual':gapText(v)}</small>${b&&b.bid!=null?`<span class="mbar" aria-hidden="true"><i style="left:${b.lo}%;width:${b.hi-b.lo}%"></i><u style="left:${b.bid}%"></u></span>`:''}</span>
  <span class="bid ${g!=null&&g<=0?'u':''}">${money(v.current_bid)}<small>${allIn(v)!=null?money(allIn(v))+' all-in':'No bids'}</small></span>`},
 hero:draw});
const refilter=()=>{const n=list.paint().length;lcount.textContent=n===D.vehicles.length?'':`${n} of ${D.vehicles.length} lots`;
 lnum.textContent=L.active()||''};
lq.oninput=()=>{L.refresh();refilter()};lsort.oninput=refilter;
ltog.onclick=()=>{const o=lpanel.hidden;lpanel.hidden=!o;ltog.setAttribute('aria-expanded',o)};

  return {
    bid: (k, a, e) => list.bid(k, a, e),
    saved: () => { const b = hero.querySelector('[data-save]'); if (b) { const s = isSaved(b.dataset.save); b.setAttribute('aria-pressed', s); b.textContent = s ? 'Saved to garage' : 'Save to garage'; } },
  };
}
