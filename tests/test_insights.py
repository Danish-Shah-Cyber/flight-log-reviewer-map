import unittest

from flightrecorder.insights import generate_insights
from flightrecorder.model import FlightSample
from flightrecorder.simulator import generate_flight


class InsightTests(unittest.TestCase):
    def test_healthy_flight_has_no_warning(self):
        report = generate_insights(generate_flight())
        self.assertFalse(any(item.severity == "critical" for item in report.findings))

    def test_low_battery_is_detected(self):
        samples = [FlightSample(time_s=float(i), armed=True, battery_remaining_pct=100 - i * 10) for i in range(10)]
        report = generate_insights(samples)
        self.assertTrue(any(item.title == "Low estimated battery remaining" for item in report.findings))
        self.assertEqual(report.status, "Critical review required")

    def test_telemetry_gap_is_reported(self):
        samples = [FlightSample(time_s=0), FlightSample(time_s=1), FlightSample(time_s=8)]
        report = generate_insights(samples)
        self.assertTrue(any(item.title == "Telemetry recording gaps" for item in report.findings))


if __name__ == "__main__":
    unittest.main()
