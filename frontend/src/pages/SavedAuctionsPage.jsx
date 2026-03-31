import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { API, authFetch } from '../api';
import { useAuth } from '../AuthContext';
import FilterSection from '../components/FilterSection';
import ChecklistFilter from '../components/ChecklistFilter';
import { REGION_LABEL, STATE_LABEL, getState } from '../constants';

const STATUS_LABEL = {
  'live-auction': 'Open',
  'pre-auction':  'Upcoming',
  'completed':    'Closed',
};

const FAR_FUTURE = '9999-12-31T00:00:00.000Z';

const SavedAuctionsPage = () => {
  const [auctions, setAuctions] = useState([]);
  const [sortOrder, setSortOrder] = useState('soonest');
  const [filters, setFilters] = useState({ city: new Set(), state: new Set() });
  const navigate = useNavigate();
  const { token } = useAuth();

  useEffect(() => {
    if (!token) return;
    authFetch(token, `${API}/saved-auctions`)
      .then(r => r.json())
      .then(setAuctions)
      .catch(console.error);
  }, [token]);

  const handleRemove = async (e, auctionId) => {
    e.stopPropagation();
    await authFetch(token, `${API}/saved-auctions/${auctionId}`, { method: 'DELETE' });
    setAuctions(prev => prev.filter(a => a.auction_id !== auctionId));
  };

  const uniqueCities = [...new Set(auctions.map(a => a.region_id).filter(Boolean))].sort();
  const uniqueStates = [...new Set(auctions.map(a => getState(a.region_id)).filter(s => s !== 'Unknown'))].sort();

  const setFilter = (key, val) => setFilters(prev => ({ ...prev, [key]: val }));
  const hasActiveFilters = filters.city.size > 0 || filters.state.size > 0;
  const clearAll = () => setFilters({ city: new Set(), state: new Set() });

  const filtered = auctions
    .filter(a => {
      if (filters.city.size > 0 && !filters.city.has(a.region_id)) return false;
      if (filters.state.size > 0 && !filters.state.has(getState(a.region_id))) return false;
      return true;
    })
    .sort((a, b) => {
      const dateA = a.closes_at || FAR_FUTURE;
      const dateB = b.closes_at || FAR_FUTURE;
      return sortOrder === 'soonest'
        ? dateA.localeCompare(dateB)
        : dateB.localeCompare(dateA);
    });

  return (
    <div className="app-wrapper">
      <aside className="sidebar">
        <div className="sidebar-header">
          <span>Filters</span>
          {hasActiveFilters && <button className="clear-all-btn" onClick={clearAll}>Clear All</button>}
        </div>

        <FilterSection title="Sort" defaultOpen={true}>
          <div className="checklist">
            {[['soonest', 'Ending Soonest'], ['latest', 'Ending Latest']].map(([val, label]) => (
              <label key={val} className="checklist-item">
                <input
                  type="radio"
                  name="sort"
                  checked={sortOrder === val}
                  onChange={() => setSortOrder(val)}
                />
                <span>{label}</span>
              </label>
            ))}
          </div>
        </FilterSection>

        <FilterSection title="City">
          <ChecklistFilter
            options={uniqueCities}
            selected={filters.city}
            onChange={v => setFilter('city', v)}
            labelMap={REGION_LABEL}
          />
        </FilterSection>

        <FilterSection title="State">
          <ChecklistFilter
            options={uniqueStates}
            selected={filters.state}
            onChange={v => setFilter('state', v)}
            labelMap={STATE_LABEL}
          />
        </FilterSection>
      </aside>

      <div className="main-content">
        <div className="auction-detail-header">
          <span className="auction-detail-name">Watchlist</span>
        </div>

        {filtered.length === 0 ? (
          <div className="empty-msg">No saved auctions.</div>
        ) : (
          <div className="auction-grid">
            {filtered.map(a => (
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
                    <span className="info-label">Location</span>
                    <span>{REGION_LABEL[a.region_id] || a.region_id || '—'}</span>
                  </div>
                  {a.closes_at && (
                    <div className="auction-card-info-row">
                      <span className="info-label">Starts</span>
                      <span>{new Date(a.closes_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</span>
                    </div>
                  )}
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
                    href={`https://app.marketplace.autura.com/auction/${a.region_id}/${a.auction_id}`}
                    target="_blank"
                    rel="noreferrer"
                    onClick={e => e.stopPropagation()}
                  >
                    Listing
                  </a>
                  <button className="btn" onClick={e => { e.stopPropagation(); navigate(`/auctions/${a.auction_id}`); }}>
                    View
                  </button>
                  <button className="btn" onClick={e => handleRemove(e, a.auction_id)}>
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default SavedAuctionsPage;
