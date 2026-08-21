from __future__ import annotations

from dataclasses import dataclass, field

from .model import FlightSample


@dataclass(slots=True)
class SignalQuality:
    name: str
    present: bool
    coverage_pct: float
    sample_count: int
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DataQualityReport:
    score: float
    grade: str
    signals: list[SignalQuality]
    warnings: list[str]
    limitations: list[str]
    gap_count: int
    longest_gap_s: float
    duplicate_timestamp_count: int
    out_of_order_timestamp_count: int
    impossible_value_count: int


def _is_present(sample: FlightSample, field_name: str) -> bool:
    value = getattr(sample, field_name)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return bool(value and value != "UNKNOWN")
    if field_name == "fuel_remaining_pct":
        return 0.0 <= float(value) <= 100.0
    return float(value) != 0.0


def _signal_quality(samples: list[FlightSample], name: str, fields: tuple[str, ...]) -> SignalQuality:
    present_rows = 0
    for sample in samples:
        if any(_is_present(sample, field_name) for field_name in fields):
            present_rows += 1
    coverage = present_rows / len(samples) * 100.0
    notes: list[str] = []
    if coverage == 0:
        notes.append("No usable samples found")
    elif coverage < 50:
        notes.append("Sparse signal coverage")
    elif coverage < 90:
        notes.append("Partial signal coverage")
    return SignalQuality(name, coverage > 0, coverage, present_rows, notes)


def assess_data_quality(samples: list[FlightSample]) -> DataQualityReport:
    if not samples:
        raise ValueError("At least one sample is required")

    signals = [
        _signal_quality(samples, "GPS position", ("latitude_deg", "longitude_deg")),
        _signal_quality(samples, "Altitude", ("relative_altitude_m",)),
        _signal_quality(samples, "Ground speed", ("groundspeed_m_s",)),
        _signal_quality(samples, "Airspeed", ("airspeed_m_s",)),
        _signal_quality(samples, "Attitude", ("roll_deg", "pitch_deg", "yaw_deg")),
        _signal_quality(samples, "Battery", ("battery_voltage_v", "battery_current_a")),
        _signal_quality(samples, "Fuel", ("fuel_flow_l_h", "fuel_used_l", "fuel_remaining_pct")),
        _signal_quality(samples, "GPS health", ("gps_fix_type", "gps_satellites", "gps_hdop")),
        _signal_quality(samples, "Mode", ("mode",)),
        _signal_quality(samples, "Arming state", ("armed",)),
    ]

    gaps = [
        right.time_s - left.time_s
        for left, right in zip(samples, samples[1:])
        if right.time_s - left.time_s > 2.5
    ]
    duplicate_timestamp_count = sum(
        1 for left, right in zip(samples, samples[1:]) if right.time_s == left.time_s
    )
    out_of_order_timestamp_count = sum(
        1 for left, right in zip(samples, samples[1:]) if right.time_s < left.time_s
    )

    impossible_value_count = 0
    for sample in samples:
        if not -90.0 <= sample.latitude_deg <= 90.0:
            impossible_value_count += 1
        if not -180.0 <= sample.longitude_deg <= 180.0:
            impossible_value_count += 1
        if sample.relative_altitude_m < -20.0:
            impossible_value_count += 1
        if sample.groundspeed_m_s < 0.0 or sample.groundspeed_m_s > 180.0:
            impossible_value_count += 1
        if sample.airspeed_m_s < 0.0 or sample.airspeed_m_s > 180.0:
            impossible_value_count += 1
        if sample.battery_voltage_v < 0.0 or sample.battery_current_a < 0.0:
            impossible_value_count += 1
        if not 0.0 <= sample.battery_remaining_pct <= 100.0:
            impossible_value_count += 1
        if sample.fuel_flow_l_h < 0.0 or sample.fuel_used_l < 0.0:
            impossible_value_count += 1
        if sample.fuel_remaining_pct > 100.0:
            impossible_value_count += 1
        if sample.gps_fix_type < 0.0 or sample.gps_satellites < 0.0 or sample.gps_hdop < 0.0:
            impossible_value_count += 1

    warnings: list[str] = []
    limitations: list[str] = []
    missing_signals = [signal.name for signal in signals if not signal.present]
    if missing_signals:
        limitations.append("Missing signals: " + ", ".join(missing_signals))
    if gaps:
        warnings.append(f"{len(gaps)} telemetry gap(s), longest {max(gaps):.1f} s")
    if duplicate_timestamp_count:
        warnings.append(f"{duplicate_timestamp_count} duplicate timestamp(s)")
    if out_of_order_timestamp_count:
        warnings.append(f"{out_of_order_timestamp_count} out-of-order timestamp(s)")
    if impossible_value_count:
        warnings.append(f"{impossible_value_count} impossible value(s) detected")
    recovered_count = sum(1 for sample in samples if sample.source_integrity != "verified")
    if recovered_count:
        warnings.append(f"{recovered_count} sample(s) came from checksum-invalid recovery")

    coverage_score = sum(signal.coverage_pct for signal in signals) / len(signals)
    penalty = (
        min(30.0, len(gaps) * 3.0)
        + min(15.0, duplicate_timestamp_count * 2.0)
        + min(20.0, out_of_order_timestamp_count * 5.0)
        + min(30.0, impossible_value_count * 2.0)
        + min(25.0, recovered_count / len(samples) * 25.0)
    )
    score = max(0.0, min(100.0, coverage_score - penalty))
    if score >= 95:
        grade = "Excellent"
    elif score >= 85:
        grade = "Good"
    elif score >= 70:
        grade = "Review"
    else:
        grade = "Limited"

    return DataQualityReport(
        score=score,
        grade=grade,
        signals=signals,
        warnings=warnings,
        limitations=limitations,
        gap_count=len(gaps),
        longest_gap_s=max(gaps) if gaps else 0.0,
        duplicate_timestamp_count=duplicate_timestamp_count,
        out_of_order_timestamp_count=out_of_order_timestamp_count,
        impossible_value_count=impossible_value_count,
    )
