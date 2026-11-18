import { useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { API, getJSON } from '../api';
import { fetchPriceRanges, useLiveBids, usePageData } from '../hooks';
import { toAuction, toLot } from '../provenance/adapt';
import { mount } from '../provenance/pages/auction';
import { useGarageOpts } from '../provenance/useGarageOpts';
import Provenance from '../provenance/Provenance';
import Printing from '../provenance/Printing';

const load = async (id) => {
  const [auction, vehicles] = await Promise.all([getJSON(`${API}/auctions/${id}`), getJSON(`${API}/auctions/${id}/vehicles`)]);
  const stats = await fetchPriceRanges(vehicles).catch(() => ({}));
  return { raw: vehicles, auction: toAuction(auction), vehicles: vehicles.map(v => toLot(v, stats)) };
};

export default function AuctionDetailPage() {
  const { id } = useParams();
  const { data, error } = usePageData(() => load(id), [id]);
  const handle = useRef(null);
  const { opts, error: saveError } = useGarageOpts(handle);
  const live = useLiveBids(data?.raw || []);
  useEffect(() => {
    Object.entries(live).forEach(([k, b]) => handle.current?.bid(k, b.amount, b.expires));
  }, [live]);

  if (error) return <Printing title="Couldn't load this sale" error="Check your connection, then try again." />;
  if (!data) return <Printing />;
  return (
    <>
      {saveError && <p className="toast" role="alert">{saveError}</p>}
      <Provenance className="pg-auction" mount={mount} data={data} opts={opts} handleRef={handle} />
    </>
  );
}
