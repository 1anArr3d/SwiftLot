import { useState } from 'react';

const FilterSection = ({ title, children, defaultOpen = false }) => {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="filter-section">
      <button className={`filter-section-title ${open ? 'is-open' : ''}`} onClick={() => setOpen(o => !o)}>
        <span>{title}</span>
        <span className={`filter-arrow ${open ? 'open' : ''}`}>›</span>
      </button>
      {open && <div className="filter-section-body">{children}</div>}
    </div>
  );
};

export default FilterSection;
