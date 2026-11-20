// Ledger filter panel: accordion sections (value, make → model, year, price, odometer, condition) with live counts,
// histogram range sliders and removable tags. Used by the Search sidebar and the auction page's Filters dropdown.
// LEDGER.mount(el, {vehicles, gap, pre, onChange, onDone, open}) → {match, active, clear, refresh}
export const LEDGER = (() => {
  const VL = { under: 'Under median', over: 'At or over', rb: 'Rollback' };
  const FACETS = ['make', 'model', 'start_status', 'engine_type', 'drivetrain'];
  // the feed spells drivetrains several ways; group them so each choice appears once
  const drive = s => !s ? null : /4wd|4x4|awd|all/i.test(s) ? '4WD / AWD' : /fwd|front/i.test(s) ? 'Front-wheel' : /rwd|rear/i.test(s) ? 'Rear-wheel' : /4x2/i.test(s) ? '2WD' : s;
  const fmt = { year: x => x, miles: x => Math.round(x / 1000) + 'k mi', bid: x => '$' + x.toLocaleString() };

  function mount(el, { vehicles: V, gap, pre = () => true, onChange = () => {}, onDone, open = ['Value', 'Make'] }) {
    const miles = v => v.odometer[0]?.miles ?? null, verdict = v => v.odo_rollback ? 'rb' : (gap(v) ?? 1) <= 0 ? 'under' : 'over';
    const val = (v, k) => k === 'drivetrain' ? drive(v[k]) : k === 'verdict' ? verdict(v) : v[k];
    const uniq = k => [...new Set(V.map(v => val(v, k)).filter(Boolean))].sort();
    const R = { year: { get: v => v.year, step: 1 }, miles: { get: miles, step: 10000 }, bid: { get: v => v.current_bid, step: 250 } };
    for (const r of Object.values(R)) { const xs = V.map(r.get).filter(x => x != null); r.min = Math.floor(Math.min(...xs) / r.step) * r.step; r.max = Math.ceil(Math.max(...xs) / r.step) * r.step || r.min + r.step; }
    const fresh = () => ({ verdict: new Set(), ...Object.fromEntries(FACETS.map(k => [k, new Set()])), hasOdo: false, year: null, miles: null, bid: null });
    let s = fresh(); const opened = new Set(open);

    const match = (v, skip) => {
      for (const k of ['verdict', ...FACETS]) if (k !== skip && s[k].size && !s[k].has(val(v, k))) return false;
      if (s.hasOdo && !v.odometer.length) return false;
      for (const k in R) if (k !== skip && s[k]) { const x = R[k].get(v); if (x == null || x < s[k][0] || x > s[k][1]) return false; }
      return true;
    };
    const pool = skip => V.filter(v => pre(v) && match(v, skip));
    const total = () => pool().length;
    const picked = k => R[k] ? (s[k] ? `${fmt[k](s[k][0])}–${fmt[k](s[k][1])}` : '') : k === 'hasOdo' ? (s.hasOdo ? 'TX records' : '') : [...s[k]].map(o => k === 'verdict' ? VL[o] : o).join(', ');
    const active = () => ['verdict', ...FACETS].reduce((n, k) => n + s[k].size, 0) + Object.keys(R).filter(k => s[k]).length + (s.hasOdo ? 1 : 0);

    const chips = (k, opts, lab = o => o, v = false) => { const p = pool(k); return `<div class="lchips">${opts.map(o => { const n = p.filter(x => val(x, k) === o).length, on = s[k].has(o);
      return `<button type="button" class="lchip${v ? ' v ' + o : ''}" data-k="${k}" data-o="${o}" aria-pressed="${on}" ${!n && !on ? 'disabled' : ''}>${v ? '<b></b>' : ''}${lab(o)}<i>${n}</i></button>`; }).join('')}</div>`; };
    const range = k => { const r = R[k], [lo, hi] = s[k] || [r.min, r.max], N = 14, w = (r.max - r.min) / N || 1, b = Array(N).fill(0);
      pool(k).forEach(v => { const x = r.get(v); if (x != null) b[Math.min(N - 1, Math.floor((x - r.min) / w))]++; }); const m = Math.max(...b, 1), pc = x => (x - r.min) / (r.max - r.min) * 100;
      return `<div class="lrange" data-r="${k}"><div class="bars" aria-hidden="true">${b.map((n, i) => `<i class="${r.min + (i + 1) * w > lo && r.min + i * w <= hi ? 'on' : ''}" style="height:${n / m * 100}%"></i>`).join('')}</div>
        <div class="rail"><b style="left:${pc(lo)}%;right:${100 - pc(hi)}%"></b><input type="range" min="${r.min}" max="${r.max}" step="${r.step}" value="${lo}" aria-label="Minimum ${k}"><input type="range" min="${r.min}" max="${r.max}" step="${r.step}" value="${hi}" aria-label="Maximum ${k}"></div>
        <div class="lab"><span>${fmt[k](lo)}</span><span>${fmt[k](hi)}</span></div></div>`; };
    const acc = (t, keys, body) => `<div class="lacc${opened.has(t) ? ' open' : ''}" data-t="${t}"><button type="button" class="lhead" aria-expanded="${opened.has(t)}"><h4>${t}</h4><em>${keys.map(picked).filter(Boolean).join(' · ')}</em></button><div class="lbody2">${body}</div></div>`;
    const group = (k, label) => { const o = uniq(k); return o.length > 1 ? `<div><small>${label}</small>${chips(k, o)}</div>` : ''; };

    function draw() {
      const tags = [...['verdict', ...FACETS].flatMap(k => [...s[k]].map(o => [k + '|' + o, k === 'verdict' ? VL[o] : o])), ...Object.keys(R).filter(k => s[k]).map(k => [k + '|', picked(k)]), ...(s.hasOdo ? [['hasOdo|', 'Has odometer records']] : [])];
      const models = uniq('model').filter(m => !s.make.size || V.some(v => v.model === m && s.make.has(v.make)));
      const cond = group('start_status', 'Runs') + group('engine_type', 'Engine') + group('drivetrain', 'Drivetrain');
      el.innerHTML = `<div class="ltags">${tags.map(([k, l]) => `<button type="button" data-tag="${k}" aria-label="Remove filter ${l}">${l}</button>`).join('')}</div>
        ${acc('Value', ['verdict'], chips('verdict', ['under', 'over', 'rb'], o => VL[o], true))}
        ${acc('Make', ['make', 'model'], chips('make', uniq('make')) + (s.make.size ? `<div class="lsub"><small>Models</small>${chips('model', models)}</div>` : ''))}
        ${acc('Year', ['year'], range('year'))}${acc('Price', ['bid'], range('bid'))}
        ${acc('Odometer', ['miles', 'hasOdo'], range('miles') + `<label class="lck"><input type="checkbox" data-ck="hasOdo" ${s.hasOdo ? 'checked' : ''}>Only cars with odometer records</label>`)}
        ${cond ? acc('Condition', ['start_status', 'engine_type', 'drivetrain'], `<div class="lgrid">${cond}</div>`) : ''}
        <div class="lfoot"><button type="button" class="btn lclear" data-clear ${active() ? '' : 'disabled'}>Clear</button>${onDone ? `<button type="button" class="btn ldone" data-done>Show ${total()} lots</button>` : `<span>${total()} of ${V.length} lots</span>`}</div>`;
    }
    const changed = (refocus) => { draw(); onChange(); if (refocus) el.querySelector(refocus)?.focus(); };

    el.addEventListener('click', e => { const b = e.target.closest('button'); if (!b || b.disabled) return;
      if (b.dataset.done != null) return onDone();
      if (b.dataset.clear != null) s = fresh();
      else if (b.dataset.tag) { const [k, o] = b.dataset.tag.split('|'); R[k] ? s[k] = null : k === 'hasOdo' ? s.hasOdo = false : s[k].delete(o); }
      else if (b.dataset.k) { const set = s[b.dataset.k]; set.has(b.dataset.o) ? set.delete(b.dataset.o) : set.add(b.dataset.o);
        if (b.dataset.k === 'make') s.model = new Set([...s.model].filter(m => !s.make.size || V.some(v => v.model === m && s.make.has(v.make)))); }
      else if (b.classList.contains('lhead')) { const t = b.parentElement.dataset.t; opened.has(t) ? opened.delete(t) : opened.add(t); draw(); el.querySelector(`[data-t="${t}"] .lhead`).focus(); return; }
      else return;
      changed(b.dataset.k ? `[data-k="${b.dataset.k}"][data-o="${CSS.escape(b.dataset.o)}"]` : null); });
    el.addEventListener('input', e => { const t = e.target;
      if (t.type === 'range') { const box = t.closest('.lrange'), k = box.dataset.r, [a, b] = box.querySelectorAll('input'); let lo = +a.value, hi = +b.value; if (lo > hi) t === a ? lo = hi : hi = lo;
        a.value = lo; b.value = hi; s[k] = lo === R[k].min && hi === R[k].max ? null : [lo, hi];
        // while dragging only move this slider's rail and labels; the full redraw waits for release so the thumb isn't replaced mid-drag
        const pc = x => (x - R[k].min) / (R[k].max - R[k].min) * 100, rail = box.querySelector('.rail b'), [l1, l2] = box.querySelectorAll('.lab span');
        rail.style.left = pc(lo) + '%'; rail.style.right = 100 - pc(hi) + '%'; l1.textContent = fmt[k](lo); l2.textContent = fmt[k](hi); onChange(); }
      else if (t.dataset.ck) { s[t.dataset.ck] = t.checked; changed(`[data-ck="${t.dataset.ck}"]`); } });
    el.addEventListener('change', e => { const t = e.target; if (t.type === 'range') changed(`.lrange[data-r="${t.closest('.lrange').dataset.r}"] input:nth-of-type(${t === t.closest('.lrange').querySelector('input') ? 1 : 2})`); });
    draw();
    return { match: v => match(v), active, clear: () => { s = fresh(); draw(); }, refresh: draw };
  }
  return { mount };
})();
