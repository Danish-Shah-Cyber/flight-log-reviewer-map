# Cesium Map Design

## Goal

Show the actual drone route over both a fast 2D map and a professional 3D
globe/map so reviewers can see where the aircraft flew, how altitude changed,
which mode it was in, and where important events occurred.

## Why Cesium

CesiumJS is built for real-world 3D geospatial visualization. It supports
imagery, terrain, camera controls, entities, polylines, and marker overlays. For
flight review, that makes it suitable for:

- Seeing the path over satellite imagery or terrain.
- Viewing altitude changes in 3D.
- Coloring route segments by flight mode.
- Marking takeoff, landing, RTL, failsafe, GPS issues, and warnings.
- Synchronizing map position with engineering plots.

## 2D And 3D Map Modes

The review page should include both:

- `2D Map`: fast top-down route inspection, best for checking lateral path,
  mission shape, geofence behavior, waypoint progress, and location redaction.
- `3D Map`: Cesium globe/terrain inspection, best for understanding altitude,
  terrain clearance, climb/descent behavior, and real-world context.

The two modes should share the same route artifact, mode colors, selected
timestamp, markers, and hover details. Switching between 2D and 3D must not
reset the selected point.

## Token Model

Cesium ion imagery/terrain requires an access token for production use. The app
should read it from an environment variable:

```text
CESIUM_ION_TOKEN=...
```

Rules:

- Never commit a token.
- Use a URL-restricted public client token for hosted deployments.
- Allow local development without terrain/imagery by falling back to a basic
  map/route view.

## Route Rendering

The backend should produce a route artifact with time, latitude, longitude,
altitude, mode, arm state, speed, battery, and event metadata. The frontend
should:

1. Filter invalid GPS points.
2. Downsample very long routes.
3. Split points into segments whenever flight mode changes.
4. Convert each segment to Cesium positions.
5. Draw each segment as a polyline with a mode color.
6. Add start and end markers.
7. Add event markers for takeoff, landing, failsafe, warnings, and mode changes.
8. Fit the camera to the route.

## Hover And Click Details

Hovering over the route should show an inspector tooltip for the nearest route
point. Clicking should pin that point and synchronize the rest of the dashboard.

The tooltip should show:

- Time from log start
- Latitude and longitude
- Absolute altitude and relative altitude
- Ground speed
- Vertical speed or climb rate
- Flight mode
- Armed/disarmed state
- Battery voltage and battery remaining when available
- GPS fix type, satellites, and HDOP when available
- Nearest event, warning, or finding near that timestamp

Interaction rules:

- Hovering a path point moves the map cursor and highlights the nearest point.
- Clicking pins the tooltip open.
- Hover/click updates the selected timestamp used by charts and timeline.
- Hovering a plot point should highlight the corresponding route point on both
  2D and 3D maps.
- Clicking a finding should move the map to that finding's location/time when
  GPS is available.

## Frontend Component Sketch

```tsx
import { useEffect, useRef } from "react";
import {
  Cartesian3,
  Color,
  Ion,
  Viewer,
} from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";

type RoutePoint = {
  time_s: number;
  lat: number;
  lon: number;
  alt_m?: number;
  relative_alt_m?: number;
  mode: string;
  armed: boolean;
  groundspeed_m_s?: number;
  battery_remaining_pct?: number;
};

type Props = {
  points: RoutePoint[];
  cesiumIonToken?: string;
};

export function CesiumRouteMap({ points, cesiumIonToken }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!containerRef.current || points.length < 2) return;
    if (cesiumIonToken) Ion.defaultAccessToken = cesiumIonToken;

    const viewer = new Viewer(containerRef.current, {
      timeline: false,
      animation: false,
      geocoder: false,
      homeButton: false,
      sceneModePicker: true,
      baseLayerPicker: true,
    });

    const valid = points.filter((point) =>
      Number.isFinite(point.lat) &&
      Number.isFinite(point.lon) &&
      Math.abs(point.lat) <= 90 &&
      Math.abs(point.lon) <= 180
    );

    const modeColors: Record<string, Color> = {};
    const palette = [Color.CYAN, Color.LIME, Color.ORANGE, Color.MAGENTA, Color.RED];

    let currentMode = valid[0]?.mode;
    let segment: RoutePoint[] = [];

    function colorForMode(mode: string) {
      if (!modeColors[mode]) {
        modeColors[mode] = palette[Object.keys(modeColors).length % palette.length];
      }
      return modeColors[mode];
    }

    function addSegment(segmentPoints: RoutePoint[]) {
      if (segmentPoints.length < 2) return;
      viewer.entities.add({
        name: segmentPoints[0].mode,
        polyline: {
          positions: segmentPoints.map((point) =>
            Cartesian3.fromDegrees(point.lon, point.lat, point.alt_m ?? point.relative_alt_m ?? 0)
          ),
          width: 4,
          material: colorForMode(segmentPoints[0].mode),
        },
      });
    }

    for (const point of valid) {
      if (point.mode !== currentMode) {
        addSegment(segment);
        segment = segment.slice(-1);
        currentMode = point.mode;
      }
      segment.push(point);
    }
    addSegment(segment);

    const first = valid[0];
    const last = valid[valid.length - 1];
    viewer.entities.add({
      name: "Start",
      position: Cartesian3.fromDegrees(first.lon, first.lat, first.alt_m ?? 0),
      point: { pixelSize: 10, color: Color.LIME },
    });
    viewer.entities.add({
      name: "End",
      position: Cartesian3.fromDegrees(last.lon, last.lat, last.alt_m ?? 0),
      point: { pixelSize: 10, color: Color.RED },
    });

    viewer.zoomTo(viewer.entities);
    return () => viewer.destroy();
  }, [points, cesiumIonToken]);

  return <div ref={containerRef} className="cesium-route-map" />;
}
```

## UX Requirements

- The map should occupy a large review panel, not a tiny preview card.
- A clear 2D/3D segmented control should switch map modes.
- The mode legend must match the timeline colors.
- Clicking a route point should move plot cursors to the same timestamp.
- Clicking a finding should fly the map to that finding's time/location when GPS
  is available.
- Shared reports should clearly indicate when location has been redacted.

## Fallback

If Cesium cannot load or no token is configured, show:

- A static SVG/Canvas route plot.
- Start/end coordinates.
- Mode segment table.
- A message explaining that 3D map imagery is unavailable.
