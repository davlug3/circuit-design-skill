"""Tests for metric-block validation and the fourier analysis directive."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate  # noqa: E402
from design_spec import validate_spec  # noqa: E402


def metric_spec(metrics: dict, analyses: list[dict] | None = None,
                requirement: bool = True) -> dict:
    spec = {
        "name": "metrics_test",
        "components": [
            {"ref": "V1", "type": "V", "value": 0, "dc": 0, "ac": 1,
             "pins": {"1": "IN", "2": "GND"}},
            {"ref": "R1", "type": "R", "value": 1000, "pins": {"1": "IN", "2": "OUT"}},
            {"ref": "C1", "type": "C", "value": 1e-7, "pins": {"1": "OUT", "2": "GND"}},
        ],
        "analyses": analyses or [
            {"type": "ac", "start": 10.0, "stop": 1e6, "points": 100}],
        "metrics": metrics,
    }
    if requirement:
        spec["design"] = {
            "requirements": [
                {"id": "A1", "text": "audio gain", "acceptance": "AC sweep",
                 "source": "test brief"},
            ],
        }
    return spec


class TestMetricValidation(unittest.TestCase):
    def test_valid_gain_metric(self):
        report = validate_spec(metric_spec({
            "conditions": {"temperature_c": 25},
            "metrics": [{
                "id": "M1", "measure": "gain_db", "requirement": "A1",
                "output": "v(out)", "input": "v(in)", "frequency": 1000.0,
                "target": -1.445, "tolerance": 0.1,
            }],
        }))
        self.assertTrue(report["ok"], report["errors"])

    def test_metric_needs_matching_analysis(self):
        report = validate_spec(metric_spec(
            {"metrics": [{"measure": "gain_db", "output": "v(out)",
                          "input": "v(in)", "target": 0.0, "tolerance": 0.1}]},
            analyses=[{"type": "op"}]))
        self.assertFalse(report["ok"])
        self.assertTrue(any("add a 'ac' entry" in e for e in report["errors"]))

    def test_requirement_must_exist(self):
        report = validate_spec(metric_spec({
            "metrics": [{"measure": "gain_db", "requirement": "A9",
                         "output": "v(out)", "input": "v(in)",
                         "target": 0.0, "tolerance": 0.1}],
        }))
        self.assertFalse(report["ok"])
        self.assertTrue(any("A9" in e and "absent" in e for e in report["errors"]))

    def test_metric_needs_target_or_limit(self):
        report = validate_spec(metric_spec({
            "metrics": [{"measure": "gain_db", "output": "v(out)",
                         "input": "v(in)", "frequency": 1000.0}],
        }))
        self.assertFalse(report["ok"])
        self.assertTrue(any("needs target+tolerance" in e for e in report["errors"]))

    def test_exploratory_metric_is_allowed_without_target(self):
        report = validate_spec(metric_spec({
            "metrics": [{"measure": "gain_db", "output": "v(out)",
                         "input": "v(in)", "frequency": 1000.0,
                         "exploratory": True}],
        }))
        self.assertTrue(report["ok"], report["errors"])

    def test_target_needs_tolerance(self):
        report = validate_spec(metric_spec({
            "metrics": [{"measure": "gain_db", "output": "v(out)",
                         "input": "v(in)", "target": 0.0}],
        }))
        self.assertFalse(report["ok"])
        self.assertTrue(any("target needs a tolerance" in e for e in report["errors"]))

    def test_thd_needs_tran_and_fourier(self):
        report = validate_spec(metric_spec(
            {"metrics": [{"measure": "thd_percent", "output": "v(out)",
                          "fundamental": 1000.0, "max": 0.1}]},
            analyses=[{"type": "tran", "step": 1e-6, "stop": 1e-3}]))
        self.assertFalse(report["ok"])
        self.assertTrue(any("add a 'fourier' entry" in e for e in report["errors"]))

        report = validate_spec(metric_spec(
            {"metrics": [{"measure": "thd_percent", "output": "v(out)",
                          "fundamental": 1000.0, "max": 0.1}]},
            analyses=[{"type": "fourier", "fundamental": 1000.0, "output": "v(out)"}]))
        self.assertFalse(report["ok"])
        self.assertTrue(any("also needs a 'tran' entry" in e for e in report["errors"]))

    def test_noise_needs_noise_analysis(self):
        report = validate_spec(metric_spec({
            "metrics": [{"measure": "ein_uv", "output": "v(out)", "max": 1.0}],
        }))
        self.assertFalse(report["ok"])
        self.assertTrue(any("add a 'noise' entry" in e for e in report["errors"]))

    def test_output_vrms_needs_tran_and_valid_window(self):
        report = validate_spec(metric_spec(
            {"metrics": [{"measure": "output_vrms", "output": "v(out)",
                          "start": 1e-3, "stop": 0.0, "min": 0.1}]},
            analyses=[{"type": "tran", "step": 1e-6, "stop": 1e-3}]))
        self.assertFalse(report["ok"])
        self.assertTrue(any("0 <= start < stop" in e for e in report["errors"]))

    def test_duplicate_metric_ids(self):
        report = validate_spec(metric_spec({
            "metrics": [
                {"id": "M1", "measure": "gain_db", "output": "v(out)",
                 "input": "v(in)", "target": 0.0, "tolerance": 0.1},
                {"id": "M1", "measure": "gain_db", "output": "v(out)",
                 "input": "v(in)", "target": 0.0, "tolerance": 0.1},
            ],
        }))
        self.assertFalse(report["ok"])
        self.assertTrue(any("duplicate metric id" in e for e in report["errors"]))

    def test_unknown_measure(self):
        report = validate_spec(metric_spec({
            "metrics": [{"measure": "loudness_lufs", "output": "v(out)",
                         "target": -23.0, "tolerance": 1.0}],
        }))
        self.assertFalse(report["ok"])
        self.assertTrue(any("unknown measure" in e for e in report["errors"]))


class TestFourierDirective(unittest.TestCase):
    def test_fourier_emits_four(self):
        directives = generate.analyses_to_spice([
            {"type": "fourier", "fundamental": 1000.0, "output": "v(out)"}])
        self.assertEqual(directives, [".four 1k v(out)"])

    def test_fourier_wraps_a_bare_node(self):
        directives = generate.analyses_to_spice([
            {"type": "fourier", "fundamental": 1000.0, "output": "out"}])
        self.assertEqual(directives, [".four 1k v(out)"])


if __name__ == "__main__":
    unittest.main()
