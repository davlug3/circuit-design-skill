"""Tests for the pcb-design-skill handoff."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate  # noqa: E402
import pcb_handoff  # noqa: E402
from design_spec import dumps, scaffold, validate_spec  # noqa: E402
from verify import _load_sibling_spec_module  # noqa: E402

EXAMPLES = ROOT / "examples"


class TestPcbExample(unittest.TestCase):
    def test_rc_handoff_generates_and_verifies(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            result = generate.generate(EXAMPLES / "rc-lowpass-pcb.json", out)
            self.assertEqual(result["pcb"]["name"], "rc_lowpass_pcb")
            self.assertTrue(result["pcb"]["ready"])
            for suffix in ("-pcb.json", "-pinmap.json", "-node-aliases.json",
                           "-pcb-handoff.md", ".cir"):
                self.assertTrue((out / (result["spec"]["name"] + suffix)).exists(),
                                suffix)

            overlay = json.loads(
                (out / "rc_lowpass_pcb-pcb.json").read_text(encoding="utf-8")
            )
            self.assertEqual({c["ref"] for c in overlay["components"]},
                             {"R1", "C1"})
            self.assertNotIn("V1", {c["ref"] for c in overlay["components"]})
            pin_map = json.loads(
                (out / "rc_lowpass_pcb-pinmap.json").read_text(encoding="utf-8")
            )
            self.assertIn("V1", pin_map["exclude"])
            aliases = json.loads(
                (out / "rc_lowpass_pcb-node-aliases.json").read_text(encoding="utf-8")
            )
            self.assertEqual(aliases["0"], "GND")

            verification = __import__("verify").verify(
                EXAMPLES / "rc-lowpass-pcb.json", out
            )
            self.assertTrue(verification["ok"], verification["summary"])
            pcb_check = next(c for c in verification["checks"]
                             if c["name"] == "pcb_handoff")
            self.assertTrue(pcb_check["ok"], pcb_check["detail"])


class TestDiodePinMap(unittest.TestCase):
    def test_diode_default_maps_anode_to_pad_two(self):
        spec = {
            "name": "diode_default",
            "components": [
                {"ref": "D1", "type": "D", "pins": {"1": "A_NET", "2": "K_NET"}},
            ],
        }
        pin_map, _needs, _warnings = pcb_handoff.build_pin_map(spec)
        # KiCad Device:D/LED pads are 1=K, 2=A; SPICE nodes are (anode, cathode).
        self.assertEqual(pin_map["defaults"]["D"], ["2", "1"])


class TestMechanicalExtraComponent(unittest.TestCase):
    def test_mounting_hole_may_have_empty_pads(self):
        spec = {
            "pcb": {
                "extra_components": [
                    {
                        "ref": "H1",
                        "value": "M3 mounting hole",
                        "footprint": "MountingHole:MountingHole_3.2mm_M3",
                        "pads": {},
                    },
                ],
            },
        }
        extra, _warnings = pcb_handoff._extra_components(spec)
        self.assertEqual(extra[0]["pads"], {})


class TestPcbHandoff(unittest.TestCase):
    def _skill(self) -> Path:
        skill = pcb_handoff.find_pcb_skill()
        if skill is None:
            self.skipTest("sibling pcb-design-skill is not installed")
        return skill

    def test_opamp_pin_map_uses_spice_x_prefix(self):
        spec = scaffold("sallen_key_lp", {"fc": "1k", "q": "0.7071"},
                        name="sk_pcb_test")
        spec["pcb"] = {
            "profile": "2layer-low-speed",
            "board": {"width_mm": 50, "height_mm": 40, "layers": 2},
            "footprints": {
                "U1": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
                "R1": "Resistor_SMD:R_0805_2012Metric",
                "R2": "Resistor_SMD:R_0805_2012Metric",
                "C1": "Capacitor_SMD:C_0805_2012Metric",
                "C2": "Capacitor_SMD:C_0805_2012Metric",
            },
            # The user may key the pin map by the circuit reference.
            "pin_map": {"refs": {"U1": ["1", "2", "8", "4", "3"]}},
        }
        with tempfile.TemporaryDirectory() as td:
            summary = pcb_handoff.write_handoff(spec, td)
            self.assertTrue(summary["ready"], summary)
            self.assertEqual(summary["ref_map"], {"U1": "XU1"})
            pin_map = json.loads(
                (Path(td) / "sk_pcb_test-pinmap.json").read_text(encoding="utf-8")
            )
            self.assertIn("XU1", pin_map["refs"])
            self.assertNotIn("U1", pin_map["refs"])
            overlay = json.loads(
                (Path(td) / "sk_pcb_test-pcb.json").read_text(encoding="utf-8")
            )
            xu1 = next(c for c in overlay["components"] if c["ref"] == "XU1")
            self.assertEqual(xu1["properties"]["circuit_ref"], "U1")
            self.assertEqual(xu1["footprint"],
                             "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm")

            skill = self._skill()
            sibling = _load_sibling_spec_module(skill)
            imported = sibling.parse_ltspice_netlist(
                Path(td) / "sk_pcb_test.cir",
                pin_map=pin_map,
                node_aliases=json.loads(
                    (Path(td) / "sk_pcb_test-node-aliases.json").read_text()
                ),
                strict=False,
            )
            self.assertEqual(imported["unresolved"], [])
            component = next(c for c in imported["components"]
                             if c["ref"] == "XU1")
            self.assertEqual(component["pads"],
                             {"1": "P", "2": "OUT", "8": "VCC",
                              "4": "VEE", "3": "OUT"})

    def test_board_is_required(self):
        spec = scaffold("rc_lowpass", {"r": "1k", "c": "100n"}, name="no_board")
        spec["pcb"] = {"profile": "2layer-low-speed"}
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                pcb_handoff.write_handoff(spec, td)

    def test_missing_footprints_are_reported(self):
        spec = scaffold("bjt_ce", {"vcc": "12", "ic": "2m", "re": "100",
                                   "vce": "6"}, name="bjt_missing")
        spec["pcb"] = {
            "profile": "2layer-low-speed",
            "board": {"width_mm": 40, "height_mm": 30, "layers": 2},
            "pin_map": {"refs": {"Q1": {"c": "3", "b": "1", "e": "2"}}},
        }
        with tempfile.TemporaryDirectory() as td:
            summary = pcb_handoff.write_handoff(spec, td)
            self.assertFalse(summary["ready"])
            self.assertIn("R2", summary["missing_footprints"])
            self.assertEqual(summary["needs_pin_map"], [])
            self.assertIn("Q1", json.loads(
                (Path(td) / "bjt_missing-pinmap.json").read_text()
            )["refs"])

    def test_extra_components_are_kept_and_excluded(self):
        spec = scaffold("rc_lowpass", {"r": "1k", "c": "100n"},
                        name="extra_pcb_test")
        spec["pcb"] = {
            "profile": "2layer-low-speed",
            "board": {"width_mm": 40, "height_mm": 30, "layers": 2},
            "footprints": {
                "R1": "Resistor_SMD:R_0805_2012Metric",
                "C1": "Capacitor_SMD:C_0805_2012Metric",
            },
            "extra_components": [{
                "ref": "J1",
                "value": "2-pin header",
                "footprint": ("Connector_PinHeader_2.54mm:"
                              "PinHeader_1x02_P2.54mm_Vertical"),
                "pads": {"1": "IN", "2": "GND"},
            }],
        }
        with tempfile.TemporaryDirectory() as td:
            summary = pcb_handoff.write_handoff(spec, td)
            self.assertTrue(summary["ready"], summary)
            overlay = json.loads(
                (Path(td) / "extra_pcb_test-pcb.json").read_text()
            )
            self.assertIn("J1", {c["ref"] for c in overlay["components"]})
            pin_map = json.loads(
                (Path(td) / "extra_pcb_test-pinmap.json").read_text()
            )
            self.assertIn("J1", pin_map["exclude"])

            skill = self._skill()
            sibling = _load_sibling_spec_module(skill)
            imported = sibling.parse_ltspice_netlist(
                Path(td) / "extra_pcb_test.cir",
                pin_map=pin_map,
                node_aliases=json.loads(
                    (Path(td) / "extra_pcb_test-node-aliases.json").read_text()
                ),
                strict=False,
            )
            merged = sibling.merge_netlist(overlay, imported)
            self.assertIn("J1", {c["ref"] for c in merged["components"]})

    def test_node_alias_restores_sanitized_net_name(self):
        spec = scaffold("rc_lowpass", {"r": "1k", "c": "100n"},
                        name="alias_test")
        for comp in spec["components"]:
            for pin, net in list(comp["pins"].items()):
                if net == "IN":
                    comp["pins"][pin] = "5V"
        spec["pcb"] = {
            "profile": "2layer-low-speed",
            "board": {"width_mm": 30, "height_mm": 20, "layers": 2},
            "footprints": {
                "R1": "Resistor_SMD:R_0805_2012Metric",
                "C1": "Capacitor_SMD:C_0805_2012Metric",
            },
        }
        with tempfile.TemporaryDirectory() as td:
            pcb_handoff.write_handoff(spec, td)
            aliases = json.loads(
                (Path(td) / "alias_test-node-aliases.json").read_text()
            )
            self.assertEqual(aliases["0"], "GND")
            self.assertEqual(aliases["N5V"], "5V")
            net_names = {
                net["name"]
                for net in json.loads(
                    (Path(td) / "alias_test-pcb.json").read_text()
                )["nets"]
            }
            self.assertIn("5V", net_names)

    def test_bare_pin_map_refs_are_accepted(self):
        spec = scaffold("bjt_ce", {"vcc": "12", "ic": "2m", "re": "100",
                                   "vce": "6"}, name="bare_map_test")
        spec["pcb"] = {
            "profile": "2layer-low-speed",
            "board": {"width_mm": 40, "height_mm": 30, "layers": 2},
            "pin_map": {"Q1": {"c": "3", "b": "1", "e": "2"}},
        }
        self.assertTrue(validate_spec(spec)["ok"])
        with tempfile.TemporaryDirectory() as td:
            pcb_handoff.write_handoff(spec, td)
            pin_map = json.loads(
                (Path(td) / "bare_map_test-pinmap.json").read_text()
            )
            self.assertEqual(pin_map["refs"]["Q1"],
                             {"c": "3", "b": "1", "e": "2"})

    def test_footprint_keyed_by_spice_element(self):
        spec = scaffold("opamp_noninverting", {"gain": "10", "rg": "1k"},
                        name="xu1_footprint")
        spec["pcb"] = {
            "profile": "2layer-low-speed",
            "board": {"width_mm": 40, "height_mm": 30, "layers": 2},
            "footprints": {
                "XU1": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
                "RF1": "Resistor_SMD:R_0805_2012Metric",
                "RG1": "Resistor_SMD:R_0805_2012Metric",
            },
            "pin_map": {"refs": {"XU1": ["1", "2", "8", "4", "3"]}},
        }
        with tempfile.TemporaryDirectory() as td:
            summary = pcb_handoff.write_handoff(spec, td)
            self.assertTrue(summary["ready"], summary)
            overlay = json.loads(
                (Path(td) / "xu1_footprint-pcb.json").read_text()
            )
            xu1 = next(c for c in overlay["components"] if c["ref"] == "XU1")
            self.assertEqual(xu1["footprint"],
                             "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm")
            self.assertNotIn("XU1", summary["missing_footprints"])

    def test_mosfet_bulk_maps_to_source_pad(self):
        spec = {
            "name": "nmos_pcb_test",
            "ground": "GND",
            "supplies": [{"name": "VCC", "voltage": 5.0}],
            "components": [
                {"ref": "V1", "type": "V", "value": 0.0,
                 "pins": {"1": "VCC", "2": "GND"}, "dc": 5.0},
                {"ref": "V2", "type": "V", "value": 0.0,
                 "pins": {"1": "GATE", "2": "GND"}, "dc": 3.3},
                {"ref": "R1", "type": "R", "value": 1000.0,
                 "pins": {"1": "VCC", "2": "OUT"}},
                {"ref": "M1", "type": "NMOS", "value": 0.0, "model": "NGEN",
                 "pins": {"1": "OUT", "2": "GATE", "3": "GND"}},
            ],
            "deliverables": ["spice", "pcb", "report"],
            "pcb": {
                "profile": "2layer-low-speed",
                "board": {"width_mm": 30, "height_mm": 20, "layers": 2},
                "footprints": {
                    "R1": "Resistor_SMD:R_0805_2012Metric",
                    "M1": "Package_TO_SOT_SMD:SOT-23",
                },
                # The SPICE MOSFET line has d g s b. A 3-pad package ties
                # bulk to the source pad.
                "pin_map": {"refs": {
                    "M1": {"d": "3", "g": "1", "s": "2", "b": "2"}
                }},
            },
        }
        validation = validate_spec(spec)
        self.assertTrue(validation["ok"], validation["errors"])
        with tempfile.TemporaryDirectory() as td:
            summary = pcb_handoff.write_handoff(
                validation["normalized"], td
            )
            self.assertTrue(summary["ready"], summary)
            skill = self._skill()
            sibling = _load_sibling_spec_module(skill)
            pin_map = json.loads(
                (Path(td) / "nmos_pcb_test-pinmap.json").read_text()
            )
            imported = sibling.parse_ltspice_netlist(
                Path(td) / "nmos_pcb_test.cir",
                pin_map=pin_map,
                node_aliases=json.loads(
                    (Path(td) / "nmos_pcb_test-node-aliases.json").read_text()
                ),
                strict=True,
            )
            self.assertEqual(imported["unresolved"], [])
            m1 = next(c for c in imported["components"] if c["ref"] == "M1")
            self.assertEqual(m1["pads"],
                             {"3": "OUT", "1": "GATE", "2": "GND"})

    def test_mosfet_needs_bulk_pad(self):
        spec = {
            "name": "nmos_missing_bulk",
            "ground": "GND",
            "components": [
                {"ref": "V1", "type": "V", "value": 0.0,
                 "pins": {"1": "VCC", "2": "GND"}, "dc": 5.0},
                {"ref": "R1", "type": "R", "value": 1000.0,
                 "pins": {"1": "VCC", "2": "OUT"}},
                {"ref": "M1", "type": "NMOS", "value": 0.0, "model": "NGEN",
                 "pins": {"1": "OUT", "2": "GATE", "3": "GND"}},
            ],
            "pcb": {
                "board": {"width_mm": 30, "height_mm": 20},
                "pin_map": {"refs": {"M1": {"d": "3", "g": "1", "s": "2"}}},
            },
        }
        result = validate_spec(spec)
        self.assertFalse(result["ok"])
        self.assertTrue(any("4 node(s)" in e for e in result["errors"]))

    def test_mosfet_pad_short_is_rejected(self):
        spec = {
            "name": "nmos_pad_short",
            "ground": "GND",
            "components": [
                {"ref": "V1", "type": "V", "value": 0.0,
                 "pins": {"1": "VCC", "2": "GND"}, "dc": 5.0},
                {"ref": "R1", "type": "R", "value": 1000.0,
                 "pins": {"1": "VCC", "2": "OUT"}},
                {"ref": "M1", "type": "NMOS", "value": 0.0, "model": "NGEN",
                 "pins": {"1": "OUT", "2": "GATE", "3": "GND"}},
            ],
            "pcb": {
                "board": {"width_mm": 30, "height_mm": 20},
                # The fourth node is bulk (source net). Pad 1 is the gate.
                "pin_map": {"refs": {"M1": ["3", "1", "2", "1"]}},
            },
        }
        result = validate_spec(spec)
        self.assertFalse(result["ok"])
        self.assertTrue(any("pad 1 maps to both" in e for e in result["errors"]))

    def test_extra_component_collision_is_rejected(self):
        spec = scaffold("rc_lowpass", {"r": "1k", "c": "100n"},
                        name="extra_collision")
        spec["pcb"] = {
            "board": {"width_mm": 30, "height_mm": 20, "layers": 2},
            "extra_components": [{
                "ref": "R1",
                "footprint": "Resistor_SMD:R_0805_2012Metric",
                "pads": {"1": "IN", "2": "OUT"},
            }],
        }
        result = validate_spec(spec)
        self.assertFalse(result["ok"])
        self.assertTrue(any("is duplicated" in e for e in result["errors"]))

    def test_pcb_can_be_disabled(self):
        spec = scaffold("rc_lowpass", {"r": "1k", "c": "100n"},
                        name="disabled_pcb")
        spec["pcb"] = {
            "enabled": False,
            "board": {"width_mm": 30, "height_mm": 20, "layers": 2},
        }
        with tempfile.TemporaryDirectory() as td:
            summary = pcb_handoff.write_handoff(spec, td)
            self.assertFalse(summary["enabled"])
            self.assertEqual(summary["files"], {})
            self.assertFalse((Path(td) / "disabled_pcb-pcb.json").exists())

    def test_ideal_switch_is_excluded(self):
        spec = json.loads((EXAMPLES / "buck-5v.json").read_text())
        spec["name"] = "buck_pcb_test"
        spec["pcb"] = {
            "profile": "2layer-low-speed",
            "board": {"width_mm": 50, "height_mm": 35, "layers": 2},
            "footprints": {
                "D1": "Diode_SMD:D_SOD-123",
                "L1": "Inductor_SMD:L_1210_3225Metric",
                "C1": "Capacitor_SMD:C_1210_3225Metric",
                "RL1": "Resistor_SMD:R_1206_3216Metric",
            },
        }
        with tempfile.TemporaryDirectory() as td:
            summary = pcb_handoff.write_handoff(spec, td)
            self.assertIn("S1", summary["excluded"])
            overlay = json.loads(
                (Path(td) / "buck_pcb_test-pcb.json").read_text()
            )
            self.assertNotIn("S1", {c["ref"] for c in overlay["components"]})


class TestPcbValidation(unittest.TestCase):
    def test_whitespace_net_is_rejected(self):
        spec = {
            "name": "bad_net",
            "ground": "GND",
            "components": [
                {"ref": "R1", "type": "R", "value": 1000,
                 "pins": {"1": "A B", "2": "GND"}},
            ],
        }
        result = validate_spec(spec)
        self.assertFalse(result["ok"])
        self.assertTrue(any("whitespace" in e for e in result["errors"]))

    def test_spice_net_collision_is_rejected(self):
        spec = {
            "name": "bad_node",
            "ground": "GND",
            "components": [
                {"ref": "R1", "type": "R", "value": 1000,
                 "pins": {"1": "5V", "2": "N5V"}},
                {"ref": "R2", "type": "R", "value": 1000,
                 "pins": {"1": "GND", "2": "GND"}},
            ],
        }
        result = validate_spec(spec)
        self.assertFalse(result["ok"])
        self.assertTrue(any("map to SPICE node" in e for e in result["errors"]))

    def test_duplicate_spice_element_is_rejected(self):
        pins = {"1": "INP", "2": "INN", "3": "VCC", "4": "VEE", "5": "OUT"}
        spec = {
            "name": "bad_ref",
            "ground": "GND",
            "components": [
                {"ref": "U1", "type": "OPAMP", "value": 100000,
                 "model": "OPAMP_GEN", "pins": pins},
                {"ref": "XU1", "type": "OPAMP", "value": 100000,
                 "model": "OPAMP_GEN", "pins": pins},
                {"ref": "R1", "type": "R", "value": 1000,
                 "pins": {"1": "OUT", "2": "GND"}},
            ],
        }
        result = validate_spec(spec)
        self.assertFalse(result["ok"])
        self.assertTrue(any("map to SPICE element" in e for e in result["errors"]))


if __name__ == "__main__":
    unittest.main()
