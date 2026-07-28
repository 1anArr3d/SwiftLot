import { useState, useRef, useEffect } from 'react'; // v2
import { BrowserRouter, Routes, Route, NavLink, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { signOut } from 'firebase/auth';
import { auth } from './firebase';
import { AuthProvider, useAuth } from './AuthContext';
import AuctionsPage from './pages/AuctionsPage';
import AuctionDetailPage from './pages/AuctionDetailPage';
import WatchlistPage from './pages/WatchlistPage';
import SavedAuctionsPage from './pages/SavedAuctionsPage';
import LoginPage from './pages/LoginPage';
import AboutPage from './pages/AboutPage';
import HomePage from './pages/HomePage';
import SearchPage from './pages/SearchPage';
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
  const [openDropdown, setOpenDropdown] = useState(null);
  const navRef = useRef(null);

  const handleSignOut = async () => {
    await signOut(auth);
    navigate('/login');
    setMenuOpen(false);
    setOpenDropdown(null);
  };

  useEffect(() => {
    const handler = (e) => {
      if (navRef.current && !navRef.current.contains(e.target)) setOpenDropdown(null);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const toggle = (name) => setOpenDropdown(prev => prev === name ? null : name);
  const close = () => { setMenuOpen(false); setOpenDropdown(null); };

  return (
    <header className="site-header" ref={navRef}>
      {/* Top bar: brand + auth */}
      <div className="topbar">
        <NavLink to="/" className="topnav-brand" onClick={close}>SwiftLot</NavLink>
        <div className="topbar-auth">
          {user
            ? <button className="nav-auth-btn" onClick={handleSignOut}>Sign Out</button>
            : <NavLink to="/login" className="nav-auth-btn">Sign In</NavLink>
          }
        </div>
      </div>

      {/* Bottom bar: navigation dropdowns */}
      <nav className="topnav">
        <button className="nav-hamburger" onClick={() => setMenuOpen(o => !o)} aria-label="Menu">
          <span /><span /><span />
        </button>

        <div className={`nav-menu${menuOpen ? ' open' : ''}`}>
          <div className="nav-dropdown">
            <button className={`nav-dropdown-trigger${openDropdown === 'browse' ? ' active' : ''}`} onClick={() => toggle('browse')}>
              Browse <span className="nav-caret">▾</span>
            </button>
            {openDropdown === 'browse' && (
              <div className="nav-dropdown-panel">
                <NavLink to="/auctions" className="nav-dropdown-item" onClick={close}>Auctions</NavLink>
                <NavLink to="/search" className="nav-dropdown-item" onClick={close}>Search Vehicles</NavLink>
              </div>
            )}
          </div>

          <div className="nav-dropdown">
            <button className={`nav-dropdown-trigger${openDropdown === 'account' ? ' active' : ''}`} onClick={() => toggle('account')}>
              My Account <span className="nav-caret">▾</span>
            </button>
            {openDropdown === 'account' && (
              <div className="nav-dropdown-panel">
                <NavLink to="/watchlist" className="nav-dropdown-item" onClick={close}>Watchlist</NavLink>
                <NavLink to="/my-garage" className="nav-dropdown-item" onClick={close}>My Garage</NavLink>
              </div>
            )}
          </div>

          <NavLink to="/about" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} onClick={close}>About</NavLink>
        </div>
      </nav>
    </header>
  );
};

const App = () => (
  <BrowserRouter>
    <AuthProvider>
      <NavBar />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<HomePage />} />
        <Route path="/auctions" element={<AuctionsPage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/auctions/:id" element={<AuctionDetailPage />} />
        <Route path="/watchlist" element={<ProtectedRoute><SavedAuctionsPage /></ProtectedRoute>} />
        <Route path="/my-garage" element={<ProtectedRoute><WatchlistPage /></ProtectedRoute>} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="*" element={
          <div style={{ padding: '64px 32px', textAlign: 'center', color: 'var(--text-secondary)' }}>
            <div style={{ fontSize: 48, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 12 }}>404</div>
            <div style={{ fontSize: 18, marginBottom: 24 }}>Page not found.</div>
            <a href="/" style={{ color: 'var(--steel-highlight)' }}>Back to home</a>
          </div>
        } />
      </Routes>
    </AuthProvider>
  </BrowserRouter>
);

export default App;
