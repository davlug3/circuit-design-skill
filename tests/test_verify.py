"""Verification pipeline tests."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import verify  # noqa: E402
from design_spec import dumps, scaffold  # noqa: E402

EXAMPLES = ROOT / "examples"


class TestVerifyExamples(unittest.TestCase):
    def test_rc_passes(self):
        with tempfile.TemporaryDirectory() as td:
            result = verify.verify(EXAMPLES / "rc-lowpass.json", td)
            self.assertTrue(result["ok"], result["summary"])
            names = {c["name"] for c in result["checks"]}
            self.assertIn("spice_netlist", names)
            self.assertIn("ltspice_asc", names)
            self.assertIn("kicad_netlist", names)
            self.assertIn("rc_corner", names)
            self.assertTrue((Path(td) / "rc_lowpass-verification.json").exists())

    def test_pcb_drc_is_skipped_without_actual_board_and_required_gate_fails(self):
        with tempfile.TemporaryDirectory() as td:
            result = verify.verify(EXAMPLES / "rc-lowpass.json", td, required=["pcb-drc"])
            check = next(c for c in result["checks"] if c["name"] == "kicad_pcb_drc")
            self.assertIsNone(check["ok"])
            required = next(c for c in result["checks"] if c["name"] == "required:pcb-drc")
            self.assertFalse(required["ok"])
            self.assertFalse(result["ok"])

    def test_pcb_drc_runs_on_actual_board(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            board = out / "sample.kicad_pcb"
            board.write_text("(kicad_pcb (version 20241229))")
            with patch.object(verify.env_probe, "probe_kicad_pcb_drc", return_value={"supported": True, "path": "/usr/bin/kicad-cli"}), patch.object(verify.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="", stderr="")) as run:
                check = verify.check_kicad_pcb_drc(board, out)
            self.assertTrue(check.ok, check.detail)
            self.assertEqual(run.call_args.args[0][1:3], ["pcb", "drc"])

    def test_operating_limits_pass_and_fail(self):
        spec = {"design": {"operating_limits": [{
            "id": "L1", "parameter": "junction temperature", "value": 105,
            "unit": "degC", "min": -40, "max": 125,
            "condition": "Vin max, Iout max, Ta 50 degC",
            "source": "Vendor datasheet rev B, thermal ratings table"
        }]}}
        check = verify.check_operating_limits(spec)
        self.assertTrue(check.ok, check.detail)
        self.assertEqual(check.evidence[0]["margin_to_max"], 20)
        spec["design"]["operating_limits"][0]["value"] = 130
        failed = verify.check_operating_limits(spec)
        self.assertFalse(failed.ok)
        self.assertIn("outside", failed.detail)

    def test_required_limits_fails_when_missing(self):
        with tempfile.TemporaryDirectory() as td:
            result = verify.verify(EXAMPLES / "rc-lowpass.json", td, required=["limits"])
            self.assertFalse(result["ok"])
            required = next(c for c in result["checks"] if c["name"] == "required:limits")
            self.assertFalse(required["ok"])

    def test_measurement_plan_requires_traceable_acceptance(self):
        spec = {"design": {
            "requirements": [{"id": "R1", "text": "Output within 5%"}],
            "measurements": [{
                "id": "M1", "requirement": "R1", "test_point": "OUT",
                "quantity": "output voltage", "method": "DMM",
                "equipment": "calibrated DMM", "conditions": "Vin=12 V, load=1 kohm",
                "acceptance": "4.75 to 5.25 V"
            }]
        }}
        self.assertTrue(verify.check_measurement_plan(spec).ok)
        spec["design"]["measurements"][0]["requirement"] = "UNKNOWN"
        self.assertFalse(verify.check_measurement_plan(spec).ok)

    def test_required_measurement_plan_fails_when_missing(self):
        with tempfile.TemporaryDirectory() as td:
            result = verify.verify(EXAMPLES / "rc-lowpass.json", td, required=["measurements"])
            self.assertFalse(result["ok"])
            required = next(c for c in result["checks"] if c["name"] == "required:measurements")
            self.assertFalse(required["ok"])

    def test_sallen_key_highpass_corner(self):
        with tempfile.TemporaryDirectory() as td:
            result = verify.verify(EXAMPLES / "sallen-key-lowpass.json", td)
            self.assertTrue(result["ok"], result["summary"])
            corner = next(c for c in result["checks"]
                          if c["name"] == "sallen_key_corner")
            self.assertTrue(corner["ok"])
            self.assertLess(abs(corner["evidence"]["actual_Hz"] - 1000), 30)

    def test_buck_passes_structurally_and_skips_mna(self):
        with tempfile.TemporaryDirectory() as td:
            result = verify.verify(EXAMPLES / "buck-5v.json", td)
            self.assertTrue(result["ok"], result["summary"])
            mna = next(c for c in result["checks"] if c["name"] == "mna_linear")
            self.assertIsNone(mna["ok"])
            self.assertIn("nonlinear", mna["detail"])
            sizing = next(c for c in result["checks"] if c["name"] == "buck_sizing")
            self.assertTrue(sizing["ok"])

    def test_failure_is_reported(self):
        # A deliberately wrong schematic must fail the connectivity check.
        with tempfile.TemporaryDirectory() as td:
            spec = scaffold("rc_lowpass", {"r": "1k", "c": "100n"}, name="bad")
            path = Path(td) / "bad.json"
            path.write_text(dumps(spec))
            result = verify.verify(path, td)
            self.assertTrue(result["ok"])
            # Corrupt one flag and re-check only the ASC.
            asc = Path(td) / "bad.asc"
            text = asc.read_text().replace("FLAG 496 176 IN", "FLAG 496 176 WRONG")
            asc.write_text(text)
            spec_norm = verify.validate_spec(spec)["normalized"]
            check = verify.check_asc(spec_norm, asc)
            self.assertFalse(check.ok)
            self.assertIn("WRONG", check.detail)


class TestScaffoldVerification(unittest.TestCase):
    def test_bjt_scaffold_skips_nonlinear(self):
        with tempfile.TemporaryDirectory() as td:
            spec = scaffold("bjt_ce", {"vcc": "12", "ic": "2m",
                                       "re": "100", "vce": "6"}, name="bjt")
            path = Path(td) / "bjt.json"
            path.write_text(dumps(spec))
            result = verify.verify(path, td)
            self.assertTrue(result["ok"], result["summary"])
            mna = next(c for c in result["checks"] if c["name"] == "mna_linear")
            self.assertIsNone(mna["ok"])

    def test_inverting_opamp_gain(self):
        with tempfile.TemporaryDirectory() as td:
            spec = scaffold("opamp_inverting", {"gain": "10", "rin": "1k"}, name="inv")
            path = Path(td) / "inv.json"
            path.write_text(dumps(spec))
            result = verify.verify(path, td)
            self.assertTrue(result["ok"], result["summary"])
            gain = next(c for c in result["checks"] if c["name"] == "opamp_gain")
            self.assertTrue(gain["ok"], gain["detail"])
            self.assertAlmostEqual(gain["evidence"]["actual"], 10.0, delta=0.05)

    def test_opamp_gain(self):
        with tempfile.TemporaryDirectory() as td:
            spec = scaffold("opamp_noninverting", {"gain": "10", "rg": "1k"},
                            name="oa")
            path = Path(td) / "oa.json"
            path.write_text(dumps(spec))
            result = verify.verify(path, td)
            self.assertTrue(result["ok"], result["summary"])
            gain = next(c for c in result["checks"] if c["name"] == "opamp_gain")
            self.assertTrue(gain["ok"])
            self.assertAlmostEqual(gain["evidence"]["actual"], 10.0, delta=0.05)


if __name__ == "__main__":
    unittest.main()
