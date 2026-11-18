import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { API, getJSON, authFetch } from './api';
import { useAuth } from './AuthContext';

const GENERIC = new Set(['other', 'unknown', 'misc', 'n/a', 'na']);

// Price ranges for every make/model/year in the list, keyed "make|model|year". Resolves {} when there is nothing to ask for.
export function fetchPriceRanges(vehicles) {
  const seen = new Set();
  const list = vehicles.filter(v => {
    if (!v.make || !v.model || !v.year || GENERIC.has(v.make.toLowerCase()) || GENERIC.has(v.model.toLowerCase())) return false;
    const k = `${v.make}|${v.model}|${v.year}`;
    if (seen.has(k)) return false;
    seen.add(k); return true;
  }).map(v => ({ make: v.make, model: v.model, year: v.year }));
  if (!list.length) return Promise.resolve({});
  return getJSON(`${API}/historical/stats/batch`, { method: 'POST', body: JSON.stringify(list) })
    .then(data => Object.fromEntries(Object.entries(data).filter(([, s]) => s.count > 0)));
}

// Every live vehicle plus its price ranges, shared by Home and Search and reused for a minute,
// so moving between pages doesn't refetch. A failed load is dropped so the next call retries.
let lots = null;
export function getLots() {
  if (!lots || Date.now() - lots.at > 60_000) {
    const p = getJSON(`${API}/vehicles`).then(async vehicles => ({ vehicles, stats: await fetchPriceRanges(vehicles).catch(() => ({})) }));
    lots = { at: Date.now(), p };
    p.catch(() => { if (lots?.p === p) lots = null; });
  }
  return lots.p;
}

// Fetches page data, then price ranges, and hands back the adapted result. Price ranges are optional:
// if that call fails the page still loads, just without ranges.
export function usePageData(load, deps) {
  const [state, setState] = useState({ data: null, error: false });
  useEffect(() => {
    let off = false;
    load()
      .then(d => { if (!off) setState({ data: d, error: false }); })
      .catch(err => { console.error(err); if (!off) setState({ data: null, error: true }); });
    return () => { off = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

// Live bids over SSE, keyed by item_key. Streams by each vehicle's own auction_id (one per lot, not per seller).
export function useLiveBids(vehicles) {
  const [liveBids, setLiveBids] = useState({});
  const key = [...new Set(vehicles.filter(v => v.auction_id).map(v => v.auction_id))].sort().join(',');
  useEffect(() => {
    if (!key) return;
    let stopped = false;
    let source;
    let retry;
    const connect = () => {
      if (stopped) return;
      source = new EventSource(`${API}/stream/multi?auctions=${key}`);
      source.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        // the server sends a per-lot snapshot on connect and after every bid
        if (msg.type === 'update') {
          setLiveBids(prev => {
            const next = { ...prev };
            (msg.vehicles || []).forEach(v => { if (v.item_key) next[v.item_key] = { amount: v.current_bid, expires: v.bid_expiration }; });
            return next;
          });
        }
      };
      source.onerror = () => { source.close(); if (!stopped) retry = setTimeout(connect, 3000); };
    };
    connect();
    return () => { stopped = true; clearTimeout(retry); source?.close(); };
  }, [key]);
  return liveBids;
}

// The signed-in user's garage VINs, with a save/remove toggle that rolls back if the server refuses.
export function useGarage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [vins, setVins] = useState(new Set());
  const [error, setError] = useState('');
  useEffect(() => {
    if (!user) return;
    authFetch(user, `${API}/garage`)
      .then(data => setVins(new Set(data.map(v => v.vin))))
      .catch(console.error);
  }, [user]);
  const flip = (vin) => setVins(prev => { const n = new Set(prev); n.has(vin) ? n.delete(vin) : n.add(vin); return n; });
  const toggle = async (vin) => {
    if (!user) { navigate('/login', { state: { from: window.location.pathname + window.location.search } }); return; }
    const saved = vins.has(vin);
    flip(vin);
    setError('');
    try {
      await authFetch(user, `${API}/garage/${vin}`, { method: saved ? 'DELETE' : 'POST' });
    } catch (err) {
      console.error(err);
      flip(vin);
      setError("Couldn't update your garage. Check your connection and try again.");
    }
  };
  return { vins, toggle, error };
}
