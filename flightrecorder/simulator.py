from __future__ import annotations

import math
import random

from .model import FlightSample


def generate_flight(duration_s: int = 240, seed: int = 42) -> list[FlightSample]:
    """Generate taxi, climb, cruise, descent, and landing phases."""

    rng = random.Random(seed)
    samples: list[FlightSample] = []
    latitude = 33.6844
    longitude = 73.0479
    battery_pct = 100.0
    fuel_used_l = 0.0

    for second in range(duration_s + 1):
        if second < 20:  # idle and taxi
            mode, armed = "MANUAL", second >= 5
            altitude, speed, throttle, climb = 0.0, max(0.0, second - 8) * 0.35, 12.0, 0.0
        elif second < 60:  # takeoff and climb
            mode, armed = "FBWA", True
            altitude = (second - 20) * 2.0
            speed, throttle, climb = 17.0, 82.0, 2.0
        elif second < 170:  # cruise
            mode, armed = "AUTO", True
            altitude = 80.0 + 2.0 * math.sin(second / 12)
            speed, throttle, climb = 23.0, 52.0, 0.15 * math.sin(second / 8)
        elif second < 225:  # descent
            mode, armed = "RTL", True
            altitude = max(0.0, 80.0 - (second - 170) * 1.45)
            speed, throttle, climb = 18.0, 30.0, -1.45
        else:  # rollout and disarm
            mode = "MANUAL"
            armed = second < 235
            altitude = 0.0
            speed = max(0.0, 12.0 - (second - 225) * 1.2)
            throttle, climb = 5.0, 0.0

        noisy_speed = max(0.0, speed + rng.gauss(0, 0.35))
        heading_deg = 55.0 + 12.0 * math.sin(second / 30)
        distance_m = noisy_speed
        latitude += (distance_m * math.cos(math.radians(heading_deg))) / 111_111
        longitude += (distance_m * math.sin(math.radians(heading_deg))) / (
            111_111 * math.cos(math.radians(latitude))
        )
        current_a = 1.5 + throttle * 0.28
        battery_pct = max(0.0, battery_pct - current_a / 360.0)
        fuel_flow_l_h = 0.4 + throttle * 0.035 if armed else 0.0
        fuel_used_l += fuel_flow_l_h / 3600.0
        fuel_remaining_pct = max(0.0, 100.0 - fuel_used_l / 2.5 * 100.0)

        samples.append(
            FlightSample(
                time_s=float(second),
                latitude_deg=latitude,
                longitude_deg=longitude,
                relative_altitude_m=max(0.0, altitude + rng.gauss(0, 0.25)),
                groundspeed_m_s=noisy_speed,
                airspeed_m_s=max(0.0, noisy_speed + rng.gauss(0, 0.5)),
                climb_rate_m_s=climb + rng.gauss(0, 0.08),
                roll_deg=4.0 * math.sin(second / 8),
                pitch_deg=8.0 if climb > 1 else (-4.0 if climb < -1 else 0.5),
                yaw_deg=heading_deg,
                throttle_pct=throttle,
                battery_voltage_v=14.8 - (100.0 - battery_pct) * 0.018,
                battery_current_a=current_a,
                battery_remaining_pct=battery_pct,
                fuel_flow_l_h=fuel_flow_l_h,
                fuel_used_l=fuel_used_l,
                fuel_remaining_pct=fuel_remaining_pct,
                gps_fix_type=3.0,
                gps_satellites=14.0 + rng.choice([-1.0, 0.0, 1.0]),
                gps_hdop=0.75 + abs(rng.gauss(0, 0.08)),
                mode=mode,
                armed=armed,
            )
        )
    return samples
