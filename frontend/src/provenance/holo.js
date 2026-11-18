import { onStop } from './life.js';
// Shared hologram behaviour: tracks the pointer over an element and writes --px/--py (0..1) for CSS,
// tilts it slightly, and drifts on its own when there is no pointer (touch, idle, reduced motion = static).
export const HOLO = (() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  function track(el, { tilt = 4 } = {}) {
    let active = false, t0 = performance.now(), raf;
    const set = (x, y, tiltOn) => {
      el.style.setProperty('--px', x.toFixed(3)); el.style.setProperty('--py', y.toFixed(3));
      el.style.transform = tiltOn && !reduce ? `perspective(1600px) rotateX(${(.5 - y) * tilt}deg) rotateY(${(x - .5) * tilt * 1.25}deg)` : '';
    };
    el.addEventListener('pointermove', e => {
      if (e.pointerType === 'touch') return;
      active = true; const r = el.getBoundingClientRect();
      set((e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height, true);
    });
    el.addEventListener('pointerleave', () => { active = false; t0 = performance.now(); });
    const idle = now => {   // slow figure-eight so the foil still catches the light without a mouse
      if (!active) { const s = (now - t0) / 4000; set(.5 + .35 * Math.sin(s * 2 * Math.PI), .5 + .2 * Math.sin(s * 4 * Math.PI), false); }
      raf = requestAnimationFrame(idle);
    };
    if (reduce) set(.3, .4, false); else raf = requestAnimationFrame(idle);
    const stop = () => cancelAnimationFrame(raf);
    onStop(stop);
    return stop;
  }
  // guilloche rosette path (hypotrochoid)
  const rose = (cx, cy, R, r, d, n = 1000) => { let p = ''; for (let k = 0; k <= n; k++) { const a = k / n * Math.PI * 2 * 12,
    x = cx + (R - r) * Math.cos(a) + d * Math.cos((R - r) / r * a), y = cy + (R - r) * Math.sin(a) - d * Math.sin((R - r) / r * a);
    p += (k ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1); } return p; };
  const guilloche = (stroke = '#7a9c8e') => `<svg class="guil" viewBox="0 0 1000 700" preserveAspectRatio="xMidYMid slice" aria-hidden="true"><g fill="none" stroke="${stroke}" stroke-width=".6">
    <path d="${rose(820, 520, 160, 37, 90)}"/><path d="${rose(820, 520, 150, 29, 70)}"/><path d="${rose(160, 160, 120, 23, 60)}"/><path d="${rose(500, 350, 300, 61, 140, 1400)}" stroke-opacity=".5"/></g></svg>`;
  return { track, guilloche };
})();
