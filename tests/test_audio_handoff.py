"""Tests for merging an audio handoff into a circuit design spec."""

from __future__ import annotations

import copy
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import design_spec  # noqa: E402
from audio_handoff import MergeError, main, merge  # noqa: E402


def base_spec() -> dict:
    return {
        "schema_version": "1.0",
        "name": "handoff_test",
        "description": "audio handoff merge fixture",
        "ground": "GND",
        "deliverables": ["spice", "report"],
        "components": [
            {"ref": "V1", "type": "V", "value": 0.0, "dc": 0.0, "ac": 1.0,
             "pins": {"1": "IN", "2": "GND"}},
            {"ref": "R1", "type": "R", "value": 1000.0,
             "pins": {"1": "IN", "2": "OUT"}},
            {"ref": "C1", "type": "C", "value": 1e-7,
             "pins": {"1": "OUT", "2": "GND"}},
        ],
        "analyses": [
            {"type": "ac", "start": 10.0, "stop": 1e6, "points": 100},
            {"type": "noise", "output": "OUT", "source": "V1",
             "start": 20.0, "stop": 20000.0, "points": 100},
        ],
        "models": {},
    }


def handoff() -> dict:
    return {
        "handoff_version": 1,
        "application": "test preamp",
        "conditions": {"input_vrms": 0.002, "temperature_c": 25},
        "requirements": [
            {"id": "A1", "text": "Flat gain", "acceptance": "40 +/-0.5 dB",
             "source": "S041"},
        ],
        "metrics": [
            {"measure": "gain_db", "target": 40.0, "tolerance": 0.5,
             "requirement": "A1"},
        ],
        "sources": [
            {"id": "S041", "title": "Audio specification",
             "url": "https://example.invalid/s041", "accessed": "2026-11-08"},
        ],
    }


def mapping() -> dict:
    return {
        "metrics": [
            {"measure": "gain_db", "requirement": "A1", "id": "M1",
             "analysis": "ac", "output": "v(out)", "input": "v(in)",
             "frequency": 1000.0},
        ],
    }


def write_audio_skill(root: Path, status: str = "verified",
                      source_id: str = "S041") -> Path:
    """Create a minimal audio-skill tree with a source registry."""
    skill = root / "audio-engineering-skill"
    (skill / "catalog").mkdir(parents=True, exist_ok=True)
    (skill / "catalog" / "sources.json").write_text(
        json.dumps({"schema_version": 1, "sources": [
            {"id": source_id, "title": "Audio specification",
             "status": status},
        ]}),
        encoding="utf-8",
    )
    return skill


class TestMerge(unittest.TestCase):
    def test_maps_requirements_metrics_and_conditions(self):
        merged = merge(handoff(), base_spec(), mapping())
        self.assertEqual(merged["design"]["requirements"][0]["id"], "A1")
        self.assertEqual(merged["metrics"]["conditions"]["input_vrms"], 0.002)
        metric = merged["metrics"]["metrics"][0]
        self.assertEqual(metric["id"], "M1")
        self.assertEqual(metric["measure"], "gain_db")
        self.assertEqual(metric["target"], 40.0)
        self.assertEqual(metric["tolerance"], 0.5)
        self.assertEqual(metric["output"], "v(out)")
        self.assertEqual(metric["input"], "v(in)")
        self.assertEqual(len(merged["components"]), 3)

    def test_merged_spec_validates(self):
        merged = merge(handoff(), base_spec(), mapping())
        report = design_spec.validate_spec(merged)
        self.assertTrue(report["ok"], report["errors"])
        self.assertFalse(
            any("differs from metric output" in warning
                for warning in report["warnings"]))

    def test_base_requirements_are_preserved(self):
        base = base_spec()
        base["design"] = {
            "requirements": [
                {"id": "B1", "text": "base requirement",
                 "acceptance": "existing", "source": "base brief"},
            ],
        }
        merged = merge(handoff(), base, mapping())
        ids = [item["id"] for item in merged["design"]["requirements"]]
        self.assertEqual(ids, ["B1", "A1"])

    def test_handoff_requirement_replaces_the_same_id(self):
        base = base_spec()
        base["design"] = {
            "requirements": [
                {"id": "A1", "text": "old", "acceptance": "old",
                 "source": "old"},
            ],
        }
        merged = merge(handoff(), base, mapping())
        self.assertEqual(len(merged["design"]["requirements"]), 1)
        self.assertEqual(merged["design"]["requirements"][0]["text"], "Flat gain")

    def test_audio_specific_metric_context_is_preserved(self):
        data = handoff()
        data["metrics"][0]["passband"] = "low"
        data["metrics"][0]["bandwidth_hz"] = [20, 20000]
        merged = merge(data, base_spec(), mapping())
        metric = merged["metrics"]["metrics"][0]
        self.assertEqual(metric["passband"], "low")
        self.assertEqual(metric["bandwidth_hz"], [20, 20000])

    def test_exploratory_metric_may_have_no_requirement(self):
        data = handoff()
        data["metrics"] = [{
            "measure": "gain_db", "exploratory": True,
            "frequency": 1000.0,
        }]
        map_data = {"metrics": [{
            "measure": "gain_db", "id": "M1", "analysis": "ac",
            "output": "v(out)", "input": "v(in)", "frequency": 1000.0,
        }]}
        merged = merge(data, base_spec(), map_data)
        self.assertNotIn("requirement", merged["metrics"]["metrics"][0])
        self.assertTrue(design_spec.validate_spec(merged)["ok"])

    def test_wrong_version_is_rejected(self):
        data = handoff()
        data["handoff_version"] = 2
        with self.assertRaisesRegex(MergeError, "handoff_version"):
            merge(data, base_spec(), mapping())

    def test_missing_application_is_rejected(self):
        data = handoff()
        data["application"] = ""
        with self.assertRaisesRegex(MergeError, "application"):
            merge(data, base_spec(), mapping())

    def test_unsupported_measure_is_rejected(self):
        data = handoff()
        data["metrics"][0]["measure"] = "loudness_lufs"
        with self.assertRaisesRegex(MergeError, "unsupported measure"):
            merge(data, base_spec(), mapping())

    def test_missing_mapping_is_rejected(self):
        with self.assertRaisesRegex(MergeError, "no mapping entry"):
            merge(handoff(), base_spec(), {
                "metrics": [{"measure": "ein_uv", "requirement": "A1"}]})

    def test_duplicate_mapping_is_rejected(self):
        map_data = mapping()
        map_data["metrics"].append(copy.deepcopy(map_data["metrics"][0]))
        with self.assertRaisesRegex(MergeError, "duplicate mapping"):
            merge(handoff(), base_spec(), map_data)

    def test_unknown_requirement_is_rejected(self):
        data = handoff()
        data["metrics"][0]["requirement"] = "A9"
        with self.assertRaisesRegex(MergeError, "absent from the merged"):
            merge(data, base_spec(), mapping())

    def test_target_without_tolerance_is_rejected(self):
        data = handoff()
        del data["metrics"][0]["tolerance"]
        with self.assertRaisesRegex(MergeError, "target needs a tolerance"):
            merge(data, base_spec(), mapping())

    def test_non_exploratory_metric_needs_a_requirement(self):
        data = handoff()
        del data["metrics"][0]["requirement"]
        map_data = mapping()
        del map_data["metrics"][0]["requirement"]
        with self.assertRaisesRegex(MergeError, "needs a requirement"):
            merge(data, base_spec(), map_data)

    def test_mapping_needs_an_output(self):
        map_data = mapping()
        del map_data["metrics"][0]["output"]
        with self.assertRaisesRegex(MergeError, "needs 'output'"):
            merge(handoff(), base_spec(), map_data)

    def test_gain_mapping_needs_an_input(self):
        map_data = mapping()
        del map_data["metrics"][0]["input"]
        with self.assertRaisesRegex(MergeError, "needs 'input'"):
            merge(handoff(), base_spec(), map_data)

    def test_wrong_analysis_is_rejected(self):
        map_data = mapping()
        map_data["metrics"][0]["analysis"] = "tran"
        with self.assertRaisesRegex(MergeError, "uses the 'ac' analysis"):
            merge(handoff(), base_spec(), map_data)


class TestRegistry(unittest.TestCase):
    def test_verified_source_passes(self):
        merged = merge(handoff(), base_spec(), mapping(),
                       registry={"S041": {"id": "S041",
                                          "status": "verified"}})
        self.assertEqual(merged["design"]["sources"][0]["id"], "S041")

    def test_candidate_source_is_rejected(self):
        with self.assertRaisesRegex(MergeError, "not verified"):
            merge(handoff(), base_spec(), mapping(),
                  registry={"S041": {"id": "S041",
                                     "status": "candidate"}})

    def test_unknown_source_is_rejected(self):
        with self.assertRaisesRegex(MergeError, "unknown source S041"):
            merge(handoff(), base_spec(), mapping(), registry={})

    def test_requirement_source_must_be_listed(self):
        payload = handoff()
        payload["sources"] = []
        with self.assertRaisesRegex(MergeError, "must be a non-empty list"):
            merge(payload, base_spec(), mapping(),
                  registry={"S041": {"id": "S041", "status": "verified"}})

    def test_duplicate_listed_source_is_rejected(self):
        payload = handoff()
        payload["sources"].append(dict(payload["sources"][0]))
        with self.assertRaisesRegex(MergeError, "duplicate source id S041"):
            merge(payload, base_spec(), mapping(),
                  registry={"S041": {"id": "S041", "status": "verified"}})


class TestCli(unittest.TestCase):
    def test_merge_and_write(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill = write_audio_skill(root)
            (root / "handoff.json").write_text(json.dumps(handoff()), encoding="utf-8")
            (root / "base.json").write_text(json.dumps(base_spec()), encoding="utf-8")
            (root / "map.json").write_text(json.dumps(mapping()), encoding="utf-8")
            out = root / "merged.json"
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                code = main([
                    "--handoff", str(root / "handoff.json"),
                    "--base", str(root / "base.json"),
                    "--map", str(root / "map.json"),
                    "--out", str(out),
                    "--audio-skill", str(skill),
                ])
            self.assertEqual(code, 0)
            merged = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(merged["metrics"]["metrics"][0]["id"], "M1")

    def test_invalid_merge_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "handoff.json").write_text(json.dumps(handoff()), encoding="utf-8")
            (root / "base.json").write_text(json.dumps(base_spec()), encoding="utf-8")
            (root / "map.json").write_text(json.dumps({"metrics": []}), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                code = main([
                    "--handoff", str(root / "handoff.json"),
                    "--base", str(root / "base.json"),
                    "--map", str(root / "map.json"),
                    "--out", str(root / "merged.json"),
                ])
            self.assertEqual(code, 1)

    def test_explicit_missing_registry_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "handoff.json").write_text(json.dumps(handoff()), encoding="utf-8")
            (root / "base.json").write_text(json.dumps(base_spec()), encoding="utf-8")
            (root / "map.json").write_text(json.dumps(mapping()), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                code = main([
                    "--handoff", str(root / "handoff.json"),
                    "--base", str(root / "base.json"),
                    "--map", str(root / "map.json"),
                    "--out", str(root / "merged.json"),
                    "--audio-skill", str(root / "missing"),
                ])
            self.assertEqual(code, 1)

    def test_require_registry_without_sibling_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "handoff.json").write_text(json.dumps(handoff()), encoding="utf-8")
            (root / "base.json").write_text(json.dumps(base_spec()), encoding="utf-8")
            (root / "map.json").write_text(json.dumps(mapping()), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                code = main([
                    "--handoff", str(root / "handoff.json"),
                    "--base", str(root / "base.json"),
                    "--map", str(root / "map.json"),
                    "--out", str(root / "merged.json"),
                    "--audio-skill", str(root / "missing"),
                    "--require-registry",
                ])
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
