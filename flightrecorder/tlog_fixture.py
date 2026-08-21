from __future__ import annotations

import math
import struct
import time
from pathlib import Path


def generate_tlog(path: str | Path, duration_s: int = 120) -> int:
    """Write a small, genuine timestamped MAVLink telemetry log.

    Mission Planner/Pymavlink telemetry logs store an eight-byte timestamp
    before each MAVLink packet. The packet payloads below are normal ArduPlane
    HEARTBEAT, position, attitude, HUD, and battery messages.
    """

    try:
        from pymavlink.dialects.v20 import ardupilotmega as mavlink
    except ImportError as error:
        raise RuntimeError("pymavlink is required to generate a .tlog fixture") from error

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    mav = mavlink.MAVLink(None, srcSystem=1, srcComponent=1)
    start_us = int(time.time() * 1_000_000)
    packet_count = 0

    def write_packet(file, message, timestamp_us: int) -> None:
        nonlocal packet_count
        file.write(struct.pack(">Q", timestamp_us))
        file.write(message.pack(mav))
        packet_count += 1

    with destination.open("wb") as file:
        for second in range(duration_s + 1):
            if second < 10:
                mode, armed, altitude, speed, throttle, climb = 0, second >= 3, 0.0, 2.0, 10, 0.0
            elif second < 35:
                mode, armed = 5, True
                altitude, speed, throttle, climb = (second - 10) * 2.0, 18.0, 80, 2.0
            elif second < 85:
                mode, armed = 10, True
                altitude, speed, throttle, climb = 50.0, 24.0, 52, 0.0
            elif second < 112:
                mode, armed = 11, True
                altitude = max(0.0, 50.0 - (second - 85) * 1.9)
                speed, throttle, climb = 17.0, 28, -1.9
            else:
                mode, armed, altitude = 0, second < 117, 0.0
                speed, throttle, climb = max(0.0, 7.0 - (second - 112)), 5, 0.0

            base_mode = mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
            if armed:
                base_mode |= mavlink.MAV_MODE_FLAG_SAFETY_ARMED
            heading = 60.0 + 8.0 * math.sin(second / 20.0)
            latitude = 33.6844 + second * 0.00008
            longitude = 73.0479 + second * 0.00009
            battery_remaining = max(15, 100 - int(second * 0.65))
            voltage_mv = int(14_800 - second * 12)
            current_ca = int((2.0 + throttle * 0.25) * 100)
            timestamp = start_us + second * 1_000_000

            messages = [
                mav.heartbeat_encode(
                    mavlink.MAV_TYPE_FIXED_WING,
                    mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA,
                    base_mode,
                    mode,
                    mavlink.MAV_STATE_ACTIVE,
                ),
                mav.global_position_int_encode(
                    second * 1000,
                    int(latitude * 1e7),
                    int(longitude * 1e7),
                    int((500.0 + altitude) * 1000),
                    int(altitude * 1000),
                    int(speed * math.cos(math.radians(heading)) * 100),
                    int(speed * math.sin(math.radians(heading)) * 100),
                    int(-climb * 100),
                    int(heading * 100),
                ),
                mav.attitude_encode(
                    second * 1000,
                    math.radians(4.0 * math.sin(second / 7.0)),
                    math.radians(8.0 if climb > 0 else (-4.0 if climb < 0 else 0.0)),
                    math.radians(heading),
                    0.0,
                    0.0,
                    0.0,
                ),
                mav.vfr_hud_encode(speed + 0.5, speed, int(heading), throttle, 500.0 + altitude, climb),
                mav.sys_status_encode(
                    0, 0, 0, 350, voltage_mv, current_ca, battery_remaining,
                    0, 0, 0, 0, 0, 0,
                ),
            ]
            for index, message in enumerate(messages):
                write_packet(file, message, timestamp + index * 1000)
    return packet_count
