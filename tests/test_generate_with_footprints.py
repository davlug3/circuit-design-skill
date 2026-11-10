import unittest

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from generate_with_footprints import (
    assign_common_footprints,
    semiconductor_refs_requiring_research,
)


class TestCommonFootprints(unittest.TestCase):
    def test_smd_defaults_cover_common_passives_only(self):
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
        self.assertEqual(assigned["L1"], "Inductor_SMD:L_0805_2012Metric")
        self.assertNotIn("D1", assigned)
        self.assertNotIn("LED1", assigned)
        self.assertNotIn("Q1", assigned)
        self.assertNotIn("U1", assigned)
        self.assertEqual(
            semiconductor_refs_requiring_research(spec),
            ["D1", "LED1", "Q1", "U1"],
        )

    def test_through_hole_defaults_cover_passives_only(self):
        spec = {"components": [
            {"ref": "R1", "type": "R"},
            {"ref": "C1", "type": "C"},
            {"ref": "LED1", "type": "LED"},
            {"ref": "L1", "type": "L"},
            {"ref": "Q1", "type": "NPN"},
            {"ref": "U1", "type": "OPAMP"},
        ]}
        assigned = assign_common_footprints(spec, "through-hole")
        self.assertIn("P12.70mm", assigned["R1"])
        self.assertIn("DIN0309", assigned["R1"])
        self.assertIn("C1", assigned)
        self.assertIn("L1", assigned)
        self.assertNotIn("LED1", assigned)
        self.assertNotIn("Q1", assigned)
        self.assertNotIn("U1", assigned)

    def test_existing_footprint_is_preserved(self):
        spec = {"components": [
            {"ref": "Q1", "type": "NPN", "footprint": "Package_TO_SOT_THT:TO-92_Inline"}
        ]}
        self.assertEqual(assign_common_footprints(spec, "through-hole"), {})
        self.assertEqual(semiconductor_refs_requiring_research(spec), [])

    def test_invalid_assembly_is_rejected(self):
        with self.assertRaises(ValueError):
            assign_common_footprints({"components": []}, "mixed")


if __name__ == "__main__":
    unittest.main()
