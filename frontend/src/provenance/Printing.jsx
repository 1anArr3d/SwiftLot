import { PAT } from './patterns.js';

const CAR = { __html: PAT.brand().replace(/<span class="wm">.*<\/span>/, '') };

// The "printing certificate" loader. With error set it becomes the could-not-load card.
export default function Printing({ title = 'Printing certificate…', error }) {
  return (
    <div className="pload" role={error ? 'alert' : 'status'} aria-busy={!error}>
      <div className="sheet go">
        <span dangerouslySetInnerHTML={CAR} />
        <h1>{title}</h1>
        {error
          ? <><p>{error}</p><button type="button" className="btn go" onClick={() => window.location.reload()}>Try again</button></>
          : <><div className="print" /><div className="print s" /><div className="print" /></>}
      </div>
    </div>
  );
}
