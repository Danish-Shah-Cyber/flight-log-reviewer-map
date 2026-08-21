# Reviewer Core

Shared Python core for the professional flight-log reviewer.

This package is intentionally independent from the web app and the desktop app.
Both shells should call the same parser, normalization, artifact, and analysis
code so the hosted and local versions behave the same.

## Responsibilities

- Normalize parsed telemetry into common models.
- Build route artifacts for 2D and 3D maps.
- Build time-series artifacts for plots.
- Run deterministic health checks.
- Produce report/export data.

## Current First Slice

The first implemented slice is the route artifact contract used by both map
modes:

- `RoutePoint`
- `RouteEvent`
- `RouteArtifact`
- `build_route_artifact`

This gives the future web UI and Electron UI the same data shape for 2D maps,
Cesium 3D maps, hover details, timeline sync, and plot sync.
