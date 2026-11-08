"""Tests for CI dispatch safety and the required-stage gate."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ci_dispatch  # noqa: E402
import env_probe  # noqa: E402
import verify  # noqa: E402

GH = ci_dispatch.shutil.which("gh")


class TestWorkflowInputs(unittest.TestCase):
    def test_strings_and_booleans(self):
        args = ci_dispatch.workflow_inputs({
            "spec": "examples/rc-lowpass.json",
            "require": "simulate,erc",
            "erc": True,
            "empty": "",
            "none": None,
        })
        self.assertEqual(args, [
            "-f", "spec=examples/rc-lowpass.json",
            "-f", "require=simulate,erc",
            "-F", "erc=true",
        ])


@unittest.skipUnless(GH, "gh CLI not installed")
class TestDispatchRefusals(unittest.TestCase):
    def test_not_a_repository(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ci_dispatch.CiError) as ctx:
                ci_dispatch.dispatch("spec.json", cwd=Path(td))
        self.assertIn("not inside a git repository", str(ctx.exception))

    def test_no_upstream_is_refused_before_dispatch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "spec.json").write_text("{}", encoding="utf-8")
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "design.yml").write_text("name: x\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
            subprocess.run(
                ["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
                 "add", "spec.json", ".github/workflows/design.yml"],
                cwd=root, check=True)
            subprocess.run(
                ["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
                 "commit", "-q", "-m", "init"],
                cwd=root, check=True)
            with self.assertRaises(ci_dispatch.CiError) as ctx:
                ci_dispatch.dispatch("spec.json", cwd=root)
        self.assertIn("refusing to dispatch", str(ctx.exception))
        self.assertIn("no upstream", str(ctx.exception))


class TestRequiredStages(unittest.TestCase):
    def setUp(self):
        env_probe._CACHE.clear()

    def tearDown(self):
        env_probe._CACHE.clear()

    def test_missing_simulator_fails_a_required_stage(self):
        with tempfile.TemporaryDirectory() as td:
            old = os.environ.get("PATH", "")
            os.environ["PATH"] = td  # no ngspice here
            try:
                result = verify.verify(
                    ROOT / "examples" / "rc-lowpass.json", Path(td) / "out",
                    update_report=False, required=["simulate"])
            finally:
                os.environ["PATH"] = old
        self.assertFalse(result["ok"])
        required = [c for c in result["checks"] if c["name"] == "required:simulate"]
        self.assertEqual(len(required), 1)
        self.assertFalse(required[0]["ok"])

    def test_provenance_defaults_to_local(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GITHUB_ACTIONS", None)
            os.environ.pop("CIRCUIT_BACKEND", None)
            prov = verify.provenance(["simulate"])
        self.assertEqual(prov["backend"], "local")
        self.assertEqual(prov["required_stages"], ["simulate"])

    def test_provenance_records_ci_identity(self):
        with mock.patch.dict(os.environ, {
            "GITHUB_ACTIONS": "true",
            "GITHUB_SHA": "a" * 40,
            "GITHUB_RUN_ID": "123",
            "GITHUB_REPOSITORY": "davlug3/circuit-design-skill",
        }, clear=False):
            prov = verify.provenance()
        self.assertEqual(prov["backend"], "ci")
        self.assertEqual(prov["run_id"], "123")
        self.assertEqual(prov["repository"], "davlug3/circuit-design-skill")


if __name__ == "__main__":
    unittest.main()
