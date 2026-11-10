"""Checks the TPS5430DDA package pin map against its sourced datasheet record."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN_MAP = ROOT / "examples" / "tps5430d-da-pin-map.json"


class TestTPS5430PinMap(unittest.TestCase):
    def test_eight_signal_pins_match_ti_datasheet(self):
        mapping = json.loads(PIN_MAP.read_text(encoding="utf-8"))
        self.assertEqual(mapping["device"], "Texas Instruments TPS5430")
        self.assertEqual(mapping["orderable_part"], "TPS5430DDA")
        self.assertEqual(mapping["datasheet"]["document"], "SLVS632")
        self.assertEqual(mapping["datasheet"]["section"], "4, Pin Configuration and Functions")
        self.assertEqual(
            {number: pin["name"] for number, pin in mapping["symbol"]["pins"].items()},
            {
                "1": "BOOT",
                "2": "NC",
                "3": "NC",
                "4": "VSENSE",
                "5": "ENA",
                "6": "GND",
                "7": "VIN",
                "8": "PH",
                "9": "DAP",
            },
        )

    def test_exposed_pad_is_explicitly_grounded_but_not_faked_as_ic8_pin(self):
        mapping = json.loads(PIN_MAP.read_text(encoding="utf-8"))
        pad = mapping["exposed_pad"]
        self.assertEqual(pad["package_terminal"], "DAP")
        self.assertIsNone(pad["pin_number"])
        self.assertEqual(pad["net"], "GND")
        self.assertEqual(pad["schematic_symbol_pin_number"], "9")
        self.assertIn("internal placeholder", " ".join(mapping["limitations"]).lower())

    def test_mapping_does_not_claim_electrical_or_hardware_validation(self):
        mapping = json.loads(PIN_MAP.read_text(encoding="utf-8"))
        limitations = " ".join(mapping["limitations"]).lower()
        self.assertIn("internal placeholder", limitations)
        self.assertIn("electrical simulation", limitations)
        self.assertIn("hardware readiness", limitations)


if __name__ == "__main__":
    unittest.main()
