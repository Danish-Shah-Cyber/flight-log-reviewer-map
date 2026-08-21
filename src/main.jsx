import React from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const routePoints = [
  { x: 9, y: 77, t: "00:00", mode: "MANUAL", speed: "0.6 m/s", altitude: "2 m", battery: "100%" },
  { x: 18, y: 65, t: "00:28", mode: "FBWA", speed: "14.2 m/s", altitude: "42 m", battery: "96%" },
  { x: 31, y: 42, t: "01:06", mode: "AUTO", speed: "21.8 m/s", altitude: "88 m", battery: "91%" },
  { x: 48, y: 33, t: "01:45", mode: "AUTO", speed: "23.1 m/s", altitude: "93 m", battery: "86%" },
  { x: 66, y: 45, t: "02:27", mode: "RTL", speed: "18.4 m/s", altitude: "68 m", battery: "80%" },
  { x: 82, y: 70, t: "03:18", mode: "MANUAL", speed: "5.2 m/s", altitude: "9 m", battery: "74%" },
];

const features = [
  "2D route map and Cesium 3D map modes",
  "Hover/click route inspector",
  "Mode-colored timeline and path segments",
  "Zoomable plots with x/y labels",
  "Private Electron desktop app path",
  "Hosted web review workflow",
];

function App() {
  const points = routePoints.map((point) => `${point.x},${point.y}`).join(" ");
  return (
    <main className="shell">
      <aside className="sidebar">
        <p className="eyebrow">Flight Log Reviewer Map</p>
        <h1>Professional drone log review for web and desktop</h1>
        <p className="lede">
          A new private project for reviewing PX4 and ArduPilot logs with maps,
          plots, hover details, findings, and shared parser artifacts.
        </p>
        <div className="actions">
          <a href="#preview">Open Preview</a>
          <a href="#workflow" className="secondary">Workflow</a>
        </div>
      </aside>

      <section className="workspace" id="preview">
        <div className="topbar">
          <div>
            <p className="eyebrow">Review Surface</p>
            <h2>2D / 3D route review preview</h2>
          </div>
          <div className="segmented">
            <button>2D Map</button>
            <button className="active">3D Map</button>
          </div>
        </div>

        <section className="map-panel">
          <div className="map-grid" />
          <svg viewBox="0 0 100 100" aria-label="Drone route preview">
            <polyline points={points} />
            {routePoints.map((point, index) => (
              <g key={point.t} className="route-point">
                <circle cx={point.x} cy={point.y} r={index === 0 || index === routePoints.length - 1 ? 2.5 : 1.8} />
                <title>
                  {`${point.t} | ${point.mode} | ${point.speed} | ${point.altitude} | Battery ${point.battery}`}
                </title>
              </g>
            ))}
          </svg>
          <article className="inspector">
            <span>Hover inspector</span>
            <strong>01:45 | AUTO</strong>
            <dl>
              <div><dt>Speed</dt><dd>23.1 m/s</dd></div>
              <div><dt>Altitude</dt><dd>93 m</dd></div>
              <div><dt>Location</dt><dd>33.684912, 73.049201</dd></div>
              <div><dt>Battery</dt><dd>86%</dd></div>
            </dl>
          </article>
        </section>

        <section className="plot-panel">
          <div className="plot-head">
            <strong>Altitude Plot</strong>
            <span>Zoom in / out with x and y labels</span>
          </div>
          <div className="plot">
            <span className="y-label">altitude m</span>
            <div className="plot-line" />
            <span className="x-label">time 00:00 - 03:18</span>
          </div>
        </section>

        <section className="feature-grid" id="workflow">
          {features.map((feature) => (
            <div className="feature" key={feature}>{feature}</div>
          ))}
        </section>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
