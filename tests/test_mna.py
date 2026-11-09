"""Tests for the pure-Python MNA solver."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from circuit_calc import calc_sallen_key  # noqa: E402
from mna import Circuit, MNAError, UnsupportedElement, from_components  # noqa: E402


class TestBasicMNA(unittest.TestCase):
    def test_divider(self):
        comps = [
            {"ref": "V1", "type": "V", "value": 0, "dc": 12, "pins": {"1": "IN", "2": "GND"}},
            {"ref": "R1", "type": "R", "value": 10e3, "pins": {"1": "IN", "2": "OUT"}},
            {"ref": "R2", "type": "R", "value": 4.7e3, "pins": {"1": "OUT", "2": "GND"}},
        ]
        c = from_components(comps, ground="GND")
        sol = c.solve_dc()
        self.assertAlmostEqual(sol["OUT"].real, 12 * 4.7 / 14.7, places=9)

    def test_rc_corner(self):
        comps = [
            {"ref": "V1", "type": "V", "value": 0, "dc": 0, "ac": 1,
             "pins": {"1": "IN", "2": "GND"}},
            {"ref": "R1", "type": "R", "value": 1e3, "pins": {"1": "IN", "2": "OUT"}},
            {"ref": "C1", "type": "C", "value": 100e-9, "pins": {"1": "OUT", "2": "GND"}},
        ]
        c = from_components(comps, ground="GND")
        fc = c.find_cutoff("OUT", "IN", passband="low", f_min=1, f_max=1e6)
        self.assertAlmostEqual(fc, 1 / (2 * math.pi * 1e3 * 100e-9), delta=5)

    def test_rc_highpass_corner(self):
        comps = [
            {"ref": "V1", "type": "V", "value": 0, "dc": 0, "ac": 1,
             "pins": {"1": "IN", "2": "GND"}},
            {"ref": "C1", "type": "C", "value": 100e-9, "pins": {"1": "IN", "2": "OUT"}},
            {"ref": "R1", "type": "R", "value": 1e3, "pins": {"1": "OUT", "2": "GND"}},
        ]
        c = from_components(comps, ground="GND")
        fc = c.find_cutoff("OUT", "IN", passband="high", f_min=1, f_max=1e6)
        self.assertAlmostEqual(fc, 1 / (2 * math.pi * 1e3 * 100e-9), delta=5)

    def test_opamp_gain(self):
        comps = [
            {"ref": "V1", "type": "V", "value": 0, "dc": 0, "ac": 1,
             "pins": {"1": "IN", "2": "GND"}},
            {"ref": "RF", "type": "R", "value": 9e3, "pins": {"1": "OUT", "2": "N"}},
            {"ref": "RG", "type": "R", "value": 1e3, "pins": {"1": "N", "2": "GND"}},
            {"ref": "U1", "type": "OPAMP", "value": 1e6,
             "pins": {"1": "IN", "2": "N", "3": "VCC", "4": "VEE", "5": "OUT"}},
            {"ref": "V2", "type": "V", "value": 0, "dc": 5, "pins": {"1": "VCC", "2": "GND"}},
            {"ref": "V3", "type": "V", "value": 0, "dc": -5, "pins": {"1": "VEE", "2": "GND"}},
        ]
        c = from_components(comps, ground="GND")
        self.assertAlmostEqual(abs(c.ac_gain("OUT", "IN", 10.0)), 10.0, delta=0.05)

    def test_rejects_nonlinear(self):
        with self.assertRaises(UnsupportedElement):
            from_components([{"ref": "D1", "type": "D", "value": 0,
                              "pins": {"1": "A", "2": "K"}}], ground="K")

    def test_extreme_resistance_scales(self):
        # A 1e20-ohm path has a 1e-20 S conductance. It is valid and must
        # not be rejected by an absolute pivot threshold.
        c = Circuit(ground="GND")
        c.I("I1", "GND", "OUT", dc=1e-12)
        c.R("R1", "OUT", "GND", 1e20)
        self.assertAlmostEqual(c.dc_voltage("OUT"), 1e8, delta=1e-3)

        # Also cover a very large conductance / branch-current scale.
        c = Circuit(ground="GND")
        c.V("V1", "IN", "GND", dc=1.0)
        c.R("R1", "IN", "GND", 1e-12)
        sol = c.solve_dc()
        self.assertAlmostEqual(sol["IN"].real, 1.0, places=12)
        self.assertAlmostEqual(abs(sol["@V1"].real), 1e12, delta=1e3)

    def test_singular(self):
        c = Circuit(ground="GND")
        c.R("R1", "A", "GND", 1000)
        c.V("V1", "A", "GND", dc=1)
        c.V("V2", "A", "GND", dc=2)
        with self.assertRaises(MNAError):
            c.solve_dc()


class TestActiveFilters(unittest.TestCase):
    def _build(self, topology: str) -> tuple[Circuit, float]:
        design = calc_sallen_key({"topology": topology, "fc": 1000,
                                  "q": 1 / math.sqrt(2)})
        r = design["results"]
        if topology == "lowpass":
            comps = [
                {"ref": "V1", "type": "V", "value": 0, "dc": 0, "ac": 1,
                 "pins": {"1": "IN", "2": "GND"}},
                {"ref": "R1", "type": "R", "value": r["r1_ohm"], "pins": {"1": "IN", "2": "A"}},
                {"ref": "R2", "type": "R", "value": r["r2_ohm"], "pins": {"1": "A", "2": "P"}},
                {"ref": "C1", "type": "C", "value": r["c1_F"], "pins": {"1": "A", "2": "OUT"}},
                {"ref": "C2", "type": "C", "value": r["c2_F"], "pins": {"1": "P", "2": "GND"}},
            ]
        else:
            comps = [
                {"ref": "V1", "type": "V", "value": 0, "dc": 0, "ac": 1,
                 "pins": {"1": "IN", "2": "GND"}},
                {"ref": "C1", "type": "C", "value": r["c1_F"], "pins": {"1": "IN", "2": "A"}},
                {"ref": "C2", "type": "C", "value": r["c2_F"], "pins": {"1": "A", "2": "P"}},
                {"ref": "R1", "type": "R", "value": r["r1_ohm"], "pins": {"1": "A", "2": "OUT"}},
                {"ref": "R2", "type": "R", "value": r["r2_ohm"], "pins": {"1": "P", "2": "GND"}},
            ]
        comps += [
            {"ref": "U1", "type": "OPAMP", "value": 1e6,
             "pins": {"1": "P", "2": "OUT", "3": "VCC", "4": "VEE", "5": "OUT"}},
            {"ref": "V2", "type": "V", "value": 0, "dc": 5, "pins": {"1": "VCC", "2": "GND"}},
            {"ref": "V3", "type": "V", "value": 0, "dc": -5, "pins": {"1": "VEE", "2": "GND"}},
        ]
        return from_components(comps, ground="GND"), r["fc_Hz"]

    def test_lowpass_corner(self):
        c, fc = self._build("lowpass")
        actual = c.find_cutoff("OUT", "IN", passband="low", f_min=1, f_max=1e4)
        self.assertAlmostEqual(actual, fc, delta=fc * 0.01)

    def test_highpass_corner(self):
        c, fc = self._build("highpass")
        actual = c.find_cutoff("OUT", "IN", passband="high", f_min=1, f_max=1e4)
        self.assertAlmostEqual(actual, fc, delta=fc * 0.01)


if __name__ == "__main__":
    unittest.main()
