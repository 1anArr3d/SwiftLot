import { API, getJSON } from '../api';
import { usePageData } from '../hooks';
import { toSale } from '../provenance/adapt';
import { mount } from '../provenance/pages/auctions';
import Provenance from '../provenance/Provenance';
import Printing from '../provenance/Printing';

const load = async () => ({ auctions: (await getJSON(`${API}/auctions`)).map(toSale) });

export default function AuctionsPage() {
  const { data, error } = usePageData(load, []);
  if (error) return <Printing title="Couldn't load the sales" error="Check your connection, then try again." />;
  if (!data) return <Printing title="Posting the notices…" />;
  return <Provenance className="pg-auctions" mount={mount} data={data} />;
}
