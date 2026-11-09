"""Regression test for the plain-language 12 V to 5 V / 2 A golden workflow."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate  # noqa: E402
import verify  # noqa: E402
from design_spec import validate_spec  # noqa: E402

EXAMPLE = ROOT / "examples" / "buck-5v.json"
PROMPT = ROOT / "examples" / "plain-language-buck.md"


class TestPlainLanguageBuckWorkflow(unittest.TestCase):
    def test_prompt_is_documented_and_maps_to_machine_spec(self):
        prompt = PROMPT.read_text()
        self.assertIn("Build a 5 V power supply from a 12 V DC input", prompt)
        self.assertIn("Clarifications and locked assumptions", prompt)
        self.assertIn("not a production design", prompt)

        spec = json.loads(EXAMPLE.read_text())
        self.assertEqual(spec["topology"], "buck")
        self.assertEqual(spec["parameters"]["vin"], 12.0)
        self.assertEqual(spec["parameters"]["vout"], 5.0)
        self.assertEqual(spec["parameters"]["iout"], 2.0)
        self.assertEqual(spec["parameters"]["fsw"], 500000.0)
        self.assertEqual(spec["design"]["requirements"][0]["source"],
                         "examples/plain-language-buck.md")
        self.assertGreaterEqual(len(spec["design"]["requirements"]), 3)
        self.assertTrue(spec["design"]["architecture"]["summary"])
        self.assertTrue(spec["design"]["decisions"])
        self.assertTrue(spec["design"]["risks"])
        self.assertTrue(spec["design"]["sources"])

        result = validate_spec(spec)
        self.assertTrue(result["ok"], result["errors"])

    def test_end_to_end_generation_and_required_design_verification(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            generated = generate.generate(EXAMPLE, out)
            name = generated["spec"]["name"]

            for suffix in (
                ".cir", ".asc", ".net", ".kicad_sch",
                "-bom.csv", "-report.md", "-report.json",
            ):
                self.assertTrue((out / f"{name}{suffix}").is_file(), suffix)

            netlist = (out / f"{name}.cir").read_text()
            self.assertIn("V1 ", netlist)
            self.assertIn("L1 ", netlist)
            self.assertIn("C1 ", netlist)
            self.assertIn(".tran", netlist)
            self.assertIn("unverified", (out / f"{name}-report.md").read_text().lower())

            result = verify.verify(EXAMPLE, out / "verified", required=["design"])
            self.assertTrue(result["ok"], result["summary"])
            checks = {item["name"]: item for item in result["checks"]}
            self.assertTrue(checks["design"]["ok"], checks["design"]["detail"])
            self.assertTrue(checks["buck_sizing"]["ok"], checks["buck_sizing"]["detail"])
            self.assertIsNone(checks["mna_linear"]["ok"])
            self.assertIn("nonlinear", checks["mna_linear"]["detail"].lower())


if __name__ == "__main__":
    unittest.main()
