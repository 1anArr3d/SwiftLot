import { useState, useEffect } from 'react';
import './App.css';

const FilterSection = ({ title, children, defaultOpen = false }) => {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="filter-section">
      <button className={`filter-section-title ${open ? 'is-open' : ''}`} onClick={() => setOpen(o => !o)}>
        <span>{title}</span>
        <span className={`filter-arrow ${open ? 'open' : ''}`}>›</span>
      </button>
      {open && <div className="filter-section-body">{children}</div>}
    </div>
  );
};

const ChecklistFilter = ({ options, selected, onChange }) => {
  const toggle = (val) => {
    const next = new Set(selected);
    next.has(val) ? next.delete(val) : next.add(val);
    onChange(next);
  };
  return (
    <div className="checklist">
      {options.map(opt => (
        <label key={opt} className="checklist-item">
          <input type="checkbox" checked={selected.has(opt)} onChange={() => toggle(opt)} />
          <span>{opt || '—'}</span>
        </label>
      ))}
    </div>
  );
};

const ImageCycler = ({ images, large = false }) => {
  const [idx, setIdx] = useState(0);
  const [lightbox, setLightbox] = useState(false);

  const prev = (e) => { e.stopPropagation(); setIdx(i => (i - 1 + images.length) % images.length); };
  const next = (e) => { e.stopPropagation(); setIdx(i => (i + 1) % images.length); };

  useEffect(() => {
    if (!lightbox) return;
    const onKey = (e) => {
      if (e.key === 'Escape') setLightbox(false);
      if (e.key === 'ArrowLeft') setIdx(i => (i - 1 + images.length) % images.length);
      if (e.key === 'ArrowRight') setIdx(i => (i + 1) % images.length);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [lightbox, images.length]);

  if (!images || images.length === 0) return <div className={`no-img ${large ? 'no-img-large' : ''}`}>No Photos</div>;
  return (
    <>
      <div className={`img-cycler ${large ? 'img-cycler-large' : ''}`}>
        <div
          className={`cycler-img-wrap ${large ? 'cycler-img-wrap-large' : ''}`}
          onClick={large ? (e) => { e.stopPropagation(); setLightbox(true); } : undefined}
        >
          <img src={images[idx]} alt="vehicle" className={`cycler-img ${large ? 'cycler-img-large' : ''}`} />
        </div>
        {images.length > 1 && (
          <div className="cycler-controls">
            <button onClick={prev}>‹</button>
            <span>{idx + 1}/{images.length}</span>
            <button onClick={next}>›</button>
          </div>
        )}
      </div>

      {lightbox && (
        <div className="lightbox-overlay" onClick={() => setLightbox(false)}>
          <button className="lightbox-close" onClick={() => setLightbox(false)}>✕</button>
          <button className="lightbox-arrow lightbox-prev" onClick={prev}>‹</button>
          <img
            src={images[idx]}
            alt="vehicle"
            className="lightbox-img"
            onClick={e => e.stopPropagation()}
          />
          <button className="lightbox-arrow lightbox-next" onClick={next}>›</button>
          <div className="lightbox-counter">{idx + 1} / {images.length}</div>
        </div>
      )}
    </>
  );
};

const App = () => {
  const [vehicles, setVehicles] = useState([]);
  const [auctionId, setAuctionId] = useState("");
  const [city, setCity] = useState("SA-TX");
  const [scrapeStatus, setScrapeStatus] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [loadingVins, setLoadingVins] = useState(new Set());
  const [expandedVin, setExpandedVin] = useState(null);

  const [yearRange, setYearRange] = useState([null, null]);
  const [filters, setFilters] = useState({
    make: new Set(), model: new Set(), start_status: new Set(),
    engine_type: new Set(), transmission: new Set(),
  });

  const fetchVehicles = async () => {
    try {
      const res = await fetch("http://127.0.0.1:8000/vehicles");
      const data = await res.json();
      setVehicles(data);
    } catch (err) {
      console.error("Fetch failed:", err);
    }
  };

  const handleAction = async (path, method = 'POST') => {
    const res = await fetch(`http://127.0.0.1:8000${path}`, { method });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Request failed: ${res.status}`);
    }
    return res.json();
  };

  const handleScrapeAuction = async () => {
    if (!auctionId) return;
    try {
      setScrapeStatus('running');
      await handleAction(`/scrape/${auctionId}?city=${city}`);
      const poll = setInterval(async () => {
        try {
          const res = await fetch(`http://127.0.0.1:8000/scrape/${auctionId}/status`);
          const data = await res.json();
          setScrapeStatus(data.status);
          if (data.status !== 'running') clearInterval(poll);
        } catch { clearInterval(poll); setScrapeStatus('failed'); }
      }, 2000);
    } catch (err) {
      setScrapeStatus('failed');
      alert(`Scrape failed: ${err.message}`);
    }
  };

  const handleInspectVin = async (e, vin) => {
    e.stopPropagation();
    setLoadingVins(prev => new Set(prev).add(vin));
    try {
      await handleAction(`/inspectionscrape/${vin}`);
    } catch (err) {
      alert(`Inspection failed for ${vin}: ${err.message}`);
    } finally {
      setLoadingVins(prev => { const s = new Set(prev); s.delete(vin); return s; });
    }
  };

  useEffect(() => {
    fetchVehicles();
  }, []);

  const years = [...new Set(vehicles.map(c => c.year).filter(Boolean))].sort();
  const minYear = years[0] ? parseInt(years[0]) : 2000;
  const maxYear = years[years.length - 1] ? parseInt(years[years.length - 1]) : new Date().getFullYear();
  const yearMin = yearRange[0] ?? minYear;
  const yearMax = yearRange[1] ?? maxYear;

  const uniqueOpts = (key) => [...new Set(vehicles.map(c => c[key]).filter(Boolean))].sort();

  const setFilter = (key, val) => setFilters(prev => ({ ...prev, [key]: val }));

  const hasActiveFilters = Object.values(filters).some(s => s.size > 0) ||
    yearRange[0] !== null || yearRange[1] !== null;

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
      if (!Object.values(car).some(v => String(v || "").toLowerCase().includes(term))) return false;
    }
    return true;
  });

  const COLS = 11;

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
            onChange={e => setYearRange([parseInt(e.target.value), yearRange[1]])}
            className="slider" />
          <input type="range" min={minYear} max={maxYear} value={yearMax}
            onChange={e => setYearRange([yearRange[0], parseInt(e.target.value)])}
            className="slider" />
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
        <header className="main-header">
          <div className="header-info">
            <h1>Auction Inventory</h1>
            <div className="vehicle-count">{filteredVehicles.length} / {vehicles.length} Units</div>
          </div>
          <div className="controls">
            <input
              placeholder="Auction ID"
              value={auctionId}
              onChange={e => setAuctionId(e.target.value)}
              className="input-auction"
            />
            <input
              placeholder="City (e.g. SA-TX)"
              value={city}
              onChange={e => setCity(e.target.value)}
              className="input-auction"
            />
            <button onClick={handleScrapeAuction} className={`btn-start ${scrapeStatus === 'running' ? 'btn-running' : ''}`} disabled={scrapeStatus === 'running'}>
              {scrapeStatus === 'running' ? 'Scraping...' : scrapeStatus === 'done' ? 'Done ✓' : scrapeStatus === 'failed' ? 'Failed ✗' : 'Scrape Auction'}
            </button>
            <button onClick={() => { if (window.confirm("Clear all?")) handleAction('/vehicles', 'DELETE').then(() => setScrapeStatus(null)).catch(err => alert(err.message)); }} className="btn-clear">
              Clear
            </button>
            <input
              placeholder="Search..."
              className="input-search"
              onChange={e => setSearchTerm(e.target.value)}
            />
          </div>
        </header>

        <div className="table-container">
          <table className="vehicle-table">
            <thead>
              <tr>
                {["Year", "Make", "Model", "Color", "Keys", "Cat", "Status", "Engine", "Trans", "VIN", "Odometer"].map(h => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredVehicles.map((car, idx) => {
                const images = car.images ? JSON.parse(car.images) : [];
                const isExpanded = expandedVin === car.vin;
                return (
                  <>
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
                      <td className={car.catalytic_converter === 'Present' ? 'cat-present' : 'cat-missing'}>
                        {car.catalytic_converter}
                      </td>
                      <td>{car.start_status}</td>
                      <td>{car.engine_type}</td>
                      <td>{car.transmission}</td>
                      <td className="vin-text">{car.vin}</td>
                      <td className="odo-text">{car.last_recorded_odo || '—'}</td>
                    </tr>
                    {isExpanded && (
                      <tr key={`${car.vin}-expanded`} className="expanded-row">
                        <td colSpan={COLS}>
                          <div className="expanded-panel">
                            <div className="expanded-images">
                              <ImageCycler images={images} large />
                            </div>
                            <div className="expanded-details">
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
                              {car.city?.endsWith('-TX') && (
                                <button
                                  onClick={e => handleInspectVin(e, car.vin)}
                                  disabled={loadingVins.has(car.vin)}
                                  className={`btn-inspect ${loadingVins.has(car.vin) ? 'loading' : ''}`}
                                >
                                  {loadingVins.has(car.vin) ? 'Scraping...' : 'Inspect VIN'}
                                </button>
                              )}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default App;
