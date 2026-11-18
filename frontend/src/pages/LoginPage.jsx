import { useState } from 'react';
import { signInWithPopup, signInWithEmailAndPassword, createUserWithEmailAndPassword, sendPasswordResetEmail } from 'firebase/auth';
import { useNavigate, useLocation } from 'react-router-dom';
import { auth, googleProvider } from '../firebase';
import { PAT } from '../provenance/patterns';
import '../provenance/pages/sheet.css';

const GUIL = { __html: PAT.lace('#3f6b5c') };
// Firebase error codes -> a sentence a person can act on
const MESSAGES = {
  'auth/invalid-credential': 'That email and password don’t match. Try again or reset your password.',
  'auth/wrong-password': 'That email and password don’t match. Try again or reset your password.',
  'auth/user-not-found': 'No account uses that email. Create one below.',
  'auth/email-already-in-use': 'An account already uses that email. Sign in instead.',
  'auth/weak-password': 'Passwords need at least 6 characters.',
  'auth/invalid-email': 'Enter the email you signed up with.',
  'auth/popup-closed-by-user': '',
};
const say = (e) => MESSAGES[e.code] ?? e.message.replace('Firebase: ', '').replace(/ \(auth\/.*\)\.?/, '');

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [register, setRegister] = useState(false);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const navigate = useNavigate();
  const from = useLocation().state?.from || '/garage';

  const done = () => navigate(from, { replace: true });
  const google = async () => {
    setError('');
    try { await signInWithPopup(auth, googleProvider); done(); } catch (e) { setError(say(e)); }
  };
  const submit = async (e) => {
    e.preventDefault(); setError(''); setNote('');
    if (!email.includes('@')) { setError('Enter the email you signed up with.'); return; }
    try {
      await (register ? createUserWithEmailAndPassword : signInWithEmailAndPassword)(auth, email, password);
      done();
    } catch (err) { setError(say(err)); }
  };
  const reset = async () => {
    setError(''); setNote('');
    if (!email.includes('@')) { setError('Enter your email above first.'); return; }
    try { await sendPasswordResetEmail(auth, email); setNote('Password reset email sent. Check your inbox.'); } catch (err) { setError(say(err)); }
  };

  return (
    <div className="pg-sheet">
      <main className="wrap">
        <form className="sheet" onSubmit={submit} noValidate>
          <div className="guil" dangerouslySetInnerHTML={GUIL} />
          <h1>{register ? 'Create an account' : 'Sign in'}</h1>
          <p>Your garage follows you to any device.</p>
          <label>Email<input type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} /></label>
          <label>Password<input type="password" autoComplete={register ? 'new-password' : 'current-password'} required value={password} onChange={e => setPassword(e.target.value)} /></label>
          <div className="err" role="alert">{error}</div>
          {note && <p role="status">{note}</p>}
          <div className="actions">
            <button className="btn go">{register ? 'Create account' : 'Sign in'}</button>
            <button type="button" className="btn" onClick={google}>Continue with Google</button>
          </div>
          <div className="actions">
            <button type="button" className="linkish" onClick={() => { setRegister(r => !r); setError(''); setNote(''); }}>
              {register ? 'I already have an account' : 'Create an account'}
            </button>
            {!register && <button type="button" className="linkish" onClick={reset}>Forgot password?</button>}
          </div>
        </form>
      </main>
    </div>
  );
}
