import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { API } from '../api';

const STATUS_LABEL = {
  'live-auction': 'Open',
  'pre-auction':  'Upcoming',
  'completed':    'Closed',
};

const REGION_LABEL = {
  'SA-TX':  'San Antonio, TX',
  'AUS-TX': 'Austin, TX',
  'DL-TX':  'Dallas – Fort Worth, TX',
  'EP-TX':  'El Paso, TX',
  'HOU-TX': 'Houston, TX',
  'CHI-IL': 'Chicago, IL',
  'DET-MI': 'Detroit, MI',
  'IN-IN':  'Indianapolis, IN',
  'KC-MO':  'Kansas City, MO',
  'LAX-CA': 'Los Angeles, CA',
  'LV-NV':  'Las Vegas, NV',
  'LX-KY':  'Lexington, KY',
  'NSH-TN': 'Nashville, TN',
  'OC-CA':  'Orange County, CA',
  'PHX-AZ': 'Phoenix, AZ',
  'RDU-NC': 'Raleigh, NC',
  'SBC-CA': 'San Bernardino, CA',
  'SD-CA':  'San Diego, CA',
  'SF-CA':  'San Francisco, CA',
  'SJ-CA':  'San Jose, CA',
  'VC-CA':  'Ventura County, CA',
  'ATL-GA': 'Atlanta, GA',
  'MIA-FL': 'Miami, FL',
  'ORL-FL': 'Orlando, FL',
  'DEN-CO': 'Denver, CO',
  'SEA-WA': 'Seattle, WA',
  'PDX-OR': 'Portland, OR',
  'MIN-MN': 'Minneapolis, MN',
  'STL-MO': 'St. Louis, MO',
  'PHL-PA': 'Philadelphia, PA',
  'BAL-MD': 'Baltimore, MD',
  'CLT-NC': 'Charlotte, NC',
  'MSP-MN': 'Minneapolis, MN',
  'NO-LA':  'New Orleans, LA',
  'OKC-OK': 'Oklahoma City, OK',
  'TUL-OK': 'Tulsa, OK',
  'ABQ-NM': 'Albuquerque, NM',
  'TUC-AZ': 'Tucson, AZ',
  'FRE-CA': 'Fresno, CA',
  'SAC-CA': 'Sacramento, CA',
  'BKR-CA': 'Bakersfield, CA',
};


const STATE_LABEL = {
  TX: 'Texas', IL: 'Illinois', MI: 'Michigan', MO: 'Missouri',
  CA: 'California', NV: 'Nevada', KY: 'Kentucky', TN: 'Tennessee',
  AZ: 'Arizona', NC: 'North Carolina', IN: 'Indiana',
};

const getState = (regionId) => regionId?.split('-').pop() || 'Unknown';

const AuctionsPage = () => {
  const [auctions, setAuctions] = useState([]);
  const [openStates, setOpenStates] = useState(new Set());
  const navigate = useNavigate();

  useEffect(() => {
    fetch(`${API}/auctions`)
      .then(r => r.json())
      .then(setAuctions)
      .catch(console.error);
  }, []);

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
