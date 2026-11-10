import unittest

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from generate_with_footprints import assign_common_footprints


class TestCommonFootprints(unittest.TestCase):
    def test_smd_defaults_cover_common_passives_and_diodes(self):
        spec = {"components": [
            {"ref": "R1", "type": "R"},
            {"ref": "C1", "type": "C"},
            {"ref": "L1", "type": "L"},
            {"ref": "D1", "type": "D"},
            {"ref": "LED1", "type": "LED"},
            {"ref": "Q1", "type": "NPN"},
            {"ref": "U1", "type": "OPAMP"},
        ]}
        assigned = assign_common_footprints(spec, "smd")
        self.assertEqual(assigned["R1"], "Resistor_SMD:R_0805_2012Metric")
        self.assertEqual(assigned["C1"], "Capacitor_SMD:C_0805_2012Metric")
        self.assertEqual(assigned["D1"], "Diode_SMD:D_SOD-123")
        self.assertEqual(assigned["Q1"], "Package_TO_SOT_SMD:SOT-23")
        self.assertEqual(assigned["U1"], "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm")

    def test_through_hole_defaults(self):
        spec = {"components": [
            {"ref": "R1", "type": "R"},
            {"ref": "LED1", "type": "LED"},
            {"ref": "L1", "type": "L"},
            {"ref": "Q1", "type": "NPN"},
            {"ref": "U1", "type": "OPAMP"},
        ]}
        assigned = assign_common_footprints(spec, "through-hole")
        self.assertIn("P12.70mm", assigned["R1"])\n        self.assertIn("DIN0309", assigned["R1"])
        self.assertEqual(assigned["LED1"], "LED_THT:LED_D3.0mm")
        self.assertIn("L1", assigned)
        self.assertEqual(assigned["Q1"], "Package_TO_SOT_THT:TO-92_Inline")
        self.assertEqual(assigned["U1"], "Package_DIP:DIP-8_W7.62mm")

    def test_existing_footprint_is_preserved(self):
        spec = {"components": [
            {"ref": "R1", "type": "R", "footprint": "MyLibrary:Custom_R"}
        ]}
        self.assertEqual(assign_common_footprints(spec, "smd"), {})
        self.assertEqual(spec["components"][0]["footprint"], "MyLibrary:Custom_R")

    def test_invalid_assembly_is_rejected(self):
        with self.assertRaises(ValueError):
            assign_common_footprints({"components": []}, "mixed")


if __name__ == "__main__":
    unittest.main()
