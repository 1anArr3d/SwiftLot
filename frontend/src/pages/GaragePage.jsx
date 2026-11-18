import { useMemo, useState } from 'react';
import { API, authFetch } from '../api';
import { useAuth } from '../AuthContext';
import { fetchPriceRanges, usePageData } from '../hooks';
import { toLot } from '../provenance/adapt';
import { mount } from '../provenance/pages/garage';
import Provenance from '../provenance/Provenance';
import Printing from '../provenance/Printing';

export default function GaragePage() {
  const { user } = useAuth();
  const [removeError, setRemoveError] = useState('');
  const { data, error } = usePageData(async () => {
    const vehicles = await authFetch(user, `${API}/garage`);
    const stats = await fetchPriceRanges(vehicles).catch(() => ({}));
    return { vehicles: vehicles.map(v => toLot(v, stats)) };
  }, [user]);
  const opts = useMemo(() => ({
    onRemove: async (vin) => {
      setRemoveError('');
      try { await authFetch(user, `${API}/garage/${vin}`, { method: 'DELETE' }); return true; } catch (err) {
        console.error(err);
        setRemoveError("Couldn't remove that car. Check your connection and try again.");
        return false;
      }
    },
  }), [user]);

  if (error) return <Printing title="Couldn't load your garage" error="Check your connection, then try again." />;
  if (!data) return <Printing title="Opening your garage…" />;
  return (
    <>
      {removeError && <p className="toast" role="alert">{removeError}</p>}
      <Provenance className="pg-garage" mount={mount} data={data} opts={opts} />
    </>
  );
}
