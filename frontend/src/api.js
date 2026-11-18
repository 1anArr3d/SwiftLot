export const API = import.meta.env.DEV ? 'http://127.0.0.1:8000/api/v1' : 'https://api.swift-lot.com/api/v1';

// Throws on a non-2xx response so a server error is never mistaken for an empty result.
const request = async (url, options = {}, token) => {
  const r = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.headers.get('content-type')?.includes('json') ? r.json() : null;
};

export const getJSON = (url, options) => request(url, options);

// getIdToken() hands back Firebase's cached token and refreshes it once expired, so requests keep working after sleep.
export const authFetch = async (user, url, options) => request(url, options, await user.getIdToken());
