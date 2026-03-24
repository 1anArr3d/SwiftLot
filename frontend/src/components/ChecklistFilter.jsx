const ChecklistFilter = ({ options, selected, onChange }) => {
  const toggle = (val) => {
    const next = new Set(selected);
    next.has(val) ? next.delete(val) : next.add(val);
    onChange(next);
  };
  return (
    <div className="checklist">
      {options.map(opt => (
        <label key={opt} className="checklist-item">
          <input type="checkbox" checked={selected.has(opt)} onChange={() => toggle(opt)} />
          <span>{opt || '—'}</span>
        </label>
      ))}
    </div>
  );
};

export default ChecklistFilter;
