// Timers and animation loops started by a mounted page. The React wrapper calls stopAll() on unmount,
// so nothing keeps ticking against a page that is gone.
const stops = new Set();
export const onStop = (fn) => { stops.add(fn); };
export const stopAll = () => { stops.forEach(f => f()); stops.clear(); };
export const every = (fn, ms) => { const t = setInterval(fn, ms); onStop(() => clearInterval(t)); return t; };
