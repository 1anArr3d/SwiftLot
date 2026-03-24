import { useState, useEffect } from 'react';

const ImageCycler = ({ images, large = false }) => {
  const [idx, setIdx] = useState(0);
  const [lightbox, setLightbox] = useState(false);

  const prev = (e) => { e.stopPropagation(); setIdx(i => (i - 1 + images.length) % images.length); };
  const next = (e) => { e.stopPropagation(); setIdx(i => (i + 1) % images.length); };

  useEffect(() => {
    if (!lightbox) return;
    const onKey = (e) => {
      if (e.key === 'Escape') setLightbox(false);
      if (e.key === 'ArrowLeft') setIdx(i => (i - 1 + images.length) % images.length);
      if (e.key === 'ArrowRight') setIdx(i => (i + 1) % images.length);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [lightbox, images.length]);

  if (!images || images.length === 0) return <div className={`no-img ${large ? 'no-img-large' : ''}`}>No Photos</div>;
  return (
    <>
      <div className={`img-cycler ${large ? 'img-cycler-large' : ''}`}>
        <div
          className={`cycler-img-wrap ${large ? 'cycler-img-wrap-large' : ''}`}
          onClick={large ? (e) => { e.stopPropagation(); setLightbox(true); } : undefined}
        >
          <img src={images[idx]} alt="vehicle" className={`cycler-img ${large ? 'cycler-img-large' : ''}`} />
        </div>
        {images.length > 1 && (
          <div className="cycler-controls">
            <button onClick={prev}>‹</button>
            <span>{idx + 1}/{images.length}</span>
            <button onClick={next}>›</button>
          </div>
        )}
      </div>

      {lightbox && (
        <div className="lightbox-overlay" onClick={() => setLightbox(false)}>
          <button className="lightbox-close" onClick={() => setLightbox(false)}>✕</button>
          <button className="lightbox-arrow lightbox-prev" onClick={prev}>‹</button>
          <img
            src={images[idx]}
            alt="vehicle"
            className="lightbox-img"
            onClick={e => e.stopPropagation()}
          />
          <button className="lightbox-arrow lightbox-next" onClick={next}>›</button>
          <div className="lightbox-counter">{idx + 1} / {images.length}</div>
        </div>
      )}
    </>
  );
};

export default ImageCycler;
