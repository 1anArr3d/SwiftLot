import { PAT } from '../provenance/patterns';
import '../provenance/pages/sheet.css';

const GUIL = { __html: PAT.waves('#35507a') };

export default function AboutPage() {
  return (
    <div className="pg-sheet">
      <main className="wrap">
        <article className="sheet">
          <div className="guil" dangerouslySetInnerHTML={GUIL} />
          <h1>Where the numbers come from</h1>
          <p>SwiftLot helps first-time buyers at tow-yard and impound auctions avoid overbidding. Every car gets three certificates, each backed by real records.</p>
          <h2>Value</h2>
          <p>The typical price is the middle half (25th–75th percentile) of past sales of the same make and model. We use the same year when there are 5 or more sales, widen to ±2 years if not, then all years. With fewer than 5 sales we show no range rather than guess.</p>
          <h2>Odometer</h2>
          <p>For Texas cars we pull state inspection records for the VIN. A drop of more than 2,000 miles between readings flags a possible rollback. A single reading that looks like a typo is ignored, so one bad entry doesn't flag an honest car.</p>
          <h2>Vehicle</h2>
          <p>Make, model, year and condition notes come straight from the yard's listing. "If you win now" is what you'd pay Autura if the current bid wins, worked out the same way Autura's checkout does it: the bid, plus the yard's platform fee (usually 12.5%), any extra yard fees, and the 3% card processing fee.</p>
          <h2>What we can't tell you</h2>
          <ul>
            <li>Mechanical condition — inspect in person when the yard allows it.</li>
            <li>Odometer history outside Texas. We show the mileage the seller lists on Autura when there is one, dated the day we first saw it.</li>
            <li>Title problems beyond what the yard lists.</li>
          </ul>
        </article>
      </main>
    </div>
  );
}
