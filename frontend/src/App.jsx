import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom';
import AuctionsPage from './pages/AuctionsPage';
import AuctionDetailPage from './pages/AuctionDetailPage';
import WatchlistPage from './pages/WatchlistPage';
import './App.css';

const App = () => (
  <BrowserRouter>
    <nav className="topnav">
      <span className="topnav-brand">SwiftLot</span>
      <NavLink to="/auctions" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>Auctions</NavLink>
      <NavLink to="/watchlist" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>Watchlist</NavLink>
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
