#!/usr/bin/env python3
import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GENERATOR = Path(__file__).resolve().with_name("oreport.py")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from oreport import generate_ppa_charts  # noqa: E402


class HtmlReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "test_project"
        (self.project / "out" / "runs").mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def generate(self):
        result = subprocess.run(
            [sys.executable, str(GENERATOR), str(self.project)],
            text=True, capture_output=True, timeout=15
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        output = self.project / "out" / "report.html"
        self.assertTrue(output.is_file())
        return output.read_text(encoding="utf-8")

    def test_empty_history(self):
        html = self.generate()
        self.assertIn("No saved runs found.", html)
        self.assertIn('id="runFilter"', html)
        self.assertIn("data-sort", html)

    def test_valid_history_and_missing_artifacts(self):
        history = self.project / "out" / "runs.tsv"
        with history.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=["id", "clk_ns", "slack_ns", "power_mW",
                            "area_um2", "util", "drc", "clock_tree"],
                delimiter="\t"
            )
            writer.writeheader()
            writer.writerow({
                "id": "run_5ns", "clk_ns": "5.0", "slack_ns": "-0.2",
                "power_mW": "0.12", "area_um2": "250",
                "util": "4%", "drc": "2", "clock_tree": "2 buffers"
            })
        html = self.generate()
        self.assertIn("run_5ns", html)
        self.assertIn("-0.2", html)
        self.assertIn("2", html)
        self.assertIn("History only", html)
        self.assertIn("VIOLATED", html)

    def test_malformed_manifest_is_tolerated(self):
        run = self.project / "out" / "runs" / "bad_manifest"
        run.mkdir()
        (run / "manifest.json").write_text("{not json", encoding="utf-8")
        (run / "summary.txt").write_text("Test summary", encoding="utf-8")
        html = self.generate()
        self.assertIn("bad_manifest", html)

    def test_manifest_and_summary_are_optional(self):
        run = self.project / "out" / "runs" / "bare_run"
        run.mkdir()
        html = self.generate()
        self.assertIn("bare_run", html)
        self.assertIn("History only", html)

    def test_manifest_values_and_timing_report(self):
        run = self.project / "out" / "runs" / "run_detail"
        reports = run / "reports"
        reports.mkdir(parents=True)
        (run / "manifest.json").write_text(json.dumps({
            "platform": "sky130hd",
            "input_hash": "abc123",
            "env_hash": "env456",
            "openroad": "OpenROAD test",
            "timing_met": False
        }), encoding="utf-8")
        (reports / "6_finish.rpt").write_text(
            "tns max -0.20\nwns max -0.20\n"
            "worst slack max -0.20\n"
            "core_clock period_min = 4.20 fmax = 238.1\n",
            encoding="utf-8"
        )
        html = self.generate()
        self.assertIn("abc123", html)
        self.assertIn("4.20", html)
        self.assertIn("238.1", html)

    def test_run_id_path_traversal_is_ignored(self):
        history = self.project / "out" / "runs.tsv"
        history.write_text(
            "id\tclk_ns\tslack_ns\tpower_mW\tarea_um2\tutil\tdrc\tclock_tree\n"
            "../outside\t5\t0.1\t0.1\t100\t1%\t0\t-\n",
            encoding="utf-8"
        )
        html = self.generate()
        self.assertNotIn("../outside", html)



    def test_chart_generation_with_metrics(self):
        runs = [
            {"run_id": "r1", "clock_period": "5.0", "slack": "0.12", "area": "1200", "power": "0.04"},
            {"run_id": "r2", "clock_period": "4.0", "slack": "-0.05", "area": "1250", "power": "0.05"}
        ]
        charts_html = generate_ppa_charts(runs)
        self.assertIn("PPA Trade-Off Trends", charts_html)
        self.assertIn("polyline", charts_html)
        self.assertIn("circle", charts_html)

    def test_chart_omitted_when_insufficient_data(self):
        runs = [{"run_id": "r1", "clock_period": "5.0", "slack": "0.12"}]
        charts_html = generate_ppa_charts(runs)
        self.assertIn("Insufficient numeric data", charts_html)

    def test_ppa_chart_svg_zero_line(self):
        runs = [
            {"run_id": "r1", "clock_period": "5.0", "slack": "0.12", "area": "100", "power": "1"},
            {"run_id": "r2", "clock_period": "3.0", "slack": "-0.20", "area": "100", "power": "1"}
        ]
        charts_html = generate_ppa_charts(runs)
        self.assertIn("0.0 (slack)", charts_html)

if __name__ == "__main__":
    unittest.main(verbosity=2)
