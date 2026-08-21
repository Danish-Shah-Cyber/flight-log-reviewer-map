from __future__ import annotations

import math
import struct
from pathlib import Path

from .model import FlightSample


def _read_unsigned_mavlink_v1(path: str | Path) -> list[FlightSample]:
    """Best-effort reader for MAVLink v1 frames with invalid checksums.

    Some exported or synthetic `.tlog` files contain recognizable MAVLink v1
    frames but placeholder checksums. Pymavlink quite rightly rejects those.
    This fallback decodes only a small allow-list of common telemetry messages
    and ignores every other frame.
    """

    data = Path(path).read_bytes()
    state = FlightSample()
    state.source_integrity = "checksum_invalid_recovered"
    samples: list[FlightSample] = []
    first_time_ms: int | None = None
    index = 0

    def valid_position(latitude_deg: float, longitude_deg: float) -> bool:
        return -90.0 <= latitude_deg <= 90.0 and -180.0 <= longitude_deg <= 180.0

    def set_time(time_ms: int) -> None:
        nonlocal first_time_ms
        if first_time_ms is None:
            first_time_ms = time_ms
        state.time_s = max(0.0, (time_ms - first_time_ms) / 1000.0)

    while index < len(data):
        marker = data.find(b"\xfe", index)
        if marker < 0 or marker + 8 > len(data):
            break
        length = data[marker + 1]
        packet_end = marker + 6 + length + 2
        if packet_end > len(data):
            index = marker + 1
            continue
        message_id = data[marker + 5]
        payload = data[marker + 6:marker + 6 + length]
        changed = False

        try:
            if message_id == 33 and len(payload) >= 28:  # GLOBAL_POSITION_INT
                time_ms, lat, lon, _alt, relative_alt, vx, vy, vz, hdg = struct.unpack_from("<IiiiihhhH", payload)
                latitude_deg = lat / 1e7
                longitude_deg = lon / 1e7
                if not valid_position(latitude_deg, longitude_deg):
                    index = packet_end
                    continue
                groundspeed = math.hypot(vx, vy) / 100.0
                if groundspeed > 180.0:
                    index = packet_end
                    continue
                set_time(time_ms)
                state.latitude_deg = latitude_deg
                state.longitude_deg = longitude_deg
                state.relative_altitude_m = relative_alt / 1000.0
                state.groundspeed_m_s = groundspeed
                state.climb_rate_m_s = -vz / 100.0
                if hdg != 65535:
                    state.yaw_deg = hdg / 100.0
                changed = True
            elif message_id == 24 and len(payload) >= 30:  # GPS_RAW_INT
                time_us, fix, lat, lon, _alt, eph, _epv, vel, _cog, satellites = struct.unpack_from(
                    "<QBiiiHHHHB", payload
                )
                latitude_deg = lat / 1e7
                longitude_deg = lon / 1e7
                hdop = eph / 100.0 if eph != 65535 else state.gps_hdop
                if (
                    not valid_position(latitude_deg, longitude_deg)
                    or fix > 6
                    or satellites > 80
                    or hdop > 20.0
                    or (vel != 65535 and vel / 100.0 > 180.0)
                ):
                    index = packet_end
                    continue
                set_time(int(time_us / 1000))
                state.gps_fix_type = float(fix)
                state.latitude_deg = latitude_deg
                state.longitude_deg = longitude_deg
                state.gps_hdop = hdop
                state.groundspeed_m_s = vel / 100.0 if vel != 65535 else state.groundspeed_m_s
                state.gps_satellites = float(satellites)
                changed = True
            elif message_id == 74 and len(payload) >= 20:  # VFR_HUD
                airspeed, groundspeed, _alt, climb, heading, throttle = struct.unpack_from("<ffffhH", payload)
                if (
                    first_time_ms is None
                    or not 0.0 <= airspeed <= 180.0
                    or not 0.0 <= groundspeed <= 180.0
                    or not -100.0 <= climb <= 100.0
                    or throttle > 100
                ):
                    index = packet_end
                    continue
                state.airspeed_m_s = float(airspeed)
                state.groundspeed_m_s = float(groundspeed)
                state.climb_rate_m_s = float(climb)
                state.throttle_pct = float(throttle)
                state.yaw_deg = float(heading) % 360.0
                changed = True
            elif message_id == 30 and len(payload) >= 28:  # ATTITUDE
                time_ms, roll, pitch, yaw, _rollspeed, _pitchspeed, _yawspeed = struct.unpack_from(
                    "<Iffffff", payload
                )
                if not -math.tau <= roll <= math.tau or not -math.tau <= pitch <= math.tau:
                    index = packet_end
                    continue
                set_time(time_ms)
                state.roll_deg = math.degrees(roll)
                state.pitch_deg = math.degrees(pitch)
                state.yaw_deg = math.degrees(yaw) % 360.0
                changed = True
            elif message_id == 0 and len(payload) >= 9:  # HEARTBEAT
                _custom_mode, mav_type, autopilot, base_mode, _system_status, _version = struct.unpack_from(
                    "<IBBBBB", payload
                )
                state.armed = bool(base_mode & 128)
                state.mode = f"TYPE_{mav_type}_AP_{autopilot}"
        except struct.error:
            changed = False

        if changed:
            state.time_s = len(samples) * 0.1
            samples.append(FlightSample(**state.to_dict()))
        index = packet_end

    return samples


def read_tlog(path: str | Path) -> list[FlightSample]:
    """Convert selected Mission Planner MAVLink messages to normalized samples.

    MAVLink messages arrive at different rates. We therefore keep the latest
    value from every message type and emit a snapshot whenever useful telemetry
    arrives. This is called state reconstruction.
    """

    try:
        from pymavlink import mavutil
    except ImportError as error:
        raise RuntimeError(
            "pymavlink is required for .tlog import; run: python -m pip install pymavlink"
        ) from error

    connection = mavutil.mavlink_connection(str(path), robust_parsing=True)
    state = FlightSample()
    samples: list[FlightSample] = []
    first_timestamp: float | None = None
    last_emit_s = -1.0
    useful = {
        "GLOBAL_POSITION_INT",
        "GPS_RAW_INT",
        "VFR_HUD",
        "ATTITUDE",
        "SYS_STATUS",
        "HEARTBEAT",
        "FUEL_STATUS",
        "EFI_STATUS",
    }

    while True:
        message = connection.recv_match(blocking=False)
        if message is None:
            break
        kind = message.get_type()
        if kind == "BAD_DATA" or kind not in useful:
            continue
        timestamp = float(getattr(message, "_timestamp", 0.0))
        if first_timestamp is None:
            first_timestamp = timestamp
        state.time_s = max(0.0, timestamp - first_timestamp)

        changed = False
        if kind == "GLOBAL_POSITION_INT":
            state.latitude_deg = message.lat / 1e7
            state.longitude_deg = message.lon / 1e7
            state.relative_altitude_m = message.relative_alt / 1000.0
            state.groundspeed_m_s = math.hypot(message.vx, message.vy) / 100.0
            state.climb_rate_m_s = -message.vz / 100.0
            if message.hdg != 65535:
                state.yaw_deg = message.hdg / 100.0
            changed = True
        elif kind == "GPS_RAW_INT":
            state.gps_fix_type = float(message.fix_type)
            state.gps_satellites = float(message.satellites_visible)
            if message.eph != 65535:
                state.gps_hdop = message.eph / 100.0
            changed = True
        elif kind == "VFR_HUD":
            state.airspeed_m_s = float(message.airspeed)
            state.groundspeed_m_s = float(message.groundspeed)
            state.throttle_pct = float(message.throttle)
            state.climb_rate_m_s = float(message.climb)
            changed = True
        elif kind == "ATTITUDE":
            state.roll_deg = math.degrees(message.roll)
            state.pitch_deg = math.degrees(message.pitch)
            state.yaw_deg = math.degrees(message.yaw) % 360.0
            changed = True
        elif kind == "SYS_STATUS":
            if message.voltage_battery != 65535:
                state.battery_voltage_v = message.voltage_battery / 1000.0
            if message.current_battery != -1:
                state.battery_current_a = message.current_battery / 100.0
            if message.battery_remaining != -1:
                state.battery_remaining_pct = float(message.battery_remaining)
            changed = True
        elif kind == "HEARTBEAT":
            state.armed = bool(message.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            state.mode = mavutil.mode_string_v10(message)
            changed = True
        elif kind == "FUEL_STATUS":
            if hasattr(message, "consumed_fuel") and message.consumed_fuel >= 0:
                state.fuel_used_l = message.consumed_fuel / 100.0
            if hasattr(message, "fuel_remaining") and message.fuel_remaining >= 0:
                state.fuel_remaining_pct = float(message.fuel_remaining)
            changed = True
        elif kind == "EFI_STATUS":
            if hasattr(message, "fuel_flow"):
                state.fuel_flow_l_h = float(message.fuel_flow) * 3.6
                changed = True

        if changed and (state.time_s - last_emit_s >= 0.1 or not samples):
            samples.append(FlightSample(**state.to_dict()))
            last_emit_s = state.time_s

    if not samples:
        samples = _read_unsigned_mavlink_v1(path)
    if not samples:
        raise ValueError("No supported MAVLink telemetry was found in the .tlog")
    return samples
