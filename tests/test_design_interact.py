"""Tests for the optional graphical interaction wrapper."""

import contextlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "design_interact.py"
SPEC = importlib.util.spec_from_file_location("circuit_design_interact", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class DesignInteractTests(unittest.TestCase):
    def test_intake_payload_builds_without_optional_dependency(self):
        payload = MODULE.build_intake_payload()
        self.assertEqual(payload["session_kind"], "intake")
        self.assertTrue(any(block.get("id") == "intake_review" for block in payload["blocks"]))

    def test_missing_shared_dependency_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "not-installed"
            with mock.patch.object(MODULE, "SHARED_SCRIPTS", missing):
                with self.assertRaisesRegex(RuntimeError, "shared design-interact UI not found") as caught:
                    MODULE._load_shared_dependency()
        self.assertIn("README.md", str(caught.exception))
        self.assertIn(str(missing), str(caught.exception))

    def test_cli_help_does_not_require_shared_dependency(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Graphical interaction UI", result.stdout)

    def test_cli_reports_missing_dependency_without_traceback(self):
        stderr = io.StringIO()
        with mock.patch.object(MODULE, "SHARED_SCRIPTS", Path("/definitely/missing/shared-ui")):
            with contextlib.redirect_stderr(stderr):
                result = MODULE.main(["intake", "--out", "/tmp/intake.json"])
        self.assertEqual(result, 2)
        self.assertIn("graphical interaction unavailable:", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
