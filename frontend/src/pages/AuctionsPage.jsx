import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { API } from '../api';

const STATUS_LABEL = {
  'live-auction': 'Open',
  'pre-auction':  'Upcoming',
  'completed':    'Closed',
};

const AuctionsPage = () => {
  const [auctions, setAuctions] = useState([]);
  const [filter, setFilter] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    fetch(`${API}/auctions`)
      .then(r => r.json())
      .then(setAuctions)
      .catch(console.error);
  }, []);

  const regions = [...new Set(auctions.map(a => a.region_id))].sort();

  const visible = filter
    ? auctions.filter(a => a.region_id === filter)
    : auctions;

  const withVehicles = visible.filter(a => a.vehicles_listed > 0);
  const empty = visible.length === 0;

  return (
    <div className="page-content">
      <div className="page-header">
        <div className="page-header-left">
          <h1 className="page-title">Auctions</h1>
          <span className="page-subtitle">{withVehicles.length} with vehicles · {visible.length} total</span>
        </div>
        {regions.length > 1 && (
          <div className="region-tabs">
            <button
              className={`region-tab${!filter ? ' active' : ''}`}
              onClick={() => setFilter('')}
            >
              All
            </button>
            {regions.map(r => (
              <button
                key={r}
                className={`region-tab${filter === r ? ' active' : ''}`}
                onClick={() => setFilter(r)}
              >
                {r}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="auction-grid">
        {visible.map(a => (
          <div
            key={a.auction_id}
            className={`auction-card${a.vehicles_listed > 0 ? ' has-vehicles' : ''}`}
            onClick={() => navigate(`/auctions/${a.auction_id}`)}
          >
            <div className="auction-card-top">
              <span className={`status-badge status-${a.auction_status}`}>
                {STATUS_LABEL[a.auction_status] ?? a.auction_status}
              </span>
              <span className="auction-card-region">{a.region_id}</span>
            </div>

            <div className="auction-card-seller">
              {a.seller_name || a.auction_id}
            </div>

            <div className="auction-card-info">
              <div className="auction-card-info-row">
                <span className="info-icon">📅</span>
                <span>{a.auction_date || '—'}</span>
              </div>
              <div className="auction-card-info-row">
                <span className="info-icon">🚗</span>
                <span className={a.vehicles_listed > 0 ? 'vehicles-count' : 'vehicles-none'}>
                  {a.vehicles_listed > 0 ? `${a.vehicles_listed} vehicles` : 'No vehicles listed'}
                </span>
              </div>
            </div>
          </div>
        ))}

        {empty && (
          <div className="empty-msg">No auctions found. Run discovery to populate.</div>
        )}
      </div>
    </div>
  );
};

export default AuctionsPage;
