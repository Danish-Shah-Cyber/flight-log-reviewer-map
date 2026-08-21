from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Protocol


class TelemetryPoint(Protocol):
    time_s: float
    latitude_deg: float
    longitude_deg: float
    relative_altitude_m: float
    groundspeed_m_s: float
    climb_rate_m_s: float
    mode: str
    armed: bool
    battery_voltage_v: float
    battery_remaining_pct: float
    gps_fix_type: float
    gps_satellites: float
    gps_hdop: float


class ReviewEvent(Protocol):
    time_s: float
    kind: str
    description: str


@dataclass(slots=True)
class RoutePoint:
    time_s: float
    lat: float
    lon: float
    alt_m: float
    relative_alt_m: float
    groundspeed_m_s: float
    vertical_speed_m_s: float
    mode: str
    armed: bool
    battery_voltage_v: float
    battery_remaining_pct: float
    gps_fix_type: float
    gps_satellites: float
    gps_hdop: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class RouteEvent:
    time_s: float
    kind: str
    label: str
    lat: float | None = None
    lon: float | None = None
    alt_m: float | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class RouteArtifact:
    points: list[RoutePoint]
    events: list[RouteEvent]
    source_sample_count: int
    display_sample_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "points": [point.to_dict() for point in self.points],
            "events": [event.to_dict() for event in self.events],
            "source_sample_count": self.source_sample_count,
            "display_sample_count": self.display_sample_count,
        }


def _valid_gps(point: TelemetryPoint) -> bool:
    return (
        -90.0 <= float(point.latitude_deg) <= 90.0
        and -180.0 <= float(point.longitude_deg) <= 180.0
        and not (float(point.latitude_deg) == 0.0 and float(point.longitude_deg) == 0.0)
    )


def _downsample(items: list[TelemetryPoint], limit: int) -> list[TelemetryPoint]:
    if len(items) <= limit:
        return items
    step = max(1, -(-len(items) // limit))
    reduced = items[::step]
    if reduced[-1] is not items[-1]:
        reduced.append(items[-1])
    return reduced


def _nearest_point(points: list[RoutePoint], time_s: float) -> RoutePoint | None:
    if not points:
        return None
    return min(points, key=lambda point: abs(point.time_s - time_s))


def build_route_artifact(
    samples: Iterable[TelemetryPoint],
    events: Iterable[ReviewEvent] = (),
    max_points: int = 12000,
) -> RouteArtifact:
    source_samples = list(samples)
    valid_samples = [sample for sample in source_samples if _valid_gps(sample)]
    display_samples = _downsample(valid_samples, max(1000, max_points))
    route_points = [
        RoutePoint(
            time_s=float(sample.time_s),
            lat=float(sample.latitude_deg),
            lon=float(sample.longitude_deg),
            alt_m=float(sample.relative_altitude_m),
            relative_alt_m=float(sample.relative_altitude_m),
            groundspeed_m_s=float(sample.groundspeed_m_s),
            vertical_speed_m_s=float(sample.climb_rate_m_s),
            mode=str(sample.mode),
            armed=bool(sample.armed),
            battery_voltage_v=float(sample.battery_voltage_v),
            battery_remaining_pct=float(sample.battery_remaining_pct),
            gps_fix_type=float(sample.gps_fix_type),
            gps_satellites=float(sample.gps_satellites),
            gps_hdop=float(sample.gps_hdop),
        )
        for sample in display_samples
    ]
    route_events = []
    for event in events:
        nearest = _nearest_point(route_points, float(event.time_s))
        route_events.append(
            RouteEvent(
                time_s=float(event.time_s),
                kind=str(event.kind),
                label=str(event.description),
                lat=nearest.lat if nearest else None,
                lon=nearest.lon if nearest else None,
                alt_m=nearest.alt_m if nearest else None,
            )
        )
    return RouteArtifact(
        points=route_points,
        events=route_events,
        source_sample_count=len(source_samples),
        display_sample_count=len(route_points),
    )
