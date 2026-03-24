import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { API } from '../api';

const AuctionsPage = () => {
  const [auctions, setAuctions] = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    fetch(`${API}/auctions`)
      .then(r => r.json())
      .then(setAuctions)
      .catch(console.error);
  }, []);

  return (
    <div className="page-content">
      <header className="main-header">
        <div className="header-info">
          <h1>Auctions</h1>
          <div className="vehicle-count">{auctions.length} Locations</div>
        </div>
      </header>

      <div className="auction-grid">
        {auctions.map(a => (
          <div key={a.auction_id} className="auction-card" onClick={() => navigate(`/auctions/${a.auction_id}`)}>
            <div className="auction-card-seller">{a.seller_name || a.auction_id}</div>
            <div className="auction-card-meta">
              <span className="auction-card-region">{a.region_id}</span>
              <span className={`auction-card-status status-${a.auction_status}`}>{a.auction_status}</span>
            </div>
            <div className="auction-card-date">{a.auction_date || 'No date'}</div>
            <div className="auction-card-count">{a.vehicles_listed ?? 0} vehicles</div>
          </div>
        ))}
        {auctions.length === 0 && (
          <div className="empty-msg">No auctions found. Run discovery to populate.</div>
        )}
      </div>
    </div>
  );
};

export default AuctionsPage;
