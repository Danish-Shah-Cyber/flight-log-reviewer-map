# Architecture

## Recommended Direction

Use a parse-once, review-many architecture.

The old PX4 Flight Review style is proven: upload logs, analyze in browser,
interactive plots, and share review pages. The more modern Flight Review v2
direction is even better for our product: convert raw logs once into efficient
review artifacts, then let the frontend query those artifacts quickly.

## High-Level Architecture

```mermaid
flowchart LR
  U["User upload"] --> API["Upload API"]
  API --> Q["Parse job queue"]
  Q --> P["Parser workers"]
  P --> N["Normalized telemetry"]
  P --> M["Metadata JSON"]
  N --> A["Analysis engine"]
  A --> F["Findings JSON"]
  N --> S["Columnar storage"]
  M --> DB["Database"]
  F --> DB
  S --> FE["Review frontend"]
  DB --> FE
  FE --> R["Export report"]
```

## Web And Desktop Architecture

The product should be implemented as one shared engine with two shells:

```mermaid
flowchart TD
  Core["packages/reviewer-core"]
  UI["shared React review UI"]
  Web["apps/web hosted app"]
  Desktop["apps/desktop Electron app"]
  Core --> Web
  Core --> Desktop
  UI --> Web
  UI --> Desktop
```

The web app is optimized for hosted review and sharing. The desktop app is
optimized for privacy, offline operation, and very large logs that should not be
uploaded or held inside one hosted request.

## Components

### Frontend

Suggested stack:

- React or SvelteKit
- Plotly, uPlot, ECharts, or Bokeh-compatible embedded plots
- CesiumJS for the primary 3D route map
- MapLibre, Leaflet, or canvas/SVG for the fast 2D route map
- A public Cesium ion token injected as `CESIUM_ION_TOKEN` for hosted imagery
  and terrain
- DuckDB-WASM or Apache Arrow for large local table exploration

Responsibilities:

- Upload UX and parse status
- Review dashboard
- Synchronized plots
- 2D/3D map and timeline interaction
- Findings review workflow
- Export/share UI

### Backend API

Suggested stack:

- Python FastAPI for fast iteration, or Rust for a high-performance parser
  service later.
- PostgreSQL for review metadata.
- Local filesystem in development, S3-compatible object storage in production.
- Background jobs with RQ/Celery/Arq or a lightweight worker process.

Responsibilities:

- Upload validation
- Job creation and status
- Serving review metadata
- Authentication and sharing
- Export generation

### Parser Layer

Parser adapters:

- PX4 `.ulg`: `pyulog` first, possible Rust parser later.
- ArduPilot `.bin` / `.log`: `pymavlink` DataFlash.
- Mission Planner `.tlog`: `pymavlink` MAVLink telemetry.

Output:

- `metadata.json`
- `events.json`
- `findings.json`
- normalized topic tables, ideally Arrow/Parquet

### Analysis Engine

Analysis modules:

- Data quality
- GPS
- Estimator
- Power
- Vibration
- Attitude/rate control
- Position control
- Mission/failsafe
- Messages and errors

Each module returns findings with:

- severity
- confidence
- title
- time range
- affected subsystem
- evidence values
- chart/topic links
- recommendation

## Data Model Sketch

### Review

- `id`
- `created_at`
- `log_type`
- `vehicle_type`
- `firmware`
- `duration_s`
- `distance_m`
- `health_score`
- `privacy_mode`
- `status`

### Finding

- `id`
- `review_id`
- `severity`
- `subsystem`
- `title`
- `start_us`
- `end_us`
- `confidence`
- `evidence_json`
- `recommendation`
- `reviewer_status`
- `reviewer_note`

### Artifact

- `review_id`
- `artifact_type`
- `uri`
- `content_type`
- `size_bytes`
- `checksum`

## Deployment Modes

### Local Engineering Mode

- Runs on one machine.
- Stores artifacts locally.
- No login required.
- Best for private flight logs.

### Hosted Team Mode

- Login required.
- Stores metadata in Postgres.
- Stores artifacts in S3-compatible storage.
- Supports share links, retention policy, and redaction.

### Local Desktop Mode

- Electron shell.
- React review UI.
- Local Python review service using `packages/reviewer-core`.
- Opens files from disk without uploading.
- Avoids hosted request timeouts for large `.BIN`, `.log`, `.tlog`, and `.ulg`
  files.
- Stores artifacts in a local user-selected workspace.

## Important Design Decisions

- Do not parse raw logs repeatedly for every page load.
- Keep analysis outputs explainable and evidence-first.
- Preserve raw-topic access for expert users.
- Allow missing-data limitations instead of pretending every check is certain.
- Keep parser adapters isolated from the common review UI.
- Treat Cesium as an optional visualization layer over normalized telemetry, not
  as the source of truth. The route must still be exportable and reviewable when
  imagery/terrain services are unavailable.

## Cesium Route Data Contract

The parser/analysis layer should produce a compact route artifact for the UI:

```json
{
  "points": [
    {
      "time_s": 0.0,
      "lat": 33.6844,
      "lon": 73.0479,
      "alt_m": 12.4,
      "relative_alt_m": 0.0,
      "mode": "MANUAL",
      "armed": false,
      "groundspeed_m_s": 0.0,
      "battery_remaining_pct": 100.0
    }
  ],
  "events": [
    {
      "time_s": 42.5,
      "kind": "TAKEOFF",
      "label": "Takeoff detected",
      "lat": 33.6851,
      "lon": 73.0492,
      "alt_m": 28.0
    }
  ]
}
```

The frontend should convert route points to Cesium positions with
`Cartesian3.fromDegrees(lon, lat, alt_m)`, create polyline entities for each
mode segment, add event markers, then fly the camera to the route bounds.

## Map Interaction Contract

The 2D map, 3D map, timeline, plots, and findings panel should share one
selected timestamp. Hovering or clicking any route point updates that selected
time. Every tooltip should be generated from the same normalized point data:

```json
{
  "time_s": 52.4,
  "lat": 33.684912,
  "lon": 73.049201,
  "alt_m": 124.7,
  "relative_alt_m": 81.5,
  "groundspeed_m_s": 18.2,
  "vertical_speed_m_s": 1.1,
  "mode": "AUTO",
  "armed": true,
  "battery_remaining_pct": 86.0,
  "gps_fix_type": 3,
  "gps_satellites": 14,
  "gps_hdop": 0.8,
  "nearest_event": "Waypoint 3 reached"
}
```
