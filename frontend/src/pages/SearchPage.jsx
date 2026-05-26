import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { API, authFetch } from '../api';
import { useAuth } from '../AuthContext';
import { REGION_LABEL } from '../constants';
import FilterSection from '../components/FilterSection';
import ChecklistFilter from '../components/ChecklistFilter';
import ImageCycler from '../components/ImageCycler';

const SearchPage = () => {
  const navigate = useNavigate();
  const { token } = useAuth();
  const [vehicles, setVehicles] = useState([]);
  const [liveBids, setLiveBids] = useState({});
  const [watchlistVins, setWatchlistVins] = useState(new Set());
  const [histStats, setHistStats] = useState({});
  const [searchTerm, setSearchTerm] = useState('');
  const [expandedVin, setExpandedVin] = useState(null);
  const [yearRange, setYearRange] = useState([null, null]);
  const [odoRange, setOdoRange] = useState([null, null]);
  const [filters, setFilters] = useState({
    make: new Set(), model: new Set(), region_id: new Set(),
    start_status: new Set(), engine_type: new Set(), drivetrain: new Set(),
  });

  useEffect(() => {
    fetch(`${API}/vehicles`)
      .then(r => r.json())
      .then(setVehicles)
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (!token) return;
    authFetch(token, `${API}/garage`)
      .then(r => r.json())
      .then(data => setWatchlistVins(new Set(data.map(v => v.vin))))
      .catch(console.error);
  }, [token]);

  const auctionIdKey = [...new Set(vehicles.filter(v => v.auction_id).map(v => v.auction_id))].sort().join(',');
  useEffect(() => {
    if (!auctionIdKey) return;
    setLiveBids({});
    let stopped = false;
    let source;

    const connect = () => {
      if (stopped) return;
      source = new EventSource(`${API}/stream/multi?auctions=${auctionIdKey}`);
      source.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === 'bid') {
          setLiveBids(prev => ({ ...prev, [msg.item_key]: { amount: msg.amount, expires: msg.expires } }));
        }
      };
      source.onerror = () => {
        source.close();
        if (!stopped) setTimeout(connect, 3000);
      };
    };

    connect();
    return () => { stopped = true; source?.close(); };
  }, [auctionIdKey]);

  const statsKey = (v) => `${v.make}|${v.model}|${v.year}`;

  useEffect(() => {
    if (!vehicles.length) return;
    const GENERIC = new Set(['other', 'unknown', 'misc', 'n/a', 'na']);
    const seen = new Set();
    const combos = vehicles.filter(v => {
      if (!v.make || !v.model || !v.year) return false;
      if (GENERIC.has(v.make.toLowerCase()) || GENERIC.has(v.model.toLowerCase())) return false;
      const k = statsKey(v);
      if (seen.has(k)) return false;
      seen.add(k); return true;
    });
    Promise.all(combos.map(v =>
      fetch(`${API}/historical/stats?make=${encodeURIComponent(v.make)}&model=${encodeURIComponent(v.model)}&year=${v.year}`)
        .then(r => r.json())
        .then(data => [statsKey(v), data])
        .catch(() => null)
    )).then(results => {
      const map = {};
      results.forEach(r => { if (r && r[1].count > 0) map[r[0]] = r[1]; });
      setHistStats(map);
    });
  }, [vehicles.length]);

  const parseOdo = (odoStr) => {
    if (!odoStr) return null;
    const m = odoStr.split('\n')[0].match(/:\s*([\d,]+)/);
    return m ? parseInt(m[1].replace(/,/g, '')) : null;
  };

  const years = [...new Set(vehicles.map(c => c.year).filter(Boolean))].sort();
  const minYear = years[0] ? parseInt(years[0]) : 2000;
  const maxYear = years[years.length - 1] ? parseInt(years[years.length - 1]) : new Date().getFullYear();
  const yearMin = yearRange[0] ?? minYear;
  const yearMax = yearRange[1] ?? maxYear;
  const uniqueOpts = (key) => [...new Set(vehicles.map(c => c[key]).filter(Boolean))].sort();
  const odoValues = vehicles.map(v => parseOdo(v.last_recorded_odo)).filter(v => v !== null);
  const odoSliderMin = odoValues.length ? Math.floor(Math.min(...odoValues) / 10000) * 10000 : 0;
  const odoSliderMax = odoValues.length ? Math.ceil(Math.max(...odoValues) / 10000) * 10000 : 300000;
  const odoMin = odoRange[0] ?? odoSliderMin;
  const odoMax = odoRange[1] ?? odoSliderMax;

  const setFilter = (key, val) => setFilters(prev => ({ ...prev, [key]: val }));
  const hasActiveFilters = Object.values(filters).some(s => s.size > 0) || yearRange[0] !== null || yearRange[1] !== null || odoRange[0] !== null || odoRange[1] !== null;
  const clearAll = () => {
    setFilters({ make: new Set(), model: new Set(), region_id: new Set(), start_status: new Set(), engine_type: new Set(), drivetrain: new Set() });
    setYearRange([null, null]);
    setOdoRange([null, null]);
  };

  const filtered = vehicles.filter(car => {
    const y = parseInt(car.year);
    if (!isNaN(y) && (y < yearMin || y > yearMax)) return false;
    if (odoRange[0] !== null || odoRange[1] !== null) {
      const odo = parseOdo(car.last_recorded_odo);
      if (odo !== null && (odo < odoMin || odo > odoMax)) return false;
    }
    for (const [key, sel] of Object.entries(filters)) {
      if (sel.size > 0 && !sel.has(car[key])) return false;
    }
    if (searchTerm) {
      const terms = searchTerm.toLowerCase().split(/\s+/).filter(Boolean);
      const haystack = Object.values(car).map(v => String(v || '').toLowerCase()).join(' ');
      if (!terms.every(t => haystack.includes(t))) return false;
    }
    return true;
  }).sort((a, b) => {
    const ma = (a.make || '').localeCompare(b.make || '');
    if (ma !== 0) return ma;
    const mo = (a.model || '').localeCompare(b.model || '');
    if (mo !== 0) return mo;
    return (parseInt(a.year) || 0) - (parseInt(b.year) || 0);
  });

  const toggleWatchlist = async (e, vin) => {
    e.stopPropagation();
    if (!token) { navigate('/login', { state: { from: window.location.pathname } }); return; }
    const inList = watchlistVins.has(vin);
    try {
      await authFetch(token, `${API}/garage/${vin}`, { method: inList ? 'DELETE' : 'POST' });
      setWatchlistVins(prev => {
        const next = new Set(prev);
        inList ? next.delete(vin) : next.add(vin);
        return next;
      });
    } catch (err) {
      console.error('Watchlist toggle failed:', err);
    }
  };

  const COLS = 17;
  const fmt$ = v => v != null ? `$${Number(v).toLocaleString()}` : '—';
  const getBid = (car) => liveBids[car.item_key]?.amount ?? car.current_bid;

  return (
    <div className="app-wrapper">
      <aside className="sidebar">
        <div className="sidebar-header">
          <span>Filters</span>
          {hasActiveFilters && <button className="clear-all-btn" onClick={clearAll}>Clear All</button>}
        </div>
        <FilterSection title="Year">
          <div className="year-range-labels">
            <span>{yearMin}</span><span>{yearMax}</span>
          </div>
          <input type="range" min={minYear} max={maxYear} value={yearMin}
            onChange={e => setYearRange([parseInt(e.target.value), yearRange[1]])} className="slider" />
          <input type="range" min={minYear} max={maxYear} value={yearMax}
            onChange={e => setYearRange([yearRange[0], parseInt(e.target.value)])} className="slider" />
        </FilterSection>
        <FilterSection title="Odometer">
          <div className="year-range-labels">
            <span>{odoMin.toLocaleString()} mi</span><span>{odoMax.toLocaleString()} mi</span>
          </div>
          <input type="range" min={odoSliderMin} max={odoSliderMax} step={10000} value={odoMin}
            onChange={e => setOdoRange([parseInt(e.target.value), odoRange[1]])} className="slider" />
          <input type="range" min={odoSliderMin} max={odoSliderMax} step={10000} value={odoMax}
            onChange={e => setOdoRange([odoRange[0], parseInt(e.target.value)])} className="slider" />
        </FilterSection>
        <FilterSection title="Make">
          <ChecklistFilter options={uniqueOpts('make')} selected={filters.make} onChange={v => setFilter('make', v)} />
        </FilterSection>
        <FilterSection title="Model">
          <ChecklistFilter options={uniqueOpts('model')} selected={filters.model} onChange={v => setFilter('model', v)} />
        </FilterSection>
        <FilterSection title="Status">
          <ChecklistFilter options={uniqueOpts('start_status')} selected={filters.start_status} onChange={v => setFilter('start_status', v)} />
        </FilterSection>
        <FilterSection title="Engine">
          <ChecklistFilter options={uniqueOpts('engine_type')} selected={filters.engine_type} onChange={v => setFilter('engine_type', v)} />
        </FilterSection>
        <FilterSection title="Drivetrain">
          <ChecklistFilter options={uniqueOpts('drivetrain')} selected={filters.drivetrain} onChange={v => setFilter('drivetrain', v)} />
        </FilterSection>
        <FilterSection title="Region">
          <ChecklistFilter
            options={uniqueOpts('region_id')}
            selected={filters.region_id}
            onChange={v => setFilter('region_id', v)}
            labelMap={REGION_LABEL}
          />
        </FilterSection>
      </aside>

      <div className="main-content">
        <div className="controls">
          <input
            placeholder="Search..."
            className="input-search"
            onChange={e => setSearchTerm(e.target.value)}
          />
          <span className="vehicle-count-badge">{filtered.length} / {vehicles.length} vehicles</span>
        </div>

        <div className="table-container">
          <table className="vehicle-table">
            <thead>
              <tr>
                {['Year', 'Make', 'Model', 'Region', 'Color', 'Keys', 'Cat', 'Status', 'Engine', 'Drive', 'Fuel', 'Bid', 'Reserve', 'VIN', 'Odometer', 'Avg Sale', ''].map((h, i) => (
                  <th key={i}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((car, idx) => {
                const images = car.images ? (() => { try { return JSON.parse(car.images); } catch { return []; } })() : [];
                const isExpanded = expandedVin === car.vin;
                const liked = watchlistVins.has(car.vin);
                return [
                  <tr
                    key={car.vin}
                    data-vin={car.vin}
                    className={`${idx % 2 === 0 ? 'row-even' : 'row-odd'} row-clickable ${isExpanded ? 'row-expanded' : ''}`}
                    onClick={() => setExpandedVin(isExpanded ? null : car.vin)}
                  >
                    <td>{car.year}</td>
                    <td>{car.make}</td>
                    <td>{car.model}</td>
                    <td>{REGION_LABEL[car.region_id] ?? car.region_id}</td>
                    <td>{car.color}</td>
                    <td>{car.key_status}</td>
                    <td className={car.catalytic_converter === 'Present' ? 'cat-present' : 'cat-missing'}>{car.catalytic_converter}</td>
                    <td>{car.start_status}</td>
                    <td>{car.engine_type}</td>
                    <td>{car.drivetrain}</td>
                    <td>{car.fuel_type || '—'}</td>
                    <td className={getBid(car) ? 'bid-active' : ''}>{fmt$(getBid(car))}</td>
                    <td>{fmt$(car.reserve_price)}</td>
                    <td className="vin-text">{car.vin}</td>
                    <td className="odo-text">{car.last_recorded_odo || '—'}</td>
                    <td className="avg-sale-text">{histStats[statsKey(car)] ? fmt$(histStats[statsKey(car)].avg_sale) : '—'}</td>
                    <td>
                      <button
                        className={`btn${liked ? ' saved' : ''}`}
                        onClick={e => toggleWatchlist(e, car.vin)}
                      >
                        {liked ? 'Saved' : 'Save'}
                      </button>
                    </td>
                  </tr>,
                  isExpanded && (
                    <tr key={`${car.vin}-expanded`} className="expanded-row">
                      <td colSpan={COLS}>
                        <div className="expanded-panel">
                          <div className="expanded-images">
                            <ImageCycler images={images} large />
                          </div>
                          <div className="expanded-details">
                            <div className="expanded-actions">
                              <button
                                className="btn"
                                onClick={e => { e.stopPropagation(); navigate(`/auctions/${car.auction_id}`, { state: { vin: car.vin } }); }}
                              >
                                View in Auction
                              </button>
                              <a
                                className="btn"
                                href={car.item_id
                                  ? `https://app.marketplace.autura.com/auction/${car.region_id}/${car.auction_id}/vehicle/${car.item_id}`
                                  : `https://app.marketplace.autura.com/auction/${car.region_id}/${car.auction_id}`}
                                target="_blank"
                                rel="noreferrer"
                                onClick={e => e.stopPropagation()}
                              >
                                View Listing
                              </a>
                            </div>
                            <div className="detail-grid">
                              <div className="detail-item"><span className="detail-label">Year</span><span>{car.year}</span></div>
                              <div className="detail-item"><span className="detail-label">Make</span><span>{car.make}</span></div>
                              <div className="detail-item"><span className="detail-label">Model</span><span>{car.model}</span></div>
                              <div className="detail-item"><span className="detail-label">Region</span><span>{REGION_LABEL[car.region_id] ?? car.region_id}</span></div>
                              <div className="detail-item"><span className="detail-label">Color</span><span>{car.color}</span></div>
                              <div className="detail-item"><span className="detail-label">Keys</span><span>{car.key_status}</span></div>
                              <div className="detail-item"><span className="detail-label">Cat. Converter</span><span className={car.catalytic_converter === 'Present' ? 'cat-present' : 'cat-missing'}>{car.catalytic_converter}</span></div>
                              <div className="detail-item"><span className="detail-label">Start Status</span><span>{car.start_status}</span></div>
                              <div className="detail-item"><span className="detail-label">Engine</span><span>{car.engine_type}</span></div>
                              <div className="detail-item"><span className="detail-label">Drivetrain</span><span>{car.drivetrain}</span></div>
                              <div className="detail-item"><span className="detail-label">Body</span><span>{car.body_type || '—'}</span></div>
                              <div className="detail-item"><span className="detail-label">Cylinders</span><span>{car.num_cylinders || '—'}</span></div>
                              <div className="detail-item"><span className="detail-label">Doc Type</span><span>{car.documentation_type || '—'}</span></div>
                              <div className="detail-item"><span className="detail-label">Current Bid</span><span className={getBid(car) ? 'bid-active' : ''}>{fmt$(getBid(car))}</span></div>
                              <div className="detail-item"><span className="detail-label">Avg Sale</span><span className="avg-sale-text">{histStats[statsKey(car)] ? fmt$(histStats[statsKey(car)].avg_sale) : '—'}</span></div>
                              <div className="detail-item"><span className="detail-label">Reserve</span><span>{fmt$(car.reserve_price)}</span></div>
                              <div className="detail-item"><span className="detail-label">Buyer Fee</span><span>{fmt$(car.fee_price)}</span></div>
                              {car.bid_expiration && <div className="detail-item"><span className="detail-label">Bid Expires</span><span>{new Date(car.bid_expiration).toLocaleString()}</span></div>}
                              {car.seller_notes && <div className="detail-item detail-item-full"><span className="detail-label">Seller Notes</span><span>{car.seller_notes}</span></div>}
                              <div className="detail-item detail-item-full"><span className="detail-label">VIN</span><span className="vin-text">{car.vin}</span></div>
                              {car.last_recorded_odo && (
                                <div className="detail-item detail-item-full"><span className="detail-label">Odometer History</span><span className="odo-text">{car.last_recorded_odo}</span></div>
                              )}
                            </div>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )
                ];
              })}
              {filtered.length === 0 && vehicles.length > 0 && (
                <tr><td colSpan={COLS} className="empty-msg">No vehicles match your filters.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default SearchPage;
