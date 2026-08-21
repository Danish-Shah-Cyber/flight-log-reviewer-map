# Product Requirements

## Product Name

Flight Log Reviewer Pro

## Vision

Create a professional flight-log review platform that helps operators and
engineers understand drone flights quickly, accurately, and defensibly. The tool
should combine PX4 Flight Review style interactive exploration with structured
issue detection, evidence, reviewer notes, and exportable reports.

## Target Users

- Drone test engineers reviewing prototype flights
- Operators checking fleet logs before the next mission
- Maintenance teams diagnosing failures and degraded performance
- Students and builders learning from PX4 or ArduPilot logs
- Incident reviewers who need evidence rather than guesswork

## Supported Log Types

MVP:

- PX4 `.ulg`
- ArduPilot DataFlash `.bin`
- ArduPilot DataFlash `.log`
- Mission Planner MAVLink `.tlog`

Later:

- CSV imports
- ROS bag / ROS 2 bag derived telemetry
- Batch upload ZIPs
- Fleet API ingestion

## Core Jobs To Be Done

1. Upload a flight log and know whether it parsed successfully.
2. See flight metadata, vehicle type, firmware, duration, location, and mode
   sequence.
3. Inspect route, altitude, speed, attitude, power, GPS, estimator, vibration,
   control, and failsafe behavior.
4. Identify warnings and critical issues with exact supporting evidence.
5. Compare setpoints against actual vehicle response.
6. Review every mode segment from start to end.
7. Add human reviewer notes, assign finding status, and export a report.
8. Share a review link without exposing unrelated private data.

## MVP Feature Set

### Upload And Ingest

- Drag and drop upload with clear accepted extensions.
- Configurable maximum upload size, default `200 MB`.
- Parse progress states: uploaded, parsing, extracting metadata, generating
  analysis, ready, failed.
- Friendly parse failure messages with likely cause.
- Store original log only when configured. Default local mode may delete raw
  logs after processing; team mode should support retention policies.

### Review Dashboard

- Summary header with duration, distance, max altitude, max speed, firmware,
  vehicle type, board, log type, and health score.
- Dual map review with both a fast 2D route map and a Cesium 3D route map.
- Route hover/click inspection showing timestamp, speed, altitude, location,
  mode, arm state, battery, GPS quality, and nearby events.
- Cesium 3D route map with start/end, path line, altitude, mode colors,
  terrain/imagery context, and 2D/3D switching.
- Mode timeline with arm/disarm, takeoff, land, mission, failsafe, return, and
  manual override events.
- Engineering plot groups:
  - Overview
  - Position and altitude
  - Attitude and rates
  - Control setpoint vs actual
  - Power and battery
  - GPS and estimator
  - Vibration and sensors
  - Actuator and motor outputs
  - Messages, warnings, failsafes
  - Raw topics / raw fields
- Full data explorer with topic/field search and CSV export.

### Automated Review

- Data quality checks: dropouts, missing topics, timestamp gaps, impossible
  values, sensor coverage.
- GPS checks: fix quality, satellites, HDOP/EPH, jumps, accuracy degradation.
- Estimator checks: innovation spikes, vibration, position reset events,
  estimator status flags.
- Power checks: voltage sag, current spikes, battery remaining inconsistency,
  brownout risk.
- Control checks: setpoint tracking, attitude/rate error, saturation, clipping.
- Mission checks: waypoint progress, loiter/RTL/landing behavior, geofence or
  failsafe transitions.
- Finding model: severity, title, time range, evidence, explanation,
  recommended action, confidence, reviewer status.

### Report And Collaboration

- Reviewer notes per finding and per flight.
- Finding statuses: open, accepted, dismissed, fixed next flight, needs review.
- Export HTML and PDF.
- Public/private share link.
- Metadata redaction option for location-sensitive logs.

### Cesium Map Requirements

- Provide a 2D map mode for quick plan-view inspection and a 3D Cesium mode for
  altitude, terrain, and real-world context.
- Draw the drone route as a polyline over Cesium imagery/terrain.
- Use recorded altitude when available; otherwise clamp the line to ground.
- Color route segments by flight mode and show a legend.
- Add start, end, takeoff, landing, failsafe, and notable event markers.
- Hover/click route points to show time, coordinates, altitude, speed, mode,
  arm state, battery, GPS fix/satellites/HDOP when available, and event context.
- Hovering a route point should also move the timeline/plot cursor to the same
  timestamp.
- Sync the map cursor with the timeline and plots.
- Add privacy controls to blur or hide coordinates before sharing.
- Support a no-token fallback using local 2D/SVG map output when Cesium ion is
  not configured.
- Keep `CESIUM_ION_TOKEN` out of source control and inject it through
  environment configuration.

### Web And Local App Requirements

- The hosted web version and local desktop version must use the same core parser
  and analysis engine.
- The hosted web version should support sharing, deployment, and public/private
  review links.
- The local desktop version should support private offline review and very large
  files without hosted request timeout limits.
- The local desktop app should use Electron plus a local Python review service.

## Non-Functional Requirements

- Large logs must parse once and then load quickly.
- UI should remain usable for long logs with millions of samples.
- Raw data handling must be privacy-conscious.
- Analysis rules must be transparent and traceable to telemetry evidence.
- The app must work locally for private engineering use and deploy as a hosted
  web app.
- The parser layer must be modular so PX4 and ArduPilot support can evolve
  independently.

## Success Criteria For MVP

- Uploading a real PX4 `.ulg` produces a review page.
- Uploading a real ArduPilot `.bin` or `.log` produces a review page.
- Review page loads summary, map, mode timeline, key plots, findings, and raw
  data explorer.
- At least 15 automated checks run with severity and evidence.
- Report export produces a professional engineering review document.
- Tests cover parsers, normalization, findings, and report generation.
