import { useState } from 'react';
import { BrowserRouter, Routes, Route, NavLink, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { signOut } from 'firebase/auth';
import { auth } from './firebase';
import { AuthProvider, useAuth } from './AuthContext';
import AuctionsPage from './pages/AuctionsPage';
import AuctionDetailPage from './pages/AuctionDetailPage';
import WatchlistPage from './pages/WatchlistPage';
import SavedAuctionsPage from './pages/SavedAuctionsPage';
import LoginPage from './pages/LoginPage';
import './App.css';

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
  const [menuOpen, setMenuOpen] = useState(false);

  const handleSignOut = async () => {
    await signOut(auth);
    navigate('/login');
    setMenuOpen(false);
  };

  const close = () => setMenuOpen(false);

  return (
    <nav className="topnav">
      <NavLink to="/auctions" className="topnav-brand" onClick={close}>SwiftLot</NavLink>
      <button className="nav-hamburger" onClick={() => setMenuOpen(o => !o)} aria-label="Menu">
        <span /><span /><span />
      </button>
      <div className={`nav-menu${menuOpen ? ' open' : ''}`}>
        <NavLink to="/auctions" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} onClick={close}>Auctions</NavLink>
        <NavLink to="/watchlist" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} onClick={close}>Watchlist</NavLink>
        <NavLink to="/my-garage" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} onClick={close}>My Garage</NavLink>
        {user
          ? <button className="btn-link nav-signout" onClick={handleSignOut}>Sign Out</button>
          : <NavLink to="/login" className="nav-link nav-signout" onClick={close}>Sign In</NavLink>
        }
      </div>
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
        <Route path="/watchlist" element={<ProtectedRoute><SavedAuctionsPage /></ProtectedRoute>} />
        <Route path="/my-garage" element={<ProtectedRoute><WatchlistPage /></ProtectedRoute>} />
      </Routes>
    </AuthProvider>
  </BrowserRouter>
);

export default App;
