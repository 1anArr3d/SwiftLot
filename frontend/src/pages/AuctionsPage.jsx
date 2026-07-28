import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { API } from '../api';

const CARD_GAP  = 16;
const NUM_CARDS = 16;
const SPEED     = 0.5;

const sanitize = (card) => ({
  id:             card.id,
  source:         card.source,
  name:           card.name || card.id,
  city:           card.city || null,
  state:          card.state || null,
  vehicles_count: Number(card.vehicles_count) || 0,
  closes_at:      card.closes_at || null,
});

function formatDate(iso) {
  if (!iso) return null;
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function groupByState(cards) {
  const map = {};
  for (const card of cards) {
    const key = card.state || 'Other';
    if (!map[key]) map[key] = [];
    map[key].push(card);
  }
  return Object.entries(map).sort(([a], [b]) => a.localeCompare(b));
}

function AuctionCard({ card, onClick }) {
  const hasVehicles = card.vehicles_count > 0;
  return (
    <div
      className={`auction-card source-${card.source}${hasVehicles ? ' has-vehicles' : ''}`}
      onClick={onClick}
    >
      <div className="auction-card-top">
        <div className="auction-card-seller">{card.name}</div>
      </div>
      <div className="auction-card-divider" />
      <div className="auction-card-info">
        {(card.city || card.state) && (
          <div className="auction-card-info-row">
            <span className="info-label">Location</span>
            <span>{[card.city, card.state].filter(Boolean).join(', ')}</span>
          </div>
        )}
        {card.closes_at && (
          <div className="auction-card-info-row">
            <span className="info-label">Ends</span>
            <span>{formatDate(card.closes_at)}</span>
          </div>
        )}
      </div>
      <div className="auction-card-footer">
        <span className="vehicles-count">
          {hasVehicles ? `${card.vehicles_count} vehicles` : 'No vehicles listed'}
        </span>
      </div>
    </div>
  );
}

const AuctionsPage = () => {
  const [auctionList, setAuctionList] = useState([]);
  const [loading, setLoading]         = useState(true);
  const navigate = useNavigate();

  // — Carousel refs —
  const pool   = useRef([]);
  const poolIdx = useRef(0);
  const slots  = useRef([]);
  const cards  = useRef([]);
  const scroll = useRef(0);
  const vel    = useRef(SPEED);
  const raf    = useRef(null);
  const ready  = useRef(false);
  const drag   = useRef({ on: false, startX: 0, startScroll: 0, delta: 0, target: null, lastX: 0, lastTime: 0 });
  const stride = useRef(0);

  function nextAuction() {
    const p = pool.current;
    if (!p.length) return null;
    const v = p[poolIdx.current % p.length];
    poolIdx.current++;
    return v;
  }

  function paintCard(i, card) {
    if (!card || !cards.current[i]) return;
    cards.current[i].data = card;
    const { el, seller, location, ends, count } = cards.current[i];
    el.dataset.auctionId = card.id;
    el.className = `auction-card source-${card.source}${card.vehicles_count > 0 ? ' has-vehicles' : ''}`;
    seller.textContent = card.name;
    location.textContent = [card.city, card.state].filter(Boolean).join(', ');
    ends.textContent = card.closes_at ? `Ends ${formatDate(card.closes_at)}` : '';
    count.textContent = card.vehicles_count > 0 ? `${card.vehicles_count} vehicles` : 'No vehicles listed';
  }

  function tryInit(newPool) {
    if (ready.current) {
      pool.current = newPool;
      poolIdx.current = 0;
      cards.current.forEach((_, i) => paintCard(i, nextAuction()));
      return;
    }
    pool.current = newPool;
    if (!pool.current.length || cards.current.filter(Boolean).length < NUM_CARDS) return;
    stride.current = (cards.current[0].el.offsetWidth || 220) + CARD_GAP;
    ready.current = true;
    slots.current = Array.from({ length: NUM_CARDS }, (_, i) => i);
    for (let i = 0; i < NUM_CARDS; i++) paintCard(i, nextAuction());
  }

  useEffect(() => {
    const tick = () => {
      if (!drag.current.on) {
        vel.current += (SPEED - vel.current) * 0.04;
        scroll.current += vel.current;
      }
      if (ready.current) {
        const s  = slots.current;
        const sc = scroll.current;
        const st = stride.current;
        const cardW = st - CARD_GAP;
        for (let i = 0; i < NUM_CARDS; i++) {
          const x = s[i] * st - sc;
          if (x < -(cardW + 10 * st)) {
            s[i] = Math.max(...s) + 1;
            paintCard(i, nextAuction());
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

  const onPointerDown = e => {
    drag.current = { on: true, startX: e.clientX, startScroll: scroll.current, delta: 0, target: e.target, lastX: e.clientX, lastTime: performance.now() };
    vel.current = 0;
    e.currentTarget.setPointerCapture(e.pointerId);
    e.currentTarget.style.cursor = 'grabbing';
  };
  const onPointerMove = e => {
    if (!drag.current.on) return;
    const now = performance.now();
    const dt = Math.max(now - drag.current.lastTime, 1);
    const dx = e.clientX - drag.current.startX;
    drag.current.delta = Math.abs(dx);
    vel.current = (-(e.clientX - drag.current.lastX) / dt) * 16;
    drag.current.lastX = e.clientX;
    drag.current.lastTime = now;
    scroll.current = drag.current.startScroll - dx;
  };
  const onPointerUp = e => { drag.current.on = false; e.currentTarget.style.cursor = 'grab'; };
  const onPointerCancel = () => { drag.current.on = false; };
  const onCarouselClick = e => {
    if (drag.current.delta > 5) return;
    const card = drag.current.target?.closest('[data-auction-id]');
    if (card) navigate(`/auctions/${card.dataset.auctionId}`);
  };

  const regCard = (i, el) => {
    if (!el || cards.current[i]) return;
    cards.current[i] = {
      el,
      seller:   el.querySelector('.ac-seller'),
      location: el.querySelector('.ac-location'),
      ends:     el.querySelector('.ac-ends'),
      count:    el.querySelector('.ac-count'),
    };
    if (pool.current.length) tryInit(pool.current);
  };

  // Fetch auctions
  useEffect(() => {
    fetch(`${API}/auctions`)
      .then(r => r.json())
      .then(data => {
        const sanitized = data.map(sanitize);
        setAuctionList(sanitized);
        const soonest = [...sanitized]
          .filter(c => c.closes_at)
          .sort((a, b) => new Date(a.closes_at) - new Date(b.closes_at));
        tryInit(soonest);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="page-content" style={{ color: 'var(--text-secondary)', padding: 32 }}>Loading auctions…</div>;
  if (!auctionList.length) return <div className="page-content" style={{ color: 'var(--text-secondary)', padding: 32 }}>No active auctions.</div>;

  const stateGroups = groupByState(auctionList);

  return (
    <div className="page-content">
      <section className="auctions-soon-section">
        <div className="auctions-section-title">Ending Soon</div>
        <div
          className="auctions-carousel-outer"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerCancel}
          onClick={onCarouselClick}
        >
          <div className="auctions-carousel-track" style={{ position: 'relative' }}>
            {Array.from({ length: NUM_CARDS }, (_, i) => (
              <div
                key={i}
                ref={el => regCard(i, el)}
                style={{ position: 'absolute', top: 0, left: 0, willChange: 'transform' }}
              >
                <div className="auction-card-top">
                  <div className="auction-card-seller ac-seller"></div>
                </div>
                <div className="auction-card-divider" />
                <div className="auction-card-info">
                  <div className="auction-card-info-row">
                    <span className="info-label">Location</span>
                    <span className="ac-location"></span>
                  </div>
                  <div className="auction-card-info-row">
                    <span className="ac-ends" style={{ fontSize: 12, color: 'var(--text-secondary)' }}></span>
                  </div>
                </div>
                <div className="auction-card-footer">
                  <span className="ac-count vehicles-count"></span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {stateGroups.map(([state, stateCards]) => (
        <section key={state} className="auctions-state-group">
          <div className="auctions-section-title">{state}</div>
          <div className="auctions-pair-grid">
            {stateCards.map(card => (
              <AuctionCard key={card.id} card={card} onClick={() => navigate(`/auctions/${card.id}`)} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
};

export default AuctionsPage;
