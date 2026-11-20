import { pic } from '../adapt.js';
// Auction page, ported from design/provenance/auction.html. mount() builds the page inside root.
import { D, SL } from '../sl.js';
import { ENG } from '../engine.js';
import { PAT } from '../patterns.js';
import { HOLO } from '../holo.js';
import { LEDGER } from '../ledger.js';
import { GAL } from '../gallery.js';
import { every, onStop } from '../life.js';
import { API, getJSON } from '../../api.js';
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
// Returns { bid(itemKey, amount, expires, total), saved() } for live bids and garage changes.
export function mount(root, { onSave = () => {}, isSaved = () => false } = {}) {
  root.innerHTML = MARKUP;
  const navr = document.getElementById('navr');
  if (navr) navr.innerHTML = 'Sale closes in <span id="clock"></span>';
  const clock = navr ? navr.querySelector('#clock') : document.createElement('span');
  const $ = id => root.querySelector('#' + id);
  const [seller, where, nlots, hero, rows, lq, lsort, ltog, lpanel, ldg, lnum, lcount] = ['seller', 'where', 'nlots', 'hero', 'rows', 'lq', 'lsort', 'ltog', 'lpanel', 'ldg', 'lnum', 'lcount'].map($);
  const { money, miles, title, fees, allIn, allInText, nextBid, lotNotes, timeLeft, bar } = SL, { gap, gapText, lot, clock: clk, run } = ENG;

seller.textContent=D.auction.seller_name;where.textContent=`${D.auction.seller_city}, ${D.auction.seller_state}`;nlots.textContent=D.auction.vehicles_listed;
every(()=>clock.textContent=clk(D.auction.closes_at),1000);clock.textContent=clk(D.auction.closes_at);
const COPIES=[['value','Value'],['odometer','Odometer'],['vehicle','Vehicle']];
const MICRO='SWIFTLOT LOT CERTIFICATE · '.repeat(40);
const SEAL={value:()=>PAT.inkSeal('Market<br>value'),
 odometer:()=>PAT.odoSeal(),
 vehicle:v=>PAT.vinSeal(v.vin)};
let front='value',stop=null;
// Mirrors the backend's is_rollback (inspection_scraper.py): a middle reading out of line with both neighbours,
// while those neighbours agree with each other, is a likely inspector typo and is left out of the rollback check.
// p is oldest-first; returns the indexes of likely typos.
const typos=p=>{const s=new Set();for(let i=1;i<p.length-1;i++){const a=p[i-1].miles,b=p[i+1].miles,x=p[i].miles;if(a<=b&&!(a-2000<=x&&x<=b+2000))s.add(i)}return s};
const chart=v=>{const p=[...v.odometer].reverse();if(p.length<2)return '';
 const W=560,H=190,L=58,R=14,T=22,B=30,t=p.map(q=>new Date(q.date).getTime()),t0=Math.min(...t),t1=Math.max(...t);
 const step=10**Math.floor(Math.log10(Math.max(...p.map(q=>q.miles))-Math.min(...p.map(q=>q.miles))||1e4)),lo=Math.floor(Math.min(...p.map(q=>q.miles))/step)*step,hi=Math.ceil(Math.max(...p.map(q=>q.miles))/step)*step||lo+step;
 const X=x=>L+(x-t0)/Math.max(t1-t0,1)*(W-L-R),Y=m=>T+(1-(m-lo)/Math.max(hi-lo,1))*(H-T-B),xy=p.map((q,i)=>[X(t[i]),Y(q.miles)]),f=n=>n.toFixed(1);
 const ticks=[0,1,2,3,4].map(k=>lo+(hi-lo)*k/4),yrs=[];for(let y=new Date(t0).getFullYear()+1;y<=new Date(t1).getFullYear();y++)yrs.push(y);
 const ty=typos(p),K=xy.map((q,i)=>i).filter(i=>!ty.has(i)),kxy=K.map(i=>xy[i]);
 const seg=K.slice(1).map((j,k)=>{const i=K[k];return {a:xy[i],b:xy[j],end:j,bad:p[j].miles<p[i].miles-2000,d:p[j].miles-p[i].miles}});
 const line=pts=>pts.map((q,i)=>(i?'L':'M')+f(q[0])+' '+f(q[1])).join('');
 return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Odometer readings over time${v.odo_rollback?', with a rollback':''}">
  <defs><pattern id="hatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="4" stroke="currentColor" stroke-width=".6" opacity=".35"/></pattern>
   <pattern id="hatchR" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)"><line x1="0" y1="0" x2="0" y2="4" stroke="#a3132a" stroke-width=".8" opacity=".45"/></pattern></defs>
  <g class="grid">${ticks.map(m=>`<line x1="${L}" x2="${W-R}" y1="${f(Y(m))}" y2="${f(Y(m))}"/>`).join('')}${yrs.map(y=>`<line y1="${T}" y2="${H-B}" x1="${f(X(new Date(y,0,1)))}" x2="${f(X(new Date(y,0,1)))}"/>`).join('')}</g>
  ${ticks.map(m=>`<text class="ax" x="${L-8}" y="${f(Y(m)+3)}" text-anchor="end">${Math.round(m/1000)}k</text>`).join('')}
  ${yrs.map(y=>`<text class="yr" x="${f(X(new Date(y,0,1)))}" y="${H-10}" text-anchor="middle">${y}</text>`).join('')}
  <line class="base" x1="${L}" x2="${W-R}" y1="${H-B}" y2="${H-B}"/>
  <path d="${line(kxy)}L${f(kxy.at(-1)[0])} ${H-B}L${f(kxy[0][0])} ${H-B}Z" fill="url(#hatch)" style="color:var(--ink)"/>
  ${[...ty].map(i=>`<path class="tline" d="M${f(xy[i-1][0])} ${f(xy[i-1][1])}L${f(xy[i][0])} ${f(xy[i][1])}L${f(xy[i+1][0])} ${f(xy[i+1][1])}"/>`).join('')}
  ${seg.filter(s=>s.bad).map(s=>`<path class="badarea" d="M${f(s.a[0])} ${f(s.a[1])}L${f(s.b[0])} ${f(s.b[1])}L${f(s.b[0])} ${f(s.a[1])}Z"/>`).join('')}
  <path class="ln" d="${line(kxy)}"/>${seg.filter(s=>s.bad).map(s=>`<path class="ln bad" d="M${f(s.a[0])} ${f(s.a[1])}L${f(s.b[0])} ${f(s.b[1])}"/>`).join('')}<path class="ln2" d="${line(kxy)}"/>
  ${xy.map((q,i)=>{const r=seg.find(s=>s.end===i)?.bad;return `<path class="mk ${i===xy.length-1?'last':''} ${r?'r':''} ${ty.has(i)?'typo':''}" d="M${f(q[0])} ${f(q[1]-5)}l5 5l-5 5l-5 -5Z"/>`}).join('')}
  ${[...ty].map(i=>`<text class="tnote" x="${f(xy[i][0]+9)}" y="${f(xy[i][1]+4)}">likely typo</text>`).join('')}
  ${seg.filter(s=>s.bad).map(s=>`<text class="drop" x="${f(s.b[0]+8)}" y="${f((s.a[1]+s.b[1])/2)}">${Math.round(s.d).toLocaleString()} mi</text>`).join('')}
  <text class="now" x="${f(xy.at(-1)[0])}" y="${f(xy.at(-1)[1]-10)}" text-anchor="end">${Math.round(p.at(-1).miles).toLocaleString()} mi</text></svg>`};
function place(){const ids=COPIES.map(c=>c[0]),i=ids.indexOf(front),o=[front,...ids.slice(i+1),...ids.slice(0,i)];
 hero.querySelectorAll('.stack .cert').forEach(c=>{const d=o.indexOf(c.dataset.copy);c.dataset.depth=d;c.style.zIndex=3-d});
 hero.querySelectorAll('.tabs button').forEach(b=>b.setAttribute('aria-selected',b.dataset.copy===front))}
// Autura-style price breakdown for the next bid Autura would accept
const cents=n=>'$'+n.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
const feeBox=v=>{const n=nextBid(v),f=n==null?null:fees(v,n);if(!f)return '';
 const row=(k,a,cls='')=>`<div class="${cls}"><span>${k}</span><i></i><span>${cents(a)}</span></div>`;
 return `<details class="feebox"><summary>Next bid ${money(n)}: ${cents(f.total)} all-in</summary>
  ${row('Bid',f.bid,'h')}${row('Vehicle',f.bid)}
  ${row('Fees',f.platform+f.extra+f.card,'h')}${row(`Platform fee (${+((v.platform_fee_rate??0.125)*100).toFixed(2)}%)`,f.platform)}${f.extra?row('Seller fees',f.extra):''}${row('Card processing (3%)',f.card)}
  ${row('Est. total',f.total,'t')}</details>`};
function draw(v){const b=bar(v),g=gap(v),pts=[...v.odometer].reverse(),no=`SL-${lot(v)}-${v.vin.slice(-6)}`;
 const shell=(k,label,inner)=>`<article class="cert copy-${k}" data-copy="${k}">${(S=>`<div class="guil tile" style="background-image:${S.map(s=>s.img).join(',')};background-position:${S.map(s=>s.pos).join(',')};background-size:${S.map(s=>s.size).join(',')}"></div>`)(PAT.spots({value:'#3f6b5c',odometer:'#35507a',vehicle:'#7a3f45'}[k],v.vin,k))}<div class="micro">${MICRO}</div><div class="micro b">${MICRO}</div>
   ${PAT.strip(k,v.vin,label,k==='odometer'&&v.odo_rollback)}${k==='value'?'':`<div class="sealspot">${SEAL[k](v)}</div>`}
   <div class="c-head"><div><small>Certificate of lot ${label.toLowerCase()}</small><h2>${v.year} ${v.make} ${v.model}</h2></div><div class="no">Certificate no.<b>${no}</b>Copy: ${label}</div></div>${inner}</article>`;
 hero.innerHTML=`<div class="tabs" role="tablist">${COPIES.map(([k,l])=>`<button role="tab" data-copy="${k}">${l}</button>`).join('')}</div><div class="stack" id="stack">
  ${shell('value','Value',`<div class="c-body">${GAL.html(v.images,title(v))}
    <div><div class="field"><small>Held by</small><b style="font-size:15px">${D.auction.seller_name}, ${D.auction.seller_city}</b></div>
     <div class="value"><small>Current bid against comparable sales</small><div class="big ${g==null?'':g<=0?'u':'o'}">${money(v.current_bid)}</div><div style="font-size:13px">${gapText(v)}</div>
      ${b?`<div class="bandbar"><i style="left:${b.lo}%;width:${b.hi-b.lo}%"></i>${b.bid!=null?`<b style="left:${b.bid}%"></b>`:''}</div><div class="vlab"><span>Typical ${money(v.price.low)}–${money(v.price.high)}</span><span>${v.price.count} sales</span></div>`:''}</div>
     <div class="grid2"><div class="field"><small>If you win now</small><b>${allInText(v)}</b></div><div class="field"><small>Bidding closes in</small><b>${timeLeft(v.bid_expiration)}</b></div></div>${feeBox(v)}
     ${lotNotes(v).length?`<ul class="lotnotes">${lotNotes(v).map(n=>`<li>${n}</li>`).join('')}</ul>`:''}<div class="bidhist" data-vin="${v.vin}"></div></div></div>
   <div class="foot">${SEAL.value(v)}<div style="display:flex;gap:10px"><button class="btn" data-save="${v.vin}" aria-pressed="${isSaved(v.vin)}">${isSaved(v.vin)?'Saved to garage':'Save to garage'}</button><a class="btn go" href="https://mp.autura.com/auctions/listings/${v.item_key}" target="_blank" rel="noreferrer" style="display:inline-grid;place-items:center;text-decoration:none">View listing on Autura</a></div></div>`)}
  ${shell('odometer','Odometer',`<div class="status"><span class="sc" style="font-size:13px;letter-spacing:.12em;color:var(--ink2)">Odometer status</span><label><i>${v.odometer.length>1&&!v.odo_rollback?'✓':''}</i>Actual</label><label><i>${v.odo_rollback?'✕':''}</i>Not actual</label></div>
   <div class="chart">${chart(v)}</div><div class="readings" style="max-width:520px">${(ty=>{let prev=null;return pts.map((p,i)=>{if(ty.has(i))return `<div class="typo" title="Out of line with the readings either side, so it's left out of the rollback check"><span>${p.date}</span><span>${miles(p.miles)}</span><span>likely typo</span></div>`;const d=prev==null?null:p.miles-prev;prev=p.miles;return `<div class="${d!=null&&d<-2000?'bad':''}"><span>${p.date}</span><span>${miles(p.miles)}</span><span>${d==null?'':(d>=0?'+':'')+Math.round(d).toLocaleString()}</span></div>`}).join('')})(typos(pts))||'<div><span>No odometer records</span></div>'}</div>
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
 loadBids(v);
 hero.querySelector('[data-save]')?.addEventListener('click',e=>onSave(e.currentTarget.dataset.save));
 stop&&stop();stop=HOLO.track(document.getElementById('stack'),{tilt:3})}
// Bid history under the value: a step line of the standing bid over time. Cached per car for 20s since every
// live bid redraws the certificate; the API caches Autura's side for 30s.
const bidCache=new Map();
const ago=iso=>{const m=(Date.now()-new Date(iso))/6e4;return m<60?`${Math.max(1,Math.round(m))}m ago`:m<1440?`${Math.round(m/60)}h ago`:`${Math.round(m/1440)}d ago`};
function bidChart(b){const W=300,H=56,t0=+new Date(b[0].at),t1=Math.max(+new Date(b.at(-1).at),t0+1),lo=b[0].amount,hi=Math.max(b.at(-1).amount,lo+1);
 const X=t=>4+(W-8)*(t-t0)/(t1-t0),Y=a=>H-6-(H-12)*(a-lo)/(hi-lo);let d=`M${X(t0).toFixed(1)} ${Y(lo).toFixed(1)}`;
 b.forEach(x=>{const xx=X(+new Date(x.at)).toFixed(1);d+=`H${xx}V${Y(x.amount).toFixed(1)}`});
 return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img" aria-label="Bids from ${money(lo)} to ${money(b.at(-1).amount)}"><path d="${d}" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="${X(+new Date(b.at(-1).at)).toFixed(1)}" cy="${Y(b.at(-1).amount).toFixed(1)}" r="3" fill="currentColor"/></svg>`}
function loadBids(v){const box=hero.querySelector(`.bidhist[data-vin="${v.vin}"]`);if(!box)return;
 // history includes bids a max bid beat in the same instant, so plot the running high: the standing bid
 const show=r=>{if(!box.isConnected)return;let top=0;const b=r.bids.map(x=>({at:x.at,amount:top=Math.max(top,x.amount)}));
  box.innerHTML=!b.length?'':`<small>Bid history</small>${b.length>1?bidChart(b):''}<p>${r.total} bid${r.total===1?'':'s'}, ${money(b[0].amount)} to ${money(b.at(-1).amount)}. Last bid ${ago(b.at(-1).at)}.</p>`};
 const c=bidCache.get(v.vin);if(c&&Date.now()-c.t<2e4)return show(c.r);
 getJSON(`${API}/vehicles/${encodeURIComponent(v.vin)}/bids`).then(r=>{bidCache.set(v.vin,{t:Date.now(),r});show(r)}).catch(()=>{})}
const mi=v=>v.odometer[0]?.miles;
const words=v=>{const t=lq.value.trim().toLowerCase().split(/\s+/).filter(Boolean),hay=`${v.year} ${v.make} ${v.model} ${v.vin}`.toLowerCase();return t.every(w=>hay.includes(w))};
const keep=v=>words(v)&&L.match(v);
const cmp=()=>({deal:null,low:(a,b)=>(a.current_bid??1e9)-(b.current_bid??1e9),close:(a,b)=>new Date(a.bid_expiration)-new Date(b.bid_expiration),miles:(a,b)=>(mi(a)??1e9)-(mi(b)??1e9),new:(a,b)=>b.year-a.year})[lsort.value];
const closeL=()=>{lpanel.hidden=true;ltog.setAttribute('aria-expanded',false);ltog.focus()};
const L=LEDGER.mount(ldg,{vehicles:D.vehicles,gap,pre:words,onChange:()=>refilter(),onDone:closeL});
// Desktop: the certificate is pinned beside the list, so picking a lot just swaps it. Otherwise scroll to the
// certificate and offer a way back to the row the reader came from.
const back=document.createElement('button');back.type='button';back.className='btn go backlist';back.hidden=true;root.append(back);
let arriving=false;
const reveal=(v,el)=>{if(getComputedStyle(hero).position==='sticky')return;
 arriving=true;hero.scrollIntoView({behavior:'smooth',block:'start'});back.textContent=`Back to lot ${+el.dataset.i+1}`;back.hidden=false;
 back.onclick=()=>{back.hidden=true;el.scrollIntoView({behavior:'smooth',block:'center'});el.focus({preventScroll:true})}};
// hide once the reader scrolls on past the certificate by themselves (not during the scroll up to it)
const hideBack=()=>{const r=hero.getBoundingClientRect();if(arriving){if(r.top>-20&&r.top<innerHeight/2)arriving=false;return}if(!back.hidden&&r.bottom<0)back.hidden=true};
window.addEventListener('scroll',hideBack,{passive:true});onStop(()=>window.removeEventListener('scroll',hideBack));
const list=run({keep,cmp,reveal,rowsEl:rows,rowH:106,rowClass:'mini',
 row:(v,c)=>{const b=bar(v),g=gap(v);return `<span class="stub">${PAT.lat(PAT.verdict(v,g))}<small>${c.pole?'Best':'Lot'}</small><b>${c.pos}</b></span><img src="${pic(v.images[0],'THUMBNAIL')}" alt="" loading="lazy">
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
