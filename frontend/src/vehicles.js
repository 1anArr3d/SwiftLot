export const parseImages = (raw) => { try { return JSON.parse(raw) || []; } catch { return []; } };

export const statsKey = (v) => `${v.make}|${v.model}|${v.year}`;
