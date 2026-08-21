from __future__ import annotations

from dataclasses import asdict, dataclass, fields


@dataclass(slots=True)
class FlightSample:
    """One normalized observation.

    Units are deliberately part of the field names. This prevents one of the
    most common telemetry bugs: silently mixing metres, feet, degrees, radians,
    amps, and milliamps.
    """

    time_s: float = 0.0
    latitude_deg: float = 0.0
    longitude_deg: float = 0.0
    relative_altitude_m: float = 0.0
    groundspeed_m_s: float = 0.0
    airspeed_m_s: float = 0.0
    climb_rate_m_s: float = 0.0
    roll_deg: float = 0.0
    pitch_deg: float = 0.0
    yaw_deg: float = 0.0
    throttle_pct: float = 0.0
    battery_voltage_v: float = 0.0
    battery_current_a: float = 0.0
    battery_remaining_pct: float = 100.0
    fuel_flow_l_h: float = 0.0
    fuel_used_l: float = 0.0
    fuel_remaining_pct: float = -1.0
    gps_fix_type: float = 0.0
    gps_satellites: float = 0.0
    gps_hdop: float = 0.0
    source_integrity: str = "verified"
    mode: str = "UNKNOWN"
    armed: bool = False

    @classmethod
    def column_names(cls) -> list[str]:
        return [field.name for field in fields(cls)]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
