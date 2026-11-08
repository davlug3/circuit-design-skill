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
