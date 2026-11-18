import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { API, getJSON, authFetch } from './api';
import { useAuth } from './AuthContext';

const GENERIC = new Set(['other', 'unknown', 'misc', 'n/a', 'na']);

// Price ranges for every make/model/year in the list, keyed "make|model|year".
export function usePriceRanges(vehicles) {
  const [stats, setStats] = useState({});
  // Keyed on the combos themselves, so a different list of the same length still refetches
  const combos = JSON.stringify([...new Set(vehicles
    .filter(v => v.make && v.model && v.year && !GENERIC.has(v.make.toLowerCase()) && !GENERIC.has(v.model.toLowerCase()))
    .map(v => JSON.stringify([v.make, v.model, v.year])))].sort());
  useEffect(() => {
    const list = JSON.parse(combos).map(c => { const [make, model, year] = JSON.parse(c); return { make, model, year }; });
    if (!list.length) return;
    let cancelled = false;
    getJSON(`${API}/historical/stats/batch`, { method: 'POST', body: JSON.stringify(list) })
      .then(data => { if (!cancelled) setStats(Object.fromEntries(Object.entries(data).filter(([, s]) => s.count > 0))); })
      .catch(console.error);
    return () => { cancelled = true; };
  }, [combos]);
  return stats;
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
        if (msg.type === 'bid') {
          setLiveBids(prev => ({ ...prev, [msg.item_key]: { amount: msg.amount, expires: msg.expires } }));
        } else if (msg.type === 'update') {
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
