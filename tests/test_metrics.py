"""Tests for the generic ngspice metric evaluator."""

from __future__ import annotations

import math
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from metrics import compare, evaluate  # noqa: E402
from ngspice_raw import Plot  # noqa: E402
import verify  # noqa: E402


def ac_plot(gains: list[complex], frequencies: list[float], input_value: complex = 1.0) -> Plot:
    return Plot(
        name="AC Analysis",
        flags={"complex"},
        variables=["frequency", "v(in)", "v(out)"],
        types=["frequency", "voltage", "voltage"],
        points=[[f, input_value, gain] for f, gain in zip(frequencies, gains)],
    )


def logspace(start: float, stop: float, points: int) -> list[float]:
    return [10.0 ** (math.log10(start) + i * (math.log10(stop) - math.log10(start)) / (points - 1))
            for i in range(points)]


class TestMetrics(unittest.TestCase):
    def test_gain_db_at_frequency(self):
        plots = {"AC Analysis": ac_plot([0.5 + 0j, 0.25 + 0j], [100.0, 1000.0])}
        results, errors = evaluate(
            {"metrics": [{"measure": "gain_db", "output": "v(out)",
                          "input": "v(in)", "frequency": 1000.0}]},
            plots, "")
        self.assertFalse(errors)
        self.assertAlmostEqual(results[0].value, -12.041199826, places=6)

    def test_low_pass_upper_corner(self):
        fc = 1000.0
        frequencies = logspace(0.1, 1e5, 250)
        gains = [1.0 / math.sqrt(1.0 + (f / fc) ** 2) for f in frequencies]
        plots = {"AC Analysis": ac_plot(gains, frequencies)}
        results, errors = evaluate(
            {"metrics": [{"measure": "bandwidth_hz", "output": "v(out)",
                          "input": "v(in)"}]},
            plots, "")
        self.assertFalse(errors)
        expected = fc * math.sqrt(10.0 ** 0.3 - 1.0)
        self.assertAlmostEqual(results[0].value, expected, delta=1.0)

    def test_high_pass_lower_corner(self):
        fc = 1000.0
        frequencies = logspace(0.1, 1e6, 250)
        gains = [(f / fc) / math.sqrt(1.0 + (f / fc) ** 2) for f in frequencies]
        plots = {"AC Analysis": ac_plot(gains, frequencies)}
        results, errors = evaluate(
            {"metrics": [{"measure": "bandwidth_low_hz", "output": "v(out)",
                          "input": "v(in)"}]},
            plots, "")
        self.assertFalse(errors)
        expected = fc / math.sqrt(10.0 ** 0.3 - 1.0)
        self.assertAlmostEqual(results[0].value, expected, delta=1.0)

    def test_bandwidth_uses_dominant_passband_not_outermost_bands(self):
        frequencies = [1.0, 10.0, 100.0, 1000.0, 10000.0,
                       100000.0, 1e6, 1e7, 1e8]
        gains = [0.1, 0.5, 1.0, 0.5, 0.1, 0.2, 0.8, 0.2, 0.1]
        plots = {"AC Analysis": ac_plot(gains, frequencies)}
        results, errors = evaluate(
            {"metrics": [{"measure": "bandwidth_width_hz",
                          "output": "v(out)", "input": "v(in)"}]},
            plots, "")
        self.assertFalse(errors)
        self.assertTrue(10.0 < results[0].value < 1000.0)
        self.assertIn("dominant passband", results[0].detail)
        self.assertIn("100 Hz", results[0].detail)

    def test_bandwidth_ripple_does_not_jump_to_a_later_passband(self):
        frequencies = [1.0, 10.0, 100.0, 1000.0, 10000.0,
                       100000.0, 1e6]
        # A deep ripple notch separates the dominant peak from a smaller
        # secondary passband. The upper corner must be the first crossing.
        gains = [0.1, 0.5, 1.0, 0.1, 0.8, 0.2, 0.1]
        plots = {"AC Analysis": ac_plot(gains, frequencies)}
        results, errors = evaluate(
            {"metrics": [{"measure": "bandwidth_hz",
                          "output": "v(out)", "input": "v(in)"}]},
            plots, "")
        self.assertFalse(errors)
        self.assertGreater(results[0].value, 100.0)
        self.assertLess(results[0].value, 10000.0)
        self.assertIn("dominant peak 100 Hz", results[0].detail)

    def test_bandwidth_rejects_unsorted_frequency_axis(self):
        plots = {"AC Analysis": ac_plot([0.1, 1.0, 0.1], [10.0, 100.0, 50.0])}
        _, errors = evaluate(
            {"metrics": [{"measure": "bandwidth_hz",
                          "output": "v(out)", "input": "v(in)"}]},
            plots, "")
        self.assertTrue(errors)
        self.assertIn("strictly ascending", errors[0])

    def test_bandwidth_needs_a_corner(self):
        plots = {"AC Analysis": ac_plot([1.0, 0.99, 0.98], [10.0, 100.0, 1000.0])}
        _, errors = evaluate(
            {"metrics": [{"measure": "bandwidth_hz", "output": "v(out)",
                          "input": "v(in)"}]},
            plots, "")
        self.assertTrue(errors)
        self.assertIn("extend stop", errors[0])

    def test_thd_from_four_log(self):
        log = ("Fourier analysis for v(out):\n"
               "Total harmonic distortion = 0.012300 percent\n")
        results, errors = evaluate(
            {"metrics": [{"measure": "thd_percent", "output": "v(out)",
                          "fundamental": 1000.0}]},
            {}, log)
        self.assertFalse(errors)
        self.assertAlmostEqual(results[0].value, 0.0123, places=9)
        self.assertEqual(results[0].unit, "%")

    def test_thd_missing_log_line(self):
        _, errors = evaluate(
            {"metrics": [{"measure": "thd_percent", "output": "v(out)",
                          "fundamental": 1000.0}]},
            {}, "no fourier output")
        self.assertTrue(errors)
        self.assertIn("no THD line", errors[0])

    def test_thd_selects_the_matching_four_block(self):
        log = ("Fourier analysis for v(other):\n"
               "Total harmonic distortion = 1.000000 percent\n"
               "Fourier analysis for v(out):\n"
               "Total harmonic distortion = 0.012300 percent\n")
        results, errors = evaluate(
            {"metrics": [{"measure": "thd_percent", "output": "v(out)",
                          "fundamental": 1000.0}]},
            {}, log)
        self.assertFalse(errors)
        self.assertAlmostEqual(results[0].value, 0.0123, places=9)

    def test_input_noise_integration(self):
        plot = Plot(
            name="Noise Analysis",
            flags={"real"},
            variables=["frequency", "onoise_spectrum", "inoise_spectrum"],
            types=["frequency", "voltage", "voltage"],
            points=[[10.0, 1e-9, 2e-9], [1000.0, 1e-9, 2e-9]],
        )
        results, errors = evaluate(
            {"metrics": [{"measure": "ein_uv", "output": "v(out)"}]},
            {"Noise Analysis": plot}, "")
        self.assertFalse(errors)
        expected = 2e-9 * math.sqrt(990.0) * 1e6
        self.assertAlmostEqual(results[0].value, expected, places=9)

    def test_output_noise_integration(self):
        plot = Plot(
            name="Noise Analysis",
            flags={"real"},
            variables=["frequency", "onoise_spectrum", "inoise_spectrum"],
            types=["frequency", "voltage", "voltage"],
            points=[[10.0, 1e-9, 2e-9], [1000.0, 1e-9, 2e-9]],
        )
        results, errors = evaluate(
            {"metrics": [{"measure": "noise_uv", "output": "v(out)"}]},
            {"Noise Analysis": plot}, "")
        self.assertFalse(errors)
        expected = 1e-9 * math.sqrt(990.0) * 1e6
        self.assertAlmostEqual(results[0].value, expected, places=9)

    def test_output_vrms_over_window(self):
        frequency = 1000.0
        times = [i * 1e-5 for i in range(101)]
        values = [math.sin(2.0 * math.pi * frequency * t) for t in times]
        plot = Plot(
            name="Transient Analysis",
            flags={"real"},
            variables=["time", "v(out)"],
            types=["time", "voltage"],
            points=[[t, v] for t, v in zip(times, values)],
        )
        results, errors = evaluate(
            {"metrics": [{"measure": "output_vrms", "output": "v(out)",
                          "start": 0.0, "stop": 1e-3}]},
            {"Transient Analysis": plot}, "")
        self.assertFalse(errors)
        self.assertAlmostEqual(results[0].value, 1.0 / math.sqrt(2.0), places=5)

    def test_missing_plot_is_an_error(self):
        _, errors = evaluate(
            {"metrics": [{"measure": "gain_db", "output": "v(out)",
                          "input": "v(in)", "frequency": 1000.0}]},
            {}, "")
        self.assertTrue(errors)
        self.assertIn("no AC analysis plot", errors[0])

    def test_gain_frequency_must_be_near_a_sweep_point(self):
        plots = {"AC Analysis": ac_plot([1.0, 1.0], [10.0, 1e5])}
        _, errors = evaluate(
            {"metrics": [{"measure": "gain_db", "output": "v(out)",
                          "input": "v(in)", "frequency": 1000.0}]},
            plots, "")
        self.assertTrue(errors)
        self.assertIn("nearest AC point", errors[0])

    def test_compare_forms(self):
        self.assertEqual(compare({"target": 10.0, "tolerance": 0.5}, 10.2), (True, "target 10 +/- 0.5"))
        self.assertEqual(compare({"max": 1.0}, 1.1)[0], False)
        self.assertEqual(compare({"min": 1.0}, 1.1)[0], True)
        self.assertEqual(compare({"exploratory": True}, 0.0), (None, "exploratory"))
        self.assertEqual(compare({}, 0.0), (None, "no target or limit"))


class TestMetricsCheck(unittest.TestCase):
    def setUp(self):
        self.plots = {"AC Analysis": ac_plot([0.5 + 0j], [1000.0])}
        self.spec = {
            "metrics": {
                "metrics": [{
                    "id": "M1", "measure": "gain_db", "output": "v(out)",
                    "input": "v(in)", "frequency": 1000.0,
                    "target": -6.0206, "tolerance": 0.01,
                }],
            },
        }
        self.ngspice_ok = verify.Check("ngspice", True, "ran")

    def test_passing_metric(self):
        check = verify.check_metrics(self.spec, self.plots, "", self.ngspice_ok)
        self.assertTrue(check.ok, check.detail)
        self.assertIn("PASS", check.detail)

    def test_failing_metric(self):
        self.spec["metrics"]["metrics"][0]["target"] = 0.0
        check = verify.check_metrics(self.spec, self.plots, "", self.ngspice_ok)
        self.assertFalse(check.ok)
        self.assertIn("FAIL", check.detail)

    def test_missing_plot_fails_after_ngspice_ran(self):
        check = verify.check_metrics(self.spec, {}, "", self.ngspice_ok)
        self.assertFalse(check.ok)
        self.assertIn("no AC analysis plot", check.detail)

    def test_ngspice_unavailable_is_a_skip(self):
        check = verify.check_metrics(
            self.spec, self.plots, "", verify.Check("ngspice", None, "absent"))
        self.assertIsNone(check.ok)
        self.assertIn("unavailable", check.detail)

    def test_no_metrics_means_no_check(self):
        self.assertIsNone(verify.check_metrics({}, self.plots, "", self.ngspice_ok))

    def test_metrics_without_spice_deliverable_fail(self):
        spec = {
            "name": "metrics_without_spice",
            "deliverables": ["report"],
            "components": [
                {"ref": "V1", "type": "V", "value": 0, "dc": 0, "ac": 1,
                 "pins": {"1": "IN", "2": "GND"}},
                {"ref": "R1", "type": "R", "value": 1000,
                 "pins": {"1": "IN", "2": "OUT"}},
                {"ref": "C1", "type": "C", "value": 1e-7,
                 "pins": {"1": "OUT", "2": "GND"}},
            ],
            "analyses": [{"type": "ac", "start": 10, "stop": 1e6, "points": 100}],
            "metrics": {"metrics": [{
                "measure": "gain_db", "output": "v(out)", "input": "v(in)",
                "frequency": 1000.0, "target": -1.445, "tolerance": 0.1,
            }]},
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "spec.json"
            path.write_text(json.dumps(spec), encoding="utf-8")
            result = verify.verify(path, Path(td) / "out", update_report=False)
        check = next(item for item in result["checks"] if item["name"] == "metrics")
        self.assertFalse(check["ok"])
        self.assertIn("no SPICE netlist", check["detail"])


if __name__ == "__main__":
    unittest.main()
