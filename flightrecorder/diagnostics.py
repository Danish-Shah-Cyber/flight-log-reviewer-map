from __future__ import annotations

from dataclasses import dataclass, field

from .model import FlightSample


@dataclass(slots=True)
class DiagnosticFinding:
    severity: str
    title: str
    evidence: list[str]
    recommendation: str


@dataclass(slots=True)
class FuelFlowReport:
    status: str
    fuel_data_present: bool
    total_used_l: float
    peak_flow_l_h: float
    average_flow_l_h: float
    estimated_endurance_min: float
    findings: list[DiagnosticFinding] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GpsHealthReport:
    status: str
    gps_health_present: bool
    minimum_fix_type: float
    minimum_satellites: float
    maximum_hdop: float
    findings: list[DiagnosticFinding] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


def _positive_values(samples: list[FlightSample], field_name: str) -> list[float]:
    return [float(getattr(sample, field_name)) for sample in samples if float(getattr(sample, field_name)) > 0.0]


def analyze_fuel_flow(samples: list[FlightSample]) -> FuelFlowReport:
    if not samples:
        raise ValueError("At least one sample is required")

    flow_values = _positive_values(samples, "fuel_flow_l_h")
    used_values = _positive_values(samples, "fuel_used_l")
    remaining_values = [
        sample.fuel_remaining_pct
        for sample in samples
        if 0.0 <= sample.fuel_remaining_pct <= 100.0
    ]
    findings: list[DiagnosticFinding] = []
    limitations: list[str] = []

    if not flow_values and not used_values and not remaining_values:
        return FuelFlowReport(
            status="Fuel data unavailable",
            fuel_data_present=False,
            total_used_l=0.0,
            peak_flow_l_h=0.0,
            average_flow_l_h=0.0,
            estimated_endurance_min=0.0,
            limitations=["No fuel-flow, fuel-used, or fuel-remaining signal was recorded."],
        )

    total_used_l = max(used_values) if used_values else 0.0
    peak_flow_l_h = max(flow_values) if flow_values else 0.0
    average_flow_l_h = sum(flow_values) / len(flow_values) if flow_values else 0.0
    estimated_endurance_min = 0.0
    if remaining_values and average_flow_l_h > 0.0 and total_used_l > 0.0:
        used_pct = max(0.1, 100.0 - remaining_values[-1])
        estimated_capacity_l = total_used_l / used_pct * 100.0
        remaining_l = max(0.0, estimated_capacity_l - total_used_l)
        estimated_endurance_min = remaining_l / average_flow_l_h * 60.0

    if flow_values:
        high_flow = [value for value in flow_values if value > average_flow_l_h * 1.8 and value > 0.5]
        if high_flow:
            findings.append(DiagnosticFinding(
                "warning",
                "Fuel-flow spikes",
                [f"{len(high_flow)} sample(s) exceeded 180% of average flow", f"Peak flow was {peak_flow_l_h:.2f} L/h"],
                "Check sensor plumbing, pulse calibration, and engine throttle correlation.",
            ))

        zero_while_armed = [
            sample for sample in samples
            if sample.armed and sample.throttle_pct > 20.0 and sample.fuel_flow_l_h == 0.0
        ]
        if len(zero_while_armed) > max(3, len(samples) * 0.05):
            findings.append(DiagnosticFinding(
                "warning",
                "Fuel-flow dropout while powered",
                [f"{len(zero_while_armed)} armed sample(s) had throttle but zero fuel flow"],
                "Inspect fuel-flow sensor wiring, pulse capture, and logging rate.",
            ))
    else:
        limitations.append("No instantaneous fuel-flow rate was recorded.")

    if not used_values:
        limitations.append("No cumulative fuel-used signal was recorded.")
    if not remaining_values:
        limitations.append("No fuel-remaining estimate was recorded.")

    if any(item.severity == "warning" for item in findings):
        status = "Fuel review recommended"
    elif limitations:
        status = "Fuel data partial"
    else:
        status = "Fuel data looks consistent"

    return FuelFlowReport(
        status=status,
        fuel_data_present=True,
        total_used_l=total_used_l,
        peak_flow_l_h=peak_flow_l_h,
        average_flow_l_h=average_flow_l_h,
        estimated_endurance_min=estimated_endurance_min,
        findings=findings,
        limitations=limitations,
    )


def analyze_gps_health(samples: list[FlightSample]) -> GpsHealthReport:
    if not samples:
        raise ValueError("At least one sample is required")

    fix_values = _positive_values(samples, "gps_fix_type")
    satellite_values = _positive_values(samples, "gps_satellites")
    hdop_values = _positive_values(samples, "gps_hdop")
    findings: list[DiagnosticFinding] = []
    limitations: list[str] = []

    if not fix_values and not satellite_values and not hdop_values:
        return GpsHealthReport(
            status="GPS health unavailable",
            gps_health_present=False,
            minimum_fix_type=0.0,
            minimum_satellites=0.0,
            maximum_hdop=0.0,
            limitations=["GPS fix type, satellite count, and HDOP were not recorded."],
        )

    minimum_fix_type = min(fix_values) if fix_values else 0.0
    minimum_satellites = min(satellite_values) if satellite_values else 0.0
    maximum_hdop = max(hdop_values) if hdop_values else 0.0

    if fix_values and minimum_fix_type < 3:
        findings.append(DiagnosticFinding(
            "warning",
            "GPS fix dropped below 3D",
            [f"Minimum fix type was {minimum_fix_type:.0f}"],
            "Review GPS placement, sky view, and failsafe behaviour around the drop.",
        ))
    if satellite_values and minimum_satellites < 8:
        findings.append(DiagnosticFinding(
            "warning",
            "Low satellite count",
            [f"Minimum satellite count was {minimum_satellites:.0f}"],
            "Check antenna placement and compare the interval with GPS position jumps.",
        ))
    if hdop_values and maximum_hdop > 2.0:
        findings.append(DiagnosticFinding(
            "notice",
            "High GPS dilution of precision",
            [f"Maximum HDOP was {maximum_hdop:.2f}"],
            "Treat position-derived conclusions with reduced confidence during high-HDOP intervals.",
        ))

    if not fix_values:
        limitations.append("GPS fix type was not recorded.")
    if not satellite_values:
        limitations.append("GPS satellite count was not recorded.")
    if not hdop_values:
        limitations.append("GPS HDOP was not recorded.")

    if any(item.severity == "warning" for item in findings):
        status = "GPS review recommended"
    elif findings:
        status = "GPS caution"
    elif limitations:
        status = "GPS health partial"
    else:
        status = "GPS health looks good"

    return GpsHealthReport(
        status=status,
        gps_health_present=True,
        minimum_fix_type=minimum_fix_type,
        minimum_satellites=minimum_satellites,
        maximum_hdop=maximum_hdop,
        findings=findings,
        limitations=limitations,
    )
