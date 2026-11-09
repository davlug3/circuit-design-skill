"""Tests for the discrete RC low-pass optimizer."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from optimize import optimize_rc_lowpass  # noqa: E402


class TestRCLowpassOptimizer(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((ROOT / "examples" / "rc-lowpass.json").read_text())

    def test_returns_feasible_e_series_candidate_and_updates_spec(self):
        result = optimize_rc_lowpass(
            self.spec,
            target_fc_hz=1 / (2 * 3.141592653589793 * 1e3 * 100e-9),
            r_min=1e3, r_max=1e3,
            c_min=100e-9, c_max=100e-9,
            r_tolerance_percent=1,
            c_tolerance_percent=1,
            max_error_percent=3,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["candidates_evaluated"], 1)
        optimized = result["optimized_spec"]
        r = next(x for x in optimized["components"] if x["type"] == "R")
        c = next(x for x in optimized["components"] if x["type"] == "C")
        self.assertEqual(r["value"], 1000)
        self.assertEqual(c["value"], 100e-9)
        self.assertEqual(r["tolerance_percent"], 1)
        self.assertIn("source/load impedance", optimized["assumptions"][-1])

    def test_ranks_by_exact_worst_case_error(self):
        result = optimize_rc_lowpass(
            self.spec, target_fc_hz=1500,
            r_min=1e3, r_max=10e3,
            c_min=10e-9, c_max=1e-6,
            max_error_percent=100,
            top_n=5,
        )
        candidates = result["top_candidates"]
        self.assertLessEqual(
            candidates[0]["worst_case_error_percent"],
            candidates[-1]["worst_case_error_percent"],
        )
        self.assertGreater(result["candidates_evaluated"], 1)

    def test_rejects_non_rc_topology(self):
        self.spec["topology"] = "buck"
        with self.assertRaisesRegex(ValueError, "rc_lowpass"):
            optimize_rc_lowpass(self.spec, target_fc_hz=1000)


if __name__ == "__main__":
    unittest.main()
