# Flight Log Reviewer Pro

A professional flight-log review platform for PX4 and ArduPilot logs.

This project is intended to move beyond a simple "upload and chart" analyzer. It
should support a full review workflow: ingest logs, normalize telemetry, inspect
interactive plots, review health checks, document findings, and export a
defensible report.

## Product Direction

The product should feel closer to an engineering review workstation than a demo.
The core user is a drone operator, test engineer, maintainer, or safety reviewer
who needs to answer:

- What happened during this flight?
- Was the vehicle healthy?
- Did estimator, GPS, vibration, power, control, failsafe, or mission behavior
  show abnormal patterns?
- What exact evidence supports each finding?
- What should be checked before the next flight?

## Inspired By

- PX4 Flight Review documentation:
  https://docs.px4.io/main/en/log/flight_review
- PX4 public example plot app:
  https://logs.px4.io/plot_app?log=3c6236a7-b838-493f-b94c-cae4fdc966f8
- PX4 Flight Review source:
  https://github.com/PX4/flight_review
- PX4 Flight Review v2 architecture:
  https://github.com/PX4/flight-review-rs
- pyulog:
  https://github.com/PX4/pyulog

## Initial Documents

- `docs/product-requirements.md`
- `docs/core-workflow.md`
- `docs/architecture.md`
- `docs/mvp-backlog.md`
- `docs/cesium-map-design.md`

## Implementation Scaffold

The repository now starts the professional app as one shared core with two app
shells:

- `packages/reviewer-core/`: shared route artifact, parser, analysis, and report
  code.
- `apps/web/`: hosted FastAPI/React web version.
- `apps/desktop/`: local Electron version for private and very large logs.

## First Build Goal

Build an MVP that accepts `.ulg`, `.bin`, `.log`, and `.tlog`, produces an
interactive review page, and shows:

- Flight summary and metadata
- 2D route map, Cesium 3D route map, hover/click route details, and
  mode-colored timeline
- Interactive plots grouped by engineering system
- Health checks with severity and evidence
- Full normalized data explorer
- Reviewer notes and exportable HTML/PDF report
