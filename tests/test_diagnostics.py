import unittest

from flightrecorder.diagnostics import analyze_fuel_flow, analyze_gps_health
from flightrecorder.model import FlightSample
from flightrecorder.simulator import generate_flight


class DiagnosticTests(unittest.TestCase):
    def test_simulated_flight_has_fuel_data(self):
        report = analyze_fuel_flow(generate_flight())

        self.assertTrue(report.fuel_data_present)
        self.assertGreater(report.total_used_l, 0)
        self.assertGreater(report.peak_flow_l_h, 0)
        self.assertNotEqual(report.status, "Fuel data unavailable")

    def test_fuel_unavailable_is_explicit(self):
        report = analyze_fuel_flow([FlightSample(time_s=0), FlightSample(time_s=1)])

        self.assertFalse(report.fuel_data_present)
        self.assertEqual(report.status, "Fuel data unavailable")
        self.assertTrue(report.limitations)

    def test_degraded_gps_is_flagged(self):
        samples = [
            FlightSample(time_s=0, gps_fix_type=3, gps_satellites=12, gps_hdop=0.8),
            FlightSample(time_s=1, gps_fix_type=2, gps_satellites=6, gps_hdop=2.4),
        ]

        report = analyze_gps_health(samples)

        self.assertEqual(report.status, "GPS review recommended")
        self.assertTrue(any(item.title == "GPS fix dropped below 3D" for item in report.findings))
        self.assertTrue(any(item.title == "Low satellite count" for item in report.findings))


if __name__ == "__main__":
    unittest.main()
