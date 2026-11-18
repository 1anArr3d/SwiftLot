import { useRef } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { signOut } from 'firebase/auth';
import { auth } from '../firebase';
import { useAuth } from '../AuthContext';
import { PAT } from './patterns.js';

const BRAND = { __html: PAT.brand() };
const cls = ({ isActive }) => (isActive ? 'on' : '');

export default function Nav() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const brand = useRef(null);
  // replay the drive-in and glint on hover
  const replay = () => { const b = brand.current; b.classList.remove('go'); void b.offsetWidth; b.classList.add('go'); };
  const out = async () => { await signOut(auth); navigate('/login'); };
  return (
    <header className="top">
      <b ref={brand} className="go" aria-label="SwiftLot" onMouseEnter={replay} dangerouslySetInnerHTML={BRAND} />
      <NavLink to="/" end className={cls}>Home</NavLink>
      <NavLink to="/auctions" className={cls}>Auctions</NavLink>
      <NavLink to="/search" className={cls}>Search</NavLink>
      <NavLink to="/garage" className={cls}>Garage</NavLink>
      <NavLink to="/about" className={cls}>About</NavLink>
      {/* pages write their live figure here (sale clock, totals) */}
      <span className="r" id="navr" />
      {user === undefined ? null : user
        ? <button type="button" className="auth" onClick={out}>Sign out</button>
        : <NavLink to="/login" className="auth">Sign in</NavLink>}
    </header>
  );
}
