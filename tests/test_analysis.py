import unittest

from flightrecorder.analysis import analyze
from flightrecorder.simulator import generate_flight


class AnalysisTests(unittest.TestCase):
    def test_simulated_flight_has_takeoff_and_landing(self):
        summary = analyze(generate_flight())
        event_types = [event.kind for event in summary.events]
        self.assertIn("TAKEOFF", event_types)
        self.assertIn("LANDING", event_types)
        self.assertGreater(summary.distance_km, 1.0)
        self.assertGreater(summary.max_altitude_m, 70.0)

    def test_simulation_is_repeatable(self):
        first = generate_flight(seed=7)
        second = generate_flight(seed=7)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
