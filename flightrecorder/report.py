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

    display_points = _downsample(route_samples, 160)
    point_lookup = {id(sample): (x, y) for sample, x, y in projected}
    sample_dots = "".join(
        f'<circle cx="{point_lookup[id(sample)][0]:.1f}" cy="{point_lookup[id(sample)][1]:.1f}" r="1.8" />'
        for sample in display_points
    )
    start_sample, start_x, start_y = projected[0]
    end_sample, end_x, end_y = projected[-1]
    return f"""<div class="route-meta">
      <div><span class="muted">Start</span><strong>{html.escape(_format_position(start_sample))}</strong></div>
      <div><span class="muted">End</span><strong>{html.escape(_format_position(end_sample))}</strong></div>
      <div><span class="muted">GPS points</span><strong>{len(route_samples)}</strong></div>
    </div>
    <svg class="route-map" viewBox="0 0 {width} {height}" role="img" aria-label="Drone route map">
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
            "title": "AI Analyst Placeholder",
            "html": "<p class=\"muted\">Future module: explain deterministic findings, answer questions, and compare flights without changing raw measurements.</p>",
        },
    }
    templates = []
    for module_id, module in modules.items():
        templates.append(
            f"""<template id="template-{html.escape(module_id)}">
              <section class="module" data-module="{html.escape(module_id)}" draggable="true">
                <div class="module-head">
                  <h2>{html.escape(module["title"])}</h2>
                  <div>
                    <button class="icon-button drag-handle" type="button" title="Drag module">Move</button>
                    <button class="icon-button remove-module" type="button" title="Remove module">Remove</button>
                  </div>
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
    default_modules = ["quality", "map", "modes", "charts", "assessment", "events", "data"]
    module_library = [
        ("quality", "Data Quality", "Signal coverage, gaps, and confidence"),
        ("map", "Route Map", "Drone path, start/end points, and mode colors"),
        ("modes", "Mode Segments", "Mode, arm state, time range, and positions"),
        ("charts", "Flight Trends", "Altitude, speed, and battery plots"),
        ("assessment", "Flight Assessment", "Rule-based findings and evidence"),
        ("events", "Event Timeline", "Detected flight events"),
        ("power", "Power Review", "Voltage and current behaviour"),
        ("fuel", "Fuel Flow", "Fuel burn, flow spikes, and endurance"),
        ("gps", "GPS Health", "Fix type, satellites, and HDOP"),
        ("attitude", "Attitude Review", "Roll, pitch, and yaw"),
        ("limitations", "Analysis Limits", "What this report cannot prove"),
        ("data", "All Data", "Browse and export every normalized sample"),
        ("ai", "AI Analyst", "Future narrative and Q&A assistant"),
    ]
    library_html = "".join(
        f"""<button class="library-item" type="button" draggable="true" data-module="{module_id}">
          <span>{html.escape(title)}</span><small>{html.escape(description)}</small>
        </button>"""
        for module_id, title, description in module_library
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
<title>Flight Data Dashboard</title><style>
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
.library-item:hover, .drop-target {{ border-color: var(--accent); }}
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
.module.dragging {{ opacity: .5; }}
.module-head {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; }}
.module-head h2 {{ font-size: 17px; margin: 0; }}
.icon-button {{ padding: 7px 9px; margin-left: 6px; font-size: 13px; }}
.plot {{ margin: 12px 0; }}
.plot-head {{ display: flex; justify-content: space-between; color: var(--muted); margin-bottom: 7px; }}
.plot-tools {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 8px; }}
.plot-tools .ghost {{ width: auto; padding: 6px 9px; font-size: 13px; }}
.plot-readout {{ margin-left: auto; font-size: 13px; }}
svg {{ width: 100%; height: auto; background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px; }}
polyline {{ fill: none; stroke-width: 3; stroke-linejoin: round; }}
.axis {{ stroke: var(--line); }}
.plot-grid line {{ stroke: var(--line); stroke-width: 1; opacity: .72; }}
.plot-labels text {{ fill: var(--muted); font-size: 11px; }}
.plot-cursor {{ fill: var(--accent); stroke: var(--panel); stroke-width: 2; }}
.route-meta {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }}
.route-meta div {{ background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px; padding: 11px; min-width: 0; }}
.route-meta strong {{ display: block; margin-top: 4px; overflow-wrap: anywhere; }}
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
const workspace = document.getElementById("workspace");
const storageKey = "flight-dashboard-layout";
const themeKey = "flight-dashboard-theme";
let draggedModule = null;
const svgNS = "http://www.w3.org/2000/svg";
const plotState = new WeakMap();

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

function createModule(id) {{
  const template = document.getElementById(`template-${{id}}`);
  if (!template) return null;
  const node = template.content.firstElementChild.cloneNode(true);
  node.querySelector(".remove-module").addEventListener("click", () => {{
    node.remove();
    saveLayout();
  }});
  node.addEventListener("dragstart", event => {{
    draggedModule = node;
    node.classList.add("dragging");
    event.dataTransfer.setData("text/plain", id);
  }});
  node.addEventListener("dragend", () => {{
    node.classList.remove("dragging");
    draggedModule = null;
    saveLayout();
  }});
  if (id === "data") initDataExplorer(node);
  initPlots(node);
  return node;
}}

function addModule(id) {{
  const node = createModule(id);
  if (!node) return;
  workspace.appendChild(node);
  saveLayout();
}}

function loadLayout() {{
  workspace.innerHTML = "";
  const saved = JSON.parse(localStorage.getItem(storageKey) || "null");
  const modules = Array.isArray(saved) && saved.length ? saved : defaultModules;
  modules.forEach(id => {{
    const node = createModule(id);
    if (node) workspace.appendChild(node);
  }});
}}

function saveLayout() {{
  const ids = [...workspace.querySelectorAll(".module")].map(node => node.dataset.module);
  localStorage.setItem(storageKey, JSON.stringify(ids));
}}

workspace.addEventListener("dragover", event => {{
  event.preventDefault();
  workspace.classList.add("drop-target");
  const after = [...workspace.querySelectorAll(".module:not(.dragging)")].find(child => {{
    const box = child.getBoundingClientRect();
    return event.clientY < box.top + box.height / 2;
  }});
  if (draggedModule) workspace.insertBefore(draggedModule, after || null);
}});
workspace.addEventListener("dragleave", () => workspace.classList.remove("drop-target"));
workspace.addEventListener("drop", event => {{
  event.preventDefault();
  workspace.classList.remove("drop-target");
  const id = event.dataTransfer.getData("text/plain");
  if (!draggedModule && id) addModule(id);
  saveLayout();
}});

document.querySelectorAll(".library-item").forEach(item => {{
  item.addEventListener("click", () => addModule(item.dataset.module));
  item.addEventListener("dragstart", event => event.dataTransfer.setData("text/plain", item.dataset.module));
}});
document.getElementById("resetLayout").addEventListener("click", () => {{
  localStorage.removeItem(storageKey);
  loadLayout();
}});
document.getElementById("themeToggle").addEventListener("click", () => {{
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem(themeKey, next);
}});
document.documentElement.dataset.theme = localStorage.getItem(themeKey) || "light";
loadLayout();
</script></body></html>"""
    destination.write_text(document, encoding="utf-8")
