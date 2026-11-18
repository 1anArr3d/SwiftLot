export const parseImages = (raw) => { try { return JSON.parse(raw) || []; } catch { return []; } };

// last_recorded_odo is "M/D/YYYY: 123,456" lines, newest first
export const parseOdo = (odoStr) => {
  if (!odoStr) return null;
  const m = odoStr.split('\n')[0].match(/:\s*([\d,]+)/);
  return m ? parseInt(m[1].replace(/,/g, '')) : null;
};

export const statsKey = (v) => `${v.make}|${v.model}|${v.year}`;

export const LEVEL_LABEL = { year: 'same year', near: '±2 yrs', all: 'all years' };
export const fmtRange = (s, fmt$) => s ? `${fmt$(s.low)}–${fmt$(s.high)}` : '—';
export const fmtRangeDetail = (s, fmt$) => {
  if (!s) return 'Not enough sales data';
  return `${fmtRange(s, fmt$)} · median ${fmt$(s.median)} · ${s.count} sales (${LEVEL_LABEL[s.level]})`;
};

// Only what a buyer would type: year, make, model, VIN. Not photo URLs or other raw fields.
export const matchesSearch = (v, term) => {
  const words = term.toLowerCase().split(/\s+/).filter(Boolean);
  const hay = `${v.year} ${v.make} ${v.model} ${v.vin}`.toLowerCase();
  return words.every(w => hay.includes(w));
};
