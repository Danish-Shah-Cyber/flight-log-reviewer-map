import unittest

from flightrecorder.model import FlightSample
from flightrecorder.quality import assess_data_quality
from flightrecorder.simulator import generate_flight


class DataQualityTests(unittest.TestCase):
    def test_simulated_flight_has_high_quality_score(self):
        report = assess_data_quality(generate_flight())

        self.assertGreaterEqual(report.score, 90)
        self.assertEqual(report.grade, "Excellent")
        self.assertFalse(report.warnings)

    def test_missing_signals_are_reported_as_limitations(self):
        report = assess_data_quality([FlightSample(time_s=0), FlightSample(time_s=1)])

        self.assertLess(report.score, 70)
        self.assertEqual(report.grade, "Limited")
        self.assertTrue(any("Missing signals" in item for item in report.limitations))

    def test_gaps_and_impossible_values_reduce_confidence(self):
        samples = [
            FlightSample(time_s=0, latitude_deg=33, longitude_deg=73, battery_voltage_v=12),
            FlightSample(time_s=9, latitude_deg=120, longitude_deg=73, battery_voltage_v=-1),
        ]

        report = assess_data_quality(samples)

        self.assertEqual(report.gap_count, 1)
        self.assertEqual(report.impossible_value_count, 2)
        self.assertTrue(report.warnings)


if __name__ == "__main__":
    unittest.main()
