#!/usr/bin/env python3
"""Merge an audio-engineering-skill handoff into a circuit design spec.

The audio skill owns *what* must be achieved.  This script maps its versioned
handoff into the circuit skill's ``design`` and ``metrics`` blocks.  It needs a
base circuit spec (the electrical implementation and its analyses) and a small
mapping file that supplies the electrical test points the audio handoff cannot
know: output/input rawfile variables, test frequencies and generated metric ids.

The merged spec is validated with ``design_spec.validate_spec``.  A missing
analysis, an unsupported measure, a metric without a target or limit, or a
metric that does not name an existing requirement is an error.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import design_spec  # noqa: E402

HANDOFF_VERSION = 1


class MergeError(ValueError):
    """A handoff, base spec or mapping cannot be merged safely."""


def _load(path: str | Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise MergeError(f"{label} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise MergeError(f"{label} {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise MergeError(f"{label} {path}: top level must be an object")
    return data


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _metric_key(metric: dict[str, Any]) -> tuple[Any, Any]:
    return metric.get("measure"), metric.get("requirement")


def _require_metric_limits(metric: dict[str, Any], where: str) -> None:
    has_target = "target" in metric
    has_limits = "max" in metric or "min" in metric
    exploratory = metric.get("exploratory") is True
    if not has_target and not has_limits and not exploratory:
        raise MergeError(
            f"{where}: needs target+tolerance, min, max, or exploratory=true")
    if has_target and "tolerance" not in metric:
        raise MergeError(f"{where}: target needs a tolerance")
    if has_target and not isinstance(metric["tolerance"], (int, float)):
        raise MergeError(f"{where}: tolerance must be a number")


def _merge_by_id(existing: Any, incoming: Any, label: str) -> list[dict[str, Any]]:
    if existing is None:
        existing = []
    if not isinstance(existing, list) or not all(isinstance(item, dict) for item in existing):
        raise MergeError(f"base design.{label} must be a list of objects")
    if not isinstance(incoming, list):
        raise MergeError(f"handoff.{label} must be a list")
    result = list(existing)
    index_by_id = {
        item["id"]: index for index, item in enumerate(result)
        if isinstance(item.get("id"), str)
    }
    for item in incoming:
        if not isinstance(item, dict):
            raise MergeError(f"handoff.{label} entries must be objects")
        identifier = item.get("id")
        if isinstance(identifier, str) and identifier in index_by_id:
            result[index_by_id[identifier]] = copy.deepcopy(item)
        else:
            if isinstance(identifier, str):
                index_by_id[identifier] = len(result)
            result.append(copy.deepcopy(item))
    return result


def merge(handoff: dict[str, Any], base: dict[str, Any],
          mapping: dict[str, Any]) -> dict[str, Any]:
    """Return a circuit design spec built from the three inputs.

    The base spec supplies components, analyses and deliverables.  The handoff
    supplies requirements, conditions, architecture, risks, sources and limits.
    The mapping supplies the electrical test points for each handoff metric.
    """
    if not isinstance(handoff, dict):
        raise MergeError("handoff must be an object")
    if handoff.get("handoff_version") != HANDOFF_VERSION:
        raise MergeError(
            f"handoff_version must be {HANDOFF_VERSION}, got "
            f"{handoff.get('handoff_version')!r}")
    if not _nonempty(handoff.get("application")):
        raise MergeError("handoff.application is required")
    if not isinstance(base, dict) or not _nonempty(base.get("name")):
        raise MergeError("base spec must be an object with a non-empty name")

    spec = copy.deepcopy(base)
    design = dict(spec.get("design") or {})

    # Requirements: merge by id, keeping base-only requirements.
    handoff_requirements = handoff.get("requirements")
    if not isinstance(handoff_requirements, list) or not handoff_requirements:
        raise MergeError("handoff.requirements must be a non-empty list")
    requirements = list(design.get("requirements") or [])
    if not all(isinstance(item, dict) for item in requirements):
        raise MergeError("base design.requirements must contain objects")
    by_id = {
        item["id"]: index for index, item in enumerate(requirements)
        if isinstance(item.get("id"), str)
    }
    for index, requirement in enumerate(handoff_requirements):
        where = f"handoff.requirements[{index}]"
        if not isinstance(requirement, dict):
            raise MergeError(f"{where} must be an object")
        for field in ("id", "text", "acceptance", "source"):
            if not _nonempty(requirement.get(field)):
                raise MergeError(f"{where}.{field} is required")
        rid = requirement["id"]
        if rid in by_id:
            requirements[by_id[rid]] = copy.deepcopy(requirement)
        else:
            by_id[rid] = len(requirements)
            requirements.append(copy.deepcopy(requirement))
    design["requirements"] = requirements

    if handoff.get("architecture") is not None:
        if not isinstance(handoff["architecture"], dict):
            raise MergeError("handoff.architecture must be an object")
        design["architecture"] = copy.deepcopy(handoff["architecture"])
    for key in ("risks", "sources"):
        if handoff.get(key) is not None:
            design[key] = _merge_by_id(design.get(key), handoff[key], key)
    spec["design"] = design

    # Metrics: each handoff metric needs a mapping entry with the electrical
    # test point.  Match by (measure, requirement), not by list position.
    handoff_metrics = handoff.get("metrics")
    if not isinstance(handoff_metrics, list) or not handoff_metrics:
        raise MergeError("handoff.metrics must be a non-empty list")
    map_metrics = mapping.get("metrics")
    if not isinstance(map_metrics, list) or not map_metrics:
        raise MergeError("mapping.metrics must be a non-empty list")
    mapping_by_key: dict[tuple[Any, Any], dict[str, Any]] = {}
    for index, entry in enumerate(map_metrics):
        where = f"mapping.metrics[{index}]"
        if not isinstance(entry, dict):
            raise MergeError(f"{where} must be an object")
        measure = entry.get("measure")
        if measure not in design_spec.METRIC_MEASURES:
            raise MergeError(f"{where}: unsupported measure {measure!r}")
        key = (measure, entry.get("requirement"))
        if key in mapping_by_key:
            raise MergeError(f"{where}: duplicate mapping for {key!r}")
        mapping_by_key[key] = entry

    merged_metrics: list[dict[str, Any]] = []
    used_mappings: set[tuple[Any, Any]] = set()
    for index, metric in enumerate(handoff_metrics):
        where = f"handoff.metrics[{index}]"
        if not isinstance(metric, dict):
            raise MergeError(f"{where} must be an object")
        measure = metric.get("measure")
        if measure not in design_spec.METRIC_MEASURES:
            raise MergeError(f"{where}: unsupported measure {measure!r}")
        requirement = metric.get("requirement")
        if requirement is not None and requirement not in by_id:
            raise MergeError(
                f"{where}: requirement {requirement!r} is absent from the "
                f"merged requirements")
        if requirement is None and metric.get("exploratory") is not True:
            raise MergeError(
                f"{where}: a non-exploratory metric needs a requirement")
        _require_metric_limits(metric, where)
        key = _metric_key(metric)
        entry = mapping_by_key.get(key)
        if entry is None:
            raise MergeError(
                f"{where}: no mapping entry for measure={measure!r}, "
                f"requirement={requirement!r}")
        if key in used_mappings:
            raise MergeError(f"{where}: mapping already used for {key!r}")
        used_mappings.add(key)

        expected_analysis = design_spec.METRIC_ANALYSIS[measure]
        analysis = entry.get("analysis", metric.get("analysis", expected_analysis))
        if analysis != expected_analysis:
            raise MergeError(
                f"{where}: {measure} uses the {expected_analysis!r} analysis, "
                f"not {analysis!r}")
        output = entry.get("output", metric.get("output"))
        if not _nonempty(output):
            raise MergeError(
                f"{where}: mapping needs 'output' (a rawfile variable such as "
                f"'v(out)')")
        merged: dict[str, Any] = {
            "id": entry.get("id") or f"M{len(merged_metrics) + 1}",
            "measure": measure,
            "analysis": analysis,
            "output": output,
        }
        if requirement is not None:
            merged["requirement"] = requirement
        if measure in ("gain_db", "bandwidth_hz", "bandwidth_low_hz",
                       "bandwidth_width_hz"):
            source = entry.get("input", metric.get("input"))
            if not _nonempty(source):
                raise MergeError(
                    f"{where}: mapping needs 'input' (a rawfile variable such "
                    f"as 'v(in)') for {measure}")
            merged["input"] = source
        for field in ("frequency", "fundamental", "start", "stop", "harmonics",
                      "unit"):
            if field in entry:
                merged[field] = entry[field]
            elif field in metric:
                merged[field] = metric[field]
        for field in ("target", "tolerance", "min", "max", "exploratory"):
            if field in metric:
                merged[field] = metric[field]
        # Preserve audio-specific context (bandwidth_hz, passband, weighting,
        # detector, etc.) for the record.  The circuit validator ignores fields
        # it does not use.
        for field, value in metric.items():
            if field not in merged and field not in ("measure", "requirement"):
                merged[field] = copy.deepcopy(value)
        merged_metrics.append(merged)

    conditions = dict((spec.get("metrics") or {}).get("conditions") or {})
    handoff_conditions = handoff.get("conditions")
    if isinstance(handoff_conditions, dict):
        conditions.update(copy.deepcopy(handoff_conditions))
    spec["metrics"] = {"conditions": conditions, "metrics": merged_metrics}
    return spec


def validate_merged(spec: dict[str, Any], base_dir: str | Path | None = None) -> dict[str, Any]:
    return design_spec.validate_spec(spec, base_dir=base_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", required=True, help="audio handoff JSON")
    parser.add_argument("--base", required=True,
                        help="base circuit spec with components and analyses")
    parser.add_argument("--map", dest="mapping", required=True,
                        help="metric mapping JSON")
    parser.add_argument("--out", required=True, help="merged spec JSON")
    args = parser.parse_args(argv)
    try:
        handoff = _load(args.handoff, "handoff")
        base = _load(args.base, "base spec")
        mapping = _load(args.mapping, "mapping")
        merged = merge(handoff, base, mapping)
        report = validate_merged(merged, Path(args.base).resolve().parent)
        if not report["ok"]:
            for error in report["errors"]:
                print(f"error: {error}", file=sys.stderr)
            return 1
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out}: {len(merged['metrics']['metrics'])} metrics, "
              f"{len(merged['design']['requirements'])} requirements")
        return 0
    except MergeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
