"""Tests for the generic numbered eight-pin KiCad symbol."""

from __future__ import annotations

import unittest

from scripts.symbols import KICAD_PINS, kicad_lib_symbols, kicad_pins
from scripts.generate import kicad_schematic


class TestGenericIC8Symbol(unittest.TestCase):
    def test_symbol_has_eight_distinct_numbered_pins(self):
        pins = KICAD_PINS["IC8"]
        self.assertEqual(set(pins), {str(n) for n in range(1, 9)})
        world = kicad_pins("IC8", 50.8, 50.8)
        self.assertEqual(set(world), set(pins))
        self.assertEqual(len({(point[0], point[1]) for point in world.values()}), 8)

    def test_embedded_library_contains_generic_body_and_all_pin_numbers(self):
        library = kicad_lib_symbols(["IC8"])
        self.assertIn('"circuit:IC8"', library)
        for number in range(1, 9):
            self.assertIn(f'(number "{number}"', library)

    def test_schematic_emits_pin_labels_and_instances(self):
        spec = {
            "name": "ic8-symbol-check",
            "ground": "GND",
            "components": [{
                "ref": "U1", "type": "IC8", "value": 0,
                "pins": {str(n): f"NET{n}" for n in range(1, 9)},
            }],
        }
        schematic = kicad_schematic(spec)
        for number in range(1, 9):
            self.assertIn(f'(global_label "NET{number}"', schematic)
            self.assertIn(f'(pin "{number}"', schematic)


if __name__ == "__main__":
    unittest.main()
