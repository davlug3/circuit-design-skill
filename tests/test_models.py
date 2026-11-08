"""Tests for vendor/real model ingestion.

The failure this guards against is presenting a generic transistor or diode as
a verified part. A model only counts as vendor-backed when it comes from a
file or card with recorded provenance, and a subcircuit model must state its
node order explicitly.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "models"
sys.path.insert(0, str(ROOT / "scripts"))

import generate  # noqa: E402
import verify  # noqa: E402
from design_spec import (  # noqa: E402
    model_status,
    resolve_model,
    validate_spec,
)

LIB = FIXTURES / "test_parts.lib"
SHA = hashlib.sha256(LIB.read_bytes()).hexdigest()


def _spec(models: dict, components: list[dict] | None = None) -> dict:
    return {
        "name": "model_fixture",
        "description": "model ingestion fixture",
        "ground": "GND",
        "deliverables": ["spice", "bom", "report"],
        "analyses": [{"type": "op"}],
        "components": components or [
            {"ref": "V1", "type": "V", "value": 5, "pins": {"1": "VIN", "2": "GND"}},
            {"ref": "R1", "type": "R", "value": 1000, "pins": {"1": "VIN", "2": "A"}},
            {"ref": "D1", "type": "D", "value": 0, "model": "TESTDIODE",
             "pins": {"1": "A", "2": "GND"}},
        ],
        "models": models,
    }


VENDOR_DIODE = {
    "file": LIB.name,
    "vendor": "TestVendor",
    "part": "TEST-1",
    "source": "https://example.invalid/test_parts.lib",
    "sha256": SHA,
}


class TestResolveModel(unittest.TestCase):
    def test_extracts_only_the_named_model(self):
        spec = _spec({"TESTDIODE": VENDOR_DIODE})
        info = resolve_model(spec, "TESTDIODE", base_dir=FIXTURES)
        self.assertIsNone(info["error"])
        self.assertIn(".model TESTDIODE", info["card"])
        self.assertNotIn("OTHERDIODE", info["card"])
        self.assertFalse(info["subckt"])
        self.assertEqual(info["kind"], "vendor")
        self.assertEqual(info["sha256"], SHA)

    def test_extracts_subcircuit_and_flags_it(self):
        comps = [
            {"ref": "V1", "type": "V", "value": 5, "pins": {"1": "VIN", "2": "GND"}},
            {"ref": "M1", "type": "NMOS", "value": 0, "model": "TESTNMOS",
             "pins": {"1": "D", "2": "G", "3": "GND"}},
        ]
        spec = _spec({"TESTNMOS": {**VENDOR_DIODE, "subckt_pins": ["D", "G", "S"]}}, comps)
        info = resolve_model(spec, "TESTNMOS", base_dir=FIXTURES)
        self.assertTrue(info["subckt"])
        self.assertIn(".subckt TESTNMOS", info["card"])
        self.assertIn(".ends", info["card"])

    def test_missing_file_is_an_error(self):
        spec = _spec({"TESTDIODE": {**VENDOR_DIODE, "file": "does-not-exist.lib"}})
        info = resolve_model(spec, "TESTDIODE", base_dir=FIXTURES)
        self.assertIn("cannot read model file", info["error"])

    def test_hash_mismatch_is_an_error(self):
        spec = _spec({"TESTDIODE": {**VENDOR_DIODE, "sha256": "0" * 64}})
        info = resolve_model(spec, "TESTDIODE", base_dir=FIXTURES)
        self.assertIn("sha256 mismatch", info["error"])

    def test_missing_definition_is_an_error(self):
        spec = _spec({"NOPE": {**VENDOR_DIODE}})
        info = resolve_model(spec, "NOPE", base_dir=FIXTURES)
        self.assertIn("does not define", info["error"])


class TestModelStatus(unittest.TestCase):
    def test_generic_when_undeclared(self):
        self.assertEqual(model_status(_spec({})), "unverified (generic models)")

    def test_declared_without_provenance(self):
        spec = _spec({"TESTDIODE": {**VENDOR_DIODE, "vendor": None, "part": None,
                                    "source": None}})
        self.assertEqual(model_status(spec, FIXTURES),
                         "declared models (no vendor provenance)")

    def test_vendor_when_provenance_complete(self):
        self.assertEqual(model_status(_spec({"TESTDIODE": VENDOR_DIODE}), FIXTURES),
                         "vendor models supplied")


class TestValidation(unittest.TestCase):
    def test_missing_file_is_rejected(self):
        spec = _spec({"TESTDIODE": {**VENDOR_DIODE, "file": "nope.lib"}})
        report = validate_spec(spec, base_dir=FIXTURES)
        self.assertFalse(report["ok"])
        self.assertTrue(any("cannot read model file" in e for e in report["errors"]))

    def test_bad_card_is_rejected(self):
        spec = _spec({"TESTDIODE": {"card": "not a spice card", "vendor": "V",
                                    "part": "P", "source": "s"}})
        report = validate_spec(spec, base_dir=FIXTURES)
        self.assertFalse(report["ok"])
        self.assertTrue(any("does not contain" in e for e in report["errors"]))

    def test_subckt_without_pin_order_is_rejected(self):
        comps = [
            {"ref": "V1", "type": "V", "value": 5, "pins": {"1": "VIN", "2": "GND"}},
            {"ref": "M1", "type": "NMOS", "value": 0, "model": "TESTNMOS",
             "pins": {"1": "D", "2": "G", "3": "GND"}},
        ]
        spec = _spec({"TESTNMOS": VENDOR_DIODE}, comps)
        report = validate_spec(spec, base_dir=FIXTURES)
        self.assertFalse(report["ok"])
        self.assertTrue(any("subckt_pins" in e for e in report["errors"]))

    def test_subckt_pin_order_is_accepted(self):
        comps = [
            {"ref": "V1", "type": "V", "value": 5, "pins": {"1": "VIN", "2": "GND"}},
            {"ref": "M1", "type": "NMOS", "value": 0, "model": "TESTNMOS",
             "pins": {"1": "D", "2": "G", "3": "GND"}},
        ]
        spec = _spec({"TESTNMOS": {**VENDOR_DIODE, "subckt_pins": ["D", "G", "S"]}}, comps)
        report = validate_spec(spec, base_dir=FIXTURES)
        self.assertTrue(report["ok"], report["errors"])


class TestGeneration(unittest.TestCase):
    def test_vendor_model_is_inlined_with_provenance(self):
        spec = _spec({"TESTDIODE": VENDOR_DIODE})
        netlist = generate.spice_netlist(spec, base_dir=FIXTURES)
        self.assertIn("* Models: vendor models supplied", netlist)
        self.assertIn("vendor=TestVendor", netlist)
        self.assertIn("sha256=" + SHA, netlist)
        self.assertIn(".model TESTDIODE", netlist)
        self.assertIn("D1", netlist)
        self.assertNotIn("UNVERIFIED", netlist)

    def test_subcircuit_emits_x_device_in_given_order(self):
        comps = [
            {"ref": "V1", "type": "V", "value": 5, "pins": {"1": "VIN", "2": "GND"}},
            {"ref": "M1", "type": "NMOS", "value": 0, "model": "TESTNMOS",
             "pins": {"1": "DRAINNET", "2": "GATENET", "3": "GND"}},
        ]
        spec = _spec({"TESTNMOS": {**VENDOR_DIODE, "subckt_pins": ["D", "G", "S"]}}, comps)
        netlist = generate.spice_netlist(spec, base_dir=FIXTURES)
        self.assertIn("XM1 DRAINNET GATENET 0 TESTNMOS", netlist)

    def test_generic_netlist_keeps_the_warning(self):
        netlist = generate.spice_netlist(_spec({}), base_dir=FIXTURES)
        self.assertIn("UNVERIFIED", netlist)

    def test_subcircuit_ltspice_uses_x_prefix(self):
        comps = [
            {"ref": "V1", "type": "V", "value": 5, "pins": {"1": "VIN", "2": "GND"}},
            {"ref": "M1", "type": "NMOS", "value": 0, "model": "TESTNMOS",
             "pins": {"1": "DRAINNET", "2": "GATENET", "3": "GND"}},
        ]
        spec = _spec({"TESTNMOS": {**VENDOR_DIODE, "subckt_pins": ["D", "G", "S"]}}, comps)
        asc = generate.ltspice_asc(spec, base_dir=FIXTURES)
        self.assertIn("SYMATTR Prefix X", asc)
        self.assertIn("SYMATTR Value TESTNMOS", asc)

    def test_subcircuit_ltspice_rejects_wrong_pin_order(self):
        comps = [
            {"ref": "V1", "type": "V", "value": 5, "pins": {"1": "VIN", "2": "GND"}},
            {"ref": "M1", "type": "NMOS", "value": 0, "model": "TESTNMOS",
             "pins": {"1": "DRAINNET", "2": "GATENET", "3": "GND"}},
        ]
        spec = _spec({"TESTNMOS": {**VENDOR_DIODE, "subckt_pins": ["G", "D", "S"]}}, comps)
        with self.assertRaises(ValueError):
            generate.ltspice_asc(spec, base_dir=FIXTURES)


class TestVerifyModels(unittest.TestCase):
    def test_required_models_fails_for_generic(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "generic.json"
            path.write_text(json.dumps(_spec({})), encoding="utf-8")
            result = verify.verify(path, Path(td) / "out",
                                   update_report=False, required=["models"])
        self.assertFalse(result["ok"])
        self.assertTrue(any(c["name"] == "required:models" and c["ok"] is False
                            for c in result["checks"]))

    def test_required_models_passes_for_vendor(self):
        spec = _spec({"TESTDIODE": {**VENDOR_DIODE, "file": str(LIB)}})
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "vendor.json"
            path.write_text(json.dumps(spec), encoding="utf-8")
            result = verify.verify(path, Path(td) / "out",
                                   update_report=False, required=["models"])
        checks = {c["name"]: c for c in result["checks"]}
        self.assertTrue(checks["models"]["ok"], checks["models"]["detail"])
        self.assertTrue(checks["required:models"]["ok"])

    def test_subcircuit_netlist_and_asc_are_checked(self):
        comps = [
            {"ref": "V1", "type": "V", "value": 5, "pins": {"1": "VDD", "2": "GND"}},
            {"ref": "V2", "type": "V", "value": 3.3, "pins": {"1": "GATE", "2": "GND"}},
            {"ref": "R1", "type": "R", "value": 100, "pins": {"1": "VDD", "2": "DRAIN"}},
            {"ref": "M1", "type": "NMOS", "value": 0, "model": "TESTNMOS",
             "pins": {"1": "DRAIN", "2": "GATE", "3": "GND"}},
        ]
        spec = _spec(
            {"TESTNMOS": {**VENDOR_DIODE, "file": str(LIB),
                          "subckt_pins": ["D", "G", "S"]}},
            comps,
        )
        spec["deliverables"] = ["spice", "ltspice_asc"]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "subckt.json"
            path.write_text(json.dumps(spec), encoding="utf-8")
            result = verify.verify(path, Path(td) / "out",
                                   update_report=False, required=["models"])
        checks = {c["name"]: c for c in result["checks"]}
        self.assertTrue(checks["spice_netlist"]["ok"], checks["spice_netlist"]["detail"])
        self.assertTrue(checks["ltspice_asc"]["ok"], checks["ltspice_asc"]["detail"])


    @unittest.skipUnless(shutil.which("ngspice"), "ngspice is not installed")
    def test_subcircuit_vendor_model_simulates(self):
        comps = [
            {"ref": "V1", "type": "V", "value": 5, "pins": {"1": "VDD", "2": "GND"}},
            {"ref": "V2", "type": "V", "value": 3.3, "pins": {"1": "GATE", "2": "GND"}},
            {"ref": "R1", "type": "R", "value": 100, "pins": {"1": "VDD", "2": "DRAIN"}},
            {"ref": "M1", "type": "NMOS", "value": 0, "model": "TESTNMOS",
             "pins": {"1": "DRAIN", "2": "GATE", "3": "GND"}},
        ]
        spec = _spec(
            {"TESTNMOS": {**VENDOR_DIODE, "file": str(LIB),
                          "subckt_pins": ["D", "G", "S"]}},
            comps,
        )
        spec["deliverables"] = ["spice"]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "subckt.json"
            path.write_text(json.dumps(spec), encoding="utf-8")
            result = verify.verify(path, Path(td) / "out",
                                   update_report=False,
                                   required=["models", "simulate"])
            netlist = (Path(td) / "out" / "model_fixture.cir").read_text(encoding="utf-8")
        checks = {c["name"]: c for c in result["checks"]}
        self.assertTrue(checks["ngspice"]["ok"], checks["ngspice"]["detail"])
        self.assertIn("XM1 DRAIN GATE 0 TESTNMOS", netlist)


if __name__ == "__main__":
    unittest.main()
