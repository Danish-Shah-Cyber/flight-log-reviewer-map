from __future__ import annotations

from dataclasses import dataclass, field

from .model import FlightSample


@dataclass(slots=True)
class Insight:
    severity: str
    title: str
    start_s: float
    end_s: float
    evidence: list[str]
    possible_causes: list[str]
    recommendation: str
    confidence: str = "medium"


@dataclass(slots=True)
class InsightReport:
    status: str
    findings: list[Insight] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


_SEVERITY_ORDER = {"critical": 0, "warning": 1, "notice": 2, "positive": 3}


def _runs(samples: list[FlightSample], predicate, minimum_duration_s: float) -> list[list[FlightSample]]:
    runs: list[list[FlightSample]] = []
    current: list[FlightSample] = []
    for sample in samples:
        if predicate(sample):
            current.append(sample)
        else:
            if current and current[-1].time_s - current[0].time_s >= minimum_duration_s:
                runs.append(current)
            current = []
    if current and current[-1].time_s - current[0].time_s >= minimum_duration_s:
        runs.append(current)
    return runs


def generate_insights(samples: list[FlightSample]) -> InsightReport:
    if not samples:
        raise ValueError("At least one sample is required")

    findings: list[Insight] = []
    limitations: list[str] = []

    # Data quality must be assessed before aircraft behaviour.
    gaps = [
        (left, right)
        for left, right in zip(samples, samples[1:])
        if right.time_s - left.time_s > 2.5
    ]
    if gaps:
        worst = max(gaps, key=lambda pair: pair[1].time_s - pair[0].time_s)
        gap_s = worst[1].time_s - worst[0].time_s
        findings.append(Insight(
            "warning", "Telemetry recording gaps", gaps[0][0].time_s, gaps[-1][1].time_s,
            [f"{len(gaps)} gap(s) exceeded 2.5 s", f"Longest gap was {gap_s:.1f} s"],
            ["Telemetry link interruption", "Ground-station recording pause", "Packet loss"],
            "Inspect radio link quality and avoid drawing conclusions inside missing intervals.", "high",
        ))
        limitations.append("Some flight intervals are missing from the recording.")

    if all(abs(sample.latitude_deg) < 0.0001 and abs(sample.longitude_deg) < 0.0001 for sample in samples):
        limitations.append("No usable GPS position was recorded.")
    if all(sample.airspeed_m_s == 0 for sample in samples):
        limitations.append("No airspeed data was recorded; air-data checks were skipped.")
    if all(sample.battery_voltage_v == 0 for sample in samples):
        limitations.append("No battery voltage was recorded; electrical checks were skipped.")

    battery_values = [sample.battery_remaining_pct for sample in samples if sample.battery_remaining_pct >= 0]
    if battery_values and min(battery_values) < 25:
        first = next(sample for sample in samples if sample.battery_remaining_pct < 25)
        minimum = min(samples, key=lambda sample: sample.battery_remaining_pct)
        severity = "critical" if minimum.battery_remaining_pct < 15 else "warning"
        findings.append(Insight(
            severity, "Low estimated battery remaining", first.time_s, samples[-1].time_s,
            [f"Battery crossed 25% at {first.time_s:.1f} s", f"Minimum estimate was {minimum.battery_remaining_pct:.0f}%"],
            ["Normal mission energy consumption", "Battery capacity mismatch", "Battery estimate not calibrated"],
            "Check consumed capacity against charger data and verify battery-monitor calibration.", "high",
        ))

    armed_voltage = [sample.battery_voltage_v for sample in samples if sample.armed and sample.battery_voltage_v > 0]
    if armed_voltage:
        reference_voltage = max(armed_voltage[: max(1, min(20, len(armed_voltage)))])
        sag_limit = reference_voltage * 0.85
        sag_runs = _runs(samples, lambda s: s.armed and s.throttle_pct >= 70 and 0 < s.battery_voltage_v < sag_limit, 2.0)
        if sag_runs:
            run = sag_runs[0]
            minimum = min(sample.battery_voltage_v for sample in run)
            findings.append(Insight(
                "warning", "Excessive voltage sag under high throttle", run[0].time_s, run[-1].time_s,
                [f"Voltage fell to {minimum:.2f} V", f"Reference voltage was {reference_voltage:.2f} V", "Throttle was at least 70%"],
                ["High battery internal resistance", "Undersized battery", "Connector or wiring resistance"],
                "Inspect connectors and compare battery voltage under a controlled load.", "high",
            ))

    discrepancy_runs = _runs(
        samples,
        lambda s: s.airspeed_m_s > 3 and s.groundspeed_m_s > 3 and abs(s.airspeed_m_s - s.groundspeed_m_s) > 10,
        5.0,
    )
    if discrepancy_runs:
        run = discrepancy_runs[0]
        maximum = max(abs(s.airspeed_m_s - s.groundspeed_m_s) for s in run)
        findings.append(Insight(
            "notice", "Persistent airspeed and groundspeed difference", run[0].time_s, run[-1].time_s,
            [f"Difference reached {maximum:.1f} m/s", "Difference persisted for at least 5 s"],
            ["Strong headwind or tailwind", "Pitot-system error", "Airspeed calibration error"],
            "Compare the difference with wind estimates before inspecting the pitot system.", "medium",
        ))

    attitude_runs = _runs(samples, lambda s: abs(s.roll_deg) > 45 or abs(s.pitch_deg) > 30, 1.0)
    if attitude_runs:
        run = attitude_runs[0]
        findings.append(Insight(
            "warning", "Large sustained attitude excursion", run[0].time_s, run[-1].time_s,
            [f"Maximum absolute roll was {max(abs(s.roll_deg) for s in run):.1f}°", f"Maximum absolute pitch was {max(abs(s.pitch_deg) for s in run):.1f}°"],
            ["Aggressive commanded manoeuvre", "Control instability", "Disturbance or incorrect tuning"],
            "Review pilot commands, demanded attitude, and servo outputs over the same interval.", "medium",
        ))

    fast_descent_runs = _runs(
        samples, lambda s: s.armed and s.relative_altitude_m > 10 and s.climb_rate_m_s < -5, 2.0
    )
    if fast_descent_runs:
        run = fast_descent_runs[0]
        findings.append(Insight(
            "warning", "High descent rate", run[0].time_s, run[-1].time_s,
            [f"Peak descent rate was {min(s.climb_rate_m_s for s in run):.1f} m/s", "Vehicle was armed and above 10 m"],
            ["Commanded rapid descent", "Loss of lift or power", "Altitude-estimation disturbance"],
            "Correlate throttle, airspeed, flight mode, and demanded altitude during this period.", "medium",
        ))

    if not any(item.severity in {"critical", "warning"} for item in findings):
        findings.append(Insight(
            "positive", "No major rule-based fault detected", samples[0].time_s, samples[-1].time_s,
            ["No configured critical or warning threshold was exceeded"],
            ["This result is limited to the signals and rules currently implemented"],
            "Continue reviewing plots and expand rules as more aircraft-specific limits become known.", "medium",
        ))

    findings.sort(key=lambda item: (_SEVERITY_ORDER[item.severity], item.start_s))
    if any(item.severity == "critical" for item in findings):
        status = "Critical review required"
    elif any(item.severity == "warning" for item in findings):
        status = "Review recommended"
    else:
        status = "No major issue detected"
    return InsightReport(status, findings, limitations)
