import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { API } from '../api';
import FilterSection from '../components/FilterSection';
import ChecklistFilter from '../components/ChecklistFilter';
import ImageCycler from '../components/ImageCycler';

const AuctionDetailPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [auction, setAuction] = useState(null);
  const [vehicles, setVehicles] = useState([]);
  const [watchlistVins, setWatchlistVins] = useState(new Set());
  const [searchTerm, setSearchTerm] = useState('');
  const [expandedVin, setExpandedVin] = useState(null);
  const [yearRange, setYearRange] = useState([null, null]);
  const [filters, setFilters] = useState({
    make: new Set(), model: new Set(), start_status: new Set(),
    engine_type: new Set(), transmission: new Set(),
  });

  useEffect(() => {
    fetch(`${API}/auctions/${id}`)
      .then(r => r.json())
      .then(setAuction)
      .catch(console.error);
    fetch(`${API}/auctions/${id}/vehicles`)
      .then(r => r.json())
      .then(setVehicles)
      .catch(console.error);
    fetch(`${API}/watchlist`)
      .then(r => r.json())
      .then(data => setWatchlistVins(new Set(data.map(v => v.vin))))
      .catch(console.error);
  }, [id]);

  const toggleWatchlist = async (e, vin) => {
    e.stopPropagation();
    const inList = watchlistVins.has(vin);
    try {
      await fetch(`${API}/watchlist/${vin}`, { method: inList ? 'DELETE' : 'POST' });
      setWatchlistVins(prev => {
        const next = new Set(prev);
        inList ? next.delete(vin) : next.add(vin);
        return next;
      });
    } catch (err) {
      console.error('Watchlist toggle failed:', err);
    }
  };

  const years = [...new Set(vehicles.map(c => c.year).filter(Boolean))].sort();
  const minYear = years[0] ? parseInt(years[0]) : 2000;
  const maxYear = years[years.length - 1] ? parseInt(years[years.length - 1]) : new Date().getFullYear();
  const yearMin = yearRange[0] ?? minYear;
  const yearMax = yearRange[1] ?? maxYear;
  const uniqueOpts = (key) => [...new Set(vehicles.map(c => c[key]).filter(Boolean))].sort();
  const setFilter = (key, val) => setFilters(prev => ({ ...prev, [key]: val }));
  const hasActiveFilters = Object.values(filters).some(s => s.size > 0) || yearRange[0] !== null || yearRange[1] !== null;
  const clearAll = () => {
    setFilters({ make: new Set(), model: new Set(), start_status: new Set(), engine_type: new Set(), transmission: new Set() });
    setYearRange([null, null]);
  };

  const filteredVehicles = vehicles.filter(car => {
    const y = parseInt(car.year);
    if (!isNaN(y) && (y < yearMin || y > yearMax)) return false;
    for (const [key, sel] of Object.entries(filters)) {
      if (sel.size > 0 && !sel.has(car[key])) return false;
    }
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      if (!Object.values(car).some(v => String(v || '').toLowerCase().includes(term))) return false;
    }
    return true;
  });

  const COLS = 13;

  return (
    <div className="app-wrapper">
      <aside className="sidebar">
        <div className="sidebar-header">
          <span>Filters</span>
          {hasActiveFilters && <button className="clear-all-btn" onClick={clearAll}>Clear All</button>}
        </div>
        <FilterSection title="Year" defaultOpen={true}>
          <div className="year-range-labels">
            <span>{yearMin}</span><span>{yearMax}</span>
          </div>
          <input type="range" min={minYear} max={maxYear} value={yearMin}
            onChange={e => setYearRange([parseInt(e.target.value), yearRange[1]])} className="slider" />
          <input type="range" min={minYear} max={maxYear} value={yearMax}
            onChange={e => setYearRange([yearRange[0], parseInt(e.target.value)])} className="slider" />
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
        <FilterSection title="Transmission">
          <ChecklistFilter options={uniqueOpts('transmission')} selected={filters.transmission} onChange={v => setFilter('transmission', v)} />
        </FilterSection>
      </aside>

      <div className="main-content">
        <div className="auction-detail-header">
          <div className="auction-detail-header-left">
            <button className="btn" onClick={() => navigate(-1)}>Back</button>
            <div className="auction-detail-title">
              <span className="auction-detail-name">{auction?.title || auction?.seller_name || id}</span>
              {auction?.region_id && <span className="auction-detail-meta">{auction.region_id}</span>}
            </div>
          </div>
          <div className="auction-detail-header-right">
            <span className="vehicle-count-badge">{filteredVehicles.length} / {vehicles.length} vehicles</span>
            {auction && (
              <a
                className="btn"
                href={`https://app.marketplace.autura.com/auction/${auction.region_id}/auction-${id}`}
                target="_blank"
                rel="noreferrer"
              >
                Listing
              </a>
            )}
          </div>
        </div>
        <div className="controls">
          <input
            placeholder="Search..."
            className="input-search"
            onChange={e => setSearchTerm(e.target.value)}
          />
        </div>

        <div className="table-container">
          <table className="vehicle-table">
            <thead>
              <tr>
                {['Year', 'Make', 'Model', 'Color', 'Keys', 'Cat', 'Status', 'Engine', 'Trans', 'Fuel', 'VIN', 'Odometer', ''].map((h, i) => (
                  <th key={i}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredVehicles.map((car, idx) => {
                const images = car.images ? JSON.parse(car.images) : [];
                const isExpanded = expandedVin === car.vin;
                const liked = watchlistVins.has(car.vin);
                return [
                  <tr
                    key={car.vin}
                    className={`${idx % 2 === 0 ? 'row-even' : 'row-odd'} row-clickable ${isExpanded ? 'row-expanded' : ''}`}
                    onClick={() => setExpandedVin(isExpanded ? null : car.vin)}
                  >
                    <td>{car.year}</td>
                    <td>{car.make}</td>
                    <td>{car.model}</td>
                    <td>{car.color}</td>
                    <td>{car.key_status}</td>
                    <td className={car.catalytic_converter === 'Present' ? 'cat-present' : 'cat-missing'}>{car.catalytic_converter}</td>
                    <td>{car.start_status}</td>
                    <td>{car.engine_type}</td>
                    <td>{car.transmission}</td>
                    <td>{car.fuel_type || '—'}</td>
                    <td className="vin-text">{car.vin}</td>
                    <td className="odo-text">{car.last_recorded_odo || '—'}</td>
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
                              <a
                                className="btn"
                                href={car.vehicle_id
                                  ? `https://app.marketplace.autura.com/auction/${car.city}/auction-${car.auction_id}/vehicle/${car.vehicle_id}`
                                  : `https://app.marketplace.autura.com/auction/${car.city}/auction-${car.auction_id}`}
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
                              <div className="detail-item"><span className="detail-label">Color</span><span>{car.color}</span></div>
                              <div className="detail-item"><span className="detail-label">Keys</span><span>{car.key_status}</span></div>
                              <div className="detail-item"><span className="detail-label">Cat. Converter</span><span className={car.catalytic_converter === 'Present' ? 'cat-present' : 'cat-missing'}>{car.catalytic_converter}</span></div>
                              <div className="detail-item"><span className="detail-label">Start Status</span><span>{car.start_status}</span></div>
                              <div className="detail-item"><span className="detail-label">Engine</span><span>{car.engine_type}</span></div>
                              <div className="detail-item"><span className="detail-label">Transmission</span><span>{car.transmission}</span></div>
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
              {filteredVehicles.length === 0 && (
                <tr><td colSpan={COLS} className="empty-msg">No vehicles available.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default AuctionDetailPage;
