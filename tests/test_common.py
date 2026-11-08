"""Unit tests for value parsing, formatting and E-series helpers."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from circuit_common import (  # noqa: E402
    ValueParseError,
    divider_ratio,
    dumps,
    nearest_eseries,
    parallel,
    parse_value,
    si_number,
    spice_number,
)


class TestParseValue(unittest.TestCase):
    def test_plain_and_si(self):
        self.assertAlmostEqual(parse_value("1k")[0], 1e3)
        self.assertAlmostEqual(parse_value("4k7")[0], 4.7e3)
        self.assertAlmostEqual(parse_value("2u2")[0], 2.2e-6)
        self.assertAlmostEqual(parse_value("1r5")[0], 1.5)
        self.assertAlmostEqual(parse_value("100n")[0], 100e-9)
        self.assertAlmostEqual(parse_value("1meg")[0], 1e6)
        self.assertAlmostEqual(parse_value("10kohm")[0], 1e4)
        self.assertAlmostEqual(parse_value("5V")[0], 5.0)
        self.assertAlmostEqual(parse_value("1e-6")[0], 1e-6)
        self.assertAlmostEqual(parse_value("2.2")[0], 2.2)

    def test_m_is_milli_and_warns(self):
        value, warnings = parse_value("1M", name="R1")
        self.assertEqual(value, 1e-3)
        self.assertTrue(any("milli" in w for w in warnings))

    def test_mil(self):
        self.assertAlmostEqual(parse_value("10mil")[0], 254e-6)

    def test_micro_symbol(self):
        self.assertAlmostEqual(parse_value("10µ")[0], 10e-6)
        self.assertAlmostEqual(parse_value("10μ")[0], 10e-6)

    def test_invalid(self):
        for bad in ("", "abc", "1kx", "1..2"):
            with self.assertRaises(ValueParseError):
                parse_value(bad)


class TestFormatting(unittest.TestCase):
    def test_spice_number(self):
        self.assertEqual(spice_number(1000), "1k")
        self.assertEqual(spice_number(1e6), "1Meg")
        self.assertEqual(spice_number(1e-6), "1u")
        self.assertEqual(spice_number(4.7e3), "4.7k")
        self.assertEqual(spice_number(0), "0")

    def test_si_number(self):
        self.assertEqual(si_number(1591.55, "Hz"), "1.59155 kHz")
        self.assertEqual(si_number(1e-9, "F"), "1 nF")

    def test_eseries(self):
        result = nearest_eseries(1000, "E24")
        self.assertEqual(result["value"], 1000.0)
        self.assertAlmostEqual(result["error_percent"], 0.0)
        up = nearest_eseries(1000, "E24", "up")
        self.assertGreaterEqual(up["value"], 1000.0)

    def test_parallel_and_divider(self):
        self.assertAlmostEqual(parallel(1000, 1000), 500.0)
        self.assertAlmostEqual(divider_ratio(10e3, 4.7e3), 4.7 / 14.7)
        self.assertTrue(math.isinf(parallel()))

    def test_dumps_handles_non_finite(self):
        import json
        text = dumps({"a": math.inf, "b": -math.inf, "c": math.nan,
                      "nested": [math.inf]})
        data = json.loads(text)
        self.assertEqual(data["a"], "Infinity")
        self.assertEqual(data["b"], "-Infinity")
        self.assertEqual(data["c"], "NaN")
        self.assertEqual(data["nested"], ["Infinity"])


if __name__ == "__main__":
    unittest.main()
