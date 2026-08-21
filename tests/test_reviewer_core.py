import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "reviewer-core"))

from flightrecorder.analysis import analyze
from flightrecorder.simulator import generate_flight
from flightreviewer_core import build_route_artifact


class ReviewerCoreTests(unittest.TestCase):
    def test_route_artifact_contains_hover_fields_and_events(self):
        samples = generate_flight(duration_s=90)
        summary = analyze(samples)
        artifact = build_route_artifact(samples, summary.events)
        first = artifact.points[0].to_dict()

        self.assertIn("time_s", first)
        self.assertIn("lat", first)
        self.assertIn("lon", first)
        self.assertIn("groundspeed_m_s", first)
        self.assertIn("relative_alt_m", first)
        self.assertIn("battery_remaining_pct", first)
        self.assertGreater(len(artifact.events), 0)

    def test_route_artifact_downsamples_large_routes(self):
        samples = generate_flight(duration_s=5000)
        artifact = build_route_artifact(samples, max_points=1200)

        self.assertEqual(artifact.source_sample_count, len(samples))
        self.assertLessEqual(artifact.display_sample_count, 1202)


if __name__ == "__main__":
    unittest.main()
