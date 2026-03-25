import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { API } from '../api';

const STATUS_LABEL = {
  'live-auction': 'Open',
  'pre-auction':  'Upcoming',
  'completed':    'Closed',
};

const REGION_LABEL = {
  'SA-TX': 'San Antonio, TX',
  'AUS-TX': 'Austin, TX',
  'DL-TX': 'Dallas – Fort Worth, TX',
  'EP-TX': 'El Paso, TX',
};

const AuctionsPage = () => {
  const [auctions, setAuctions] = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    fetch(`${API}/auctions`)
      .then(r => r.json())
      .then(setAuctions)
      .catch(console.error);
  }, []);

  // Group by region
  const regions = [...new Set(auctions.map(a => a.region_id))].sort();
  const byRegion = regions.reduce((acc, r) => {
    acc[r] = auctions.filter(a => a.region_id === r);
    return acc;
  }, {});

  if (auctions.length === 0) {
    return (
      <div className="page-content">
        <div className="empty-msg">No auctions found. Run discovery to populate.</div>
      </div>
    );
  }

  return (
    <div className="page-content">
      {regions.map(regionId => {
        const regionAuctions = byRegion[regionId];
        const label = REGION_LABEL[regionId] || regionId;

        return (
          <div key={regionId} className="region-section">
            <div className="region-hero">
              <div className="region-hero-overlay">
                <h2 className="region-hero-title">{label}</h2>
              </div>
            </div>

            <div className="region-section-header">
              <span className="region-section-label">Upcoming auctions</span>
            </div>

            <div className="auction-grid">
              {regionAuctions.map(a => (
                <div
                  key={a.auction_id}
                  className={`auction-card${a.vehicles_listed > 0 ? ' has-vehicles' : ''}`}
                  onClick={() => navigate(`/auctions/${a.auction_id}`)}
                >
                  <div className="auction-card-top">
                    <div className="auction-card-seller">{a.seller_name || a.auction_id}</div>
                    <span className={`status-badge status-${a.auction_status}`}>
                      {STATUS_LABEL[a.auction_status] ?? a.auction_status}
                    </span>
                  </div>

                  <div className="auction-card-divider" />

                  <div className="auction-card-info">
                    <div className="auction-card-info-row">
                      <span className="info-label">Vehicles</span>
                      <span className={a.vehicles_listed > 0 ? 'vehicles-count' : 'vehicles-none'}>
                        {a.vehicles_listed > 0 ? a.vehicles_listed : 'None listed'}
                      </span>
                    </div>
                  </div>

                  <div className="auction-card-divider" />

                  <div className="auction-card-footer">
                    <a
                      className="btn"
                      href={`https://app.marketplace.autura.com/auction/${a.region_id}/auction-${a.auction_id}`}
                      target="_blank"
                      rel="noreferrer"
                      onClick={e => e.stopPropagation()}
                    >
                      Listing
                    </a>
                    <button className="btn" onClick={e => { e.stopPropagation(); navigate(`/auctions/${a.auction_id}`); }}>
                      View
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default AuctionsPage;
