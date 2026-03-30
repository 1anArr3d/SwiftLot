import { useState } from 'react';
import { BrowserRouter, Routes, Route, NavLink, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { signOut } from 'firebase/auth';
import { auth } from './firebase';
import { AuthProvider, useAuth } from './AuthContext';
import AuctionsPage from './pages/AuctionsPage';
import AuctionDetailPage from './pages/AuctionDetailPage';
import WatchlistPage from './pages/WatchlistPage';
import LoginPage from './pages/LoginPage';
import { API } from './api';
import './App.css';

const PipelineButton = () => {
  const [status, setStatus] = useState('idle');
  const { token } = useAuth();

  const run = async () => {
    if (status === 'running') return;
    setStatus('running');
    try {
      await fetch(`${API}/pipeline/run`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch (e) {
      console.error('Pipeline error:', e);
    }
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

const ProtectedRoute = ({ children }) => {
  const { user } = useAuth();
  const location = useLocation();
  if (user === undefined) return null;
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  return children;
};

const NavBar = () => {
  const { user } = useAuth();
  const navigate = useNavigate();

  const handleSignOut = async () => {
    await signOut(auth);
    navigate('/login');
  };

  return (
    <nav className="topnav">
      <NavLink to="/auctions" className="topnav-brand">SwiftLot</NavLink>
      <NavLink to="/auctions" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>Auctions</NavLink>
      <NavLink to="/watchlist" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>Watchlist</NavLink>
      {user && <PipelineButton />}
      {user
        ? <button className="btn-link nav-signout" onClick={handleSignOut}>Sign Out</button>
        : <NavLink to="/login" className="nav-link nav-signout">Sign In</NavLink>
      }
    </nav>
  );
};

const App = () => (
  <BrowserRouter>
    <AuthProvider>
      <NavBar />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<Navigate to="/auctions" replace />} />
        <Route path="/auctions" element={<AuctionsPage />} />
        <Route path="/auctions/:id" element={<AuctionDetailPage />} />
        <Route path="/watchlist" element={<ProtectedRoute><WatchlistPage /></ProtectedRoute>} />
      </Routes>
    </AuthProvider>
  </BrowserRouter>
);

export default App;
