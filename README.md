# Flight Log Reviewer Map

Professional flight-log review software with a shared review engine, hosted web
version, and local desktop version.

This repository is the new map-focused project that will be upgraded over time.
It is separate from the older `flight-data-analyzer` repository so the original
deployed analyzer can stay stable while this app grows into the professional
reviewer.

## Product Goal

Review PX4 and ArduPilot logs with:

- 2D route map for fast plan-view inspection.
- Cesium 3D route map for terrain, imagery, altitude, and real-world context.
- Hover/click route inspector showing time, speed, altitude, location, mode,
  battery, GPS quality, and nearby events.
- Zoomable plots with timestamp and value readouts.
- Large-log parsing that avoids short web request timeouts.
- Shared core used by both the hosted web app and local Electron app.

## Repository Layout

```text
apps/
  web/                   Hosted web version scaffold
  desktop/               Electron local app scaffold
packages/
  reviewer-core/          Shared route/artifact/analysis core
flightrecorder/           Current working parser and report baseline
docs/
  flight-log-reviewer-pro/
tests/
```

## Current State

Implemented now:

- Existing `.tlog`, `.BIN`, and `.log` parser baseline from the original app.
- Upload parser timeout removal in the current dashboard path.
- Report display downsampling for large logs.
- Plot x/y labels, hover readout, zoom in/out, and reset controls.
- Shared route artifact model for 2D/3D maps.
- Web app scaffold.
- Electron desktop scaffold.
- Professional product and architecture docs.

## First MVP Target

```text
Open/upload log
-> parse log
-> create route artifact
-> web page reads route artifact
-> show drone path on 2D map and Cesium 3D map
-> hover path to inspect speed, altitude, location, mode, battery, and GPS
```

## Development

Run Python tests:

```powershell
python -m unittest discover -s tests -v
```

With the Codex bundled Python runtime:

```powershell
& 'C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests -v
```

## Privacy

Flight logs can contain sensitive locations. Raw logs, generated reports, local
artifacts, and environment files must not be committed.

For Cesium production imagery/terrain, use:

```text
CESIUM_ION_TOKEN=...
```

Do not commit that token.
