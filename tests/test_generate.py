"""End-to-end generation tests."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate  # noqa: E402
from design_spec import validate_spec  # noqa: E402
from symbols import asc_pins  # noqa: E402
from verify import parse_sexp, sexp_children  # noqa: E402

EXAMPLES = ROOT / "examples"


class TestGenerateRC(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.spec_path = EXAMPLES / "rc-lowpass.json"
        self.result = generate.generate(self.spec_path, self.out)
        self.spec = self.result["spec"]
        self.name = self.spec["name"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_files(self):
        for suffix in (".cir", ".asc", ".models", ".net", ".kicad_sch",
                       "-bom.csv", "-report.md", "-report.json"):
            self.assertTrue((self.out / (self.name + suffix)).exists(), suffix)

    def test_netlist_devices(self):
        text = (self.out / f"{self.name}.cir").read_text()
        for ref in ("V1", "R1", "C1"):
            self.assertIn(f"\n{ref} ", text)
        self.assertIn(".ac dec", text)
        self.assertTrue(text.rstrip().endswith(".end"))

    def test_asc_flags(self):
        text = (self.out / f"{self.name}.asc").read_text()
        self.assertTrue(text.startswith("Version 4"))
        symbols = {}
        flags = {}
        current = None
        for line in text.splitlines():
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "SYMBOL":
                current = {"x": int(parts[2]), "y": int(parts[3]), "rot": int(parts[4][1:])}
            elif parts[0] == "SYMATTR" and parts[1] == "InstName":
                symbols[parts[2]] = current
            elif parts[0] == "FLAG":
                flags[(int(parts[1]), int(parts[2]))] = parts[3]
        for comp in self.spec["components"]:
            entry = symbols[comp["ref"]]
            for pin, (x, y) in asc_pins(comp["type"], entry["x"], entry["y"],
                                        entry["rot"], False).items():
                expected = generate.spice_net(comp["pins"][pin], self.spec["ground"])
                self.assertEqual(flags.get((x, y)), expected, f"{comp['ref']} pin {pin}")

    def test_kicad_netlist(self):
        root = parse_sexp((self.out / f"{self.name}.net").read_text())
        nets = {}
        for section in sexp_children(root, "nets"):
            for net in sexp_children(section, "net"):
                name = next(item[1] for item in net
                            if isinstance(item, list) and item[0] == "name")
                nodes = set()
                for item in net:
                    if isinstance(item, list) and item[0] == "node":
                        ref = next(sub[1] for sub in item
                                   if isinstance(sub, list) and sub[0] == "ref")
                        pin = next(sub[1] for sub in item
                                   if isinstance(sub, list) and sub[0] == "pin")
                        nodes.add((ref, pin))
                nets[name] = nodes
        self.assertEqual(nets["IN"], {("V1", "1"), ("R1", "1")})
        self.assertEqual(nets["OUT"], {("R1", "2"), ("C1", "1")})
        self.assertEqual(nets["GND"], {("V1", "2"), ("C1", "2")})

    def test_bom(self):
        text = (self.out / f"{self.name}-bom.csv").read_text()
        self.assertIn("R1", text)
        self.assertIn("C1", text)

    def test_report(self):
        text = (self.out / f"{self.name}-report.md").read_text()
        self.assertIn("Bill of materials", text)
        self.assertIn("Verification", text)


class TestGenerateBuck(unittest.TestCase):
    def test_generic_models_and_switching(self):
        with tempfile.TemporaryDirectory() as td:
            result = generate.generate(EXAMPLES / "buck-5v.json", td)
            name = result["spec"]["name"]
            cir = (Path(td) / f"{name}.cir").read_text()
            self.assertIn(".model SWMOD_S1 SW(", cir)
            self.assertIn("PULSE(", cir)
            self.assertIn(".tran", cir)
            report = (Path(td) / f"{name}-report.md").read_text()
            self.assertIn("unverified", report.lower())


class TestKicadParse(unittest.TestCase):
    def test_kiutils_parse_if_available(self):
        try:
            from kiutils.schematic import Schematic  # type: ignore
        except ImportError:
            self.skipTest("kiutils not installed")
        with tempfile.TemporaryDirectory() as td:
            result = generate.generate(EXAMPLES / "sallen-key-lowpass.json", td)
            name = result["spec"]["name"]
            sch = Schematic.from_file(str(Path(td) / f"{name}.kicad_sch"))
            self.assertEqual(len(sch.schematicSymbols), len(result["spec"]["components"]))
            self.assertGreater(len(sch.globalLabels), 0)


class TestScaffolds(unittest.TestCase):
    def test_every_scaffold_validates(self):
        from design_spec import scaffold
        cases = {
            "rc_lowpass": {"r": "1k", "c": "100n"},
            "rc_highpass": {"r": "1k", "c": "100n"},
            "divider": {"vin": "12", "r1": "10k", "r2": "4k7"},
            "sallen_key_lp": {"fc": "1k", "q": "0.7071"},
            "sallen_key_hp": {"fc": "1k", "q": "0.7071"},
            "bjt_ce": {"vcc": "12", "ic": "2m", "re": "100", "vce": "6"},
            "led": {"vs": "5", "vf": "2", "if": "10m"},
            "i2c": {"vdd": "3.3", "rp": "1k5", "cb": "200p"},
            "opamp_noninverting": {"gain": "10", "rg": "1k"},
            "zener_regulator": {"vin": "12", "vz": "5.1", "rs": "470"},
            "buck": {"vin": "12", "vout": "5", "iout": "2", "fsw": "500k"},
        }
        for topology, params in cases.items():
            with self.subTest(topology=topology):
                report = validate_spec(scaffold(topology, params))
                self.assertTrue(report["ok"], report["errors"])


if __name__ == "__main__":
    unittest.main()
