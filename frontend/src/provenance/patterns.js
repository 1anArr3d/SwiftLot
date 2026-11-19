import { pic } from './adapt.js';
// Guilloche pattern generators (pure SVG path math). All take a stroke colour; size is a 400x260 tile.
export const PAT = (() => {
  const f = n => n.toFixed(1);
  // hypotrochoid: R ring, r gear, d pen offset; turns = enough revolutions to close the curve
  const troch = (cx, cy, R, r, d, turns, n = 1400, rot = 0) => { let p = '';
    for (let k = 0; k <= n; k++) { const a = k / n * Math.PI * 2 * turns, x = (R - r) * Math.cos(a) + d * Math.cos((R - r) / r * a), y = (R - r) * Math.sin(a) - d * Math.sin((R - r) / r * a);
      const c = Math.cos(rot), s = Math.sin(rot); p += (k ? 'L' : 'M') + f(cx + x * c - y * s) + ' ' + f(cy + x * s + y * c); } return p; };
  // epitrochoid petals for star rosettes
  const epi = (cx, cy, R, r, d, turns, n = 1400) => { let p = '';
    for (let k = 0; k <= n; k++) { const a = k / n * Math.PI * 2 * turns, x = (R + r) * Math.cos(a) - d * Math.cos((R + r) / r * a), y = (R + r) * Math.sin(a) - d * Math.sin((R + r) / r * a);
      p += (k ? 'L' : 'M') + f(cx + x) + ' ' + f(cy + y); } return p; };
  const svg = (inner, c, w = .6) => `<svg viewBox="0 0 400 260" preserveAspectRatio="xMidYMid slice" aria-hidden="true"><g fill="none" stroke="${c}" stroke-width="${w}">${inner}</g></svg>`;
  const path = (d, o = 1) => `<path d="${d}" stroke-opacity="${o}"/>`;
  // seeded random from a string (VIN), so each car gets a repeatable pattern
  const seed = s => { let h = 2166136261; for (const ch of s) h = Math.imul(h ^ ch.charCodeAt(0), 16777619); return () => ((h = Math.imul(h ^ (h >>> 15), 2246822507) ^ Math.imul(h ^ (h >>> 13), 3266489909)) >>> 0) / 4294967296; };
  const P = {
    current: c => svg(path(troch(330, 200, 110, 25, 60, 25)) + path(troch(70, 60, 80, 15, 40, 15)) + path(troch(200, 130, 190, 39, 90, 39), .5), c),
    lace: c => svg([0, 1, 2, 3].map(i => path(troch(200, 130, 120 - i * 14, 9 + i, 50 - i * 6, 9 + i, 1600))).join(''), c, .45),
    star: c => svg(path(epi(200, 130, 60, 12, 30, 12)) + path(epi(200, 130, 50, 10, 34, 10), .6) + path(epi(200, 130, 30, 6, 20, 6), .8), c),
    waves: c => svg(Array.from({ length: 26 }, (_, i) => { let d = ''; for (let x = 0; x <= 400; x += 4) { const y = 40 + i * 7 + 14 * Math.sin(x / 38 + i * .35) + 6 * Math.sin(x / 13 - i * .2); d += (x ? 'L' : 'M') + x + ' ' + f(y); } return path(d, .8); }).join(''), c, .5),
    border: c => { let d = ''; const n = 2400; for (let k = 0; k <= n; k++) { const t = k / n, per = 2 * (380 + 240), s = t * per;
        let x, y; if (s < 380) { x = 10 + s; y = 10; } else if (s < 620) { x = 390; y = 10 + s - 380; } else if (s < 1000) { x = 390 - (s - 620); y = 250; } else { x = 10; y = 250 - (s - 1000); }
        const w = 6 * Math.sin(t * Math.PI * 2 * 90); const nx = (x === 10 ? 1 : x === 390 ? -1 : 0), ny = (y === 10 ? 1 : y === 250 ? -1 : 0);
        d += (k ? 'L' : 'M') + f(x + nx * (8 + w)) + ' ' + f(y + ny * (8 + w)); }
      return svg(path(d) + `<rect x="26" y="26" width="348" height="208" stroke-opacity=".5"/>`, c, .6); },
    medallion: c => svg([0, 1, 2, 3, 4].map(i => path(troch(200, 130, 100 - i * 12, 7, 26 - i * 3, 7, 1400, i * .15), 1 - i * .12)).join('') + `<circle cx="200" cy="130" r="34" fill="none" stroke-opacity=".9"/>`, c, .5),
    moire: c => svg(Array.from({ length: 60 }, (_, i) => `<line x1="${i * 8 - 40}" y1="0" x2="${i * 8 + 40}" y2="260" stroke-opacity=".55"/>`).join('') + Array.from({ length: 60 }, (_, i) => `<line x1="${i * 8 - 60}" y1="0" x2="${i * 8 + 70}" y2="260" stroke-opacity=".45"/>`).join(''), c, .45),
    vin: (c, vin = '3FAHP0GA0AR121390') => { const r = seed(vin), R = 70 + r() * 50, g = 7 + Math.floor(r() * 18), d = 20 + r() * 50, gx = 70 + r() * 260, gy = 60 + r() * 140;
      return svg(path(troch(gx, gy, R, g, d, g)) + path(troch(gx, gy, R * .7, g + 3, d * .7, g + 3), .6) + path(troch(400 - gx, 260 - gy, 50 + r() * 30, 5 + Math.floor(r() * 9), 20 + r() * 20, 13), .7), c); },
  };
  // Composed fingerprint: one centred medallion that always closes cleanly. Seeded by VIN + copy,
  // so each copy of a car differs but is stable. Sized for a square slot (viewBox 200x200).
  const gcd = (a, b) => b ? gcd(b, a % b) : a;
  P.fingerprint = (c, vin, copy = 'value') => {
    const r = seed(vin + '|' + copy), pick = a => a[Math.floor(r() * a.length)];
    // integer ring + gear: closes after gear/gcd turns with R/gcd lobes. Gears chosen so lobes and turns
    // land in a lace-like range (8–32 lobes, 3–15 turns) instead of a plain gear outline.
    const ring = (R, gear, depth, rot) => troch(100, 100, R, gear, gear * depth, gear / gcd(R, gear), 3000, rot);
    const g1 = pick([40, 42, 44, 45, 54, 66]), g2 = pick([21, 24, 35, 40]), rot = r() * Math.PI;
    return `<svg viewBox="0 0 200 200" aria-hidden="true"><g fill="none" stroke="${c}">
      <circle cx="100" cy="100" r="98" stroke-width=".7"/><circle cx="100" cy="100" r="95" stroke-width=".35"/>
      <path d="${ring(96 - Math.round(g1 * .0), g1, .55 + r() * .4, rot).replace(/^/, '')}" stroke-width=".4" transform="scale(.94) translate(6.4 6.4)"/>
      <path d="${ring(56, g2, .6 + r() * .35, -rot)}" stroke-width=".4" stroke-opacity=".85"/>
      <circle cx="100" cy="100" r="${12 + Math.floor(r() * 8)}" stroke-width=".6"/></g></svg>`; };
  // small repeating tile of the fingerprint, as a CSS background-image value (single-quoted so it is safe inside style="")
  const url = s => `url('data:image/svg+xml;utf8,${encodeURIComponent(s.replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" ')).replace(/'/g, '%27')}')`;
  P.tile = (c, vin, copy) => url(P.fingerprint(c, vin, copy));
  // horizontal squiggle bands; line count, wavelengths, amplitudes and phase seeded by VIN
  P.vinwaves = (c, vin) => { const r = seed(vin + '|odo'), n = 18 + Math.floor(r() * 10), w1 = 28 + r() * 30, w2 = 9 + r() * 8, a1 = 8 + r() * 10, a2 = 3 + r() * 5, ph = r() * 6, tw = .2 + r() * .4;
    return svg(Array.from({ length: n }, (_, i) => { let d = ''; for (let x = 0; x <= 400; x += 4) { const y = 260 / n * (i + .5) + a1 * Math.sin(x / w1 + i * tw + ph) + a2 * Math.sin(x / w2 - i * tw * .6); d += (x ? 'L' : 'M') + x + ' ' + f(y); } return path(d, .8); }).join(''), c, .5); };
  // odometer: full-sheet VIN waves; vehicle: star rosette centred; value: two fingerprints, top-left and bottom-right, fixed size
  // VIN-seeded star rosette: three nested epitrochoids; integer ring/gear so each closes cleanly
  P.vinstar = (c, vin) => { const r = seed(vin + '|veh'), pick = a => a[Math.floor(r() * a.length)], ring = (R, g, d, o) => path(epi(200, 130, R, g, d, g / gcd(R, g), 2400), o);
    return svg(ring(60, pick([8, 10, 12, 15, 20]), 24 + r() * 14, 1) + ring(48, pick([6, 8, 12, 16]), 26 + r() * 12, .6) + ring(30, pick([5, 6, 10]), 14 + r() * 10, .8), c); };
  P.spots = (c, vin, copy) => copy === 'odometer' ? [{ img: url(P.vinwaves(c, vin)), pos: '0 0', size: '100% 100%' }]
    : copy === 'vehicle' ? [{ img: url(P.vinstar(c, vin)), pos: 'center', size: '640px' }]
    : [['0 0', copy + 'a'], ['100% 100%', copy + 'b']].map(([pos, k]) => ({ img: P.tile(c, vin, k), pos, size: '220px' }));
  // blue ink seal: two rings, micro-text ring, two offset 12-lobe rosettes
  // Embossed seals, one per certificate copy: same frame (double ring, text ring, inner ring), own centre pattern and tone.
  let sealN = 0;
  const f2 = n => n.toFixed(2);
  const centres = {
    rosette: (n, a, b) => { let d = ''; for (let k = 0; k <= 720; k++) { const t = k / 720 * 2 * Math.PI; d += (k ? 'L' : 'M') + f2(55 + a * Math.cos(t) + b * Math.cos(n * t)) + ' ' + f2(55 + a * Math.sin(t) - b * Math.sin(n * t)); } return `<path class="ros" d="${d}" stroke-width=".6"/>`; },
    dial: () => { let d = ''; for (let i = 0; i <= 40; i++) { const t = (135 + i * 270 / 40) * Math.PI / 180, r0 = i % 5 ? 32 : 28; d += `M${f2(55 + r0 * Math.cos(t))} ${f2(55 + r0 * Math.sin(t))}L${f2(55 + 35 * Math.cos(t))} ${f2(55 + 35 * Math.sin(t))}`; }
      return `<path d="${d}" stroke-width=".8"/><path d="M90 55A35 35 0 0 1 79.75 79.75" stroke-width="2.2" opacity=".7"/><g class="ros"><path d="M55 55L${f2(55 + 26 * Math.cos(-1.1))} ${f2(55 + 26 * Math.sin(-1.1))}" stroke-width="1.4" stroke-linecap="round"/></g><circle cx="55" cy="55" r="2" fill="currentColor"/>`; },
  };
  P.seal = ({ label, ring, centre, tone, low }) => { const id = 'sr' + (++sealN);
    return `<div class="s-ink filled emboss ${tone}"><svg viewBox="0 0 110 110" aria-hidden="true"><defs><path id="${id}" d="M55 55 m-45 0 a45 45 0 1 1 90 0 a45 45 0 1 1 -90 0"/></defs>
      <g fill="none" stroke="currentColor"><circle cx="55" cy="55" r="53" stroke-width="1.4"/><circle cx="55" cy="55" r="50.5" stroke-width=".5"/><circle cx="55" cy="55" r="39" stroke-width=".8"/>${centre}</g>
      <text textLength="282" lengthAdjust="spacing"><textPath href="#${id}" textLength="282" lengthAdjust="spacing">${ring}</textPath></text></svg><span><b${low ? ' style="margin-top:34px"' : ''}>${label}</b></span></div>`; };
  P.inkSeal = (lines) => P.seal({ label: lines, ring: 'SWIFTLOT · MARKET VALUE · SWIFTLOT · MARKET VALUE ·', centre: centres.rosette(11, 25, 9) + centres.rosette(11, 23, 10).replace('stroke-width=".6"', 'stroke-width=".6" opacity=".6"'), tone: 'green' });
  P.odoSeal = () => P.seal({ label: 'Mileage<br>record', ring: 'SWIFTLOT · MILEAGE RECORD · TEXAS INSPECTION · ', centre: centres.dial(), tone: 'blue', low: 1 });
  P.vinSeal = vin => P.seal({ label: 'VIN<br>verified', ring: `VIN ${vin} · VIN ${vin} · `, centre: centres.rosette(7, 22, 11), tone: 'red' });
  // Lattice band: the certificate's side strip in the copy's colour, two crossing wave sets, the VIN in micro text down both edges.
  // A rollback tears the band; below the tear the lattice and VIN run backwards in a darker shade.
  const lattice = `<svg viewBox="0 0 42 340" preserveAspectRatio="none" aria-hidden="true"><g fill="none" stroke="#f3f0e4" stroke-width=".5">${[1, -1].map(sg => Array.from({ length: 8 }, (_, i) => `<path d="M${5 + i * 4.5} 0 ${Array.from({ length: 17 }, (_, k) => `Q${5 + i * 4.5 + (k % 2 ? sg * 6 : -sg * 6)} ${k * 20 + 10} ${5 + i * 4.5} ${k * 20 + 20}`).join(' ')}"/>`).join('')).join('')}</g></svg>`;
  P.strip = (copy, vin, label, rollback) => {
    const mt = a => `<span class="mt l" aria-hidden="true">${((a ? '◂◂ ' : '') + vin + ' ').repeat(16)}</span><span class="mt r" aria-hidden="true">${((a ? '◂◂ ' : '') + vin + ' ').repeat(16)}</span>`;
    if (!rollback) return `<div class="strip lband ${copy}"><div class="lbody">${lattice}${mt()}<span class="lbl">SWIFTLOT · ${label}</span></div></div>`;
    const e = [70, 72.5, 69.5, 73, 70, 72, 70.5].map((y, i) => `${(i / 6 * 100).toFixed(1)}% ${y}%`);
    return `<div class="strip lband rb"><div class="lbody" style="clip-path:polygon(0 0,100% 0,${[...e].reverse().join(',')})">${lattice}${mt(1)}<span class="lbl">ROLLBACK · NOT ACTUAL</span></div>
      <div class="lbody rev" style="clip-path:polygon(${e.join(',')},100% 100%,0 100%)">${lattice}${mt(1)}</div></div>`;
  };
  // verdict colour shared by the card seal and the lot-row stub: rollback beats price; green under median, blue otherwise
  P.verdict = (v, g) => v.odo_rollback ? 'rb' : g != null && g <= 0 ? 'under' : 'over';
  P.lat = k => `<i class="lat ${k}" aria-hidden="true">${lattice}</i>`;
  const ros = (() => { let d = ''; for (let k = 0; k <= 500; k++) { const t = k / 500 * 2 * Math.PI; d += (k ? 'L' : 'M') + f2(27 + 17 * Math.cos(t) + 6 * Math.cos(11 * t)) + ' ' + f2(27 + 17 * Math.sin(t) - 6 * Math.sin(11 * t)); } return `<svg viewBox="0 0 54 54" aria-hidden="true"><path d="${d}" fill="none" stroke="#f3f0e4" stroke-width=".6"/></svg>`; })();
  P.photo = (v, g) => { const k = P.verdict(v, g); return `<div class="ph"><img src="${pic(v.images[0], 'MOBILE')}" alt="" loading="lazy"><span class="cseal ${k}">${ros}<b>${{ rb: 'ROLL<br>BACK', under: 'UNDER', over: 'OVER' }[k]}</b></span></div>`; };
  // nav brand: the Gilt coupe emblem and the Gold glint title. Drives in and glints on load; streams, spins and glints again on hover
  const BODY = 'M17.4 3.6Q18.6 3.4 18.5 1.6Q18.4 0 17.2-.6Q12-1.6 6.4-2.6Q3.8-5.4.4-5.9Q-4.2-6.4-8-4.6Q-12.6-3-16.6-2.3Q-18-1.8-18.1.4L-17.8 3.6H-14.8A3.4 3.4 0 0 1-8 3.6H7.6A3.4 3.4 0 0 1 14.4 3.6Z';
  const wheel = x => `<g transform="translate(${x} 3.4)"><circle r="2.9" fill="#11182f" stroke="#f3f0e4" stroke-width=".35"/><circle r="2" fill="none" stroke="#c9b26a" stroke-width=".3"/><g class="spin" stroke="#c9b26a" stroke-width=".35">${[0, 60, 120].map(a => `<path d="M0-1.9V1.9" transform="rotate(${a})"/>`).join('')}</g><circle r=".5" fill="#c9b26a"/></g>`;
  P.brand = () => `<svg class="emb" viewBox="-24 -12 48 20" aria-hidden="true"><defs><linearGradient id="bg-g" gradientUnits="userSpaceOnUse" x1="-18" y1="-6" x2="18" y2="4"><stop offset="0" stop-color="#9c843d"/><stop offset=".5" stop-color="#ead594"/><stop offset="1" stop-color="#8c7535"/></linearGradient>
    <linearGradient id="bg-s"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fffbe8" stop-opacity=".9"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient><clipPath id="bg-c"><path d="${BODY}"/></clipPath></defs>
    <g class="sl" stroke="#c9b26a" stroke-width=".3" stroke-linecap="round">${[-4.6, -3.2, -1.8, -.4, 1, 2.4, 3.8].map((y, i) => `<path d="M${-23 - (i * 5) % 7} ${y}H-19" opacity="${f2(.45 + ((i * 3) % 4) * .15)}"/>`).join('')}</g>
    <g class="car"><path d="${BODY}" fill="url(#bg-g)"/><g clip-path="url(#bg-c)"><path d="M-20-1.2L20-2.4V-.6L-20 .6Z" fill="#fff6d0" opacity=".25"/><rect class="sheen" x="-4" y="-8" width="6" height="16" fill="url(#bg-s)" transform="skewX(-20)"/></g>
    <path d="${BODY}" fill="none" stroke="#f8eaa9" stroke-width=".3"/><path d="M5.2-2.7Q3-4.9.2-5.2Q-3.6-5.5-7-4L-8.4-3.1Z" fill="#1c2546" stroke="#f8eaa9" stroke-width=".25"/><path d="M-1.4-5.3V-2.9" stroke="#f8eaa9" stroke-width=".4"/>
    <path d="M5.6-2.4Q6.4.6 5.4 3.6M-8.6-2.8Q-9.4.4-8.6 3.2M-7.6 2.5H7.2M18.2.2Q16.4-.3 14.6.3M-18-.9H-16.2" fill="none" stroke="#7d672c" stroke-width=".3"/>${wheel(-11.4)}${wheel(11)}</g>
    <path d="M-24 6.3H24" stroke="#c9b26a" stroke-width=".25" opacity=".6"/></svg><span class="wm">Swift<i>Lot</i></span>`;
  return P;
})();
