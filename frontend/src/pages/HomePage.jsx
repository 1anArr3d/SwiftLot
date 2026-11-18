import { API, getJSON } from '../api';
import { getLots, usePageData } from '../hooks';
import { toLot, toSale } from '../provenance/adapt';
import { mount } from '../provenance/pages/home';
import Provenance from '../provenance/Provenance';
import Printing from '../provenance/Printing';

const load = async () => {
  const [{ vehicles, stats }, auctions] = await Promise.all([getLots(), getJSON(`${API}/auctions`)]);
  return { vehicles: vehicles.map(v => toLot(v, stats)), auctions: auctions.map(toSale) };
};

export default function HomePage() {
  const { data, error } = usePageData(load, []);
  if (error) return <Printing title="Couldn't load today's sales" error="Check your connection, then try again." />;
  if (!data) return <Printing />;
  return <Provenance className="pg-home" mount={mount} data={data} />;
}
