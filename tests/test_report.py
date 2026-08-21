import tempfile
import unittest
from pathlib import Path

from flightrecorder.analysis import analyze
from flightrecorder.insights import generate_insights
from flightrecorder.report import write_html_report
from flightrecorder.simulator import generate_flight


class ReportTests(unittest.TestCase):
    def test_report_includes_route_modes_and_data_explorer(self):
        samples = generate_flight(duration_s=80)
        with tempfile.TemporaryDirectory() as temp_dir:
            report = Path(temp_dir) / "report.html"
            write_html_report(report, samples, analyze(samples), generate_insights(samples))
            document = report.read_text(encoding="utf-8")

        self.assertIn("Route Map", document)
        self.assertIn("Flight Mode Segments", document)
        self.assertIn("All Normalized Data", document)
        self.assertIn("const flightSamples =", document)
        self.assertIn("normalized-flight-data.csv", document)
        self.assertIn("plot-zoom-in", document)
        self.assertIn("plot-zoom-out", document)
        self.assertIn("plot-readout", document)

    def test_report_includes_2d_and_cesium_route_maps(self):
        samples = generate_flight(duration_s=80)
        with tempfile.TemporaryDirectory() as temp_dir:
            report = Path(temp_dir) / "report.html"
            write_html_report(report, samples, analyze(samples), generate_insights(samples))
            document = report.read_text(encoding="utf-8")

        self.assertIn("2D Map", document)
        self.assertIn("Cesium 3D", document)
        self.assertIn("leaflet-route-map", document)
        self.assertIn("cesium-route-map", document)
        self.assertIn("routePopupHtml", document)
        self.assertIn("OpenStreetMapImageryProvider", document)

    def test_report_notes_downsampled_display(self):
        samples = generate_flight(duration_s=12100)
        with tempfile.TemporaryDirectory() as temp_dir:
            report = Path(temp_dir) / "report.html"
            write_html_report(report, samples, analyze(samples), generate_insights(samples))
            document = report.read_text(encoding="utf-8")

        self.assertIn("Display: 6051 of 12101 samples", document)


if __name__ == "__main__":
    unittest.main()
