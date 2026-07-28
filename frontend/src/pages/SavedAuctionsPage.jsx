import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { API, authFetch } from '../api';
import { useAuth } from '../AuthContext';
import FilterSection from '../components/FilterSection';
import ChecklistFilter from '../components/ChecklistFilter';

const FAR_FUTURE = '9999-12-31T00:00:00.000Z';

const SavedAuctionsPage = () => {
  const [auctions, setAuctions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ city: new Set(), state: new Set() });
  const navigate = useNavigate();
  const { token } = useAuth();

  useEffect(() => {
    if (!token) return;
    authFetch(token, `${API}/saved-auctions`)
      .then(r => r.json())
      .then(setAuctions)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [token]);

  const handleRemove = async (e, regionId) => {
    e.stopPropagation();
    await authFetch(token, `${API}/saved-auctions/${regionId}`, { method: 'DELETE' });
    setAuctions(prev => prev.filter(a => a.region_id !== regionId));
  };

  const uniqueCities = [...new Set(auctions.map(a => a.seller_city).filter(Boolean))].sort();
  const uniqueStates = [...new Set(auctions.map(a => a.seller_state).filter(Boolean))].sort();

  const setFilter = (key, val) => setFilters(prev => ({ ...prev, [key]: val }));
  const hasActiveFilters = filters.city.size > 0 || filters.state.size > 0;
  const clearAll = () => setFilters({ city: new Set(), state: new Set() });

  const filtered = auctions
    .filter(a => {
      if (filters.city.size > 0 && !filters.city.has(a.seller_city)) return false;
      if (filters.state.size > 0 && !filters.state.has(a.seller_state)) return false;
      return true;
    })
    .sort((a, b) => (a.closes_at || FAR_FUTURE).localeCompare(b.closes_at || FAR_FUTURE));

  return (
    <div className="app-wrapper">
      <aside className="sidebar">
        <div className="sidebar-header">
          <span>Filters</span>
          {hasActiveFilters && <button className="clear-all-btn" onClick={clearAll}>Clear All</button>}
        </div>

        <FilterSection title="City">
          <ChecklistFilter
            options={uniqueCities}
            selected={filters.city}
            onChange={v => setFilter('city', v)}
          />
        </FilterSection>

        <FilterSection title="State">
          <ChecklistFilter
            options={uniqueStates}
            selected={filters.state}
            onChange={v => setFilter('state', v)}
          />
        </FilterSection>
      </aside>

      <div className="main-content">
        <div className="auction-detail-header">
          <span className="auction-detail-name">Watchlist</span>
        </div>

        {loading ? (
          <div className="empty-msg">Loading…</div>
        ) : filtered.length === 0 ? (
          <div className="empty-msg">No saved auctions.</div>
        ) : (
          <div className="auction-grid">
            {filtered.map(a => (
              <div
                key={a.region_id}
                className={`auction-card${a.vehicles_listed > 0 ? ' has-vehicles' : ''}`}
                onClick={() => navigate(`/auctions/${a.region_id}`)}
              >
                <div className="auction-card-top">
                  <div className="auction-card-seller">{a.seller_name || a.region_id}</div>
                </div>

                <div className="auction-card-divider" />

                <div className="auction-card-info">
                  {(a.seller_city || a.seller_state) && (
                    <div className="auction-card-info-row">
                      <span className="info-label">Location</span>
                      <span>{[a.seller_city, a.seller_state].filter(Boolean).join(', ')}</span>
                    </div>
                  )}
                  {a.closes_at && (
                    <div className="auction-card-info-row">
                      <span className="info-label">Ends</span>
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
                    href={`https://mp.autura.com/auctions?seller=${a.region_id}`}
                    target="_blank"
                    rel="noreferrer"
                    onClick={e => e.stopPropagation()}
                  >
                    Listing
                  </a>
                  <button className="btn" onClick={e => handleRemove(e, a.region_id)}>
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
