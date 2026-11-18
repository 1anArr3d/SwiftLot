import { Link } from 'react-router-dom';
import { PAT } from '../provenance/patterns';
import '../provenance/pages/sheet.css';

const GUIL = { __html: PAT.medallion('#7a3f45') };

export default function NotFoundPage() {
  return (
    <div className="pg-sheet">
      <main className="wrap">
        <section className="sheet">
          <div className="guil" dangerouslySetInnerHTML={GUIL} />
          <div className="code">404 · No certificate on file</div>
          <h1>We can't find that page</h1>
          <p>The lot may have sold and been removed, or the link is wrong. Live sales are listed on the auctions page.</p>
          <div className="actions">
            <Link className="btn go" to="/auctions" style={{ display: 'inline-grid', placeItems: 'center', textDecoration: 'none' }}>See live auctions</Link>
            <Link to="/search">Search all cars</Link>
          </div>
        </section>
      </main>
    </div>
  );
}
