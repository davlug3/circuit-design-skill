"""Tests for the ASCII rawfile parser used by the ngspice check."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from verify import _parse_ascii_raw  # noqa: E402

RAW = """Title: rc_lowpass
Date: Sun Nov  8 06:00:00 2026
Plotname: Operating Point
Flags: real
No. Variables: 3
No. Points: 1
Variables:
\t0\ttime\ttime
\t1\tv(in)\tvoltage
\t2\tv(out)\tvoltage
Values:
0\t0.000000000000000e+00
\t1.000000000000000e+00
\t9.990000000000000e-01
Plotname: AC Analysis
Flags: complex
No. Variables: 2
No. Points: 2
Variables:
\t0\tfrequency\tfrequency
\t1\tv(out)\tvoltage
Values:
0\t1.000000000000000e+01
\t9.999999999999999e-01,0.000000000000000e+00
1\t1.000000000000000e+03
\t9.999999999999999e-01,-6.283185307179586e-03
"""


class TestAsciiRaw(unittest.TestCase):
    def test_parses_both_plots(self):
        plots = _parse_ascii_raw(RAW)
        self.assertEqual(list(plots), ["Operating Point", "AC Analysis"])
        self.assertEqual(plots["Operating Point"]["vars"], ["time", "v(in)", "v(out)"])
        self.assertEqual(plots["Operating Point"]["values"],
                         ["0.000000000000000e+00", "1.000000000000000e+00",
                          "9.990000000000000e-01"])
        self.assertEqual(plots["AC Analysis"]["vars"], ["frequency", "v(out)"])
        self.assertEqual(len(plots["AC Analysis"]["values"]), 4)

    def test_garbage_is_empty(self):
        self.assertEqual(_parse_ascii_raw("not a rawfile"), {})


if __name__ == "__main__":
    unittest.main()
