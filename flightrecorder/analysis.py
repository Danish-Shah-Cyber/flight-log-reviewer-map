from __future__ import annotations

from dataclasses import dataclass

from .model import FlightSample


@dataclass(slots=True)
class FlightEvent:
    time_s: float
    kind: str
    description: str


@dataclass(slots=True)
class FlightSummary:
    duration_s: float
    distance_km: float
    max_altitude_m: float
    max_groundspeed_m_s: float
    max_airspeed_m_s: float
    minimum_battery_pct: float
    events: list[FlightEvent]


def analyze(samples: list[FlightSample]) -> FlightSummary:
    if not samples:
        raise ValueError("At least one sample is required")

    events: list[FlightEvent] = []
    airborne = False
    low_battery_reported = False
    previous = samples[0]
    distance_m = 0.0

    if previous.armed:
        events.append(FlightEvent(previous.time_s, "ARM", "Vehicle armed"))

    for sample in samples[1:]:
        dt = max(0.0, sample.time_s - previous.time_s)
        distance_m += (previous.groundspeed_m_s + sample.groundspeed_m_s) * 0.5 * dt

        if sample.armed != previous.armed:
            label = "Vehicle armed" if sample.armed else "Vehicle disarmed"
            events.append(FlightEvent(sample.time_s, "ARM" if sample.armed else "DISARM", label))
        if sample.mode != previous.mode:
            events.append(FlightEvent(sample.time_s, "MODE", f"Mode changed: {previous.mode} -> {sample.mode}"))

        now_airborne = sample.relative_altitude_m > 3.0 and sample.groundspeed_m_s > 5.0
        if now_airborne and not airborne:
            events.append(FlightEvent(sample.time_s, "TAKEOFF", "Takeoff detected"))
            airborne = True
        elif airborne and sample.relative_altitude_m < 1.0 and sample.groundspeed_m_s < 8.0:
            events.append(FlightEvent(sample.time_s, "LANDING", "Landing detected"))
            airborne = False

        if sample.battery_remaining_pct < 20.0 and not low_battery_reported:
            events.append(FlightEvent(sample.time_s, "WARNING", "Battery below 20%"))
            low_battery_reported = True
        previous = sample

    return FlightSummary(
        duration_s=samples[-1].time_s - samples[0].time_s,
        distance_km=distance_m / 1000.0,
        max_altitude_m=max(sample.relative_altitude_m for sample in samples),
        max_groundspeed_m_s=max(sample.groundspeed_m_s for sample in samples),
        max_airspeed_m_s=max(sample.airspeed_m_s for sample in samples),
        minimum_battery_pct=min(sample.battery_remaining_pct for sample in samples),
        events=events,
    )
