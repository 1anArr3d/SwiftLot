import { useEffect, useMemo, useRef } from 'react';
import { useGarage } from '../hooks';

// Bridges the garage hook to a mounted page: stable { onSave, isSaved } opts, and tells the page
// (handle.saved()) whenever the saved set changes. Returns the garage error message, if any.
export function useGarageOpts(handleRef) {
  const garage = useGarage();
  const latest = useRef(garage);
  useEffect(() => {
    latest.current = garage;
    handleRef.current?.saved?.();
  });
  const opts = useMemo(() => ({
    onSave: vin => latest.current.toggle(vin),
    isSaved: vin => latest.current.vins.has(vin),
  }), []);
  return { opts, error: garage.error };
}
