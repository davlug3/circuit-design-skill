"""Tests for the environment capability probe.

The probe must distinguish "not installed" from "installed but cannot run
here" - the whole point is to avoid claiming a check passed when the binary
would fail with an exec format or linker error.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import env_probe  # noqa: E402


def _make_exec(path: Path, body: str) -> Path:
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


class TempPath:
    """Prepend a directory to PATH for the duration of a test."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.old = None

    def __enter__(self):
        self.old = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{self.directory}:{self.old}"
        env_probe._CACHE.clear()
        return self

    def __exit__(self, *exc):
        os.environ["PATH"] = self.old or ""
        env_probe._CACHE.clear()


class TestFailureDetail(unittest.TestCase):
    def test_exec_format_error_is_explained(self):
        proc = subprocess.CompletedProcess(
            ["x86_64-binary"], 126, "", "bash: /bin/tool: cannot execute: required file not found")
        detail = env_probe._failure_detail(proc, "fallback")
        self.assertIn("cannot be executed", detail)

    def test_missing_shared_library_is_explained(self):
        proc = subprocess.CompletedProcess(
            ["tool"], 127, "", "error while loading shared libraries: libngspice.so.0")
        detail = env_probe._failure_detail(proc, "fallback")
        self.assertIn("missing shared library", detail)

    def test_generic_failure_keeps_text(self):
        proc = subprocess.CompletedProcess(["tool"], 2, "boom", "")
        self.assertIn("boom", env_probe._failure_detail(proc, "fallback"))


class TestNgspiceProbe(unittest.TestCase):
    def test_missing_binary_is_not_incompatible(self):
        with tempfile.TemporaryDirectory() as td:
            with TempPath(Path(td)):
                result = env_probe.probe_ngspice()
        self.assertFalse(result["ok"])
        self.assertFalse(result["supported"])
        self.assertIn("not found", result["detail"])

    def test_unusable_binary_is_incompatible(self):
        with tempfile.TemporaryDirectory() as td:
            _make_exec(Path(td) / "ngspice",
                       'if [ "$1" = "-v" ]; then echo "ngspice-99"; exit 0; fi\n'
                       'echo "cannot link executable"; exit 1\n')
            with TempPath(Path(td)):
                result = env_probe.probe_ngspice()
        self.assertTrue(result["ok"], "the binary exists")
        self.assertFalse(result["supported"], "but it cannot run")
        self.assertIn("smoke netlist failed", result["detail"])

    def test_working_binary_runs_smoke_netlist(self):
        with tempfile.TemporaryDirectory() as td:
            _make_exec(
                Path(td) / "ngspice",
                'if [ "$1" = "-v" ]; then echo "ngspice-44"; exit 0; fi\n'
                'while [ $# -gt 0 ]; do\n'
                '  if [ "$1" = "-o" ]; then log="$2"; shift 2; else shift; fi\n'
                'done\n'
                'echo "v(1) = 1.000000e+00" > "$log"\n'
                'exit 0\n',
            )
            with TempPath(Path(td)):
                result = env_probe.probe_ngspice()
        self.assertTrue(result["supported"])
        self.assertIn("smoke netlist solved", result["detail"])


class TestKicadProbe(unittest.TestCase):
    def test_parse_major(self):
        self.assertEqual(env_probe.parse_kicad_major("9.0.9"), 9)
        self.assertEqual(env_probe.parse_kicad_major("8.0.1+dfsg"), 8)
        self.assertIsNone(env_probe.parse_kicad_major(""))

    def test_old_kicad_is_unsupported(self):
        with tempfile.TemporaryDirectory() as td:
            _make_exec(
                Path(td) / "kicad-cli",
                'if [ "$1" = "version" ]; then echo "7.0.11"; exit 0; fi\n'
                'echo "--exit-code-violations"; exit 0\n',
            )
            with TempPath(Path(td)):
                result = env_probe.probe_kicad_cli()
        self.assertTrue(result["ok"])
        self.assertFalse(result["supported"])
        self.assertIn("KiCad 9+ required", result["detail"])

    def test_missing_erc_flag_is_unsupported(self):
        with tempfile.TemporaryDirectory() as td:
            _make_exec(
                Path(td) / "kicad-cli",
                'if [ "$1" = "version" ]; then echo "9.0.9"; exit 0; fi\n'
                'echo "--output REPORT"; exit 0\n',
            )
            with TempPath(Path(td)):
                result = env_probe.probe_kicad_cli()
        self.assertTrue(result["ok"])
        self.assertFalse(result["supported"])


class TestStageGating(unittest.TestCase):
    def _tools(self, **overrides):
        base = {
            "ngspice": {"ok": True, "supported": True, "detail": ""},
            "kicad-cli": {"ok": True, "supported": True, "detail": ""},
            "kiutils": {"ok": True, "supported": True, "detail": ""},
        }
        base.update(overrides)
        return base

    def test_ready_when_all_supported(self):
        status = env_probe.stage_status(self._tools(), "simulate")
        self.assertTrue(status["ok"])

    def test_incompatible_is_distinct_from_missing(self):
        tools = self._tools(ngspice={"ok": True, "supported": False, "detail": "exec format"})
        status = env_probe.stage_status(tools, "simulate")
        self.assertFalse(status["ok"])
        self.assertEqual(status["incompatible"], ["ngspice"])
        self.assertEqual(status["missing"], [])

        tools = self._tools(ngspice={"ok": False, "supported": False, "detail": "absent"})
        status = env_probe.stage_status(tools, "simulate")
        self.assertEqual(status["missing"], ["ngspice"])
        self.assertEqual(status["incompatible"], [])

    def test_backend_falls_back_to_ci(self):
        probe = {
            "stages": {"simulate": {"ok": False, "missing": ["ngspice"], "incompatible": []}},
            "ci": {"usable": True},
        }
        self.assertEqual(env_probe.recommended_backend(probe, ["simulate"]), "ci")

    def test_backend_none_when_ci_unusable(self):
        probe = {
            "stages": {"simulate": {"ok": False, "missing": ["ngspice"], "incompatible": []}},
            "ci": {"usable": False},
        }
        self.assertEqual(env_probe.recommended_backend(probe, ["simulate"]), "none")


class TestCiBlockers(unittest.TestCase):
    def _repo(self, td: str) -> tuple[Path, Path]:
        root = Path(td)
        (root / "specs").mkdir()
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
        return root, root / "spec.json"

    def test_missing_workflow_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "spec.json").write_text("{}", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            blockers = env_probe.ci_blockers(root, root / "spec.json")
        self.assertTrue(any("workflow missing" in b for b in blockers))

    def test_no_upstream_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            root, spec = self._repo(td)
            blockers = env_probe.ci_blockers(root, spec)
        self.assertTrue(any("no upstream" in b for b in blockers), blockers)

    def test_dirty_tree_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            root, spec = self._repo(td)
            spec.write_text('{"changed": true}', encoding="utf-8")
            blockers = env_probe.ci_blockers(root, spec)
        self.assertTrue(any("uncommitted" in b for b in blockers), blockers)

    def test_spec_outside_repo_blocks(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as other:
            root, _ = self._repo(td)
            outside = Path(other) / "spec.json"
            outside.write_text("{}", encoding="utf-8")
            blockers = env_probe.ci_blockers(root, outside)
        self.assertTrue(any("outside the repository" in b for b in blockers), blockers)


if __name__ == "__main__":
    unittest.main()
