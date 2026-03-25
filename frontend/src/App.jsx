import { useState } from 'react';
import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom';
import AuctionsPage from './pages/AuctionsPage';
import AuctionDetailPage from './pages/AuctionDetailPage';
import WatchlistPage from './pages/WatchlistPage';
import { API } from './api';
import './App.css';

const PipelineButton = () => {
  const [status, setStatus] = useState('idle'); // idle | running | done

  const run = async () => {
    if (status === 'running') return;
    setStatus('running');
    try {
      await fetch(`${API}/pipeline/run`, { method: 'POST' });
    } catch (e) {
      console.error('Pipeline error:', e);
    }
    // Pipeline runs in background — flip to done after a short delay
    setTimeout(() => setStatus('done'), 2000);
    setTimeout(() => setStatus('idle'), 5000);
  };

  const label = status === 'running' ? 'Running...' : status === 'done' ? 'Done ✓' : 'Run';

  return (
    <button
      className={`btn-pipeline${status === 'running' ? ' running' : ''}`}
      onClick={run}
      disabled={status === 'running'}
    >
      {label}
    </button>
  );
};

const App = () => (
  <BrowserRouter>
    <nav className="topnav">
      <NavLink to="/auctions" className="topnav-brand">SwiftLot</NavLink>
      <NavLink to="/auctions" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>Auctions</NavLink>
      <NavLink to="/watchlist" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>Watchlist</NavLink>
      <PipelineButton />
    </nav>
    <Routes>
      <Route path="/" element={<Navigate to="/auctions" replace />} />
      <Route path="/auctions" element={<AuctionsPage />} />
      <Route path="/auctions/:id" element={<AuctionDetailPage />} />
      <Route path="/watchlist" element={<WatchlistPage />} />
    </Routes>
  </BrowserRouter>
);

export default App;
