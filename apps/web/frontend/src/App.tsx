const reviewFeatures = [
  "2D route map",
  "Cesium 3D route map",
  "Hover route inspector",
  "Zoomable plots",
  "Large-log background parsing",
  "Shared web and desktop reviewer core",
];

export function App() {
  return (
    <main className="app-shell">
      <section className="review-surface">
        <header>
          <p>Flight Log Reviewer Pro</p>
          <h1>Professional web review dashboard scaffold</h1>
        </header>
        <div className="feature-grid">
          {reviewFeatures.map((feature) => (
            <div className="feature" key={feature}>
              {feature}
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
