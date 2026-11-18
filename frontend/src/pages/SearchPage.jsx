import { API, getJSON } from '../api';
import { fetchPriceRanges, usePageData } from '../hooks';
import { toLot } from '../provenance/adapt';
import { mount } from '../provenance/pages/search';
import Provenance from '../provenance/Provenance';
import Printing from '../provenance/Printing';

const load = async () => {
  const vehicles = await getJSON(`${API}/vehicles`);
  const stats = await fetchPriceRanges(vehicles).catch(() => ({}));
  return { vehicles: vehicles.map(v => toLot(v, stats)) };
};

export default function SearchPage() {
  const { data, error } = usePageData(load, []);
  if (error) return <Printing title="Couldn't load the lots" error="Check your connection, then try again." />;
  if (!data) return <Printing title="Gathering every lot…" />;
  return <Provenance className="pg-search" mount={mount} data={data} />;
}
