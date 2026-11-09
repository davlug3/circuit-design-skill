"""Regression checks for the datasheet-backed TPS5430 buck design study."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "examples" / "buck-tps5430-design.md"


class TestTPS5430BuckReference(unittest.TestCase):
    def test_reference_design_is_grounded_and_scoped(self):
        plan = PLAN.read_text(encoding="utf-8")
        for text in (
            "TPS5430DDA",
            "10.8 V to 19.8 V",
            "5.0 V at 2.0 A",
            "10 µF",
            "B340A",
            "15 µH",
            "220 µF",
            "3.24 kΩ",
            "SLVMAC8.ZIP",
            "SLVMCU8.ZIP",
            "SLVS632K",
            "https://www.ti.com/lit/ds/symlink/tps5430.pdf",
        ):
            self.assertIn(text, plan)

        # Do not let a reference design or vendor model be mistaken for
        # validated hardware or a model already integrated into the generator.
        self.assertIn("Not approved for PCB release", plan)
        self.assertIn("has not been copied into this repository", plan)
        self.assertIn("model has not", plan.lower())
        self.assertIn("thermal", plan.lower())
        self.assertIn("bench", plan.lower())

    def test_feedback_and_load_arithmetic_are_explicit(self):
        plan = PLAN.read_text(encoding="utf-8")
        self.assertIn("4.9895 V", plan)
        self.assertIn("2.5 Ω", plan)
        self.assertIn("10 W", plan)
        self.assertIn("0.99 A p-p", plan)
        self.assertIn("2.50 A", plan)


if __name__ == "__main__":
    unittest.main()
