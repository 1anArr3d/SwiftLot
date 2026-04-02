import { useState } from 'react';
import { signInWithPopup, signInWithEmailAndPassword, createUserWithEmailAndPassword, sendPasswordResetEmail } from 'firebase/auth';
import { auth, googleProvider } from '../firebase';
import { useNavigate, useLocation } from 'react-router-dom';

const LoginPage = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isRegister, setIsRegister] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from || '/auctions';

  const handleGoogle = async () => {
    try {
      await signInWithPopup(auth, googleProvider);
      navigate(from, { replace: true });
    } catch (e) {
      setError(e.message);
    }
  };

  const handleForgotPassword = async () => {
    if (!email) { setError('Enter your email above first.'); return; }
    try {
      await sendPasswordResetEmail(auth, email);
      setError('');
      alert('Password reset email sent. Check your inbox.');
    } catch (e) {
      setError(e.message.replace('Firebase: ', '').replace(/ \(auth\/.*\)\.?/, ''));
    }
  };

  const handleEmail = async (e) => {
    e.preventDefault();
    setError('');
    try {
      if (isRegister) {
        await createUserWithEmailAndPassword(auth, email, password);
      } else {
        await signInWithEmailAndPassword(auth, email, password);
      }
      navigate(from, { replace: true });
    } catch (e) {
      setError(e.message.replace('Firebase: ', '').replace(/ \(auth\/.*\)\.?/, ''));
    }
  };

  return (
  <div className="login-page">
    <div className="login-card">
      {/* Centered Header Section */}
      <div style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
        <h1 className="topnav-brand" style={{ fontSize: '2rem', margin: '0 0 0.25rem 0' }}>
          SwiftLot
        </h1>
        <p className="login-subtitle" style={{ margin: '0' }}>
          Vehicle auction intelligence
        </p>
      </div>

      <button className="btn-google" onClick={handleGoogle}>
        <svg width="18" height="18" viewBox="0 0 48 48">
          <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
          <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
          <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
          <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.18 1.48-4.97 2.31-8.16 2.31-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
        </svg>
        Continue with Google
      </button>

      <div className="login-divider"><span>or</span></div>

      <form onSubmit={handleEmail} className="login-form">
        <input
          type="email"
          placeholder="Email"
          value={email}
          onChange={e => setEmail(e.target.value)}
          required
          className="login-input"
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          required
          className="login-input"
        />
        {error && <p className="login-error">{error}</p>}
        {!isRegister && (
          <button type="button" className="btn-link" onClick={handleForgotPassword}>
            Forgot password?
          </button>
        )}
        <button type="submit" className="btn-primary">
          {isRegister ? 'Create Account' : 'Sign In'}
        </button>
      </form>

      <p className="login-toggle">
        {isRegister ? 'Already have an account?' : "Don't have an account?"}
        {' '}
        <button className="btn-link" onClick={() => { setIsRegister(!isRegister); setError(''); }}>
          {isRegister ? 'Sign In' : 'Register'}
        </button>
      </p>

    </div>
  </div>
);
};

export default LoginPage;
