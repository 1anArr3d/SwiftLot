const AboutPage = () => (
  <div style={{
    maxWidth: 720,
    margin: '48px auto',
    padding: '0 24px',
    fontFamily: 'var(--font)',
    color: 'var(--text-primary)',
  }}>
    <h1 style={{ fontSize: 42, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--sky-light)', marginBottom: 4 }}>
      SwiftLot
    </h1>

    <p style={{ fontSize: 18, lineHeight: 1.7, marginBottom: 24 }}>
      Car auctions are fast, loud, and unforgiving. Without knowing what a vehicle
      actually sells for, it's easy to overbid on excitement or let a solid deal
      slip by out of uncertainty. SwiftLot cuts through that noise by putting
      historical sale data right next to the live auction — so you always know
      what fair looks like.
    </p>

    <p style={{ fontSize: 18, lineHeight: 1.7, marginBottom: 40 }}>
      Built for the first-timer who wants to show up prepared, not just hopeful.
    </p>

    <hr style={{ border: 'none', borderTop: '1px solid var(--border-bright)', marginBottom: 40 }} />

    <h2 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--sky-light)', marginBottom: 20 }}>
      What you get
    </h2>
    <ul style={{ fontSize: 17, lineHeight: 2, paddingLeft: 20, color: 'var(--text-primary)' }}>
      <li>Live auction tracking with real-time bid updates</li>
      <li>Historical average sale prices for make, model, and year</li>
      <li>Garage to save and follow vehicles across auctions</li>
      <li>Completed auction history so nothing disappears when it ends</li>
    </ul>
  </div>
);

export default AboutPage;
