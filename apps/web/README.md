# Web App

Hosted browser version of Flight Log Reviewer Pro.

## Target Shape

- FastAPI backend for uploads, parsing jobs, artifacts, and exports.
- React/Vite frontend for review dashboard.
- 2D map mode for fast plan-view inspection.
- Cesium 3D map mode for terrain, imagery, and altitude context.
- Shared `packages/reviewer-core` parser and analysis engine.

## Web-Specific Requirements

- Upload limit defaults to `200 MB`.
- Large logs must use background parse jobs rather than one blocking request.
- Raw logs should be deleted by default unless retention is configured.
- Render deployment should run the backend and serve the built frontend.
- Cesium token must come from environment configuration, not source code.
