import { API, getJSON } from '../api';
import { fetchPriceRanges, usePageData } from '../hooks';
import { toLot, toSale } from '../provenance/adapt';
import { mount } from '../provenance/pages/home';
import Provenance from '../provenance/Provenance';
import Printing from '../provenance/Printing';

const load = async () => {
  const [vehicles, auctions] = await Promise.all([getJSON(`${API}/vehicles?limit=500`), getJSON(`${API}/auctions`)]);
  const stats = await fetchPriceRanges(vehicles).catch(() => ({}));
  return { vehicles: vehicles.map(v => toLot(v, stats)), auctions: auctions.map(toSale) };
};

export default function HomePage() {
  const { data, error } = usePageData(load, []);
  if (error) return <Printing title="Couldn't load today's sales" error="Check your connection, then try again." />;
  if (!data) return <Printing />;
  return <Provenance className="pg-home" mount={mount} data={data} />;
}
