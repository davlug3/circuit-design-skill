"""Tests for the ASCII rawfile parser used by the ngspice check."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ngspice_raw import find_plot, parse_raw  # noqa: E402

OP_AC = """Title: rc_lowpass
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

TRAN = """Title: sine
Plotname: Transient Analysis
Flags: real
No. Variables: 3
No. Points: 3
Variables:
\t0\ttime\ttime
\t1\tv(in)\tvoltage
\t2\tv(out)\tvoltage
Values:
0\t0.000000000000000e+00
\t0.000000000000000e+00
\t0.000000000000000e+00
1\t1.000000000000000e-04
\t1.000000000000000e+00
\t5.000000000000000e-01
2\t2.000000000000000e-04
\t0.000000000000000e+00
\t1.000000000000000e+00
"""

NOISE = """Title: noise
Plotname: Noise Analysis
Flags: real
No. Variables: 3
No. Points: 2
Variables:
\t0\tfrequency\tfrequency
\t1\tonoise_spectrum\tvoltage
\t2\tinoise_spectrum\tvoltage
Values:
0\t1.000000000000000e+01
\t1.000000000000000e-09
\t2.000000000000000e-09
1\t1.000000000000000e+03
\t1.000000000000000e-09
\t2.000000000000000e-09
"""

DC_TRANSFER = """Title: sweep
Plotname: DC transfer characteristic
Flags: real
No. Variables: 2
No. Points: 1
Variables:
\t0\tv-sweep\tvoltage
\t1\tv(out)\tvoltage
Values:
0\t0.000000000000000e+00
\t1.000000000000000e+00
"""

TRUNCATED = """Title: broken
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
"""

# Layout emitted by ngspice's ASCII writer: complex values, a blank line after
# every point, and an extra informational line in the variable table.
REAL_LAYOUT = """Title: rc lowpass
Date: Mon Oct  5 18:00:00 2026
Command: ngspice-47+, Build
Plotname: AC Analysis
Flags: complex
No. Variables: 3
No. Points: 2
Variables:
\t0\tfrequency\tfrequency
\t1\tv(out)\tvoltage
\t2\ti(v1)\tcurrent
No. of Data Columns : 3
Values:
 0\t1.000000000000000e+02,0.000000000000000e+00
\t9.900000000000000e-01,-1.000000000000000e-02
\t-1.000000000000000e-03,1.000000000000000e-05

 1\t1.000000000000000e+03,0.000000000000000e+00
\t9.000000000000000e-01,-1.000000000000000e-01
\t-1.000000000000000e-03,1.000000000000000e-04
"""


class TestAsciiRaw(unittest.TestCase):
    def test_parses_both_plots(self):
        plots = parse_raw(OP_AC)
        self.assertEqual(list(plots), ["Operating Point", "AC Analysis"])
        op = plots["Operating Point"]
        self.assertEqual(op.variables, ["time", "v(in)", "v(out)"])
        self.assertEqual(op.points, [[0.0, 1.0, 0.999]])
        ac = plots["AC Analysis"]
        self.assertTrue(ac.is_complex)
        self.assertEqual(ac.variables, ["frequency", "v(out)"])
        self.assertEqual(ac.scale(), [10.0, 1000.0])
        values = ac.column("v(out)")
        self.assertAlmostEqual(values[0].real, 0.9999999999999999)
        self.assertAlmostEqual(values[1].imag, -0.006283185307179586)

    def test_parses_multivariable_transient(self):
        plot = parse_raw(TRAN)["Transient Analysis"]
        self.assertEqual(plot.scale(), [0.0, 1e-4, 2e-4])
        self.assertEqual(plot.column("v(out)"), [0.0, 0.5, 1.0])
        self.assertEqual(plot.column("v(in)"), [0.0, 1.0, 0.0])

    def test_parses_noise_spectra(self):
        plot = parse_raw(NOISE)["Noise Analysis"]
        self.assertEqual(plot.column("onoise_spectrum"), [1e-9, 1e-9])
        self.assertEqual(plot.column("inoise_spectrum"), [2e-9, 2e-9])

    def test_parses_real_ngspice_complex_layout(self):
        plot = parse_raw(REAL_LAYOUT)["AC Analysis"]
        self.assertEqual(plot.variables, ["frequency", "v(out)", "i(v1)"])
        self.assertEqual(len(plot.points), 2)
        self.assertEqual(plot.points[0][0], complex(100.0, 0.0))
        self.assertEqual(plot.points[1][1], complex(0.9, -0.1))
        self.assertEqual(plot.points[1][2], complex(-1e-3, 1e-4))
        self.assertEqual(plot.scale(), [100.0, 1000.0])

    def test_column_lookup_is_case_insensitive(self):
        plot = parse_raw(OP_AC)["Operating Point"]
        self.assertEqual(plot.column("V(OUT)"), [0.999])

    def test_missing_column_reports_available_names(self):
        plot = parse_raw(OP_AC)["Operating Point"]
        with self.assertRaisesRegex(KeyError, "available: time, v\\(in\\), v\\(out\\)"):
            plot.column("v(nope)")

    def test_truncated_point_is_not_invented(self):
        plot = parse_raw(TRUNCATED)["AC Analysis"]
        self.assertEqual(len(plot.points), 1)

    def test_find_plot(self):
        plots = parse_raw(OP_AC + TRAN + NOISE)
        self.assertEqual(find_plot(plots, "op").name, "Operating Point")
        self.assertEqual(find_plot(plots, "ac").name, "AC Analysis")
        self.assertEqual(find_plot(plots, "tran").name, "Transient Analysis")
        self.assertEqual(find_plot(plots, "noise").name, "Noise Analysis")
        self.assertIsNone(find_plot(plots, "missing"))

    def test_find_plot_tran_ignores_dc_transfer_characteristic(self):
        # "DC transfer characteristic" contains "tran"; a naive substring
        # match returned it as the transient plot and broke time-domain
        # metrics.  The word-boundary match must skip it.
        only_dc = parse_raw(DC_TRANSFER)
        self.assertIsNone(find_plot(only_dc, "tran"))
        mixed = parse_raw(OP_AC + DC_TRANSFER + TRAN)
        self.assertEqual(find_plot(mixed, "tran").name, "Transient Analysis")


if __name__ == "__main__":
    unittest.main()
