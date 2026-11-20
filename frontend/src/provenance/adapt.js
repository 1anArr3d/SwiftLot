// API rows -> the shapes the Provenance pages render. Pages build HTML strings, so every text field is escaped here.
import { parseImages, statsKey } from '../vehicles';

const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
// Autura's CDN serves each photo at THUMBNAIL 320px, MOBILE 1280px and DESKTOP 1920px (what the API stores).
export const pic = (s, size) => (s || '').replace('/IMAGE_DESKTOP/', `/IMAGE_${size}/`);
export const esc = (s) => typeof s === 'string' ? s.replace(/[&<>"']/g, c => ESC[c]) : s;
const escAll = (o, keys) => { const r = { ...o }; keys.forEach(k => { r[k] = esc(o[k]); }); return r; };

const VEHICLE_TEXT = ['vin', 'make', 'model', 'color', 'key_status', 'start_status', 'engine_type', 'drivetrain', 'fuel_type',
  'body_type', 'seller_notes', 'seller_name', 'seller_city', 'seller_state', 'item_key', 'region_id', 'auction_id'];

// "10/20/2022: 155,227\n5/27/2021: 148,914" (newest first) -> [{date, miles}]
export const odometer = (s) => (s || '').split('\n')
  .map(l => l.match(/^\s*([\d/]+):\s*([\d,]+)/)).filter(Boolean)
  .map(m => ({ date: m[1], miles: +m[2].replace(/,/g, '') }));

// stats: the /historical/stats/batch result, keyed by the raw make|model|year
// Adds Autura's listed mileage, dated the day we first fetched it, to the inspection readings (still newest first).
const withAutura = (pts, miles, at) => {
  if (!miles || !at || pts.some(p => p.miles === miles)) return pts;
  const [y, m, d] = at.split('-').map(Number);
  const t = p => { const [pm, pd, py] = p.date.split('/').map(Number); return py * 1e4 + pm * 100 + pd; };
  return [...pts, { date: `${m}/${d}/${y}`, miles }].sort((a, b) => t(b) - t(a));
};

export const toLot = (v, stats = {}) => ({
  ...escAll(v, VEHICLE_TEXT),
  images: (Array.isArray(v.images) ? v.images : parseImages(v.images)).map(esc),
  price: stats[statsKey(v)] || null,
  odometer: withAutura(odometer(v.last_recorded_odo), v.autura_odo, v.autura_odo_at),
});

export const toAuction = (a) => a && escAll(a, ['seller_name', 'seller_city', 'seller_state', 'region_id']);
export const toSale = (a) => escAll(a, ['id', 'region_id', 'name', 'city', 'state']);
