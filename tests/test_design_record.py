"""Tests for the planning and evidence record.

A design can be structurally valid and still be indefensible if nobody wrote
down why the parts were chosen. These tests cover the optional `design`
record, the verifier gate, and the report rendering.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate  # noqa: E402
import verify  # noqa: E402
from design_spec import validate_spec  # noqa: E402


def complete_design() -> dict:
    return {
        "requirements": [
            {"id": "R1", "text": "3.3 V rail within 3.2-3.4 V at 1 A",
             "acceptance": "measure at min/max load", "source": "brief rev A"},
        ],
        "architecture": {
            "summary": "linear regulator from a 5 V input",
            "blocks": ["input protection", "LDO", "output filter"],
            "interfaces": ["5 V in", "3.3 V out"],
            "budgets": {"dissipation": "1.5 W", "board area": "20 x 15 mm"},
            "test_points": ["TP1 = 3V3", "TP2 = GND"],
        },
        "decisions": [
            {"id": "D1", "decision": "use an LDO instead of a buck",
             "alternatives": ["buck converter"], "rationale": "no switching noise",
             "sources": ["TPS7A datasheet, section 8"]},
        ],
        "risks": [
            {"id": "K1", "risk": "LDO overheating at 1 A",
             "severity": "high", "mitigation": "copper pour and thermal vias",
             "verification": "thermal chamber at 40 C ambient"},
        ],
        "sources": [
            {"title": "TPS7A datasheet", "document": "SBVS123", "revision": "C",
             "accessed": "2026-11-08"},
            {"title": "Thermal design app note", "url": "https://example.invalid/an",
             "accessed": "2026-11-08"},
        ],
    }


def base_spec(design: dict | None = None) -> dict:
    spec = {
        "name": "design_test",
        "description": "planning record test",
        "ground": "GND",
        "deliverables": ["spice", "report"],
        "analyses": [{"type": "op"}],
        "components": [
            {"ref": "V1", "type": "V", "value": 5, "pins": {"1": "VIN", "2": "GND"}},
            {"ref": "R1", "type": "R", "value": 1000, "pins": {"1": "VIN", "2": "VOUT"}},
        ],
    }
    if design is not None:
        spec["design"] = design
    return spec


class TestDesignValidation(unittest.TestCase):
    def test_complete_record_validates(self):
        report = validate_spec(base_spec(complete_design()))
        self.assertTrue(report["ok"], report["errors"])

    def test_malformed_section_is_an_error(self):
        report = validate_spec(base_spec({"requirements": "not a list"}))
        self.assertFalse(report["ok"])
        self.assertTrue(any("must be a list" in e for e in report["errors"]))

    def test_architecture_budgets_must_be_an_object(self):
        design = complete_design()
        design["architecture"]["budgets"] = ["1.5 W"]
        report = validate_spec(base_spec(design))
        self.assertFalse(report["ok"])
        self.assertTrue(any("budgets must be an object" in e for e in report["errors"]))

    def test_requirement_without_source_warns(self):
        design = complete_design()
        design["requirements"][0]["source"] = ""
        report = validate_spec(base_spec(design))
        self.assertTrue(any("no source" in w for w in report["warnings"]))

    def test_unsourced_decision_warns(self):
        design = complete_design()
        design["decisions"][0]["sources"] = []
        report = validate_spec(base_spec(design))
        self.assertTrue(any("cites no source" in w for w in report["warnings"]))

    def test_high_risk_without_mitigation_warns(self):
        design = complete_design()
        design["risks"][0]["mitigation"] = ""
        report = validate_spec(base_spec(design))
        self.assertTrue(any("needs a mitigation" in w for w in report["warnings"]))

    def test_unknown_severity_is_an_error(self):
        design = complete_design()
        design["risks"][0]["severity"] = "critical"
        report = validate_spec(base_spec(design))
        self.assertFalse(report["ok"])


class TestDesignCheck(unittest.TestCase):
    def test_missing_record_is_a_skip(self):
        check = verify.check_design(base_spec())
        self.assertIsNone(check.ok)
        self.assertIn("no design record", check.detail)

    def test_complete_record_passes(self):
        check = verify.check_design(base_spec(complete_design()))
        self.assertTrue(check.ok, check.detail)
        self.assertIn("1 requirements", check.detail)

    def test_missing_architecture_is_incomplete(self):
        design = complete_design()
        design["architecture"] = {}
        check = verify.check_design(base_spec(design))
        self.assertIsNone(check.ok)
        self.assertIn("architecture", check.detail)

    def test_unsourced_decision_is_incomplete(self):
        design = complete_design()
        design["decisions"][0]["sources"] = []
        design["decisions"][0]["rationale"] = ""
        check = verify.check_design(base_spec(design))
        self.assertIsNone(check.ok)
        self.assertIn("without a source", check.detail)

    def test_high_risk_without_verification_is_incomplete(self):
        design = complete_design()
        design["risks"][0]["verification"] = ""
        check = verify.check_design(base_spec(design))
        self.assertIsNone(check.ok)
        self.assertIn("high risks", check.detail)


class TestDesignGate(unittest.TestCase):
    def test_required_design_fails_without_record(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "spec.json"
            path.write_text(json.dumps(base_spec()), encoding="utf-8")
            result = verify.verify(path, Path(td) / "out",
                                   update_report=False, required=["design"])
        names = {check["name"]: check for check in result["checks"]}
        self.assertIsNone(names["design"]["ok"])
        self.assertFalse(names["required:design"]["ok"])
        self.assertFalse(result["ok"])

    def test_required_design_passes_with_record(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "spec.json"
            path.write_text(json.dumps(base_spec(complete_design())), encoding="utf-8")
            result = verify.verify(path, Path(td) / "out",
                                   update_report=False, required=["design"])
        names = {check["name"]: check for check in result["checks"]}
        self.assertTrue(names["design"]["ok"], names["design"]["detail"])
        self.assertTrue(names["required:design"]["ok"])
        self.assertTrue(result["ok"])


class TestDesignReport(unittest.TestCase):
    def test_report_renders_the_record(self):
        spec = base_spec(complete_design())
        report = generate.build_report(spec, {}, [])
        text = generate.report_markdown(report)
        self.assertIn("## Design record", text)
        self.assertIn("### Requirements", text)
        self.assertIn("### Decisions", text)
        self.assertIn("### Risks", text)
        self.assertIn("### Sources", text)
        self.assertIn("LDO overheating", text)
        self.assertIn("SBVS123", text)


if __name__ == "__main__":
    unittest.main()
