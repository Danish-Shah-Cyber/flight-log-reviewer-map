from __future__ import annotations

import math
from pathlib import Path

from .model import FlightSample


def _value(message, *names, default=None):
    for name in names:
        if hasattr(message, name):
            return getattr(message, name)
    return default


def read_bin(path: str | Path) -> list[FlightSample]:
    """Read common ArduPilot DataFlash messages from an onboard `.BIN` log.

    DataFlash fields differ slightly among vehicle and firmware versions, so
    aliases are intentionally handled here. Unsupported messages are ignored;
    the report's data-quality section identifies absent signal families.
    """

    try:
        from pymavlink import mavutil
    except ImportError as error:
        raise RuntimeError("pymavlink is required for .BIN import") from error

    connection = mavutil.mavlink_connection(str(path), robust_parsing=True)
    state = FlightSample()
    samples: list[FlightSample] = []
    first_time_s: float | None = None
    last_emit_s = -1.0

    while True:
        message = connection.recv_match(blocking=False)
        if message is None:
            break
        kind = message.get_type()
        if kind in {"BAD_DATA", "FMT", "FMTU", "UNIT", "MULT", "PARM"}:
            continue

        time_us = _value(message, "TimeUS")
        time_ms = _value(message, "TimeMS")
        absolute_s = float(time_us) / 1e6 if time_us is not None else (
            float(time_ms) / 1e3 if time_ms is not None else None
        )
        if absolute_s is None:
            continue
        if first_time_s is None:
            first_time_s = absolute_s
        state.time_s = max(0.0, absolute_s - first_time_s)

        changed = False
        if kind.startswith("GPS"):
            lat = _value(message, "Lat")
            lng = _value(message, "Lng", "Lon")
            if lat is not None and lng is not None:
                state.latitude_deg = float(lat)
                state.longitude_deg = float(lng)
            speed = _value(message, "Spd", "GSpd")
            if speed is not None:
                state.groundspeed_m_s = float(speed)
            fix = _value(message, "Status", "Fix", "FixType")
            satellites = _value(message, "NSats", "Sats", "Satellites")
            hdop = _value(message, "HDop", "HDOP", "Hdop")
            if fix is not None:
                state.gps_fix_type = float(fix)
            if satellites is not None:
                state.gps_satellites = float(satellites)
            if hdop is not None:
                value = float(hdop)
                state.gps_hdop = value / 100.0 if value > 20.0 else value
            changed = True
        elif kind == "ATT":
            state.roll_deg = float(_value(message, "Roll", default=state.roll_deg))
            state.pitch_deg = float(_value(message, "Pitch", default=state.pitch_deg))
            state.yaw_deg = float(_value(message, "Yaw", default=state.yaw_deg))
            changed = True
        elif kind in {"BARO", "CTUN"}:
            altitude = _value(message, "Alt", "RelAlt")
            if altitude is not None:
                state.relative_altitude_m = float(altitude)
            climb = _value(message, "CRt", "Climb")
            if climb is not None:
                # CTUN CRt is commonly centimetres/second; BARO climb is m/s.
                state.climb_rate_m_s = float(climb) / (100.0 if kind == "CTUN" else 1.0)
            airspeed = _value(message, "Aspd", "AirSpeed")
            if airspeed is not None:
                value = float(airspeed)
                state.airspeed_m_s = value / 100.0 if abs(value) > 100 else value
            throttle = _value(message, "ThO", "ThrOut")
            if throttle is not None:
                value = float(throttle)
                state.throttle_pct = value / 10.0 if abs(value) > 100 else value
            changed = True
        elif kind in {"BAT", "BCL"}:
            voltage = _value(message, "Volt", "V")
            current = _value(message, "Curr", "I")
            remaining = _value(message, "RemPct", "Remaining")
            if voltage is not None:
                state.battery_voltage_v = float(voltage)
            if current is not None:
                state.battery_current_a = float(current)
            if remaining is not None:
                state.battery_remaining_pct = float(remaining)
            changed = True
        elif kind in {"FUEL", "EFI", "EFI2"}:
            flow = _value(message, "Flow", "FuelFlow", "fuel_flow", "FFlow")
            used = _value(message, "Used", "FuelUsed", "consumed_fuel", "Tot")
            remaining = _value(message, "RemPct", "Remaining", "FuelRemaining")
            if flow is not None:
                value = float(flow)
                state.fuel_flow_l_h = value * 3.6 if 0.0 < value < 10.0 else value
            if used is not None:
                value = float(used)
                state.fuel_used_l = value / 1000.0 if value > 100.0 else value
            if remaining is not None:
                state.fuel_remaining_pct = float(remaining)
            changed = True
        elif kind == "MODE":
            state.mode = str(_value(message, "Mode", "ModeNum", default="UNKNOWN"))
            changed = True
        elif kind in {"ARM", "EV"}:
            arm_state = _value(message, "ArmState", "Armed")
            if arm_state is not None:
                state.armed = bool(arm_state)
                changed = True

        # Limit snapshots to about 10 Hz while preserving the latest merged state.
        if changed and (state.time_s - last_emit_s >= 0.1 or not samples):
            samples.append(FlightSample(**state.to_dict()))
            last_emit_s = state.time_s

    if not samples:
        raise ValueError("No supported ArduPilot flight data was found in the .BIN log")
    return samples
