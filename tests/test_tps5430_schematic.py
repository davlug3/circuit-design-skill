"""Regression checks for the TPS5430DDA schematic symbol and reference design."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.design_spec import validate_spec
from scripts.generate import kicad_schematic
from scripts.symbols import KICAD_PINS, KICAD_PIN_NAMES, KICAD_PIN_TYPES, kicad_lib_symbols

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "examples" / "tps5430-12v-5v-2a.json"
PIN_MAP_PATH = ROOT / "examples" / "tps5430d-da-pin-map.json"


class TestTPS5430Schematic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))

    def test_device_symbol_has_named_eight_pins_and_exposed_pad(self):
        self.assertEqual(set(KICAD_PINS["TPS5430"]), {str(n) for n in range(1, 10)})
        self.assertEqual(
            KICAD_PIN_NAMES["TPS5430"],
            {"1": "BOOT", "2": "NC", "3": "NC", "4": "VSENSE",
             "5": "ENA", "6": "GND", "7": "VIN", "8": "PH", "9": "DAP"},
        )
        self.assertEqual(KICAD_PIN_TYPES["TPS5430"]["2"], "no_connect")
        self.assertEqual(KICAD_PIN_TYPES["TPS5430"]["3"], "no_connect")
        self.assertEqual(KICAD_PINS["TPS5430"]["9"][3], 1.27)

    def test_embedded_kicad_symbol_preserves_pin_names_types_and_numbers(self):
        library = kicad_lib_symbols(["TPS5430"])
        for name in ("BOOT", "NC", "VSENSE", "ENA", "GND", "VIN", "PH", "DAP"):
            self.assertIn(f'(name "{name}"', library)
        self.assertIn('(pin output line', library)
        self.assertIn('(pin no_connect line', library)
        for number in range(1, 10):
            self.assertIn(f'(number "{number}"', library)

    def test_reference_spec_validates_and_limits_unsupported_deliverables(self):
        result = validate_spec(self.spec)
        self.assertTrue(result["ok"], result["errors"])
        self.assertNotIn("spice", self.spec["deliverables"])
        self.assertNotIn("ltspice_asc", self.spec["deliverables"])
        self.assertNotIn("pcb", self.spec["deliverables"])

        bad = dict(self.spec)
        bad["deliverables"] = ["kicad_sch", "spice"]
        rejected = validate_spec(bad)
        self.assertFalse(rejected["ok"])
        self.assertTrue(any("TPS5430" in error and "spice" in error for error in rejected["errors"]))

    def test_generated_schematic_maps_controller_and_power_stage_nets(self):
        schematic = kicad_schematic(self.spec)
        self.assertIn('"circuit:TPS5430"', schematic)
        for net in ("BOOT", "FB", "VIN", "SW", "OUT", "GND"):
            self.assertIn(f'(global_label "{net}"', schematic)
        self.assertEqual(schematic.count("(no_connect (at "), 3)
        self.assertIn('(number "9"', schematic)
        # Pin 9 (DAP) and pin 6 (GND) share the same net.
        u1 = next(comp for comp in self.spec["components"] if comp["ref"] == "U1")
        self.assertEqual(u1["pins"]["6"], "GND")
        self.assertEqual(u1["pins"]["9"], "GND")
        self.assertEqual(u1["no_connect_pins"], ["2", "3", "5"])
        # Catch diode orientation and bootstrap capacitor are explicit.
        d1 = next(comp for comp in self.spec["components"] if comp["ref"] == "D1")
        c2 = next(comp for comp in self.spec["components"] if comp["ref"] == "C2")
        self.assertEqual(d1["pins"], {"1": "GND", "2": "SW"})
        self.assertEqual(c2["pins"], {"1": "BOOT", "2": "SW"})

    def test_pin_map_matches_current_ti_datasheet_revision(self):
        mapping = json.loads(PIN_MAP_PATH.read_text(encoding="utf-8"))
        self.assertEqual(mapping["datasheet"]["document"], "SLVS632")
        self.assertEqual(mapping["datasheet"]["revision"], "L")
        self.assertEqual(mapping["symbol"]["pins"]["8"]["name"], "PH")
        self.assertEqual(mapping["exposed_pad"]["net"], "GND")


if __name__ == "__main__":
    unittest.main()
