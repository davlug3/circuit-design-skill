import unittest

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from generate_with_footprints import assign_common_footprints


class TestCommonFootprints(unittest.TestCase):
    def test_smd_defaults_only_cover_common_passives_and_mark_them_provisional(self):
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
        self.assertNotIn("D1", assigned)
        self.assertNotIn("LED1", assigned)
        self.assertNotIn("Q1", assigned)
        self.assertNotIn("U1", assigned)
        self.assertEqual(spec["components"][0]["footprint_status"], "provisional")
        self.assertFalse(spec["components"][0]["pad_map_verified"])

    def test_through_hole_defaults(self):
        spec = {"components": [
            {"ref": "R1", "type": "R"},
            {"ref": "LED1", "type": "LED"},
            {"ref": "L1", "type": "L"},
            {"ref": "Q1", "type": "NPN"},
            {"ref": "U1", "type": "OPAMP"},
        ]}
        assigned = assign_common_footprints(spec, "through-hole")
        self.assertIn("P7.62mm", assigned["R1"])
        self.assertNotIn("LED1", assigned)
        self.assertIn("L1", assigned)
        self.assertNotIn("Q1", assigned)
        self.assertNotIn("U1", assigned)

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
