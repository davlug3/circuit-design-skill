"""Tests for the closed-form calculators."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from circuit_calc import (  # noqa: E402
    calc_adc,
    calc_battery,
    calc_buck,
    calc_divider,
    calc_i2c,
    calc_led,
    calc_logic,
    calc_noise,
    calc_rc,
    calc_sallen_key,
    calc_thermal,
    calc_trace,
    calc_zener,
)


class TestPassive(unittest.TestCase):
    def test_divider(self):
        out = calc_divider({"vin": 12, "r1": 10e3, "r2": 4.7e3})
        self.assertTrue(out["ok"])
        self.assertAlmostEqual(out["results"]["vout_V"], 12 * 4.7 / 14.7, places=9)
        self.assertAlmostEqual(out["results"]["thevenin_resistance_ohm"],
                               1 / (1 / 10e3 + 1 / 4.7e3), places=6)

    def test_divider_loaded(self):
        out = calc_divider({"vin": 12, "r1": 10e3, "r2": 10e3, "rload": 10e3})
        self.assertLess(out["results"]["vout_loaded_V"], out["results"]["vout_V"])
        self.assertLess(out["results"]["loading_error_percent"], 0)

    def test_rc_lowpass(self):
        out = calc_rc({"r": 1e3, "c": 100e-9})
        self.assertAlmostEqual(out["results"]["fc_Hz"], 1 / (2 * math.pi * 1e3 * 100e-9))
        self.assertAlmostEqual(out["results"]["tau_s"], 1e-4)

    def test_rc_highpass_at_corner(self):
        out = calc_rc({"r": 1e3, "c": 100e-9, "mode": "highpass", "f": 1591.5494})
        self.assertAlmostEqual(out["results"]["magnitude"], 1 / math.sqrt(2), places=4)
        self.assertAlmostEqual(out["results"]["phase_deg"], 45.0, places=2)

    def test_rc_design_from_fc(self):
        out = calc_rc({"fc": 1e3, "c": 100e-9})
        self.assertAlmostEqual(out["results"]["r_ohm"], 1 / (2 * math.pi * 1e3 * 100e-9))


class TestSallenKey(unittest.TestCase):
    def test_lowpass_butterworth(self):
        out = calc_sallen_key({"topology": "lowpass", "fc": 1000, "q": 0.70710678})
        r = out["results"]
        self.assertAlmostEqual(r["c1_over_c2"], 2.0, places=3)
        self.assertAlmostEqual(r["r1_ohm"], r["r2_ohm"], places=6)
        self.assertAlmostEqual(r["fc_Hz"], 1000, places=6)

    def test_highpass_butterworth(self):
        out = calc_sallen_key({"topology": "highpass", "fc": 1000, "q": 0.70710678})
        r = out["results"]
        self.assertAlmostEqual(r["r1_over_r2"], 0.5, places=3)
        self.assertAlmostEqual(r["c1_F"], r["c2_F"], places=12)

    def test_highpass_analysis_q(self):
        # Equal C, R2 = 2*R1 -> Q = 0.7071 for the high-pass topology.
        out = calc_sallen_key({
            "topology": "highpass", "r1": 1e3, "r2": 2e3,
            "c1": 10e-9, "c2": 10e-9,
        })
        self.assertAlmostEqual(out["results"]["q"], 1 / math.sqrt(2), places=6)

    def test_lowpass_analysis_q(self):
        out = calc_sallen_key({
            "topology": "lowpass", "r1": 1e3, "r2": 1e3,
            "c1": 20e-9, "c2": 10e-9,
        })
        self.assertAlmostEqual(out["results"]["q"], 1 / math.sqrt(2), places=6)

    def test_peaking_only_above_critical_q(self):
        flat = calc_sallen_key({
            "topology": "lowpass", "r1": 1e3, "r2": 1e3,
            "c1": 12e-9, "c2": 10e-9,
        })
        self.assertEqual(flat["results"]["peaking_dB"], 0.0)
        peaked = calc_sallen_key({
            "topology": "lowpass", "r1": 1e3, "r2": 1e3,
            "c1": 40e-9, "c2": 10e-9,
        })
        self.assertGreater(peaked["results"]["peaking_dB"], 0.0)


class TestPower(unittest.TestCase):
    def test_buck(self):
        out = calc_buck({"vin": 12, "vout": 5, "iout": 2, "fsw": 500e3})
        r = out["results"]
        self.assertAlmostEqual(r["duty_cycle"], 5 / 12, places=6)
        self.assertGreater(r["inductor_required_H"], 0)
        self.assertGreater(r["inductor_peak_A"], 2.0)
        self.assertGreater(r["output_cap_required_F"], 0)

    def test_led(self):
        out = calc_led({"vs": 5, "vf": 2.0, "if": 0.01})
        self.assertAlmostEqual(out["results"]["series_resistance_ohm"], 300.0, places=6)

    def test_zener(self):
        out = calc_zener({
            "vin_min": 10, "vin_max": 14, "vz": 5.1,
            "iz_min": 1e-3, "iz_max": 20e-3,
            "il_min": 0, "il_max": 5e-3, "rs": 470,
        })
        self.assertTrue(out["ok"])
        self.assertGreater(out["results"]["p_zener_max_W"], 0)

    def test_i2c(self):
        out = calc_i2c({"vdd": 3.3, "cb": 200e-12, "rp": 1.5e3})
        r = out["results"]
        self.assertLessEqual(r["rp_min_ohm"], 1.5e3)
        self.assertGreaterEqual(r["rp_max_ohm"], 1.5e3)
        self.assertAlmostEqual(r["rise_time_s"], 0.8473 * 1.5e3 * 200e-12)

    def test_battery_efficiency_and_peukert(self):
        plain = calc_battery({"capacity_mah": 2000, "load_ma": 200})
        self.assertAlmostEqual(plain["results"]["runtime_h"], 8.0)
        lossy = calc_battery({"capacity_mah": 2000, "load_ma": 200, "efficiency": 0.8})
        self.assertAlmostEqual(lossy["results"]["runtime_h"], 6.4)
        peukert = calc_battery({
            "capacity_mah": 2000, "load_ma": 2000,
            "peukert": 1.2, "rated_hours": 20,
        })
        self.assertAlmostEqual(
            peukert["results"]["runtime_h"],
            20 * (2000 / (2000 * 20)) ** 1.2 * 0.8,
        )


class TestDigitalAndThermal(unittest.TestCase):
    def test_adc(self):
        out = calc_adc({"bits": 12, "vref": 3.3})
        r = out["results"]
        self.assertAlmostEqual(r["lsb_V"], 3.3 / 4096)
        self.assertAlmostEqual(r["snr_ideal_dB"], 6.02 * 12 + 1.76)
        self.assertEqual(r["codes"], 4096)

    def test_adc_enob(self):
        out = calc_adc({"bits": 16, "vref": 5, "sinad": 80})
        self.assertAlmostEqual(out["results"]["enob_bits"], (80 - 1.76) / 6.02)

    def test_thermal(self):
        out = calc_thermal({"p": 1.0, "ta": 25, "theta_ja": 50})
        self.assertAlmostEqual(out["results"]["tj_C"], 75.0, places=6)

    def test_hold_margin_sign(self):
        out = calc_logic({"vdd": 3.3, "tpd": 2e-9, "tcomb": 1e-9,
                          "tsu": 1e-9, "th": 0.5e-9})
        self.assertAlmostEqual(out["results"]["hold_margin_s"], 2.5e-9)

    def test_shot_noise_is_a_current(self):
        out = calc_noise({"r": 1e3, "bandwidth": 1.0, "shot_current": 1e-3})
        r = out["results"]
        expected = math.sqrt(2 * 1.602176634e-19 * 1e-3)
        self.assertAlmostEqual(r["shot_noise_Arms"], expected)
        self.assertAlmostEqual(r["shot_noise_Vrms"], expected * 1e3)

    def test_trace(self):
        out = calc_trace({"current": 1.0, "delta_t": 10, "internal": False})
        self.assertGreater(out["results"]["width_mil"], 0)
        self.assertGreater(out["results"]["area_mil2"], 0)


if __name__ == "__main__":
    unittest.main()
