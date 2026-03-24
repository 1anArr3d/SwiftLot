import { useState, useEffect } from 'react';
import { API } from '../api';
import ImageCycler from '../components/ImageCycler';

const WatchlistPage = () => {
  const [vehicles, setVehicles] = useState([]);
  const [expandedVin, setExpandedVin] = useState(null);

  useEffect(() => {
    fetch(`${API}/watchlist`)
      .then(r => r.json())
      .then(setVehicles)
      .catch(console.error);
  }, []);

  const handleRemove = async (e, vin) => {
    e.stopPropagation();
    await fetch(`${API}/watchlist/${vin}`, { method: 'DELETE' });
    setVehicles(prev => prev.filter(v => v.vin !== vin));
  };

  const COLS = 12;

  return (
    <div className="page-content">
      <header className="main-header">
        <div className="header-info">
          <h1>Watchlist</h1>
          <div className="vehicle-count">{vehicles.length} Saved</div>
        </div>
      </header>

      <div className="table-container">
        <table className="vehicle-table">
          <thead>
            <tr>
              {['Year', 'Make', 'Model', 'Color', 'Keys', 'Cat', 'Status', 'Engine', 'Trans', 'VIN', 'Odometer', ''].map((h, i) => (
                <th key={i}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {vehicles.map((car, idx) => {
              const images = car.images ? JSON.parse(car.images) : [];
              const isExpanded = expandedVin === car.vin;
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
                  <td className="vin-text">{car.vin}</td>
                  <td className="odo-text">{car.last_recorded_odo || '—'}</td>
                  <td>
                    <button className="btn-remove" onClick={e => handleRemove(e, car.vin)}>✕</button>
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
            {vehicles.length === 0 && (
              <tr><td colSpan={COLS} className="empty-msg">No saved vehicles.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default WatchlistPage;
