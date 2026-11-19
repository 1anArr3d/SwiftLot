import { pic } from './adapt.js';
// Photo gallery for certificates: inline viewer (arrows, counter, thumbnails) + full-screen lightbox with zoom and pan.
// GAL.html(images, alt) returns markup; GAL.bind(root) wires every gallery inside root. One shared <dialog> for the lightbox.
export const GAL = (() => {
  const html = (imgs, alt) => !imgs.length ? '<div class="photo gal-empty">No photos from the yard</div>' :
    `<div class="photo gal" data-imgs='${JSON.stringify(imgs).replace(/'/g, '&#39;')}' data-alt="${alt}" data-i="0">
      <button class="gal-main" aria-label="Open photo full screen"><img src="${pic(imgs[0], 'MOBILE')}" alt="${alt}, photo 1 of ${imgs.length}"></button>
      ${imgs.length > 1 ? `<button class="gal-arrow prev" aria-label="Previous photo">‹</button><button class="gal-arrow next" aria-label="Next photo">›</button>` : ''}
      <span class="gal-count">1 / ${imgs.length}</span>
      <div class="gal-thumbs">${imgs.map((s, i) => `<button aria-label="Photo ${i + 1}" aria-current="${i === 0}"><img src="${pic(s, 'THUMBNAIL')}" alt="" loading="lazy"></button>`).join('')}</div></div>`;

  function show(g, i) {
    const imgs = JSON.parse(g.dataset.imgs), n = imgs.length; i = (i + n) % n; g.dataset.i = i;
    const m = g.querySelector('.gal-main img'); m.src = pic(imgs[i], 'MOBILE'); m.alt = `${g.dataset.alt}, photo ${i + 1} of ${n}`;
    g.querySelector('.gal-count').textContent = `${i + 1} / ${n}`;
    g.querySelectorAll('.gal-thumbs button').forEach((b, k) => b.setAttribute('aria-current', k === i));
  }

  function bind(root) {
    root.querySelectorAll('.gal').forEach(g => {
      g.querySelector('.gal-main').onclick = () => open(JSON.parse(g.dataset.imgs), +g.dataset.i, g.dataset.alt, i => show(g, i));
      g.querySelector('.prev')?.addEventListener('click', () => show(g, +g.dataset.i - 1));
      g.querySelector('.next')?.addEventListener('click', () => show(g, +g.dataset.i + 1));
      g.querySelectorAll('.gal-thumbs button').forEach((b, k) => b.onclick = () => show(g, k));
    });
  }

  // lightbox
  let dlg, st;
  function build() {
    dlg = document.createElement('dialog'); dlg.className = 'lb'; dlg.setAttribute('aria-label', 'Photo viewer');
    dlg.innerHTML = `<div class="lb-stage"><img alt="" draggable="false"></div>
      <div class="lb-bar"><span class="lb-count"></span>
        <div class="lb-tools"><button data-a="out" aria-label="Zoom out">−</button><span class="lb-zoom">100%</span><button data-a="in" aria-label="Zoom in">+</button><button data-a="fit">Fit</button></div>
        <button data-a="close" aria-label="Close photo viewer">✕</button></div>
      <button class="lb-arrow prev" data-a="prev" aria-label="Previous photo">‹</button><button class="lb-arrow next" data-a="next" aria-label="Next photo">›</button>
      <div class="lb-thumbs"></div>`;
    document.body.append(dlg);
    const stage = dlg.querySelector('.lb-stage'), img = stage.querySelector('img');
    dlg.addEventListener('click', e => { const a = e.target.closest('[data-a]')?.dataset.a; if (a) act(a); });
    stage.addEventListener('wheel', e => { e.preventDefault(); zoom(e.deltaY < 0 ? 1.2 : 1 / 1.2, e); }, { passive: false });
    stage.addEventListener('dblclick', e => st.z > 1 ? fit() : zoom(2.5, e));
    let drag = null;
    stage.addEventListener('pointerdown', e => { if (st.z <= 1) return; drag = { x: e.clientX - st.x, y: e.clientY - st.y }; stage.setPointerCapture(e.pointerId); stage.classList.add('grab'); });
    stage.addEventListener('pointermove', e => { if (!drag) return; st.x = e.clientX - drag.x; st.y = e.clientY - drag.y; paint(); });
    stage.addEventListener('pointerup', () => { drag = null; stage.classList.remove('grab'); });
    dlg.addEventListener('keydown', e => { const a = { ArrowLeft: 'prev', ArrowRight: 'next', '+': 'in', '=': 'in', '-': 'out', '0': 'fit' }[e.key]; if (a) { e.preventDefault(); act(a); } });
    dlg.addEventListener('close', () => st.done && st.done(st.i));
    st = { img };
  }
  const paint = () => { st.img.style.transform = `translate(${st.x}px,${st.y}px) scale(${st.z})`; dlg.querySelector('.lb-zoom').textContent = Math.round(st.z * 100) + '%'; dlg.querySelector('.lb-stage').classList.toggle('zoomed', st.z > 1); };
  const fit = () => { st.z = 1; st.x = st.y = 0; paint(); };
  function zoom(f, e) {
    const z = Math.min(6, Math.max(1, st.z * f)); if (z === st.z) return;
    if (e && e.clientX != null) { const r = dlg.querySelector('.lb-stage').getBoundingClientRect(), cx = e.clientX - r.left - r.width / 2, cy = e.clientY - r.top - r.height / 2; // keep the point under the cursor fixed
      st.x = cx - (cx - st.x) * z / st.z; st.y = cy - (cy - st.y) * z / st.z; }
    st.z = z; if (z === 1) st.x = st.y = 0; paint();
  }
  function go(i) {
    const n = st.imgs.length; st.i = (i + n) % n; st.img.src = st.imgs[st.i]; st.img.alt = `${st.alt}, photo ${st.i + 1} of ${n}`;
    dlg.querySelector('.lb-count').textContent = `${st.alt} · ${st.i + 1} / ${n}`;
    dlg.querySelectorAll('.lb-thumbs button').forEach((b, k) => b.setAttribute('aria-current', k === st.i)); fit();
  }
  function act(a) { ({ prev: () => go(st.i - 1), next: () => go(st.i + 1), in: () => zoom(1.4), out: () => zoom(1 / 1.4), fit, close: () => dlg.close() })[a]?.(); }
  function open(imgs, i, alt, done) {
    if (!dlg) build();
    Object.assign(st, { imgs, alt, done });
    dlg.querySelector('.lb-thumbs').innerHTML = imgs.map((s, k) => `<button aria-label="Photo ${k + 1}"><img src="${pic(s, 'THUMBNAIL')}" alt=""></button>`).join('');
    dlg.querySelectorAll('.lb-thumbs button').forEach((b, k) => b.onclick = () => go(k));
    dlg.querySelectorAll('.lb-arrow').forEach(b => b.hidden = imgs.length < 2);
    go(i); dlg.showModal();
  }
  return { html, bind, open };
})();
