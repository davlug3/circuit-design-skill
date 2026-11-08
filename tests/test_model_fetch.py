"""Tests for the open-web SPICE model fetcher.

The fetcher must not invent a model, must not accept a file that lacks the
requested model, and must record a hash that the resolver can verify.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate  # noqa: E402
import model_fetch  # noqa: E402
from design_spec import resolve_model, validate_spec  # noqa: E402

NPN = """* synthetic model for tests
* Copyright (c) Example Vendor
.model TESTNPN NPN(BF=120 IS=1e-14)
"""

SUBCKT = """* synthetic subcircuit for tests
.SUBCKT TESTNMOS d g s
M1 d g s s CORE
.MODEL CORE NMOS(VTO=2.0 KP=0.1)
.ENDS TESTNMOS
"""


def run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = model_fetch.main(argv)
    return code, out.getvalue(), err.getvalue()


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def catalog(td: Path, entries: list[dict]) -> Path:
    return write(td / "catalog.json",
                 json.dumps({"version": 1, "entries": entries}))


def spec_doc(components: list[dict] | None = None) -> dict:
    return {
        "name": "fetched",
        "description": "fetched model test",
        "ground": "GND",
        "deliverables": ["spice"],
        "analyses": [{"type": "op"}],
        "components": components or [
            {"ref": "V1", "type": "V", "value": 5, "pins": {"1": "VCC", "2": "GND"}},
            {"ref": "R1", "type": "R", "value": 1000, "pins": {"1": "VCC", "2": "C"}},
            {"ref": "Q1", "type": "NPN", "value": 0, "pins": {"1": "C", "2": "B", "3": "GND"}},
        ],
    }


class TestCatalogFetch(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.dir = Path(self.td.name)
        self.lib = write(self.dir / "parts.lib", NPN)
        self.cat = catalog(self.dir, [{
            "part": "TESTNPN",
            "model": "TESTNPN",
            "type": "NPN",
            "vendor": "Example Vendor",
            "source": self.lib.as_uri(),
            "notes": "test part",
        }])

    def tearDown(self):
        self.td.cleanup()

    def test_fetch_emits_entry_with_verifiable_hash(self):
        code, out, err = run([
            "--part", "TESTNPN", "--catalog", str(self.cat),
            "--out", str(self.dir / "models"), "--json",
        ])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)["models"]["TESTNPN"]
        path = Path(payload["file"])
        self.assertTrue(path.is_file())
        self.assertEqual(payload["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(payload["vendor"], "Example Vendor")
        self.assertEqual(payload["name"], "TESTNPN")
        self.assertEqual(payload["notes"], "test part")

        spec = {"components": [
            {"ref": "Q1", "type": "NPN", "pins": {"1": "C", "2": "B", "3": "E"},
             "model": "TESTNPN"},
        ], "models": {"TESTNPN": payload}}
        info = resolve_model(spec, "TESTNPN", base_dir=path.parent)
        self.assertIsNone(info["error"])
        self.assertEqual(info["kind"], "vendor")
        self.assertEqual(info["sha256"], payload["sha256"])

    def test_unknown_part_lists_known_parts(self):
        code, _out, err = run(["--part", "NOPE", "--catalog", str(self.cat),
                               "--out", str(self.dir / "models")])
        self.assertEqual(code, 1)
        self.assertIn("known parts", err)
        self.assertIn("TESTNPN", err)

    def test_missing_model_name_is_rejected(self):
        cat = catalog(self.dir, [{
            "part": "TESTNPN", "model": "OTHER", "vendor": "V",
            "source": self.lib.as_uri(),
        }])
        code, _out, err = run(["--part", "TESTNPN", "--catalog", str(cat),
                               "--out", str(self.dir / "models")])
        self.assertEqual(code, 1)
        self.assertIn("does not define", err)
        self.assertIn("TESTNPN", err)

    def test_type_mismatch_is_rejected(self):
        code, _out, err = run(["--part", "TESTNPN", "--catalog", str(self.cat),
                               "--type", "PNP", "--out", str(self.dir / "models")])
        self.assertEqual(code, 1)
        self.assertIn("expected a PNP", err)

    def test_invalid_url_is_reported(self):
        code, _out, err = run([
            "--part", "TESTNPN", "--url", "not-a-url",
            "--out", str(self.dir / "models"),
        ])
        self.assertEqual(code, 1)
        self.assertIn("invalid URL", err)

    def test_file_mode_requires_source(self):
        code, _out, err = run(["--file", str(self.lib), "--part", "TESTNPN",
                               "--vendor", "V", "--out", str(self.dir / "models")])
        self.assertEqual(code, 1)
        self.assertIn("--source", err)

    def test_existing_file_with_different_content_needs_force(self):
        out = self.dir / "models"
        out.mkdir()
        write(out / "TESTNPN.lib", "* different\n.model TESTNPN NPN(BF=1)\n")
        code, _out, err = run(["--part", "TESTNPN", "--catalog", str(self.cat),
                               "--out", str(out)])
        self.assertEqual(code, 1)
        self.assertIn("--force", err)
        code, _out, err = run(["--part", "TESTNPN", "--catalog", str(self.cat),
                               "--out", str(out), "--force"])
        self.assertEqual(code, 0, err)


class TestSubcircuit(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.dir = Path(self.td.name)
        self.lib = write(self.dir / "sub.lib", SUBCKT)

    def tearDown(self):
        self.td.cleanup()

    def test_subckt_without_pins_is_rejected(self):
        cat = catalog(self.dir, [{
            "part": "TESTNMOS", "model": "TESTNMOS", "type": "NMOS",
            "vendor": "V", "source": self.lib.as_uri(),
        }])
        code, _out, err = run(["--part", "TESTNMOS", "--catalog", str(cat),
                               "--out", str(self.dir / "models")])
        self.assertEqual(code, 1)
        self.assertIn("--subckt-pins", err)

    def test_subckt_with_pins_emits_x_device(self):
        cat = catalog(self.dir, [{
            "part": "TESTNMOS", "model": "TESTNMOS", "type": "NMOS",
            "vendor": "V", "source": self.lib.as_uri(),
            "subckt_pins": ["D", "G", "S"],
        }])
        code, out, err = run(["--part", "TESTNMOS", "--catalog", str(cat),
                              "--out", str(self.dir / "models"), "--json"])
        self.assertEqual(code, 0, err)
        entry = json.loads(out)["models"]["TESTNMOS"]
        self.assertEqual(entry["subckt_pins"], ["D", "G", "S"])

        spec = {
            "name": "subckt_test",
            "ground": "GND",
            "analyses": [],
            "components": [
                {"ref": "M1", "type": "NMOS", "pins": {"1": "D", "2": "G", "3": "GND"},
                 "model": "TESTNMOS"},
            ],
            "models": {"TESTNMOS": entry},
        }
        netlist = generate.spice_netlist(spec, base_dir=Path(entry["file"]).parent)
        self.assertIn("XM1 D G 0 TESTNMOS", netlist)
        self.assertIn(".SUBCKT TESTNMOS", netlist)
        self.assertNotIn("* TESTNMOS: .SUBCKT", netlist)


class TestWriteSpec(unittest.TestCase):
    def test_write_spec_assigns_ref_and_records_relative_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            lib = write(root / "parts.lib", NPN)
            cat = catalog(root, [{
                "part": "TESTNPN", "model": "TESTNPN", "type": "NPN",
                "vendor": "Example Vendor", "source": lib.as_uri(),
            }])
            spec_path = write(root / "design.json", json.dumps(spec_doc()))
            code, _out, err = run([
                "--part", "TESTNPN", "--catalog", str(cat),
                "--write-spec", str(spec_path), "--ref", "Q1",
            ])
            self.assertEqual(code, 0, err)

            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            self.assertEqual(spec["components"][2]["model"], "TESTNPN")
            entry = spec["models"]["TESTNPN"]
            self.assertEqual(entry["file"], "models/TESTNPN.lib")
            self.assertTrue((root / "models" / "TESTNPN.lib").is_file())
            self.assertTrue(validate_spec(spec, base_dir=root)["ok"])

            result = generate.spice_netlist(spec, base_dir=root)
            self.assertIn(".model TESTNPN", result)

    def test_write_spec_refuses_a_non_semiconductor_ref(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            lib = write(root / "parts.lib", NPN)
            cat = catalog(root, [{
                "part": "TESTNPN", "model": "TESTNPN", "type": "NPN",
                "vendor": "V", "source": lib.as_uri(),
            }])
            spec_path = write(root / "design.json", json.dumps(spec_doc()))
            code, _out, err = run([
                "--part", "TESTNPN", "--catalog", str(cat),
                "--write-spec", str(spec_path), "--ref", "R1",
            ])
            self.assertEqual(code, 1)
            self.assertIn("only a semiconductor", err)

    def test_write_spec_refuses_ambiguous_targets(self):
        comps = spec_doc()["components"] + [
            {"ref": "Q2", "type": "NPN", "value": 0, "pins": {"1": "C", "2": "B", "3": "GND"}},
        ]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            lib = write(root / "parts.lib", NPN)
            cat = catalog(root, [{
                "part": "TESTNPN", "model": "TESTNPN", "type": "NPN",
                "vendor": "V", "source": lib.as_uri(),
            }])
            spec_path = write(root / "design.json", json.dumps(spec_doc(comps)))
            code, _out, err = run([
                "--part", "TESTNPN", "--catalog", str(cat),
                "--write-spec", str(spec_path),
            ])
            self.assertEqual(code, 1)
            self.assertIn("--ref", err)


if __name__ == "__main__":
    unittest.main()
