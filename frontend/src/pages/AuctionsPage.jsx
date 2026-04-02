import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { API, authFetch } from '../api';
import { useAuth } from '../AuthContext';
import { REGION_LABEL, STATE_LABEL, getState } from '../constants';

const AuctionsPage = () => {
  const [auctions, setAuctions] = useState([]);
  const [openStates, setOpenStates] = useState(new Set());
  const [savedIds, setSavedIds] = useState(new Set());
  const navigate = useNavigate();
  const { token } = useAuth();

  useEffect(() => {
    fetch(`${API}/auctions`)
      .then(r => r.json())
      .then(setAuctions)
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (!token) return;
    authFetch(token, `${API}/saved-auctions`)
      .then(r => r.json())
      .then(data => setSavedIds(new Set(data.map(a => a.auction_id))))
      .catch(console.error);
  }, [token]);

  const toggleSave = async (e, auctionId) => {
    e.stopPropagation();
    if (!token) { navigate('/login'); return; }
    const isSaved = savedIds.has(auctionId);
    await authFetch(token, `${API}/saved-auctions/${auctionId}`, { method: isSaved ? 'DELETE' : 'POST' });
    setSavedIds(prev => {
      const next = new Set(prev);
      isSaved ? next.delete(auctionId) : next.add(auctionId);
      return next;
    });
  };

  const active = auctions.filter(a => a.auction_status !== 'completed');
  const states = [...new Set(active.map(a => getState(a.region_id)))].sort();
  const byState = states.reduce((acc, s) => {
    acc[s] = active.filter(a => getState(a.region_id) === s);
    return acc;
  }, {});

  const toggleState = (state) => {
    setOpenStates(prev => {
      const next = new Set(prev);
      next.has(state) ? next.delete(state) : next.add(state);
      return next;
    });
  };

  if (active.length === 0) {
    return (
      <div className="page-content">
        <div className="empty-msg">No auctions found.</div>
      </div>
    );
  }

  return (
    <div className="page-content">
      {states.map(state => {
        const stateAuctions = byState[state];
        if (!stateAuctions.length) return null;
        const isOpen = openStates.has(state);
        const stateLabel = STATE_LABEL[state] || state;
        const regions = [...new Set(stateAuctions.map(a => a.region_id))].sort();

        return (
          <div key={state} className="state-section">
            <div className="state-section-header" onClick={() => toggleState(state)}>
              <span className="state-section-label">{stateLabel}</span>
              <div className="state-section-right">
                <span className="state-section-count">{stateAuctions.length} auction{stateAuctions.length !== 1 ? 's' : ''}</span>
                <span className="state-section-toggle">{isOpen ? '▲' : '▼'}</span>
              </div>
            </div>

            {isOpen && (
              <div className="state-body">
                {regions.map(regionId => {
                  const regionAuctions = stateAuctions.filter(a => a.region_id === regionId);
                  if (!regionAuctions.length) return null;
                  const regionLabel = REGION_LABEL[regionId] || regionId;

                  return (
                    <div key={regionId} className="region-section">
                      <div className="region-hero">
                        <div className="region-hero-overlay">
                          <h2 className="region-hero-title">{regionLabel}</h2>
                        </div>
                      </div>

                      <div className="auction-grid">
                        {regionAuctions.map(a => (
                          <div
                            key={a.auction_id}
                            className={`auction-card${a.vehicles_listed > 0 ? ' has-vehicles' : ''}${a.auction_status === 'live' || a.auction_status === 'paused' ? ' is-live' : ''}`}
                            onClick={() => navigate(`/auctions/${a.auction_id}`)}
                          >
                            <div className="auction-card-top">
                              <div className="auction-card-seller">{a.seller_name || a.auction_id}</div>
                              {(a.auction_status === 'live' || a.auction_status === 'paused') && (
                                <span className={`badge-live${a.auction_status === 'paused' ? ' badge-paused' : ''}`}>
                                  {a.auction_status === 'paused' ? 'PAUSED' : 'LIVE'}
                                </span>
                              )}
                            </div>

                            <div className="auction-card-divider" />

                            <div className="auction-card-info">
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
                              <button
                                className={`btn${savedIds.has(a.auction_id) ? ' saved' : ''}`}
                                onClick={e => toggleSave(e, a.auction_id)}
                              >
                                {savedIds.has(a.auction_id) ? 'Saved' : 'Save'}
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default AuctionsPage;
