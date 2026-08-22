from __future__ import annotations

import html
import json
import math
import os
from pathlib import Path

from .analysis import FlightSummary
from .diagnostics import analyze_fuel_flow, analyze_gps_health
from .insights import InsightReport
from .model import FlightSample
from .quality import DataQualityReport, assess_data_quality


DEFAULT_REPORT_MAX_SAMPLES = 12000


def _report_max_samples() -> int:
    try:
        value = int(os.environ.get("REPORT_MAX_SAMPLES", str(DEFAULT_REPORT_MAX_SAMPLES)))
    except ValueError:
        value = DEFAULT_REPORT_MAX_SAMPLES
    return max(1000, min(value, 50000))


def _polyline(samples: list[FlightSample], field: str, width: int = 900, height: int = 180) -> str:
    values = [float(getattr(sample, field)) for sample in samples]
    low, high = min(values), max(values)
    span = high - low or 1.0
    time_start, time_end = samples[0].time_s, samples[-1].time_s
    time_span = time_end - time_start or 1.0
    points = []
    for sample, value in zip(samples, values):
        x = (sample.time_s - time_start) / time_span * width
        y = height - (value - low) / span * (height - 20) - 10
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def _chart(title: str, field: str, unit: str, color: str, samples: list[FlightSample]) -> str:
    return f"""<div class="plot" data-field="{html.escape(field)}" data-unit="{html.escape(unit)}" data-color="{html.escape(color)}">
      <div class="plot-head"><span>{html.escape(title)}</span><span>{html.escape(unit)}</span></div>
      <div class="plot-tools">
        <button class="ghost plot-zoom-in" type="button">Zoom in</button>
        <button class="ghost plot-zoom-out" type="button">Zoom out</button>
        <button class="ghost plot-reset" type="button">Reset</button>
        <span class="muted plot-readout">Hover plot for time and value</span>
      </div>
      <svg viewBox="0 0 900 180" role="img" aria-label="{html.escape(title)} plot">
        <g class="plot-grid"></g>
        <g class="plot-labels"></g>
        <line x1="54" y1="150" x2="880" y2="150" class="axis"/>
        <line x1="54" y1="16" x2="54" y2="150" class="axis"/>
        <polyline points="{_polyline(samples, field)}" stroke="{color}"/>
        <circle class="plot-cursor" r="4" hidden></circle>
      </svg>
    </div>"""


def _valid_route_samples(samples: list[FlightSample]) -> list[FlightSample]:
    return [
        sample
        for sample in samples
        if -90.0 <= sample.latitude_deg <= 90.0
        and -180.0 <= sample.longitude_deg <= 180.0
        and not (sample.latitude_deg == 0.0 and sample.longitude_deg == 0.0)
    ]


def _downsample(samples: list[FlightSample], limit: int = 900) -> list[FlightSample]:
    if len(samples) <= limit:
        return samples
    step = math.ceil(len(samples) / limit)
    reduced = samples[::step]
    if reduced[-1] != samples[-1]:
        reduced.append(samples[-1])
    return reduced


def _distance_m(first: FlightSample, second: FlightSample) -> float:
    if len(_valid_route_samples([first, second])) < 2:
        return 0.0
    radius_m = 6_371_000.0
    lat1 = math.radians(first.latitude_deg)
    lat2 = math.radians(second.latitude_deg)
    dlat = lat2 - lat1
    dlon = math.radians(second.longitude_deg - first.longitude_deg)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return radius_m * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _format_position(sample: FlightSample) -> str:
    if not _valid_route_samples([sample]):
        return "No GPS"
    return f"{sample.latitude_deg:.6f}, {sample.longitude_deg:.6f}"


def _mode_segments(samples: list[FlightSample]) -> list[dict[str, object]]:
    if not samples:
        return []
    segments: list[dict[str, object]] = []
    start_index = 0
    for index, sample in enumerate(samples[1:], start=1):
        previous = samples[index - 1]
        if sample.mode != previous.mode or sample.armed != previous.armed:
            segments.append(_segment_summary(samples, start_index, index - 1))
            start_index = index
    segments.append(_segment_summary(samples, start_index, len(samples) - 1))
    return segments


def _segment_summary(samples: list[FlightSample], start_index: int, end_index: int) -> dict[str, object]:
    segment = samples[start_index : end_index + 1]
    distance_m = sum(_distance_m(first, second) for first, second in zip(segment, segment[1:]))
    start = segment[0]
    end = segment[-1]
    return {
        "mode": start.mode,
        "armed": start.armed,
        "start_s": start.time_s,
        "end_s": end.time_s,
        "duration_s": max(0.0, end.time_s - start.time_s),
        "distance_km": distance_m / 1000.0,
        "start_position": _format_position(start),
        "end_position": _format_position(end),
    }


def _route_map(samples: list[FlightSample]) -> str:
    route_samples = _valid_route_samples(samples)
    if len(route_samples) < 2:
        return "<p class=\"muted\">No usable GPS route was found in this log.</p>"

    width, height, padding = 900, 360, 34
    projected: list[tuple[FlightSample, float, float]] = []
    center_lat = sum(sample.latitude_deg for sample in route_samples) / len(route_samples)
    lon_scale = max(0.01, math.cos(math.radians(center_lat)))
    raw_x = [sample.longitude_deg * lon_scale for sample in route_samples]
    raw_y = [sample.latitude_deg for sample in route_samples]
    min_x, max_x = min(raw_x), max(raw_x)
    min_y, max_y = min(raw_y), max(raw_y)
    span_x = max_x - min_x or 0.000001
    span_y = max_y - min_y or 0.000001
    for sample, x_value, y_value in zip(route_samples, raw_x, raw_y):
        x = padding + (x_value - min_x) / span_x * (width - padding * 2)
        y = height - padding - (y_value - min_y) / span_y * (height - padding * 2)
        projected.append((sample, x, y))

    palette = ["#1769c2", "#0f8f72", "#b36b00", "#7357c8", "#bf3145", "#0b8f8f"]
    modes = list(dict.fromkeys(sample.mode for sample in route_samples))
    mode_colors = {mode: palette[index % len(palette)] for index, mode in enumerate(modes)}
    mode_labels = "".join(
        f"<span class=\"legend-item\"><span style=\"background:{mode_colors[mode]}\"></span>{html.escape(mode)}</span>"
        for mode in modes[:8]
    )

    paths: list[str] = []
    current_mode = projected[0][0].mode
    current_points: list[tuple[float, float]] = []
    for sample, x, y in projected:
        if sample.mode != current_mode and len(current_points) > 1:
            points = " ".join(f"{px:.1f},{py:.1f}" for px, py in current_points)
            paths.append(f'<polyline points="{points}" stroke="{mode_colors[current_mode]}"/>')
            current_points = current_points[-1:]
            current_mode = sample.mode
        current_points.append((x, y))
    if len(current_points) > 1:
        points = " ".join(f"{px:.1f},{py:.1f}" for px, py in current_points)
        paths.append(f'<polyline points="{points}" stroke="{mode_colors[current_mode]}"/>')

    altitudes = [sample.relative_altitude_m for sample in route_samples]
    min_alt, max_alt = min(altitudes), max(altitudes)
    alt_span = max_alt - min_alt or 1.0
    projected_3d: list[tuple[FlightSample, float, float]] = []
    for sample, x_value, y_value in zip(route_samples, raw_x, raw_y):
        base_x = padding + (x_value - min_x) / span_x * (width - padding * 2)
        base_y = height - padding - (y_value - min_y) / span_y * (height - padding * 2) * 0.58
        altitude_offset = (sample.relative_altitude_m - min_alt) / alt_span * (height * 0.34)
        perspective_x = base_x + ((y_value - min_y) / span_y - 0.5) * 70
        perspective_y = base_y - altitude_offset
        projected_3d.append(
            (
                sample,
                min(width - padding, max(padding, perspective_x)),
                min(height - padding, max(padding, perspective_y)),
            )
        )

    paths_3d: list[str] = []
    current_mode = projected_3d[0][0].mode
    current_points = []
    for sample, x, y in projected_3d:
        if sample.mode != current_mode and len(current_points) > 1:
            points = " ".join(f"{px:.1f},{py:.1f}" for px, py in current_points)
            paths_3d.append(f'<polyline points="{points}" stroke="{mode_colors[current_mode]}"/>')
            current_points = current_points[-1:]
            current_mode = sample.mode
        current_points.append((x, y))
    if len(current_points) > 1:
        points = " ".join(f"{px:.1f},{py:.1f}" for px, py in current_points)
        paths_3d.append(f'<polyline points="{points}" stroke="{mode_colors[current_mode]}"/>')

    display_points = _downsample(route_samples, 160)
    point_lookup = {id(sample): (x, y) for sample, x, y in projected}
    sample_dots = "".join(
        f'<circle cx="{point_lookup[id(sample)][0]:.1f}" cy="{point_lookup[id(sample)][1]:.1f}" r="1.8" />'
        for sample in display_points
    )
    start_sample, start_x, start_y = projected[0]
    end_sample, end_x, end_y = projected[-1]
    start_3d, start_3d_x, start_3d_y = projected_3d[0]
    end_3d, end_3d_x, end_3d_y = projected_3d[-1]
    return f"""<div class="route-meta">
      <div><span class="muted">Start</span><strong>{html.escape(_format_position(start_sample))}</strong></div>
      <div><span class="muted">End</span><strong>{html.escape(_format_position(end_sample))}</strong></div>
      <div><span class="muted">GPS points</span><strong>{len(route_samples)}</strong></div>
    </div>
    <div class="route-tabs" role="tablist" aria-label="Route map views">
      <button class="route-tab active" type="button" data-route-view="route-2d">2D Map</button>
      <button class="route-tab" type="button" data-route-view="route-3d">Cesium 3D</button>
      <button class="route-tab" type="button" data-route-view="route-svg">Path</button>
    </div>
    <div class="route-view active" data-route-panel="route-2d">
      <svg class="route-map route-static-map" viewBox="0 0 {width} {height}" role="img" aria-label="Immediate 2D drone route path">
        <rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="8" class="map-bg"/>
        <g class="grid-lines">
          <line x1="180" y1="0" x2="180" y2="{height}"/><line x1="360" y1="0" x2="360" y2="{height}"/>
          <line x1="540" y1="0" x2="540" y2="{height}"/><line x1="720" y1="0" x2="720" y2="{height}"/>
          <line x1="0" y1="90" x2="{width}" y2="90"/><line x1="0" y1="180" x2="{width}" y2="180"/>
          <line x1="0" y1="270" x2="{width}" y2="270"/>
        </g>
        <g class="route-path">{"".join(paths)}</g>
        <g class="route-dots">{sample_dots}</g>
        <circle cx="{start_x:.1f}" cy="{start_y:.1f}" r="6" class="start-marker"/><text x="{start_x + 9:.1f}" y="{start_y - 9:.1f}">Start</text>
        <circle cx="{end_x:.1f}" cy="{end_y:.1f}" r="6" class="end-marker"/><text x="{end_x + 9:.1f}" y="{end_y - 9:.1f}">End</text>
      </svg>
      <canvas class="canvas-route-map" aria-label="2D drone route map fallback"></canvas>
      <div class="leaflet-route-map" aria-label="2D drone route map"></div>
      <div class="route-inspector muted">Hover the route for time, mode, speed, altitude, and location.</div>
      <div class="map-empty muted">Using the built-in 2D route view because online map tiles are unavailable.</div>
    </div>
    <div class="route-view" data-route-panel="route-3d">
      <svg class="route-map route-static-map route-static-3d" viewBox="0 0 {width} {height}" role="img" aria-label="Immediate altitude-aware 3D drone route path">
        <rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="8" class="map-bg"/>
        <g class="grid-lines">
          <line x1="180" y1="0" x2="180" y2="{height}"/><line x1="360" y1="0" x2="360" y2="{height}"/>
          <line x1="540" y1="0" x2="540" y2="{height}"/><line x1="720" y1="0" x2="720" y2="{height}"/>
          <line x1="0" y1="90" x2="{width}" y2="90"/><line x1="0" y1="180" x2="{width}" y2="180"/>
          <line x1="0" y1="270" x2="{width}" y2="270"/>
        </g>
        <g class="route-path">{"".join(paths_3d)}</g>
        <circle cx="{start_3d_x:.1f}" cy="{start_3d_y:.1f}" r="6" class="start-marker"/><text x="{start_3d_x + 9:.1f}" y="{start_3d_y - 9:.1f}">Start</text>
        <circle cx="{end_3d_x:.1f}" cy="{end_3d_y:.1f}" r="6" class="end-marker"/><text x="{end_3d_x + 9:.1f}" y="{end_3d_y - 9:.1f}">End</text>
        <text x="22" y="28">Altitude-projected route: {min_alt:.1f} m to {max_alt:.1f} m</text>
      </svg>
      <div class="cesium-route-map" aria-label="Cesium 3D drone route map"></div>
      <canvas class="route-3d-fallback" aria-label="3D drone route fallback"></canvas>
      <div class="route-inspector muted">Hover the 3D route for time, mode, speed, altitude, and location.</div>
      <div class="map-empty muted">Using the built-in 3D route view because Cesium is unavailable.</div>
    </div>
    <div class="route-view" data-route-panel="route-svg">
      <svg class="route-map" viewBox="0 0 {width} {height}" role="img" aria-label="Drone route path">
        <rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="8" class="map-bg"/>
        <g class="grid-lines">
          <line x1="180" y1="0" x2="180" y2="{height}"/><line x1="360" y1="0" x2="360" y2="{height}"/>
          <line x1="540" y1="0" x2="540" y2="{height}"/><line x1="720" y1="0" x2="720" y2="{height}"/>
          <line x1="0" y1="90" x2="{width}" y2="90"/><line x1="0" y1="180" x2="{width}" y2="180"/>
          <line x1="0" y1="270" x2="{width}" y2="270"/>
        </g>
        <g class="route-path">{"".join(paths)}</g>
        <g class="route-dots">{sample_dots}</g>
        <circle cx="{start_x:.1f}" cy="{start_y:.1f}" r="6" class="start-marker"/><text x="{start_x + 9:.1f}" y="{start_y - 9:.1f}">Start</text>
        <circle cx="{end_x:.1f}" cy="{end_y:.1f}" r="6" class="end-marker"/><text x="{end_x + 9:.1f}" y="{end_y - 9:.1f}">End</text>
      </svg>
    </div>
    <div class="route-legend">{mode_labels}</div>"""


def _mode_segments_html(samples: list[FlightSample]) -> str:
    rows = "".join(
        f"""<tr>
          <td>{html.escape(str(segment["mode"]))}</td>
          <td>{'Yes' if segment["armed"] else 'No'}</td>
          <td>{segment["start_s"]:.1f}</td>
          <td>{segment["end_s"]:.1f}</td>
          <td>{segment["duration_s"]:.1f}</td>
          <td>{segment["distance_km"]:.3f}</td>
          <td>{html.escape(str(segment["start_position"]))}</td>
          <td>{html.escape(str(segment["end_position"]))}</td>
        </tr>"""
        for segment in _mode_segments(samples)
    )
    return f"""<table><thead><tr><th>Mode</th><th>Armed</th><th>From (s)</th><th>To (s)</th><th>Duration (s)</th><th>Distance (km)</th><th>From</th><th>To</th></tr></thead><tbody>{rows}</tbody></table>"""


def _data_explorer(columns: list[str]) -> str:
    headers = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    options = "".join(f"<option value=\"{size}\">{size}</option>" for size in [25, 50, 100, 250])
    return f"""<div class="data-controls">
      <input class="data-search" type="search" placeholder="Filter all data">
      <select class="data-page-size" aria-label="Rows per page">{options}</select>
      <button class="ghost data-prev" type="button">Previous</button>
      <button class="ghost data-next" type="button">Next</button>
      <button class="ghost download-csv" type="button">Download CSV</button>
      <span class="muted data-status"></span>
    </div>
    <div class="table-scroll"><table class="data-table"><thead><tr>{headers}</tr></thead><tbody></tbody></table></div>"""


def _parameter_review(samples: list[FlightSample]) -> str:
    rows = []
    for column in FlightSample.column_names():
        values = [getattr(sample, column) for sample in samples]
        numeric = [float(value) for value in values if isinstance(value, (int, float))]
        if numeric:
            minimum = f"{min(numeric):.3f}"
            maximum = f"{max(numeric):.3f}"
            first = f"{numeric[0]:.3f}"
            last = f"{numeric[-1]:.3f}"
        else:
            unique = list(dict.fromkeys(str(value) for value in values))
            minimum = maximum = f"{len(unique)} unique"
            first = html.escape(str(values[0])) if values else ""
            last = html.escape(str(values[-1])) if values else ""
        rows.append(
            f"<tr><td>{html.escape(column)}</td><td>{first}</td><td>{last}</td>"
            f"<td>{minimum}</td><td>{maximum}</td><td>{len(values)}</td></tr>"
        )
    return f"""<div class="data-controls">
      <input class="parameter-search" type="search" placeholder="Filter parameters">
      <span class="muted">Normalized signals currently available from the parser.</span>
    </div>
    <div class="table-scroll"><table class="parameter-table"><thead><tr><th>Parameter</th><th>First</th><th>Last</th><th>Min / categories</th><th>Max / categories</th><th>Samples</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"""


def _timestamped_messages(summary: FlightSummary) -> str:
    rows = "".join(
        f"<tr><td>{event.time_s:.2f}</td><td>{html.escape(event.kind)}</td><td>{html.escape(event.description)}</td></tr>"
        for event in summary.events
    ) or "<tr><td colspan=\"3\">No timestamped messages or generated events were found.</td></tr>"
    return f"""<div class="data-controls">
      <input class="message-search" type="search" placeholder="Filter messages">
      <span class="muted">Parser-level messages will appear here as extraction expands.</span>
    </div>
    <div class="table-scroll"><table class="message-table"><thead><tr><th>Time (s)</th><th>Type</th><th>Message</th></tr></thead><tbody>{rows}</tbody></table></div>"""


def _manual_inputs(samples: list[FlightSample]) -> str:
    return f"""<div class="module-note">
      <strong>RCIN / Manual Inputs</strong>
      <p class="muted">Dedicated RC channel extraction is planned for BIN/LOG parsing. Current normalized review shows throttle input where available.</p>
    </div>
    {_chart("Throttle command", "throttle_pct", "%", "#1769c2", samples)}
    {_chart("Ground speed response", "groundspeed_m_s", "m/s", "#0f8f72", samples)}"""


def _actuator_outputs(samples: list[FlightSample]) -> str:
    return f"""<div class="module-note">
      <strong>RCOUT / Actuator Outputs</strong>
      <p class="muted">Motor and servo output channels will be shown here once RCOUT/SERVO extraction is added. Current proxy views battery load and throttle demand.</p>
    </div>
    {_chart("Throttle demand", "throttle_pct", "%", "#b36b00", samples)}
    {_chart("Battery current", "battery_current_a", "A", "#bf3145", samples)}
    {_chart("Battery voltage", "battery_voltage_v", "V", "#7357c8", samples)}"""


def _custom_graph_builder() -> str:
    options = "".join(f"<option value=\"{html.escape(column)}\">{html.escape(column)}</option>" for column in FlightSample.column_names())
    return f"""<div class="custom-graph-builder">
      <div class="data-controls">
        <select class="graph-x"><option value="time_s">time_s</option>{options}</select>
        <select class="graph-y">{options}</select>
        <button class="ghost graph-add" type="button">Plot selected signal</button>
        <button class="ghost graph-clear" type="button">Clear</button>
      </div>
      <div class="custom-plot-list"></div>
    </div>"""


def _pid_review(samples: list[FlightSample]) -> str:
    return f"""<div class="module-note">
      <strong>PID Review</strong>
      <p class="muted">Full desired-vs-actual PID analysis needs ATT/RATE/desired setpoint extraction. This view starts with attitude response, yaw behaviour, throttle demand, and control stability clues.</p>
    </div>
    {_chart("Roll response", "roll_deg", "deg", "#0b8f8f", samples)}
    {_chart("Pitch response", "pitch_deg", "deg", "#9a6b00", samples)}
    {_chart("Yaw response", "yaw_deg", "deg", "#7357c8", samples)}
    {_chart("Throttle demand", "throttle_pct", "%", "#bf3145", samples)}"""


def _home_overview(
    samples: list[FlightSample],
    summary: FlightSummary,
    insights: InsightReport | None,
    quality: DataQualityReport,
) -> str:
    route_samples = _valid_route_samples(samples)
    start = samples[0]
    end = samples[-1]
    start_location = _format_position(route_samples[0]) if route_samples else "No GPS"
    end_location = _format_position(route_samples[-1]) if route_samples else "No GPS"
    modes = ", ".join(list(dict.fromkeys(sample.mode for sample in samples))[:8]) or "Unknown"
    findings = insights.findings if insights else []
    finding_rows = "".join(
        f"<tr><td>{item.start_s:.1f}-{item.end_s:.1f}</td><td>{html.escape(item.severity.upper())}</td><td>{html.escape(item.title)}</td></tr>"
        for item in findings[:8]
    ) or "<tr><td colspan=\"3\">No major findings generated.</td></tr>"
    return f"""<div class="home-grid">
      <div class="home-card wide"><span class="muted">Flight window</span><strong>{start.time_s:.1f} s to {end.time_s:.1f} s</strong><p class="muted">Log-relative time. Absolute start/end time will appear when parser extracts GPS/system timestamps.</p></div>
      <div class="home-card"><span class="muted">Duration</span><strong>{summary.duration_s:.0f} s</strong></div>
      <div class="home-card"><span class="muted">Distance</span><strong>{summary.distance_km:.2f} km</strong></div>
      <div class="home-card"><span class="muted">Max altitude</span><strong>{summary.max_altitude_m:.1f} m</strong></div>
      <div class="home-card"><span class="muted">Max speed</span><strong>{summary.max_groundspeed_m_s:.1f} m/s</strong></div>
      <div class="home-card"><span class="muted">Data quality</span><strong>{html.escape(quality.grade)} ({quality.score:.0f}/100)</strong></div>
      <div class="home-card wide"><span class="muted">Start location</span><strong>{html.escape(start_location)}</strong></div>
      <div class="home-card wide"><span class="muted">End location</span><strong>{html.escape(end_location)}</strong></div>
      <div class="home-card wide"><span class="muted">Drone / vehicle</span><strong>Not identified yet</strong><p class="muted">Vehicle metadata will appear here after AUTOPILOT_VERSION, MSG, and parameter extraction are wired in.</p></div>
      <div class="home-card wide"><span class="muted">Modes used</span><strong>{html.escape(modes)}</strong></div>
    </div>
    <h3>Important Findings</h3>
    <table><thead><tr><th>Time</th><th>Severity</th><th>Finding</th></tr></thead><tbody>{finding_rows}</tbody></table>"""


def _ai_report(
    samples: list[FlightSample],
    summary: FlightSummary,
    insights: InsightReport | None,
    quality: DataQualityReport,
) -> str:
    route_samples = _valid_route_samples(samples)
    start_location = _format_position(route_samples[0]) if route_samples else "No GPS"
    end_location = _format_position(route_samples[-1]) if route_samples else "No GPS"
    findings = insights.findings if insights else []
    findings_list = _list([f"{item.severity.upper()}: {item.title}" for item in findings[:10]], "No notable findings generated.")
    return f"""<article class="report-document">
      <p class="muted">CAA/FAA-style structured engineering report. This is not an official authority approval or certification.</p>
      <h3>1. Flight Overview</h3>
      <p>The reviewed flight lasted {summary.duration_s:.0f} seconds, covered approximately {summary.distance_km:.2f} km, reached {summary.max_altitude_m:.1f} m maximum relative altitude, and reached {summary.max_groundspeed_m_s:.1f} m/s maximum groundspeed.</p>
      <h3>2. Location And Operating Area</h3>
      <p>Recorded route begins at {html.escape(start_location)} and ends at {html.escape(end_location)}. Airspace classification, NOTAM checks, and regulatory approvals must be verified externally.</p>
      <h3>3. Data Quality Statement</h3>
      <p>Data quality grade: {html.escape(quality.grade)} ({quality.score:.0f}/100). Analysis conclusions are limited by available signals, parser coverage, and timestamp fidelity.</p>
      <h3>4. Findings</h3>
      {findings_list}
      <h3>5. Reviewer Conclusion</h3>
      <p>The flight record is suitable for preliminary engineering review. Final operational conclusions should be signed off by a qualified reviewer after validating vehicle identity, maintenance state, pilot inputs, actuator outputs, airspace context, and raw log integrity.</p>
    </article>"""


def _list(items: list[str], empty: str) -> str:
    if not items:
        return f"<p class=\"muted\">{html.escape(empty)}</p>"
    return "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + "</ul>"


def _diagnostic_cards(findings) -> str:
    if not findings:
        return "<p class=\"muted\">No diagnostic finding was generated.</p>"
    return "".join(
        f"""<article class="finding {html.escape(item.severity)}">
          <div class="finding-head"><strong>{html.escape(item.title)}</strong><span>{html.escape(item.severity.upper())}</span></div>
          <p><b>Evidence:</b> {html.escape('; '.join(item.evidence))}</p>
          <p><b>Recommended check:</b> {html.escape(item.recommendation)}</p>
        </article>"""
        for item in findings
    )


def _module_templates(
    samples: list[FlightSample],
    summary: FlightSummary,
    insights: InsightReport | None,
    quality: DataQualityReport,
) -> str:
    fuel = analyze_fuel_flow(samples)
    gps = analyze_gps_health(samples)
    event_rows = "".join(
        f"<tr><td>{event.time_s:.1f}</td><td>{html.escape(event.kind)}</td>"
        f"<td>{html.escape(event.description)}</td></tr>"
        for event in summary.events
    ) or "<tr><td colspan=\"3\">No events detected</td></tr>"

    signal_rows = "".join(
        f"<tr><td>{html.escape(signal.name)}</td><td>{'Yes' if signal.present else 'No'}</td>"
        f"<td>{signal.coverage_pct:.0f}%</td><td>{html.escape('; '.join(signal.notes) or 'OK')}</td></tr>"
        for signal in quality.signals
    )

    finding_cards = ""
    if insights is not None:
        finding_cards = "".join(
            f"""<article class="finding {html.escape(item.severity)}">
              <div class="finding-head"><strong>{html.escape(item.title)}</strong><span>{html.escape(item.severity.upper())}</span></div>
              <div class="muted">{item.start_s:.1f}-{item.end_s:.1f} s | {html.escape(item.confidence)} confidence</div>
              <p><b>Evidence:</b> {html.escape('; '.join(item.evidence))}</p>
              <p><b>Possible causes:</b> {html.escape('; '.join(item.possible_causes))}</p>
              <p><b>Recommended check:</b> {html.escape(item.recommendation)}</p>
            </article>"""
            for item in insights.findings
        )

    modules = {
        "home": {
            "title": "Home",
            "html": _home_overview(samples, summary, insights, quality),
        },
        "charts": {
            "title": "Flight Trends",
            "html": "".join(
                [
                    _chart("Altitude", "relative_altitude_m", "m", "#2382d9", samples),
                    _chart("Ground speed", "groundspeed_m_s", "m/s", "#c47b10", samples),
                    _chart("Battery remaining", "battery_remaining_pct", "%", "#178f61", samples),
                ]
            ),
        },
        "map": {
            "title": "Route Map",
            "html": _route_map(samples),
        },
        "modes": {
            "title": "Flight Mode Segments",
            "html": _mode_segments_html(samples),
        },
        "assessment": {
            "title": "Flight Assessment",
            "html": (
                f"<div class=\"assessment\">{html.escape(insights.status if insights else 'Assessment unavailable')}</div>"
                + (finding_cards or "<p class=\"muted\">No assessment details available.</p>")
            ),
        },
        "quality": {
            "title": "Data Quality",
            "html": f"""<div class="quality-hero">
              <div><span class="score">{quality.score:.0f}</span><span class="muted">/100</span></div>
              <div><strong>{html.escape(quality.grade)}</strong><p class="muted">Signal coverage, gaps, timestamps, and impossible values.</p></div>
            </div>
            <table><thead><tr><th>Signal</th><th>Present</th><th>Coverage</th><th>Notes</th></tr></thead><tbody>{signal_rows}</tbody></table>
            <h4>Warnings</h4>{_list(quality.warnings, 'No quality warnings detected.')}
            <h4>Limitations</h4>{_list(quality.limitations, 'No major data limitations detected.')}""",
        },
        "events": {
            "title": "Event Timeline",
            "html": f"<table><thead><tr><th>Time (s)</th><th>Type</th><th>Description</th></tr></thead><tbody>{event_rows}</tbody></table>",
        },
        "messages": {
            "title": "Timestamped Messages",
            "html": _timestamped_messages(summary),
        },
        "parameters": {
            "title": "Parameters",
            "html": _parameter_review(samples),
        },
        "rcin": {
            "title": "RCIN / Manual Inputs",
            "html": _manual_inputs(samples),
        },
        "rcout": {
            "title": "RCOUT / Actuator Outputs",
            "html": _actuator_outputs(samples),
        },
        "custom-graphs": {
            "title": "Custom Graph Builder",
            "html": _custom_graph_builder(),
        },
        "pid": {
            "title": "PID Review",
            "html": _pid_review(samples),
        },
        "power": {
            "title": "Power Review",
            "html": "".join(
                [
                    _chart("Battery voltage", "battery_voltage_v", "V", "#7a6ff0", samples),
                    _chart("Battery current", "battery_current_a", "A", "#c4517c", samples),
                ]
            ),
        },
        "fuel": {
            "title": "Fuel Flow",
            "html": f"""<div class="mini-grid">
              <div class="mini"><span class="muted">Status</span><strong>{html.escape(fuel.status)}</strong></div>
              <div class="mini"><span class="muted">Used</span><strong>{fuel.total_used_l:.2f} L</strong></div>
              <div class="mini"><span class="muted">Peak flow</span><strong>{fuel.peak_flow_l_h:.2f} L/h</strong></div>
              <div class="mini"><span class="muted">Endurance</span><strong>{fuel.estimated_endurance_min:.0f} min</strong></div>
            </div>
            {_chart("Fuel flow", "fuel_flow_l_h", "L/h", "#0b8f8f", samples)}
            {_chart("Fuel used", "fuel_used_l", "L", "#9a6b00", samples)}
            {_diagnostic_cards(fuel.findings)}
            <h4>Limitations</h4>{_list(fuel.limitations, 'No major fuel-analysis limitations detected.')}""",
        },
        "gps": {
            "title": "GPS Health",
            "html": f"""<div class="mini-grid">
              <div class="mini"><span class="muted">Status</span><strong>{html.escape(gps.status)}</strong></div>
              <div class="mini"><span class="muted">Min fix</span><strong>{gps.minimum_fix_type:.0f}</strong></div>
              <div class="mini"><span class="muted">Min satellites</span><strong>{gps.minimum_satellites:.0f}</strong></div>
              <div class="mini"><span class="muted">Max HDOP</span><strong>{gps.maximum_hdop:.2f}</strong></div>
            </div>
            {_chart("GPS satellites", "gps_satellites", "count", "#1769c2", samples)}
            {_chart("GPS HDOP", "gps_hdop", "ratio", "#c47b10", samples)}
            {_diagnostic_cards(gps.findings)}
            <h4>Limitations</h4>{_list(gps.limitations, 'No major GPS-health limitations detected.')}""",
        },
        "attitude": {
            "title": "Attitude Review",
            "html": "".join(
                [
                    _chart("Roll", "roll_deg", "deg", "#0b8f8f", samples),
                    _chart("Pitch", "pitch_deg", "deg", "#9a6b00", samples),
                    _chart("Yaw", "yaw_deg", "deg", "#7357c8", samples),
                ]
            ),
        },
        "limitations": {
            "title": "Analysis Limits",
            "html": (
                _list(insights.limitations if insights else [], "No assessment limitations were generated.")
                + "<p class=\"muted\">Conclusions are bounded by the recorded signals. The tool should label weak evidence instead of filling gaps with guesses.</p>"
            ),
        },
        "data": {
            "title": "All Normalized Data",
            "html": _data_explorer(FlightSample.column_names()),
        },
        "ai": {
            "title": "AI Report",
            "html": _ai_report(samples, summary, insights, quality),
        },
    }
    templates = []
    for module_id, module in modules.items():
        templates.append(
            f"""<template id="template-{html.escape(module_id)}">
              <section class="module" data-module="{html.escape(module_id)}">
                <div class="module-head">
                  <h2>{html.escape(module["title"])}</h2>
                </div>
                {module["html"]}
              </section>
            </template>"""
        )
    return "\n".join(templates)


def write_html_report(
    path: str | Path,
    samples: list[FlightSample],
    summary: FlightSummary,
    insights: InsightReport | None = None,
    quality: DataQualityReport | None = None,
) -> None:
    quality = quality or assess_data_quality(samples)
    original_sample_count = len(samples)
    display_samples = _downsample(samples, _report_max_samples())
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    default_modules = ["home"]
    module_library = [
        ("home", "Home", "Overview, timing, location, quality, and key findings"),
        ("quality", "Data Quality", "Signal coverage, gaps, and confidence"),
        ("map", "Route Map", "Drone path, start/end points, and mode colors"),
        ("modes", "Mode Segments", "Mode, arm state, time range, and positions"),
        ("charts", "Flight Trends", "Altitude, speed, and battery plots"),
        ("assessment", "Flight Assessment", "Rule-based findings and evidence"),
        ("events", "Event Timeline", "Detected flight events"),
        ("messages", "Timestamped Messages", "Log messages, warnings, and event timestamps"),
        ("parameters", "Parameters", "All extracted parameters and normalized signals"),
        ("rcin", "RCIN / Manual Inputs", "Pilot command inputs and response"),
        ("rcout", "RCOUT / Actuator Outputs", "Motor and servo output review"),
        ("custom-graphs", "Custom Graph Builder", "Choose any signal and build plots"),
        ("pid", "PID Review", "Control response and tuning review"),
        ("power", "Power Review", "Voltage and current behaviour"),
        ("fuel", "Fuel Flow", "Fuel burn, flow spikes, and endurance"),
        ("gps", "GPS Health", "Fix type, satellites, and HDOP"),
        ("attitude", "Attitude Review", "Roll, pitch, and yaw"),
        ("limitations", "Analysis Limits", "What this report cannot prove"),
        ("data", "All Data", "Browse and export every normalized sample"),
    ]
    report_library = [
        ("ai", "AI Report", "CAA/FAA-style structured reviewer conclusion"),
        ("limitations", "Analysis Limits", "Evidence boundaries and missing context"),
    ]
    library_html = "".join(
        f"""<button class="library-item" type="button" data-module="{module_id}">
          <span>{html.escape(title)}</span><small>{html.escape(description)}</small>
        </button>"""
        for module_id, title, description in module_library
    )
    report_library_html = "".join(
        f"""<button class="library-item" type="button" data-module="{module_id}">
          <span>{html.escape(title)}</span><small>{html.escape(description)}</small>
        </button>"""
        for module_id, title, description in report_library
    )
    upload_card = f"""<section class="upload-card">
      <h2>Analyze Log</h2>
      <form method="post" enctype="multipart/form-data" action="/analyze">
        <label class="upload-drop">
          <span>Upload .tlog, .BIN, or .log</span>
          <input required type="file" name="flight_log" accept=".tlog,.bin,.log">
        </label>
        <button class="primary" type="submit">Analyze</button>
      </form>
      <p class="muted">Available when viewed from the local dashboard server.</p>
    </section>"""
    default_json = json.dumps(default_modules)
    sample_json = json.dumps([sample.to_dict() for sample in display_samples], separators=(",", ":"))
    column_json = json.dumps(FlightSample.column_names())
    templates = _module_templates(display_samples, summary, insights, quality)
    warnings = quality.warnings or ["No quality warnings detected"]
    display_note = (
        f"<span class=\"pill\">Display: {len(display_samples)} of {original_sample_count} samples</span>"
        if len(display_samples) < original_sample_count
        else ""
    )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Flight Data Dashboard</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<link rel="stylesheet" href="https://cesium.com/downloads/cesiumjs/releases/1.144/Build/Cesium/Widgets/widgets.css">
<style>
:root {{
  color-scheme: light;
  --bg: #f5f7fb; --panel: #ffffff; --panel-2: #eef2f7; --text: #18202b; --muted: #657184;
  --line: #d9e0ea; --accent: #1769c2; --accent-2: #0f8f72; --danger: #bf3145; --warn: #b36b00;
  --shadow: 0 12px 36px rgba(29, 39, 58, .11);
}}
[data-theme="dark"] {{
  color-scheme: dark;
  --bg: #0e131b; --panel: #151d29; --panel-2: #101722; --text: #edf3fb; --muted: #98a7ba;
  --line: #263447; --accent: #65a9ff; --accent-2: #43c49b; --danger: #ff6678; --warn: #f0a43c;
  --shadow: 0 16px 40px rgba(0, 0, 0, .28);
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5 Inter, Segoe UI, Arial, sans-serif; }}
button {{ font: inherit; }}
.app {{ min-height: 100vh; display: grid; grid-template-columns: minmax(260px, 320px) minmax(0, 1fr); }}
.sidebar {{ position: sticky; top: 0; height: 100vh; overflow: auto; border-right: 1px solid var(--line); padding: 22px; background: var(--panel); }}
.brand h1 {{ font-family: D-DIN-Bold, "D DIN", "Arial Narrow", Arial, sans-serif; letter-spacing: 0; font-size: 30px; line-height: 1.05; margin: 0 0 8px; }}
.muted, small {{ color: var(--muted); }}
.toolbar {{ display: flex; gap: 8px; margin: 18px 0 20px; }}
.toggle, .ghost, .library-item, .icon-button {{ border: 1px solid var(--line); background: var(--panel-2); color: var(--text); border-radius: 8px; cursor: pointer; }}
.primary {{ border: 0; background: var(--accent); color: #fff; border-radius: 8px; cursor: pointer; padding: 10px 12px; font-weight: 700; width: 100%; }}
.toggle, .ghost {{ padding: 9px 11px; }}
.upload-card {{ border: 1px solid var(--line); background: var(--panel-2); border-radius: 8px; padding: 13px; margin: 18px 0; }}
.upload-card h2 {{ font-size: 15px; margin: 0 0 10px; }}
.upload-drop {{ display: grid; gap: 8px; border: 1px dashed var(--line); border-radius: 8px; padding: 11px; margin-bottom: 10px; cursor: pointer; }}
.upload-drop input {{ max-width: 100%; font-size: 13px; }}
.library {{ display: grid; gap: 10px; margin-top: 12px; }}
.library-item {{ display: grid; gap: 2px; text-align: left; padding: 12px; }}
.library-item:hover, .library-item.active, .drop-target {{ border-color: var(--accent); }}
.library-item.active {{ background: color-mix(in srgb, var(--accent) 12%, var(--panel)); }}
.main {{ padding: 26px; min-width: 0; }}
.topbar {{ display: flex; justify-content: space-between; gap: 18px; align-items: start; margin-bottom: 18px; }}
.topbar h2 {{ margin: 0; font-size: 18px; }}
.essentials {{ display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); gap: 12px; margin-bottom: 18px; }}
.metric, .module {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow); }}
.metric {{ padding: 15px; min-height: 92px; }}
.metric strong {{ display: block; font-size: 24px; line-height: 1.1; margin-top: 10px; }}
.mini-grid {{ display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 10px; margin-bottom: 12px; }}
.mini {{ background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px; padding: 11px; min-height: 74px; }}
.mini strong {{ display: block; margin-top: 5px; font-size: 17px; }}
.status-strip {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 18px; }}
.pill {{ border: 1px solid var(--line); background: var(--panel); border-radius: 999px; padding: 7px 10px; color: var(--muted); }}
.workspace {{ display: grid; gap: 14px; }}
.module {{ padding: 16px; overflow: hidden; }}
.module-head {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; }}
.module-head h2 {{ font-size: 17px; margin: 0; }}
.icon-button {{ padding: 7px 9px; margin-left: 6px; font-size: 13px; }}
.home-grid {{ display: grid; grid-template-columns: repeat(4, minmax(140px, 1fr)); gap: 12px; margin-bottom: 16px; }}
.home-card {{ background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px; padding: 13px; min-height: 92px; }}
.home-card.wide {{ grid-column: span 2; }}
.home-card strong {{ display: block; font-size: 18px; margin-top: 7px; overflow-wrap: anywhere; }}
.module-note {{ border: 1px solid var(--line); background: var(--panel-2); border-radius: 8px; padding: 12px; margin-bottom: 12px; }}
.report-document {{ max-width: 980px; }}
.report-document h3 {{ margin-top: 20px; }}
.plot {{ margin: 12px 0; }}
.plot-head {{ display: flex; justify-content: space-between; color: var(--muted); margin-bottom: 7px; }}
.plot-tools {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 8px; }}
.plot-tools .ghost {{ width: auto; padding: 6px 9px; font-size: 13px; }}
.plot-readout {{ margin-left: auto; font-size: 13px; }}
.plot svg {{ touch-action: none; cursor: crosshair; }}
.plot.panning svg {{ cursor: grabbing; }}
svg {{ width: 100%; height: auto; background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px; }}
polyline {{ fill: none; stroke-width: 3; stroke-linejoin: round; }}
.axis {{ stroke: var(--line); }}
.plot-grid line {{ stroke: var(--line); stroke-width: 1; opacity: .72; }}
.plot-labels text {{ fill: var(--muted); font-size: 11px; }}
.plot-cursor {{ fill: var(--accent); stroke: var(--panel); stroke-width: 2; }}
.route-meta {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }}
.route-meta div {{ background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px; padding: 11px; min-width: 0; }}
.route-meta strong {{ display: block; margin-top: 4px; overflow-wrap: anywhere; }}
.route-tabs {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }}
.route-tab {{ border: 1px solid var(--line); background: var(--panel-2); color: var(--text); border-radius: 8px; cursor: pointer; padding: 8px 11px; }}
.route-tab.active {{ border-color: var(--accent); background: color-mix(in srgb, var(--accent) 14%, var(--panel)); }}
.route-view {{ display: none; position: relative; }}
.route-view.active {{ display: block; }}
.leaflet-route-map, .cesium-route-map, .canvas-route-map, .route-3d-fallback {{ width: 100%; height: clamp(360px, 48vh, 620px); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: var(--panel-2); }}
.canvas-route-map, .route-3d-fallback {{ display: block; }}
.leaflet-route-map, .cesium-route-map {{ display: none; }}
.route-static-map {{ margin-bottom: 10px; }}
.route-view.has-canvas .route-static-map, .route-view.has-leaflet .route-static-map, .route-view.has-cesium .route-static-map {{ display: none; }}
.route-view.has-leaflet .canvas-route-map {{ display: none; }}
.route-view.has-leaflet .leaflet-route-map {{ display: block; }}
.route-view.has-cesium .route-3d-fallback {{ display: none; }}
.route-view.has-cesium .cesium-route-map {{ display: block; }}
.route-inspector {{ border: 1px solid var(--line); background: var(--panel-2); border-radius: 8px; padding: 10px 12px; margin-top: 10px; min-height: 44px; overflow-wrap: anywhere; }}
.map-empty {{ display: none; border: 1px dashed var(--line); border-radius: 8px; padding: 14px; margin-top: 10px; }}
.route-view.map-failed .map-empty {{ display: block; }}
.leaflet-popup-content {{ color: #18202b; min-width: 210px; }}
.leaflet-popup-content strong {{ display: block; margin-bottom: 4px; }}
.waypoint-marker {{ width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; background: #ffffff; color: #111827; border: 3px solid #1769c2; box-shadow: 0 2px 8px rgba(17, 24, 39, .28); font: 800 12px/1 Segoe UI, Arial, sans-serif; }}
.cesium-route-map .cesium-widget-credits {{ display: none !important; }}
.cesium-route-map .cesium-viewer-toolbar, .cesium-route-map .cesium-viewer-animationContainer, .cesium-route-map .cesium-viewer-timelineContainer, .cesium-route-map .cesium-viewer-fullscreenContainer {{ display: none !important; }}
.route-map text {{ fill: var(--text); font-size: 14px; font-weight: 700; }}
.map-bg {{ fill: var(--panel-2); stroke: none; }}
.grid-lines line {{ stroke: var(--line); stroke-width: 1; }}
.route-path polyline {{ stroke-width: 4; stroke-linecap: round; }}
.route-dots circle {{ fill: var(--text); opacity: .22; }}
.start-marker {{ fill: var(--accent-2); stroke: var(--panel); stroke-width: 3; }}
.end-marker {{ fill: var(--danger); stroke: var(--panel); stroke-width: 3; }}
.route-legend {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }}
.legend-item {{ display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--line); border-radius: 999px; padding: 6px 9px; color: var(--muted); }}
.legend-item span {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 9px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
.table-scroll {{ overflow: auto; max-height: 520px; border: 1px solid var(--line); border-radius: 8px; }}
.table-scroll table {{ min-width: 1250px; }}
.table-scroll th {{ position: sticky; top: 0; background: var(--panel-2); z-index: 1; }}
.data-controls {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px; }}
.data-controls input, .data-controls select {{ border: 1px solid var(--line); background: var(--panel-2); color: var(--text); border-radius: 8px; padding: 9px 10px; }}
.data-controls input {{ min-width: min(260px, 100%); flex: 1; }}
.assessment {{ font-size: 21px; font-weight: 750; margin-bottom: 12px; }}
.finding {{ border-left: 4px solid var(--line); background: var(--panel-2); padding: 12px; margin: 10px 0; border-radius: 7px; }}
.finding-head {{ display: flex; justify-content: space-between; gap: 12px; }}
.critical {{ border-left-color: var(--danger); }} .warning {{ border-left-color: var(--warn); }} .notice {{ border-left-color: var(--accent); }} .positive {{ border-left-color: var(--accent-2); }}
.quality-hero {{ display: flex; gap: 18px; align-items: center; margin-bottom: 12px; }}
.score {{ font-size: 46px; font-weight: 800; color: var(--accent); line-height: 1; }}
ul {{ padding-left: 20px; }}
@media (max-width: 900px) {{
  .app {{ grid-template-columns: 1fr; }}
  .sidebar {{ position: relative; height: auto; border-right: 0; border-bottom: 1px solid var(--line); }}
  .essentials {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .route-meta {{ grid-template-columns: 1fr; }}
  .home-grid {{ grid-template-columns: 1fr; }}
  .home-card.wide {{ grid-column: auto; }}
  .mini-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .topbar {{ display: block; }}
}}
</style></head>
<body><div class="app">
  <aside class="sidebar">
    <div class="brand"><h1>Flight Data Dashboard</h1><p class="muted">{original_sample_count} samples analyzed.</p></div>
    <div class="toolbar">
      <button class="toggle" id="themeToggle" type="button">Toggle theme</button>
      <button class="ghost" id="resetLayout" type="button">Reset</button>
    </div>
    {upload_card}
    <h2>Insight Library</h2>
    <div class="library">{library_html}</div>
    <h2>Report & Conclusion</h2>
    <div class="library">{report_library_html}</div>
  </aside>
  <main class="main">
    <div class="topbar">
      <div><h2>Essential Overview</h2><p class="muted">Core flight facts and signal confidence.</p></div>
      <div class="pill">Quality: {quality.grade} ({quality.score:.0f}/100)</div>
    </div>
    <section class="essentials" aria-label="Essential flight metrics">
      <div class="metric"><span class="muted">Duration</span><strong>{summary.duration_s:.0f} s</strong></div>
      <div class="metric"><span class="muted">Distance</span><strong>{summary.distance_km:.2f} km</strong></div>
      <div class="metric"><span class="muted">Max altitude</span><strong>{summary.max_altitude_m:.1f} m</strong></div>
      <div class="metric"><span class="muted">Max speed</span><strong>{summary.max_groundspeed_m_s:.1f} m/s</strong></div>
      <div class="metric"><span class="muted">Min battery</span><strong>{summary.minimum_battery_pct:.1f}%</strong></div>
    </section>
    <div class="status-strip">{display_note}{''.join(f'<span class="pill">{html.escape(item)}</span>' for item in warnings[:4])}</div>
    <section id="workspace" class="workspace" aria-label="Analysis workspace"></section>
  </main>
</div>
{templates}
<script>
const defaultModules = {default_json};
const flightSamples = {sample_json};
const flightColumns = {column_json};
const routeSamples = flightSamples.filter(row => {{
  const lat = Number(row.latitude_deg);
  const lon = Number(row.longitude_deg);
  return Number.isFinite(lat) && Number.isFinite(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180 && !(lat === 0 && lon === 0);
}});
const workspace = document.getElementById("workspace");
const storageKey = "flight-dashboard-active-module-v2";
const themeKey = "flight-dashboard-theme";
const svgNS = "http://www.w3.org/2000/svg";
const plotState = new WeakMap();
const routeMapState = new WeakMap();
window.CESIUM_BASE_URL = "https://cesium.com/downloads/cesiumjs/releases/1.144/Build/Cesium/";

function formatTime(seconds) {{
  const safe = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(safe / 60);
  const secs = safe - minutes * 60;
  return minutes + ":" + secs.toFixed(1).padStart(4, "0");
}}

function createSvg(name, attributes = {{}}, text = "") {{
  const node = document.createElementNS(svgNS, name);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
  if (text) node.textContent = text;
  return node;
}}

function plotSamplesInRange(field, xMin, xMax) {{
  const rows = flightSamples.filter(row => Number.isFinite(Number(row.time_s)) && Number.isFinite(Number(row[field])) && Number(row.time_s) >= xMin && Number(row.time_s) <= xMax);
  return rows.length ? rows : flightSamples.filter(row => Number.isFinite(Number(row.time_s)) && Number.isFinite(Number(row[field])));
}}

function renderPlot(plot) {{
  const field = plot.dataset.field;
  const unit = plot.dataset.unit || "";
  const color = plot.dataset.color || "#1769c2";
  const svg = plot.querySelector("svg");
  const polyline = svg.querySelector("polyline");
  const grid = svg.querySelector(".plot-grid");
  const labels = svg.querySelector(".plot-labels");
  const cursor = svg.querySelector(".plot-cursor");
  const readout = plot.querySelector(".plot-readout");
  const times = flightSamples.map(row => Number(row.time_s)).filter(Number.isFinite);
  if (!times.length) return;
  const fullMin = Math.min(...times);
  const fullMax = Math.max(...times);
  const state = plotState.get(plot) || {{ xMin: fullMin, xMax: fullMax }};
  const rows = plotSamplesInRange(field, state.xMin, state.xMax);
  const values = rows.map(row => Number(row[field])).filter(Number.isFinite);
  if (!values.length) return;
  let yMin = Math.min(...values);
  let yMax = Math.max(...values);
  if (yMin === yMax) {{
    yMin -= 1;
    yMax += 1;
  }}
  const left = 54, right = 880, top = 16, bottom = 150;
  const width = right - left;
  const height = bottom - top;
  const xSpan = state.xMax - state.xMin || 1;
  const ySpan = yMax - yMin || 1;
  function px(time) {{ return left + ((Number(time) - state.xMin) / xSpan) * width; }}
  function py(value) {{ return bottom - ((Number(value) - yMin) / ySpan) * height; }}
  const points = rows.map(row => px(row.time_s).toFixed(1) + "," + py(row[field]).toFixed(1)).join(" ");
  polyline.setAttribute("points", points);
  polyline.setAttribute("stroke", color);
  grid.innerHTML = "";
  labels.innerHTML = "";
  for (let index = 0; index <= 4; index += 1) {{
    const x = left + width * index / 4;
    const time = state.xMin + xSpan * index / 4;
    grid.appendChild(createSvg("line", {{ x1: x, y1: top, x2: x, y2: bottom }}));
    labels.appendChild(createSvg("text", {{ x, y: 166, "text-anchor": "middle" }}, formatTime(time)));
    const y = top + height * index / 4;
    const value = yMax - ySpan * index / 4;
    grid.appendChild(createSvg("line", {{ x1: left, y1: y, x2: right, y2: y }}));
    labels.appendChild(createSvg("text", {{ x: 48, y: y + 4, "text-anchor": "end" }}, formatValue(value)));
  }}
  labels.appendChild(createSvg("text", {{ x: (left + right) / 2, y: 178, "text-anchor": "middle" }}, "time"));
  labels.appendChild(createSvg("text", {{ x: 14, y: 86, transform: "rotate(-90 14 86)", "text-anchor": "middle" }}, unit || field));
  readout.textContent = "Range " + formatTime(state.xMin) + "-" + formatTime(state.xMax);
  plotState.set(plot, state);

  svg.onmousemove = event => {{
    const box = svg.getBoundingClientRect();
    const x = (event.clientX - box.left) / box.width * 900;
    const targetTime = state.xMin + ((x - left) / width) * xSpan;
    let nearest = rows[0];
    let best = Infinity;
    rows.forEach(row => {{
      const distance = Math.abs(Number(row.time_s) - targetTime);
      if (distance < best) {{
        best = distance;
        nearest = row;
      }}
    }});
    cursor.hidden = false;
    cursor.setAttribute("cx", px(nearest.time_s));
    cursor.setAttribute("cy", py(nearest[field]));
    readout.textContent = formatTime(nearest.time_s) + " | " + field + ": " + formatValue(nearest[field]) + (unit ? " " + unit : "");
  }};
  svg.onmouseleave = () => {{
    cursor.hidden = true;
    readout.textContent = "Range " + formatTime(state.xMin) + "-" + formatTime(state.xMax);
  }};
}}

function initPlot(plot) {{
  if (plotState.has(plot)) return;
  const times = flightSamples.map(row => Number(row.time_s)).filter(Number.isFinite);
  if (!times.length) return;
  const fullMin = Math.min(...times);
  const fullMax = Math.max(...times);
  const svg = plot.querySelector("svg");
  let panStart = null;
  function zoomAt(clientX, factor) {{
    const state = plotState.get(plot);
    const box = svg.getBoundingClientRect();
    const left = 54, right = 880;
    const x = Math.min(right, Math.max(left, (clientX - box.left) / box.width * 900));
    const ratio = (x - left) / (right - left);
    const anchor = state.xMin + (state.xMax - state.xMin) * ratio;
    const nextSpan = Math.max(0.5, Math.min(fullMax - fullMin || 1, (state.xMax - state.xMin) * factor));
    state.xMin = Math.max(fullMin, anchor - nextSpan * ratio);
    state.xMax = Math.min(fullMax, state.xMin + nextSpan);
    state.xMin = Math.max(fullMin, state.xMax - nextSpan);
    renderPlot(plot);
  }}
  function panBy(deltaPixels) {{
    const state = plotState.get(plot);
    const box = svg.getBoundingClientRect();
    const span = state.xMax - state.xMin;
    const deltaTime = deltaPixels / Math.max(1, box.width) * span;
    state.xMin = Math.max(fullMin, Math.min(fullMax - span, state.xMin + deltaTime));
    state.xMax = state.xMin + span;
    renderPlot(plot);
  }}
  plotState.set(plot, {{ xMin: fullMin, xMax: fullMax }});
  plot.querySelector(".plot-zoom-in").addEventListener("click", () => {{
    const state = plotState.get(plot);
    const center = (state.xMin + state.xMax) / 2;
    const span = Math.max(1, (state.xMax - state.xMin) * 0.5);
    state.xMin = Math.max(fullMin, center - span / 2);
    state.xMax = Math.min(fullMax, center + span / 2);
    renderPlot(plot);
  }});
  plot.querySelector(".plot-zoom-out").addEventListener("click", () => {{
    const state = plotState.get(plot);
    const center = (state.xMin + state.xMax) / 2;
    const span = Math.min(fullMax - fullMin || 1, (state.xMax - state.xMin) * 2);
    state.xMin = Math.max(fullMin, center - span / 2);
    state.xMax = Math.min(fullMax, center + span / 2);
    renderPlot(plot);
  }});
  plot.querySelector(".plot-reset").addEventListener("click", () => {{
    plotState.set(plot, {{ xMin: fullMin, xMax: fullMax }});
    renderPlot(plot);
  }});
  svg.addEventListener("wheel", event => {{
    event.preventDefault();
    const factor = event.deltaY < 0 ? 0.82 : 1.22;
    zoomAt(event.clientX, factor);
  }}, {{ passive: false }});
  svg.addEventListener("pointerdown", event => {{
    panStart = event.clientX;
    plot.classList.add("panning");
    svg.setPointerCapture(event.pointerId);
  }});
  svg.addEventListener("pointermove", event => {{
    if (panStart === null) return;
    const delta = panStart - event.clientX;
    panStart = event.clientX;
    panBy(delta);
  }});
  svg.addEventListener("pointerup", event => {{
    panStart = null;
    plot.classList.remove("panning");
    if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
  }});
  svg.addEventListener("pointercancel", () => {{
    panStart = null;
    plot.classList.remove("panning");
  }});
  renderPlot(plot);
}}

function initPlots(root = document) {{
  root.querySelectorAll(".plot").forEach(initPlot);
}}

function formatValue(value) {{
  if (value === null || value === undefined) return "";
  if (typeof value === "number") {{
    if (Number.isInteger(value)) return String(value);
    return value.toFixed(6).replace(/0+$/, "").replace(/\\.$/, "");
  }}
  return String(value);
}}

function routePopupHtml(point) {{
  return "<strong>" + formatTime(point.time_s) + "</strong>" +
    "<div>Mode: " + escapeCell(point.mode || "Unknown") + "</div>" +
    "<div>Armed: " + (point.armed ? "Yes" : "No") + "</div>" +
    "<div>Altitude: " + formatValue(point.relative_altitude_m) + " m</div>" +
    "<div>Speed: " + formatValue(point.groundspeed_m_s) + " m/s</div>" +
    "<div>Location: " + formatValue(point.latitude_deg) + ", " + formatValue(point.longitude_deg) + "</div>";
}}

function nearestRoutePoint(lat, lon) {{
  let nearest = null;
  let best = Infinity;
  routeSamples.forEach(point => {{
    const dLat = Number(point.latitude_deg) - lat;
    const dLon = Number(point.longitude_deg) - lon;
    const score = dLat * dLat + dLon * dLon;
    if (score < best) {{
      best = score;
      nearest = point;
    }}
  }});
  return nearest;
}}

function routeColorForMode(mode) {{
  const palette = ["#1769c2", "#0f8f72", "#b36b00", "#7357c8", "#bf3145", "#0b8f8f"];
  const modes = [...new Set(routeSamples.map(point => point.mode || "Unknown"))];
  return palette[Math.max(0, modes.indexOf(mode || "Unknown")) % palette.length];
}}

function routeWaypointIndexes(maxWaypoints = 24) {{
  if (!routeSamples.length) return [];
  const step = Math.max(1, Math.ceil(routeSamples.length / maxWaypoints));
  const indexes = [];
  for (let index = 0; index < routeSamples.length; index += step) indexes.push(index);
  if (indexes[indexes.length - 1] !== routeSamples.length - 1) indexes.push(routeSamples.length - 1);
  return indexes;
}}

function loadScriptWithFallback(name, sources, isReady) {{
  if (isReady()) return Promise.resolve(true);
  if (window[name + "Loading"]) return window[name + "Loading"];
  window[name + "Loading"] = new Promise(resolve => {{
    let index = 0;
    function tryNext() {{
      if (isReady()) {{
        resolve(true);
        return;
      }}
      if (index >= sources.length) {{
        resolve(false);
        return;
      }}
      const script = document.createElement("script");
      script.src = sources[index];
      script.async = true;
      script.crossOrigin = "anonymous";
      index += 1;
      script.onload = () => resolve(isReady());
      script.onerror = tryNext;
      document.head.appendChild(script);
    }}
    tryNext();
  }});
  return window[name + "Loading"];
}}

function activeRouteModule() {{
  return workspace.querySelector('[data-module="map"]');
}}

function retryActiveRouteMaps() {{
  const moduleNode = activeRouteModule();
  if (!moduleNode) return;
  const activePanel = moduleNode.querySelector(".route-view.active");
  initCanvasRoute(moduleNode, ".canvas-route-map", "2d");
  if (activePanel && activePanel.dataset.routePanel === "route-2d") initLeafletRoute(moduleNode);
  if (activePanel && activePanel.dataset.routePanel === "route-3d") {{
    initCanvasRoute(moduleNode, ".route-3d-fallback", "3d");
    initCesiumRoute(moduleNode);
  }}
}}

function loadMapLibraries() {{
  loadScriptWithFallback("leaflet", [
    "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
    "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"
  ], () => Boolean(window.L)).then(loaded => {{
    if (loaded) retryActiveRouteMaps();
  }});
  loadScriptWithFallback("cesium", [
    "https://cesium.com/downloads/cesiumjs/releases/1.144/Build/Cesium/Cesium.js",
    "https://cdn.jsdelivr.net/npm/cesium@1.144.0/Build/Cesium/Cesium.js"
  ], () => Boolean(window.Cesium)).then(loaded => {{
    if (loaded) retryActiveRouteMaps();
  }});
}}

function routeBounds() {{
  const lats = routeSamples.map(point => Number(point.latitude_deg));
  const lons = routeSamples.map(point => Number(point.longitude_deg));
  return {{
    minLat: Math.min(...lats),
    maxLat: Math.max(...lats),
    minLon: Math.min(...lons),
    maxLon: Math.max(...lons),
    minAlt: Math.min(...routeSamples.map(point => Number(point.relative_altitude_m) || 0)),
    maxAlt: Math.max(...routeSamples.map(point => Number(point.relative_altitude_m) || 0))
  }};
}}

function routeCanvasSetup(canvas) {{
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(320, Math.floor(rect.width || canvas.clientWidth || 900));
  const height = Math.max(280, Math.floor(rect.height || 420));
  const scale = window.devicePixelRatio || 1;
  canvas.width = Math.floor(width * scale);
  canvas.height = Math.floor(height * scale);
  const context = canvas.getContext("2d");
  context.setTransform(scale, 0, 0, scale, 0, 0);
  return {{ context, width, height }};
}}

function projected2D(width, height) {{
  const bounds = routeBounds();
  const pad = 34;
  const latSpan = bounds.maxLat - bounds.minLat || 0.000001;
  const lonSpan = bounds.maxLon - bounds.minLon || 0.000001;
  return routeSamples.map(point => ({{
    point,
    x: pad + ((Number(point.longitude_deg) - bounds.minLon) / lonSpan) * (width - pad * 2),
    y: height - pad - ((Number(point.latitude_deg) - bounds.minLat) / latSpan) * (height - pad * 2)
  }}));
}}

function projected3D(width, height) {{
  const bounds = routeBounds();
  const pad = 42;
  const latSpan = bounds.maxLat - bounds.minLat || 0.000001;
  const lonSpan = bounds.maxLon - bounds.minLon || 0.000001;
  const altSpan = bounds.maxAlt - bounds.minAlt || 1;
  return routeSamples.map(point => {{
    const nx = (Number(point.longitude_deg) - bounds.minLon) / lonSpan;
    const ny = (Number(point.latitude_deg) - bounds.minLat) / latSpan;
    const nz = ((Number(point.relative_altitude_m) || 0) - bounds.minAlt) / altSpan;
    return {{
      point,
      x: pad + nx * (width - pad * 2) + (ny - 0.5) * 70,
      y: height - pad - ny * (height - pad * 2) * 0.58 - nz * (height * 0.34)
    }};
  }});
}}

function drawRouteCanvas(canvas, mode = "2d") {{
  if (!canvas || routeSamples.length < 2) return [];
  const {{ context, width, height }} = routeCanvasSetup(canvas);
  const projected = mode === "3d" ? projected3D(width, height) : projected2D(width, height);
  context.clearRect(0, 0, width, height);
  context.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--panel-2").trim() || "#eef2f7";
  context.fillRect(0, 0, width, height);
  context.strokeStyle = "rgba(101,113,132,0.28)";
  context.lineWidth = 1;
  for (let i = 1; i < 5; i += 1) {{
    const x = width * i / 5;
    const y = height * i / 5;
    context.beginPath();
    context.moveTo(x, 0);
    context.lineTo(x, height);
    context.moveTo(0, y);
    context.lineTo(width, y);
    context.stroke();
  }}
  let segmentStart = 0;
  for (let index = 1; index < projected.length; index += 1) {{
    const previousMode = projected[index - 1].point.mode || "Unknown";
    const currentMode = projected[index].point.mode || "Unknown";
    if (currentMode !== previousMode || index === projected.length - 1) {{
      const end = index === projected.length - 1 ? index : index - 1;
      context.beginPath();
      context.strokeStyle = routeColorForMode(previousMode);
      context.lineWidth = mode === "3d" ? 5 : 4;
      context.lineJoin = "round";
      context.lineCap = "round";
      context.moveTo(projected[segmentStart].x, projected[segmentStart].y);
      for (let pointIndex = segmentStart + 1; pointIndex <= end; pointIndex += 1) {{
        context.lineTo(projected[pointIndex].x, projected[pointIndex].y);
      }}
      context.stroke();
      segmentStart = Math.max(0, end);
    }}
  }}
  const first = projected[0];
  const last = projected[projected.length - 1];
  context.font = "700 13px Segoe UI, Arial";
  context.fillStyle = "#0f8f72";
  context.beginPath();
  context.arc(first.x, first.y, 7, 0, Math.PI * 2);
  context.fill();
  context.fillText("Start", first.x + 10, first.y - 10);
  context.fillStyle = "#bf3145";
  context.beginPath();
  context.arc(last.x, last.y, 7, 0, Math.PI * 2);
  context.fill();
  context.fillText("End", last.x + 10, last.y - 10);
  routeWaypointIndexes(mode === "3d" ? 20 : 24).forEach((index, sequence) => {{
    const waypoint = projected[index];
    if (!waypoint) return;
    context.beginPath();
    context.fillStyle = "#ffffff";
    context.strokeStyle = "#1769c2";
    context.lineWidth = 3;
    context.arc(waypoint.x, waypoint.y, 12, 0, Math.PI * 2);
    context.fill();
    context.stroke();
    context.fillStyle = "#111827";
    context.font = "800 11px Segoe UI, Arial";
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillText(String(sequence + 1), waypoint.x, waypoint.y);
  }});
  context.textAlign = "start";
  context.textBaseline = "alphabetic";
  return projected;
}}

function routeInspectorText(point) {{
  return formatTime(point.time_s) + " | Mode: " + (point.mode || "Unknown") +
    " | Armed: " + (point.armed ? "Yes" : "No") +
    " | Alt: " + formatValue(point.relative_altitude_m) + " m" +
    " | Speed: " + formatValue(point.groundspeed_m_s) + " m/s" +
    " | Location: " + formatValue(point.latitude_deg) + ", " + formatValue(point.longitude_deg);
}}

function initCanvasRoute(moduleNode, selector, mode) {{
  const canvas = moduleNode.querySelector(selector);
  const inspector = canvas ? canvas.parentElement.querySelector(".route-inspector") : null;
  if (!canvas || canvas.dataset.ready) return;
  canvas.dataset.ready = "true";
  let projected = drawRouteCanvas(canvas, mode);
  if (projected.length) canvas.parentElement.classList.add("has-canvas");
  canvas.addEventListener("mousemove", event => {{
    const box = canvas.getBoundingClientRect();
    const x = event.clientX - box.left;
    const y = event.clientY - box.top;
    let nearest = projected[0];
    let best = Infinity;
    projected.forEach(item => {{
      const dx = item.x - x;
      const dy = item.y - y;
      const score = dx * dx + dy * dy;
      if (score < best) {{
        best = score;
        nearest = item;
      }}
    }});
    if (nearest && inspector && best <= 18 * 18) {{
      inspector.textContent = routeInspectorText(nearest.point);
    }} else if (inspector) {{
      inspector.textContent = mode === "3d" ? "Hover the 3D route for time, mode, speed, altitude, and location." : "Hover the route for time, mode, speed, altitude, and location.";
    }}
  }});
  window.addEventListener("resize", () => {{ projected = drawRouteCanvas(canvas, mode); }});
}}

function initLeafletRoute(moduleNode) {{
  const panel = moduleNode.querySelector('[data-route-panel="route-2d"]');
  const container = moduleNode.querySelector(".leaflet-route-map");
  if (!panel || !container || routeMapState.get(container)) return;
  if (!window.L || routeSamples.length < 2) {{
    return;
  }}
  const points = routeSamples.map(point => [Number(point.latitude_deg), Number(point.longitude_deg)]);
  const inspector = panel.querySelector(".route-inspector");
  const map = L.map(container, {{ scrollWheelZoom: true, preferCanvas: true }});
  L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 20
  }}).addTo(map);
  L.polyline(points, {{ color: "#111827", weight: 10, opacity: 0.72, lineCap: "round", lineJoin: "round" }}).addTo(map);
  L.polyline(points, {{ color: "#19b7ff", weight: 5, opacity: 1, lineCap: "round", lineJoin: "round" }}).addTo(map);
  let segment = [points[0]];
  let mode = routeSamples[0].mode || "Unknown";
  routeSamples.slice(1).forEach((point, index) => {{
    const nextMode = point.mode || "Unknown";
    segment.push(points[index + 1]);
    if (nextMode !== mode || index === routeSamples.length - 2) {{
      L.polyline(segment, {{ color: routeColorForMode(mode), weight: 7, opacity: 0.95, lineCap: "round", lineJoin: "round" }}).addTo(map);
      segment = [points[index + 1]];
      mode = nextMode;
    }}
  }});
  const markerStep = Math.max(1, Math.ceil(points.length / 36));
  points.forEach((latlng, index) => {{
    if (index % markerStep !== 0 && index !== points.length - 1) return;
    L.circleMarker(latlng, {{
      radius: 3,
      color: "#ffffff",
      weight: 1,
      fillColor: routeColorForMode(routeSamples[index].mode || "Unknown"),
      fillOpacity: 0.95
    }}).addTo(map);
  }});
  routeWaypointIndexes(24).forEach((index, sequence) => {{
    const point = routeSamples[index];
    L.marker([Number(point.latitude_deg), Number(point.longitude_deg)], {{
      icon: L.divIcon({{
        className: "",
        html: `<span class="waypoint-marker">${{sequence + 1}}</span>`,
        iconSize: [26, 26],
        iconAnchor: [13, 13]
      }}),
      keyboard: false
    }}).addTo(map).bindPopup("Waypoint " + (sequence + 1) + "<br>" + routePopupHtml(point));
  }});
  const hoverMarker = L.circleMarker(points[0], {{ radius: 6, color: "#ffffff", weight: 2, fillColor: "#1769c2", fillOpacity: 1 }}).addTo(map);
  hoverMarker.setStyle({{ opacity: 0, fillOpacity: 0 }});
  const hitLine = L.polyline(points, {{ color: "#000000", weight: 26, opacity: 0.01, interactive: true }}).addTo(map);
  hitLine.on("mousemove", event => {{
    const point = nearestRoutePoint(event.latlng.lat, event.latlng.lng);
    if (!point) return;
    const latlng = [Number(point.latitude_deg), Number(point.longitude_deg)];
    hoverMarker.setLatLng(latlng);
    hoverMarker.setStyle({{ opacity: 1, fillOpacity: 1 }});
    hoverMarker.bindTooltip(routePopupHtml(point), {{ sticky: true, direction: "top", opacity: 0.96 }}).openTooltip();
    if (inspector) inspector.textContent = routeInspectorText(point);
  }});
  hitLine.on("mouseout", () => {{
    hoverMarker.closeTooltip();
    hoverMarker.setStyle({{ opacity: 0, fillOpacity: 0 }});
    if (inspector) inspector.textContent = "Hover the route for time, mode, speed, altitude, and location.";
  }});
  L.marker(points[0]).addTo(map).bindPopup("Start<br>" + routePopupHtml(routeSamples[0]));
  L.marker(points[points.length - 1]).addTo(map).bindPopup("End<br>" + routePopupHtml(routeSamples[routeSamples.length - 1]));
  map.fitBounds(points, {{ padding: [28, 28] }});
  panel.classList.add("has-leaflet");
  panel.classList.remove("map-failed");
  routeMapState.set(container, map);
}}

function initCesiumRoute(moduleNode) {{
  const panel = moduleNode.querySelector('[data-route-panel="route-3d"]');
  const container = moduleNode.querySelector(".cesium-route-map");
  if (!panel || !container || routeMapState.get(container)) return;
  if (!window.Cesium || routeSamples.length < 2) {{
    return;
  }}
  Cesium.Ion.defaultAccessToken = "";
  const viewerOptions = {{
    animation: false,
    baseLayerPicker: false,
    fullscreenButton: false,
    geocoder: false,
    homeButton: false,
    infoBox: false,
    sceneModePicker: false,
    selectionIndicator: false,
    timeline: false,
    navigationHelpButton: false,
    terrainProvider: new Cesium.EllipsoidTerrainProvider()
  }};
  let osmProvider = null;
  if (Cesium.OpenStreetMapImageryProvider) {{
    osmProvider = new Cesium.OpenStreetMapImageryProvider({{
      url: "https://tile.openstreetmap.org/"
    }});
  }} else if (Cesium.UrlTemplateImageryProvider) {{
    osmProvider = new Cesium.UrlTemplateImageryProvider({{
      url: "https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png",
      maximumLevel: 19,
      credit: "OpenStreetMap"
    }});
  }}
  if (osmProvider && Cesium.ImageryLayer) {{
    viewerOptions.baseLayer = new Cesium.ImageryLayer(osmProvider);
  }} else if (osmProvider) {{
    viewerOptions.imageryProvider = osmProvider;
  }}
  let viewer;
  try {{
    viewer = new Cesium.Viewer(container, viewerOptions);
  }} catch (error) {{
    panel.classList.add("map-failed");
    return;
  }}
  viewer.scene.globe.depthTestAgainstTerrain = false;
  viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#d7e2c8");
  if (viewer.scene.skyAtmosphere) viewer.scene.skyAtmosphere.show = false;
  const lats = routeSamples.map(point => Number(point.latitude_deg));
  const lons = routeSamples.map(point => Number(point.longitude_deg));
  const alts = routeSamples.map(point => Math.max(1, Number(point.relative_altitude_m) || 1));
  const minLat = Math.min(...lats), maxLat = Math.max(...lats);
  const minLon = Math.min(...lons), maxLon = Math.max(...lons);
  const minAlt = Math.min(...alts), maxAlt = Math.max(...alts);
  const centerLat = (minLat + maxLat) / 2;
  const centerLon = (minLon + maxLon) / 2;
  const latMeters = Math.max(50, Math.abs(maxLat - minLat) * 111320);
  const lonMeters = Math.max(50, Math.abs(maxLon - minLon) * 111320 * Math.max(0.1, Math.cos(centerLat * Math.PI / 180)));
  const routeSpanMeters = Math.max(latMeters, lonMeters, maxAlt - minAlt, 250);
  const altitudeScale = Math.max(1, Math.min(8, 900 / Math.max(80, maxAlt - minAlt || 1)));
  const positions = routeSamples.map(point => Cesium.Cartesian3.fromDegrees(
    Number(point.longitude_deg),
    Number(point.latitude_deg),
    Math.max(2, (Number(point.relative_altitude_m) || 1) * altitudeScale)
  ));
  viewer.entities.add({{
    name: "Route ground shadow",
    polyline: {{
      positions: routeSamples.map(point => Cesium.Cartesian3.fromDegrees(Number(point.longitude_deg), Number(point.latitude_deg), 1)),
      width: 3,
      material: Cesium.Color.BLACK.withAlpha(0.45),
      clampToGround: false
    }}
  }});
  viewer.entities.add({{
    name: "Drone route",
    polyline: {{
      positions,
      width: 8,
      material: new Cesium.PolylineGlowMaterialProperty({{
        glowPower: 0.28,
        color: Cesium.Color.CYAN
      }}),
      clampToGround: false
    }}
  }});
  viewer.entities.add({{
    name: "Start",
    position: positions[0],
    point: {{ pixelSize: 11, color: Cesium.Color.fromCssColorString("#0f8f72"), outlineColor: Cesium.Color.WHITE, outlineWidth: 2 }},
    label: {{ text: "Start", font: "14px sans-serif", pixelOffset: new Cesium.Cartesian2(0, -22), fillColor: Cesium.Color.WHITE }}
  }});
  viewer.entities.add({{
    name: "End",
    position: positions[positions.length - 1],
    point: {{ pixelSize: 11, color: Cesium.Color.fromCssColorString("#bf3145"), outlineColor: Cesium.Color.WHITE, outlineWidth: 2 }},
    label: {{ text: "End", font: "14px sans-serif", pixelOffset: new Cesium.Cartesian2(0, -22), fillColor: Cesium.Color.WHITE }}
  }});
  const hoverEntity = viewer.entities.add({{
    name: "Point details",
    position: positions[0],
    point: {{ pixelSize: 10, color: Cesium.Color.YELLOW, outlineColor: Cesium.Color.BLACK, outlineWidth: 1 }},
    label: {{ text: "", font: "13px sans-serif", showBackground: true, backgroundColor: Cesium.Color.BLACK.withAlpha(0.72), pixelOffset: new Cesium.Cartesian2(0, -32), fillColor: Cesium.Color.WHITE }},
    show: false
  }});
  routeWaypointIndexes(20).forEach((index, sequence) => {{
    const point = routeSamples[index];
    viewer.entities.add({{
      name: "Waypoint " + (sequence + 1),
      position: Cesium.Cartesian3.fromDegrees(Number(point.longitude_deg), Number(point.latitude_deg), Math.max(2, (Number(point.relative_altitude_m) || 1) * altitudeScale)),
      point: {{ pixelSize: 10, color: Cesium.Color.WHITE, outlineColor: Cesium.Color.fromCssColorString("#1769c2"), outlineWidth: 3 }},
      label: {{
        text: String(sequence + 1),
        font: "700 13px sans-serif",
        showBackground: true,
        backgroundColor: Cesium.Color.WHITE.withAlpha(0.92),
        fillColor: Cesium.Color.BLACK,
        pixelOffset: new Cesium.Cartesian2(0, -22)
      }}
    }});
  }});
  const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
  handler.setInputAction(movement => {{
    const picked = viewer.scene.pick(movement.endPosition);
    if (!picked || !picked.id || !["Drone route", "Route ground shadow"].includes(picked.id.name)) {{
      hoverEntity.show = false;
      return;
    }}
    const cartesian = viewer.camera.pickEllipsoid(movement.endPosition, viewer.scene.globe.ellipsoid);
    if (!cartesian) return;
    const cartographic = Cesium.Cartographic.fromCartesian(cartesian);
    const point = nearestRoutePoint(Cesium.Math.toDegrees(cartographic.latitude), Cesium.Math.toDegrees(cartographic.longitude));
    if (!point) return;
    hoverEntity.show = true;
    hoverEntity.position = Cesium.Cartesian3.fromDegrees(Number(point.longitude_deg), Number(point.latitude_deg), Math.max(2, (Number(point.relative_altitude_m) || 1) * altitudeScale));
    hoverEntity.label.text = formatTime(point.time_s) + "\\n" +
      "Mode: " + (point.mode || "Unknown") + "\\n" +
      "Alt: " + formatValue(point.relative_altitude_m) + " m | Speed: " + formatValue(point.groundspeed_m_s) + " m/s";
  }}, Cesium.ScreenSpaceEventType.MOUSE_MOVE);
  viewer.camera.setView({{
    destination: Cesium.Cartesian3.fromDegrees(centerLon, centerLat, Math.max(600, routeSpanMeters * 2.4)),
    orientation: {{
      heading: Cesium.Math.toRadians(0),
      pitch: Cesium.Math.toRadians(-62),
      roll: 0
    }}
  }});
  panel.classList.add("has-cesium");
  panel.classList.remove("map-failed");
  routeMapState.set(container, viewer);
}}

function initRouteMaps(root = document) {{
  root.querySelectorAll(".route-tabs").forEach(tabs => {{
    if (tabs.dataset.ready) return;
    tabs.dataset.ready = "true";
    const moduleNode = tabs.closest(".module");
    tabs.querySelectorAll(".route-tab").forEach(button => {{
      button.addEventListener("click", () => {{
        tabs.querySelectorAll(".route-tab").forEach(item => item.classList.toggle("active", item === button));
        moduleNode.querySelectorAll(".route-view").forEach(panel => panel.classList.toggle("active", panel.dataset.routePanel === button.dataset.routeView));
        if (button.dataset.routeView === "route-2d") {{
          initCanvasRoute(moduleNode, ".canvas-route-map", "2d");
          initLeafletRoute(moduleNode);
          const map = routeMapState.get(moduleNode.querySelector(".leaflet-route-map"));
          if (map && map.invalidateSize) setTimeout(() => map.invalidateSize(), 20);
        }}
        if (button.dataset.routeView === "route-3d") {{
          initCanvasRoute(moduleNode, ".route-3d-fallback", "3d");
          initCesiumRoute(moduleNode);
          const viewer = routeMapState.get(moduleNode.querySelector(".cesium-route-map"));
          if (viewer && viewer.resize) setTimeout(() => viewer.resize(), 20);
        }}
      }});
    }});
    initCanvasRoute(moduleNode, ".canvas-route-map", "2d");
    initLeafletRoute(moduleNode);
  }});
}}

function escapeCell(value) {{
  return formatValue(value).replace(/[&<>"']/g, character => ({{
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  }}[character]));
}}

function csvCell(value) {{
  const text = formatValue(value);
  return /[",\\n]/.test(text) ? '"' + text.replaceAll('"', '""') + '"' : text;
}}

function initDataExplorer(moduleNode) {{
  const search = moduleNode.querySelector(".data-search");
  const pageSize = moduleNode.querySelector(".data-page-size");
  const previous = moduleNode.querySelector(".data-prev");
  const next = moduleNode.querySelector(".data-next");
  const download = moduleNode.querySelector(".download-csv");
  const status = moduleNode.querySelector(".data-status");
  const body = moduleNode.querySelector(".data-table tbody");
  let page = 0;

  function filteredRows() {{
    const query = search.value.trim().toLowerCase();
    if (!query) return flightSamples;
    return flightSamples.filter(row => flightColumns.some(column => formatValue(row[column]).toLowerCase().includes(query)));
  }}

  function renderRows() {{
    const rows = filteredRows();
    const size = Number(pageSize.value) || 25;
    const maxPage = Math.max(1, Math.ceil(rows.length / size));
    page = Math.max(0, Math.min(page, maxPage - 1));
    const start = page * size;
    const visible = rows.slice(start, start + size);
    body.innerHTML = visible.map(row => "<tr>" + flightColumns.map(column => "<td>" + escapeCell(row[column]) + "</td>").join("") + "</tr>").join("");
    status.textContent = rows.length ? (start + 1) + "-" + (start + visible.length) + " of " + rows.length : "0 of 0";
    previous.disabled = page === 0;
    next.disabled = page >= maxPage - 1;
  }}

  search.addEventListener("input", () => {{ page = 0; renderRows(); }});
  pageSize.addEventListener("change", () => {{ page = 0; renderRows(); }});
  previous.addEventListener("click", () => {{ page -= 1; renderRows(); }});
  next.addEventListener("click", () => {{ page += 1; renderRows(); }});
  download.addEventListener("click", () => {{
    const rows = filteredRows();
    const csv = [flightColumns.join(",")].concat(rows.map(row => flightColumns.map(column => csvCell(row[column])).join(","))).join("\\n");
    const blob = new Blob([csv], {{ type: "text/csv" }});
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "normalized-flight-data.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  }});
  renderRows();
}}

function initSimpleTableFilter(moduleNode, inputSelector, tableSelector) {{
  const input = moduleNode.querySelector(inputSelector);
  const rows = [...moduleNode.querySelectorAll(tableSelector + " tbody tr")];
  if (!input || !rows.length || input.dataset.ready) return;
  input.dataset.ready = "true";
  input.addEventListener("input", () => {{
    const query = input.value.trim().toLowerCase();
    rows.forEach(row => {{
      row.hidden = query && !row.textContent.toLowerCase().includes(query);
    }});
  }});
}}

function initCustomGraphBuilder(moduleNode) {{
  const builder = moduleNode.querySelector(".custom-graph-builder");
  if (!builder || builder.dataset.ready) return;
  builder.dataset.ready = "true";
  const ySelect = builder.querySelector(".graph-y");
  const list = builder.querySelector(".custom-plot-list");
  function addPlot(field) {{
    if (!field) return;
    const plot = document.createElement("div");
    plot.innerHTML = `<div class="plot" data-field="${{field}}" data-unit="" data-color="#1769c2">
      <div class="plot-head"><span>${{field}}</span><span></span></div>
      <div class="plot-tools">
        <button class="ghost plot-zoom-in" type="button">Zoom in</button>
        <button class="ghost plot-zoom-out" type="button">Zoom out</button>
        <button class="ghost plot-reset" type="button">Reset</button>
        <span class="muted plot-readout">Hover plot for time and value</span>
      </div>
      <svg viewBox="0 0 900 180" role="img" aria-label="${{field}} custom plot">
        <g class="plot-grid"></g>
        <g class="plot-labels"></g>
        <line x1="54" y1="150" x2="880" y2="150" class="axis"/>
        <line x1="54" y1="16" x2="54" y2="150" class="axis"/>
        <polyline points="" stroke="#1769c2"/>
        <circle class="plot-cursor" r="4" hidden></circle>
      </svg>
    </div>`;
    const node = plot.firstElementChild;
    list.appendChild(node);
    initPlot(node);
  }}
  builder.querySelector(".graph-add").addEventListener("click", () => addPlot(ySelect.value));
  builder.querySelector(".graph-clear").addEventListener("click", () => {{ list.innerHTML = ""; }});
  addPlot(ySelect.value || "relative_altitude_m");
}}

function createModule(id) {{
  const template = document.getElementById(`template-${{id}}`);
  if (!template) return null;
  const node = template.content.firstElementChild.cloneNode(true);
  if (id === "data") initDataExplorer(node);
  if (id === "parameters") initSimpleTableFilter(node, ".parameter-search", ".parameter-table");
  if (id === "messages") initSimpleTableFilter(node, ".message-search", ".message-table");
  if (id === "custom-graphs") initCustomGraphBuilder(node);
  initPlots(node);
  if (id === "map") initRouteMaps(node);
  return node;
}}

function showModule(id) {{
  const node = createModule(id);
  if (!node) return;
  workspace.innerHTML = "";
  workspace.appendChild(node);
  localStorage.setItem(storageKey, JSON.stringify([id]));
  document.querySelectorAll(".library-item").forEach(item => item.classList.toggle("active", item.dataset.module === id));
}}

function loadLayout() {{
  const saved = JSON.parse(localStorage.getItem(storageKey) || "null");
  const id = Array.isArray(saved) && saved.length ? saved[0] : defaultModules[0];
  showModule(id || "home");
}}

document.querySelectorAll(".library-item").forEach(item => {{
  item.addEventListener("click", () => showModule(item.dataset.module));
}});
document.getElementById("resetLayout").addEventListener("click", () => {{
  localStorage.removeItem(storageKey);
  showModule("home");
}});
document.getElementById("themeToggle").addEventListener("click", () => {{
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem(themeKey, next);
}});
document.documentElement.dataset.theme = localStorage.getItem(themeKey) || "light";
loadLayout();
loadMapLibraries();
</script>
</body></html>"""
    destination.write_text(document, encoding="utf-8")
