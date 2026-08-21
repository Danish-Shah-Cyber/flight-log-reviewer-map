# MVP Backlog

## Milestone 0 - Foundation

- Decide repository name and license.
- Create app scaffold.
- Add parser interfaces and normalized schema.
- Add sample logs directory policy with `.gitignore`.
- Add CI for tests and linting.

## Milestone 1 - Upload And Parse

- Upload `.ulg`, `.bin`, `.log`, `.tlog`.
- Validate file extension, size, and basic magic/header where possible.
- Parse PX4 `.ulg` with `pyulog`.
- Parse ArduPilot `.bin` / `.log` with `pymavlink`.
- Parse Mission Planner `.tlog` with `pymavlink`.
- Extract metadata and messages.
- Store normalized artifacts.

## Milestone 2 - Review Page

- Build dashboard shell.
- Add summary metrics.
- Add 2D route map with start/end markers and mode-colored path.
- Add Cesium 3D route map with start/end markers and mode-colored path.
- Add hover/click route inspector for speed, altitude, location, mode, battery,
  GPS quality, and nearby events.
- Add mode timeline.
- Add synchronized plots.
- Add raw topic/field browser.
- Add all-data table with CSV export.

## Milestone 3 - Automated Findings

- Data quality module.
- GPS health module.
- Power health module.
- Estimator health module.
- Vibration module.
- Control tracking module.
- Failsafe/message module.
- Health score calculation.

## Milestone 4 - Reviewer Workflow

- Finding status updates.
- Reviewer notes.
- Flight conclusion field.
- Export HTML.
- Export PDF.
- Private/public share mode.

## Milestone 5 - Deployment

- Dockerfile.
- Render deployment config.
- Environment variables.
- Object storage option.
- Basic auth or account login for team mode.

## First 10 Engineering Tasks

1. Scaffold a FastAPI backend and React/Svelte frontend.
2. Define `LogParser` interface.
3. Define normalized telemetry schema.
4. Implement PX4 `.ulg` metadata extraction.
5. Implement PX4 `.ulg` topic extraction for core topics.
6. Implement artifact writer for JSON plus Parquet/Arrow.
7. Build upload page and parse status page.
8. Build first review page with summary, 2D/3D maps, hover inspector, and
   timeline.
9. Add data quality findings.
10. Add tests using synthetic and public sample logs.

## Cesium Implementation Tasks

1. Add `CESIUM_ION_TOKEN` environment variable support.
2. Add route artifact generation from normalized telemetry.
3. Add route downsampling for long logs.
4. Add Cesium viewer component.
5. Draw polyline segments by mode.
6. Add start/end/event markers.
7. Add hover/click inspector.
8. Sync selected time with plots and timeline.
9. Add privacy redaction for shared reviews.
10. Add fallback static route map for offline/no-token mode.

## Web And Desktop Implementation Tasks

1. Keep parser and analysis code in `packages/reviewer-core`.
2. Build hosted upload/review flows under `apps/web`.
3. Build local file-open/review flows under `apps/desktop`.
4. Share route, plot, findings, and report artifacts between both app versions.
5. Package the desktop version only after the web MVP review surface is stable.
