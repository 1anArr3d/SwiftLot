export const API = import.meta.env.DEV ? 'http://127.0.0.1:8000/api/v1' : '/api/v1';

export const authFetch = (token, url, options = {}) => {
  return fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
};
