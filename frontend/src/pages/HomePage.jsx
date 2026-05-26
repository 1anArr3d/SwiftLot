import { useEffect, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { API } from '../api';

const CARD_GAP  = 16;
const NUM_CARDS = 20;  // fixed DOM node count
const SPEED     = 0.65; // px/frame
const REFETCH   = 60_000;

function shuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

export default function HomePage() {
  const navigate = useNavigate();

  // All mutable state lives in refs — no useState for the carousel
  const pool     = useRef([]);
  const poolIdx  = useRef(0);
  const slots    = useRef([]); // logical slot index per card
  const cards    = useRef([]); // { el, img, name, bid, auction, closes }
  const scroll   = useRef(0);
  const raf      = useRef(null);
  const ready    = useRef(false);
  const drag     = useRef({ on: false, startX: 0, startScroll: 0, delta: 0 });
  const stride   = useRef(0); // measured at init: card offsetWidth + gap

  function nextVehicle() {
    const p = pool.current;
    if (!p.length) return null;
    const v = p[poolIdx.current % p.length];
    poolIdx.current++;
    return v;
  }

  function paintCard(i, v) {
    if (!v || !cards.current[i]) return;
    const { el, img, name, bid, auction, closes } = cards.current[i];
    let src = '';
    try { src = JSON.parse(v.images)[0] || ''; } catch {}
    img.src = src;
    img.alt = `${v.year} ${v.make} ${v.model}`;
    name.textContent = `${v.year} ${v.make} ${v.model}`;
    if (v.current_bid != null) {
      bid.textContent = `$${Number(v.current_bid).toLocaleString()}`;
      bid.style.display = '';
    } else {
      bid.style.display = 'none';
    }
    auction.textContent = v.seller_name || '';
    if (v.closes_at) {
      const d = new Date(v.closes_at);
      closes.textContent = `Closes ${d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`;
      closes.style.display = '';
    } else {
      closes.style.display = 'none';
    }
    el.dataset.auctionId = v.auction_id;
    el.dataset.vin = v.vin;
  }

  function tryInit() {
    if (ready.current) return;
    if (!pool.current.length || cards.current.filter(Boolean).length < NUM_CARDS) return;
    stride.current = (cards.current[0].el.offsetWidth || 340) + CARD_GAP;
    ready.current = true;
    slots.current = Array.from({ length: NUM_CARDS }, (_, i) => i);
    for (let i = 0; i < NUM_CARDS; i++) paintCard(i, nextVehicle());
  }

  // Fetch + reshuffle pool; new/deleted vehicles flow in on next recycle
  useEffect(() => {
    const fetchPool = async () => {
      try {
        const data = await fetch(`${API}/vehicles?limit=500`).then(r => r.json());
        pool.current = shuffle(data.filter(v => v.images_count > 0 && v.images));
        tryInit();
      } catch {}
    };
    fetchPool();
    const t = setInterval(fetchPool, REFETCH);
    return () => clearInterval(t);
  }, []);

  // RAF: advance scroll + recycle off-screen cards
  useEffect(() => {
    const tick = () => {
      if (!drag.current.on) scroll.current += SPEED;

      if (ready.current) {
        const s = slots.current;
        const sc = scroll.current;
        const st = stride.current;
        const cardW = st - CARD_GAP;
        for (let i = 0; i < NUM_CARDS; i++) {
          const x = s[i] * st - sc;
          if (x < -(cardW + 10 * st)) {
            s[i] = Math.max(...s) + 1;
            paintCard(i, nextVehicle());
          }
          if (cards.current[i]) {
            cards.current[i].el.style.transform = `translateX(${s[i] * st - sc}px)`;
          }
        }
      }

      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, []);

  // Pointer drag (works for mouse + touch via pointer events)
  const onPointerDown = e => {
    drag.current = { on: true, startX: e.clientX, startScroll: scroll.current, delta: 0, target: e.target };
    e.currentTarget.setPointerCapture(e.pointerId);
    e.currentTarget.style.cursor = 'grabbing';
  };
  const onPointerMove = e => {
    if (!drag.current.on) return;
    const dx = e.clientX - drag.current.startX;
    drag.current.delta = Math.abs(dx);
    scroll.current = drag.current.startScroll - dx;
  };
  const onPointerUp = e => {
    drag.current.on = false;
    e.currentTarget.style.cursor = 'grab';
  };
  const onClick = e => {
    if (drag.current.delta > 5) return;
    const card = drag.current.target?.closest('[data-auction-id]');
    if (card) navigate(`/auctions/${card.dataset.auctionId}`, { state: { vin: card.dataset.vin } });
  };

  // Register card DOM nodes; trigger init when all NUM_CARDS are ready
  const regCard = (i, el) => {
    if (!el || cards.current[i]) return;
    cards.current[i] = {
      el,
      img:     el.querySelector('img'),
      name:    el.querySelector('.home-vehicle-name'),
      bid:     el.querySelector('.home-vehicle-bid'),
      auction: el.querySelector('.home-vehicle-auction'),
      closes:  el.querySelector('.home-vehicle-closes'),
    };
    tryInit();
  };

  return (
    <div className="home-page">
      <div className="home-hero">
        <div className="home-hero-content">
          <h1 className="home-title">Stop guessing.<br />Start bidding smart.</h1>
          <p className="home-subtitle">
            See historical average sale prices alongside live bids — so you always know
            what a car is actually worth before you bid.
          </p>
          <div className="home-cta">
            <Link to="/auctions" className="home-cta-primary">Browse Auctions</Link>
            <Link to="/search" className="home-cta-secondary">Search Vehicles</Link>
          </div>
        </div>
      </div>

      <div className="home-carousel-section">
        <h2 className="home-section-title">Live Inventory</h2>
        <div
          className="home-carousel-outer"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onClick={onClick}
        >
          <div
            className="home-carousel-track"
            style={{ position: 'relative' }}
          >
            {Array.from({ length: NUM_CARDS }, (_, i) => (
              <div
                key={i}
                className="home-vehicle-card"
                ref={el => regCard(i, el)}
                style={{ position: 'absolute', top: 0, left: 0, willChange: 'transform' }}
              >
                <img className="home-vehicle-img" src="" alt="" draggable={false} />
                <div className="home-vehicle-info">
                  <span className="home-vehicle-name"></span>
                  <span className="home-vehicle-bid"></span>
                  <span className="home-vehicle-auction"></span>
                  <span className="home-vehicle-closes"></span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="home-features">
        <div className="auction-card home-feature-card">
          <div className="home-feature-icon">&#9711;</div>
          <div className="home-feature-title">Live Bids</div>
          <div className="home-feature-body">
            Watch bids update in real time as the auction happens — no refreshing required.
          </div>
        </div>
        <div className="auction-card home-feature-card">
          <div className="home-feature-icon">&#36;</div>
          <div className="home-feature-title">Historical Prices</div>
          <div className="home-feature-body">
            Every vehicle shows what similar cars have actually sold for, so you bid with confidence.
          </div>
        </div>
        <div className="auction-card home-feature-card">
          <div className="home-feature-icon">&#9733;</div>
          <div className="home-feature-title">Save Auctions</div>
          <div className="home-feature-body">
            Bookmark auctions you care about and track them from your watchlist.
          </div>
        </div>
      </div>
    </div>
  );
}
