import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const root = process.cwd();
const out = resolve(root, "dist");
const server = resolve(out, "server");
const hosting = resolve(out, ".openai");

mkdirSync(server, { recursive: true });
mkdirSync(hosting, { recursive: true });

const css = readFileSync(resolve(root, "src", "styles.css"), "utf8");

const html = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Flight Log Reviewer Map</title>
    <style>${css}</style>
  </head>
  <body>
    <main class="shell">
      <aside class="sidebar">
        <p class="eyebrow">Flight Log Reviewer Map</p>
        <h1>Professional drone log review for web and desktop</h1>
        <p class="lede">
          A private new project for reviewing PX4 and ArduPilot logs with 2D maps,
          Cesium 3D maps, hover details, zoomable plots, findings, and shared parser artifacts.
        </p>
        <div class="actions">
          <a href="#preview">Open Preview</a>
          <a href="#workflow" class="secondary">Workflow</a>
        </div>
      </aside>
      <section class="workspace" id="preview">
        <div class="topbar">
          <div>
            <p class="eyebrow">Review Surface</p>
            <h2>2D / 3D route review preview</h2>
          </div>
          <div class="segmented">
            <button>2D Map</button>
            <button class="active">3D Map</button>
          </div>
        </div>
        <section class="map-panel">
          <div class="map-grid"></div>
          <svg viewBox="0 0 100 100" aria-label="Drone route preview">
            <polyline points="9,77 18,65 31,42 48,33 66,45 82,70"></polyline>
            <g class="route-point"><circle cx="9" cy="77" r="2.5"><title>00:00 | MANUAL | 0.6 m/s | 2 m | Battery 100%</title></circle></g>
            <g class="route-point"><circle cx="18" cy="65" r="1.8"><title>00:28 | FBWA | 14.2 m/s | 42 m | Battery 96%</title></circle></g>
            <g class="route-point"><circle cx="31" cy="42" r="1.8"><title>01:06 | AUTO | 21.8 m/s | 88 m | Battery 91%</title></circle></g>
            <g class="route-point"><circle cx="48" cy="33" r="1.8"><title>01:45 | AUTO | 23.1 m/s | 93 m | Battery 86%</title></circle></g>
            <g class="route-point"><circle cx="66" cy="45" r="1.8"><title>02:27 | RTL | 18.4 m/s | 68 m | Battery 80%</title></circle></g>
            <g class="route-point"><circle cx="82" cy="70" r="2.5"><title>03:18 | MANUAL | 5.2 m/s | 9 m | Battery 74%</title></circle></g>
          </svg>
          <article class="inspector">
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
        <section class="plot-panel">
          <div class="plot-head">
            <strong>Altitude Plot</strong>
            <span>Zoom in / out with x and y labels</span>
          </div>
          <div class="plot">
            <span class="y-label">altitude m</span>
            <div class="plot-line"></div>
            <span class="x-label">time 00:00 - 03:18</span>
          </div>
        </section>
        <section class="feature-grid" id="workflow">
          <div class="feature">2D route map and Cesium 3D map modes</div>
          <div class="feature">Hover/click route inspector</div>
          <div class="feature">Mode-colored timeline and path segments</div>
          <div class="feature">Zoomable plots with x/y labels</div>
          <div class="feature">Private Electron desktop app path</div>
          <div class="feature">Hosted web review workflow</div>
        </section>
      </section>
    </main>
  </body>
</html>`;

const worker = `const html = ${JSON.stringify(html)};

export default {
  async fetch() {
    return new Response(html, {
      headers: {
        "content-type": "text/html; charset=utf-8",
        "cache-control": "public, max-age=60"
      }
    });
  }
};
`;

writeFileSync(resolve(server, "index.js"), worker);
writeFileSync(resolve(hosting, "hosting.json"), readFileSync(resolve(root, ".openai", "hosting.json")));
writeFileSync(resolve(out, "_headers"), "/*\\n  X-Content-Type-Options: nosniff\\n");

console.log(`Built Sites preview in ${dirname(resolve(server, "index.js"))}`);
