import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { D } from './sl.js';
import { stopAll } from './life.js';

// Hosts one Provenance page: fills the shared data, lets the page's mount() build the DOM,
// routes in-app links through React Router, and stops the page's timers on unmount.
// data: { auction, vehicles, auctions } already passed through adapt.js. handleRef receives what mount() returns.
export default function Provenance({ className, mount, data, opts, handleRef }) {
  const root = useRef(null);
  const navigate = useNavigate();
  useEffect(() => {
    const el = root.current;
    Object.assign(D, { auction: null, vehicles: [], auctions: [] }, data);
    const h = mount(el, opts) || null;
    if (handleRef) handleRef.current = h;
    return () => {
      stopAll();
      if (handleRef) handleRef.current = null;
      el.innerHTML = '';
      const navr = document.getElementById('navr'); if (navr) navr.innerHTML = '';
    };
    // opts are read once at mount; later changes go through the handle
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, mount]);
  const onClick = (e) => {
    const a = e.target.closest('a[href^="/"]');
    if (!a || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || a.target) return;
    e.preventDefault();
    navigate(a.getAttribute('href'));
  };
  return <div ref={root} className={className} onClick={onClick} />;
}
