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
        self.assertIn('svg.addEventListener("wheel"', document)
        self.assertIn('svg.addEventListener("pointerdown"', document)

    def test_report_includes_professional_review_modules(self):
        samples = generate_flight(duration_s=80)
        with tempfile.TemporaryDirectory() as temp_dir:
            report = Path(temp_dir) / "report.html"
            write_html_report(report, samples, analyze(samples), generate_insights(samples))
            document = report.read_text(encoding="utf-8")

        self.assertIn("Home", document)
        self.assertIn("Parameters", document)
        self.assertIn("Timestamped Messages", document)
        self.assertIn("RCIN / Manual Inputs", document)
        self.assertIn("RCOUT / Actuator Outputs", document)
        self.assertIn("Custom Graph Builder", document)
        self.assertIn("PID Review", document)
        self.assertIn("AI Report", document)
        self.assertIn("showModule", document)

    def test_report_includes_2d_and_cesium_route_maps(self):
        samples = generate_flight(duration_s=80)
        with tempfile.TemporaryDirectory() as temp_dir:
            report = Path(temp_dir) / "report.html"
            write_html_report(report, samples, analyze(samples), generate_insights(samples))
            document = report.read_text(encoding="utf-8")

        self.assertIn("2D Map", document)
        self.assertIn("Cesium 3D", document)
        self.assertIn("canvas-route-map", document)
        self.assertIn("leaflet-route-map", document)
        self.assertIn("cesium-route-map", document)
        self.assertIn("route-3d-fallback", document)
        self.assertIn("route-static-map", document)
        self.assertIn("Altitude-projected route", document)
        self.assertIn("initCanvasRoute", document)
        self.assertIn("routePopupHtml", document)
        self.assertIn("CESIUM_BASE_URL", document)
        self.assertIn("loadScriptWithFallback", document)
        self.assertIn("UrlTemplateImageryProvider", document)
        self.assertIn("loadMapLibraries", document)

    def test_report_notes_downsampled_display(self):
        samples = generate_flight(duration_s=12100)
        with tempfile.TemporaryDirectory() as temp_dir:
            report = Path(temp_dir) / "report.html"
            write_html_report(report, samples, analyze(samples), generate_insights(samples))
            document = report.read_text(encoding="utf-8")

        self.assertIn("Display: 6051 of 12101 samples", document)


if __name__ == "__main__":
    unittest.main()
