#!/usr/bin/env python3
"""Generate LTspice, SPICE and KiCad deliverables from a design spec.

The *generated SPICE netlist is the simulation source of truth*.  The LTspice
``.asc`` and KiCad schematic are drawn from the same component list, using
net labels at every pin instead of fragile autorouted wires, so the pictures
cannot silently disagree with the netlist.

Outputs
-------
``<name>.cir``          self-contained SPICE netlist (models inline)
``<name>.models``       model cards for the ``.asc`` ``.include`` directive
``<name>.asc``          LTspice schematic
``<name>.net``          KiCad netlist (S-expression)
``<name>.kicad_sch``    KiCad 9 schematic with embedded symbols
``<name>-bom.csv``      bill of materials
``<name>-report.md``    human-readable design report
``<name>-report.json``  machine-readable report

Usage::

    python3 generate.py spec.json --out out/
    python3 generate.py spec.json --out out/ --formats spice,ltspice_asc,kicad_sch
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
import uuid
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from circuit_common import (  # noqa: E402
    dumps,
    parse_value,
    si_number,
    spice_net,
    spice_number,
    spice_ref,
)
from design_spec import GENERIC_MODELS, model_status, validate_spec  # noqa: E402
from symbols import (  # noqa: E402
    ASC_SYMBOLS,
    KICAD_PINS,
    asc_pins,
    kicad_lib_symbols,
    kicad_pins,
)

ALL_FORMATS = ["spice", "ltspice_asc", "kicad_net", "kicad_sch", "bom", "report", "pcb"]

_UID_NS = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def uid(*parts: str) -> str:
    return str(uuid.uuid5(_UID_NS, "circuit-design-skill/" + "/".join(parts)))


# ---------------------------------------------------------------------------
# Net naming and model cards
# ---------------------------------------------------------------------------

def _fmt(value: float) -> str:
    return spice_number(value)


def _model_params(ctype: str, comp: dict[str, Any]) -> dict[str, Any]:
    base = dict(GENERIC_MODELS.get(ctype, {}))
    value = float(comp.get("value", 0.0) or 0.0)
    if ctype == "ZENER" and value > 0:
        base["bv"] = value
    if ctype == "LED":
        # Choose Is so the generic LED lands near its stated Vf at 10 mA.
        n = float(base.get("n", 1.8))
        rs = float(base.get("rs", 5.0))
        vt = 0.025852
        if value > 0.1:
            exponent = (value - 0.01 * rs) / (n * vt)
            if exponent < 700:
                base["is"] = 0.01 / math.exp(exponent)
    params = dict(comp.get("params") or {})
    base.update({k: v for k, v in params.items() if not isinstance(v, (dict, list))})
    return base


def _card_from_dict(name: str, ctype: str, values: dict[str, Any]) -> str:
    model_type = str(values.get("type", ctype))
    bits = []
    for key, value in values.items():
        if key in ("type", "name"):
            continue
        if isinstance(value, bool):
            bits.append(f"{key}={'1' if value else '0'}")
        elif isinstance(value, str):
            bits.append(f"{key}={value}")
        else:
            bits.append(f"{key}={_fmt(float(value))}")
    return f".model {name} {model_type}(" + " ".join(bits) + ")"


def _generic_card(ctype: str, name: str, comp: dict[str, Any]) -> str:
    if ctype == "SW":
        return (f".model {name} SW(Ron=0.05 Roff=1e6 Vt=2.5 Vh=0.1)")
    if ctype == "OPAMP":
        aol = float(comp.get("gain", comp.get("value", 1e6)) or 1e6)
        params = comp.get("params") or {}
        gbw = float(params.get("gbw", 1e6) or 1e6)
        rout = float(comp.get("rout", 50.0) or 50.0)
        pole_cap = aol / (2 * math.pi * gbw) if gbw > 0 else 1e-3
        return (
            f"* generic single-pole op-amp: Aol={_fmt(aol)}, GBW={_fmt(gbw)} Hz\n"
            f".subckt {name} inp inn vp vn out\n"
            f"E1 n1 0 inp inn 1\n"
            f"R1 n1 n2 1\n"
            f"C1 n2 0 {_fmt(pole_cap)}\n"
            f"E2 n3 0 n2 0 {_fmt(aol)}\n"
            f"Rout n3 out {_fmt(rout)}\n"
            f".ends {name}"
        )
    values = _model_params(ctype, comp)
    return _card_from_dict(name, ctype, values)


class ModelBook:
    """Collects model cards exactly once and resolves a model per component."""

    def __init__(self, spec: dict[str, Any]):
        self.spec = spec
        self.cards: list[str] = []
        self._emitted: dict[str, str] = {}
        self._by_ref: dict[str, str] = {}

    def _add(self, key: str, name: str, card: str) -> str:
        if key not in self._emitted:
            self._emitted[key] = name
            self.cards.append(card)
        return self._emitted[key]

    def model_for(self, comp: dict[str, Any]) -> str | None:
        ref = comp["ref"]
        ctype = comp["type"]
        if ctype not in GENERIC_MODELS and ctype not in ("SW", "OPAMP"):
            return None
        requested = comp.get("model")
        declared = self.spec.get("models") or {}
        if requested and requested in declared:
            raw = declared[requested]
            if isinstance(raw, str):
                card = raw.strip()
                if not card.startswith((".model", ".subckt", "*")):
                    card = f"* {requested}: {card}"
                name = requested
            else:
                name = str(raw.get("name", requested))
                card = _card_from_dict(name, str(raw.get("type", ctype)), dict(raw))
            return self._add(f"decl:{requested}", name, card)
        if ctype == "OPAMP":
            name = f"OPAMP_{ref}"
            return self._add(f"ref:{ref}", name, _generic_card(ctype, name, comp))
        base = requested or f"{ctype}GEN"
        name = f"{base}_{ref}"
        return self._add(f"ref:{ref}", name, _generic_card(ctype, name, comp))

    def text(self, *, header: str) -> str:
        return header + "\n" + "\n\n".join(self.cards) + "\n"


# ---------------------------------------------------------------------------
# SPICE netlist
# ---------------------------------------------------------------------------

def _source_value(comp: dict[str, Any]) -> str:
    waveform = comp.get("waveform")
    if waveform:
        wtype = str(waveform.get("type", "")).lower()
        params = waveform.get("params") or []
        if wtype in ("pulse", "sin", "pwl", "exp", "sffm"):
            body = " ".join(_fmt(float(p)) for p in params)
            return f"{wtype.upper()}({body})"
        raise ValueError(f"{comp['ref']}: unsupported waveform {wtype!r}")
    dc = float(comp.get("dc", comp.get("value", 0.0)) or 0.0)
    ac = float(comp.get("ac", 0.0) or 0.0)
    text = f"DC {_fmt(dc)}"
    if ac:
        text += f" AC {_fmt(ac)}"
    return text


def spice_netlist(spec: dict[str, Any]) -> str:
    norm = spec
    ground = norm["ground"]
    book = ModelBook(norm)
    lines = [
        f"* {norm['name']}: {norm.get('description') or 'circuit'}",
        "* Generated by circuit-design-skill.",
        "* Generic device models are placeholders: simulation results are UNVERIFIED",
        "* until vendor models are supplied.  Verify with the real datasheet.",
        "",
    ]

    device_lines: list[str] = []
    for comp in norm["components"]:
        ctype, ref = comp["type"], comp["ref"]
        element = spice_ref(ref, ctype)
        pins = comp["pins"]

        def net(key: str) -> str:
            return spice_net(pins[key], ground)

        if ctype in ("R", "C", "L"):
            device_lines.append(f"{element} {net('1')} {net('2')} {_fmt(comp['value'])}")
        elif ctype in ("V", "I"):
            device_lines.append(f"{element} {net('1')} {net('2')} {_source_value(comp)}")
        elif ctype in ("D", "LED", "ZENER"):
            model = book.model_for(comp)
            device_lines.append(f"{element} {net('1')} {net('2')} {model}")
        elif ctype in ("NPN", "PNP"):
            model = book.model_for(comp)
            device_lines.append(f"{element} {net('1')} {net('2')} {net('3')} {model}")
        elif ctype in ("NMOS", "PMOS"):
            model = book.model_for(comp)
            # Standard 4-terminal SPICE MOSFET; bulk tied to source.
            device_lines.append(
                f"{element} {net('1')} {net('2')} {net('3')} {net('3')} {model}"
            )
        elif ctype == "OPAMP":
            model = book.model_for(comp)
            device_lines.append(
                f"{element} {net('1')} {net('2')} {net('3')} {net('4')} {net('5')} {model}"
            )
        elif ctype == "SW":
            model = book.model_for(comp)
            device_lines.append(
                f"{element} {net('1')} {net('2')} {net('3')} {net('4')} {model}"
            )
        elif ctype in ("E", "G"):
            device_lines.append(
                f"{element} {net('1')} {net('2')} {net('3')} {net('4')} {_fmt(comp['value'])}"
            )
        else:  # pragma: no cover - validation rejects this
            raise ValueError(f"cannot netlist component type {ctype!r}")

    if book.cards:
        lines.append("* --- device models ---")
        lines.extend(book.cards)
        lines.append("")

    lines.append("* --- circuit ---")
    lines.extend(device_lines)
    lines.append("")

    directives = analyses_to_spice(norm["analyses"])
    if directives:
        lines.append("* --- analyses ---")
        lines.extend(directives)
        lines.append("")
    lines.append(".end")
    return "\n".join(lines) + "\n"


def analyses_to_spice(analyses: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for analysis in analyses:
        atype = analysis.get("type")
        if atype == "op":
            out.append(".op")
        elif atype == "ac":
            points = int(analysis.get("points", 100) or 100)
            out.append(f".ac dec {points} {_fmt(float(analysis['start']))} {_fmt(float(analysis['stop']))}")
        elif atype == "tran":
            bits = [f".tran {_fmt(float(analysis['step']))} {_fmt(float(analysis['stop']))}"]
            if analysis.get("start"):
                bits.append(_fmt(float(analysis["start"])))
            out.append(" ".join(bits))
        elif atype == "dc":
            source = analysis.get("source", "V1")
            start = float(analysis.get("start", 0.0))
            stop = float(analysis.get("stop", 1.0))
            step = float(analysis.get("step", 0.1))
            out.append(f".dc {source} {_fmt(start)} {_fmt(stop)} {_fmt(step)}")
        elif atype == "noise":
            output = analysis.get("output", "OUT")
            source = analysis.get("source", "V1")
            points = int(analysis.get("points", 100) or 100)
            start = float(analysis.get("start", 10.0))
            stop = float(analysis.get("stop", 1e6))
            out.append(f".noise v({output}) {source} dec {points} {_fmt(start)} {_fmt(stop)}")
        elif atype == "tf":
            output = analysis.get("output", "OUT")
            source = analysis.get("source", "V1")
            out.append(f".tf v({output}) {source}")
        else:
            raise ValueError(f"unsupported analysis type {atype!r}")
    return out


# ---------------------------------------------------------------------------
# LTspice .asc
# ---------------------------------------------------------------------------

def _asc_layout(components: list[dict[str, Any]]) -> dict[str, tuple[int, int]]:
    """Place one component per cell; net labels make routing unnecessary."""
    cols = 4 if len(components) > 3 else max(1, len(components))
    positions: dict[str, tuple[int, int]] = {}
    for i, comp in enumerate(components):
        row, col = divmod(i, cols)
        positions[comp["ref"]] = (200 + col * 280, 160 + row * 240)
    return positions


def _asc_value(comp: dict[str, Any], model: str | None) -> str:
    ctype = comp["type"]
    if ctype in ("R", "C", "L"):
        return _fmt(comp["value"])
    if ctype in ("V", "I"):
        waveform = comp.get("waveform")
        if waveform:
            return _source_value(comp)
        dc = float(comp.get("dc", comp.get("value", 0.0)) or 0.0)
        return _fmt(dc)
    if ctype in ("D", "LED", "ZENER", "NPN", "PNP", "NMOS", "PMOS", "SW", "OPAMP"):
        return model or ctype
    return _fmt(comp["value"])


def ltspice_asc(spec: dict[str, Any], *, version: str = "4") -> str:
    norm = spec
    book = ModelBook(norm)
    ground = norm["ground"]
    positions = _asc_layout(norm["components"])
    lines = [f"Version {version}", "SHEET 1 880 680"]
    flag_lines: list[str] = []
    seen_flags: set[tuple[int, int, str]] = set()

    for comp in norm["components"]:
        ctype, ref = comp["type"], comp["ref"]
        sx, sy = positions[ref]
        symbol, _pins = ASC_SYMBOLS[ctype]
        model = book.model_for(comp) if ctype in GENERIC_MODELS or ctype in ("SW", "OPAMP") else None
        lines.append(f"SYMBOL {symbol} {sx} {sy} R0")
        lines.append(f"SYMATTR InstName {ref}")
        lines.append(f"SYMATTR Value {_asc_value(comp, model)}")
        if ctype in ("V", "I") and comp.get("ac"):
            lines.append(f"SYMATTR Value2 AC {_fmt(float(comp['ac']))}")
        params = comp.get("params") or {}
        body = " ".join(
            f"{key}={_fmt(value)}"
            for key, value in params.items()
            if not isinstance(value, (dict, list))
        )
        if body:
            lines.append(f"SYMATTR SpiceLine {body}")

        for pin, (x, y) in asc_pins(ctype, sx, sy, 0, False).items():
            net = spice_net(comp["pins"][pin], ground)
            key = (x, y, net)
            if key not in seen_flags:
                seen_flags.add(key)
                flag_lines.append(f"FLAG {x} {y} {net}")

    lines.extend(flag_lines)

    # Directives: include the companion model file, then the analyses.
    lines.append(f"TEXT -260 160 Left 2 !.include {norm['name']}.models")
    y = 200
    for directive in analyses_to_spice(norm["analyses"]):
        lines.append(f"TEXT -260 {y} Left 2 !{directive}")
        y += 24
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# KiCad netlist
# ---------------------------------------------------------------------------

def _q(text: str) -> str:
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def kicad_netlist(spec: dict[str, Any], *, source: str = "") -> str:
    norm = spec
    ground = norm["ground"]
    nets: dict[str, list[tuple[str, str]]] = {}
    for comp in norm["components"]:
        for pin, net in comp["pins"].items():
            nets.setdefault(net, []).append((comp["ref"], pin))

    ordered = sorted(nets, key=lambda n: (n != ground, n.lower()))
    out = [
        "(export (version \"E\")",
        "\t(design",
        f"\t\t(source {_q(source or norm['name'] + '.kicad_sch')})",
        f"\t\t(date {_q(date.today().isoformat())})",
        "\t\t(tool \"circuit-design-skill\")",
        "\t)",
        "\t(components",
    ]
    for comp in norm["components"]:
        out.append(
            f"\t\t(comp (ref {_q(comp['ref'])}) (value {_q(_bom_value(comp))})"
            f" (footprint {_q(comp.get('footprint', ''))})"
            f" (description {_q(comp.get('notes', ''))}))"
        )
    out.append("\t)")
    out.append("\t(nets")
    for code, net in enumerate(ordered, start=1):
        out.append(f"\t\t(net (code {_q(str(code))}) (name {_q(net)})")
        for ref, pin in sorted(nets[net]):
            out.append(f"\t\t\t(node (ref {_q(ref)}) (pin {_q(pin)}))")
        out.append("\t\t)")
    out.append("\t)")
    out.append(")")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# KiCad schematic
# ---------------------------------------------------------------------------

def _kicad_effects(size: float = 1.27, hide: bool = False, justify: str | None = None) -> str:
    bits = [f"(font (size {size} {size}))"]
    if justify:
        bits.append(f"(justify {justify})")
    if hide:
        bits.append("(hide yes)")
    return "(effects " + " ".join(bits) + ")"


def _kicad_layout(components: list[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    cols = 4 if len(components) > 3 else max(1, len(components))
    out: dict[str, tuple[float, float]] = {}
    for i, comp in enumerate(components):
        row, col = divmod(i, cols)
        out[comp["ref"]] = (63.5 + col * 63.5, 50.8 + row * 50.8)
    return out


def kicad_schematic(spec: dict[str, Any], *, version: str = "20250114") -> str:
    norm = spec
    root = uid(norm["name"], "root")
    positions = _kicad_layout(norm["components"])
    types = [c["type"] for c in norm["components"]]

    out = [
        "(kicad_sch",
        f"\t(version {version})",
        "\t(generator \"circuit-design-skill\")",
        "\t(generator_version \"9.0\")",
        f"\t(uuid {_q(root)})",
        "\t(paper \"A4\")",
        "\t(title_block",
        f"\t\t(title {_q(norm['name'])})",
        f"\t\t(date {_q(date.today().isoformat())})",
        f"\t\t(comment 1 {_q(norm.get('description') or '')})",
        "\t)",
        kicad_lib_symbols(types),
        "",
    ]

    # Component symbols.
    for comp in norm["components"]:
        ref = comp["ref"]
        sx, sy = positions[ref]
        out.append(f"\t(symbol (lib_id {_q('circuit:' + comp['type'])}) (at {sx:g} {sy:g} 0) (unit 1)")
        out.append("\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)")
        out.append(f"\t\t(uuid {_q(uid(norm['name'], 'sym', ref))})")
        out.append(
            f"\t\t(property \"Reference\" {_q(ref)} (at {sx + 2.54:g} {sy - 3.81:g} 0) "
            f"{_kicad_effects()})"
        )
        out.append(
            f"\t\t(property \"Value\" {_q(_bom_value(comp))} (at {sx + 2.54:g} {sy + 3.81:g} 0) "
            f"{_kicad_effects()})"
        )
        for name in ("Footprint", "Datasheet", "Description"):
            value = comp.get("footprint", "") if name == "Footprint" else (
                comp.get("notes", "") if name == "Description" else ""
            )
            out.append(
                f"\t\t(property {_q(name)} {_q(value)} (at {sx:g} {sy:g} 0) "
                f"{_kicad_effects(hide=True)})"
            )
        for pin in KICAD_PINS[comp["type"]]:
            out.append(f"\t\t(pin {_q(pin)} (uuid {_q(uid(norm['name'], 'pin', ref, pin))}))")
        out.append("\t\t(instances")
        out.append(f"\t\t\t(project {_q(norm['name'])}")
        out.append(f"\t\t\t\t(path {_q('/' + root)} (reference {_q(ref)}) (unit 1))")
        out.append("\t\t\t)")
        out.append("\t\t)")
        out.append("\t)")

    # One global label per pin endpoint: exact-coordinate connectivity.
    seen: set[tuple[float, float, str]] = set()
    for comp in norm["components"]:
        ref = comp["ref"]
        sx, sy = positions[ref]
        for pin, (x, y, angle) in kicad_pins(comp["type"], sx, sy, 0, None).items():
            net = comp["pins"][pin]
            key = (round(x, 4), round(y, 4), net)
            if key in seen:
                continue
            seen.add(key)
            # Text points away from the symbol body.
            label_angle = (angle + 180) % 360
            if label_angle == 270:
                label_angle = 90
            out.append(f"\t(global_label {_q(net)} (shape input) (at {x:g} {y:g} {label_angle})")
            out.append("\t\t(fields_autoplaced yes)")
            out.append(f"\t\t{_kicad_effects(justify='left')}")
            out.append(f"\t\t(uuid {_q(uid(norm['name'], 'label', ref, pin, net))})")
            out.append(
                f"\t\t(property \"Intersheetrefs\" \"${{INTERSHEET_REFS}}\" "
                f"(at {x:g} {y:g} 0) {_kicad_effects(hide=True)})"
            )
            out.append("\t)")

    out.append("\t(sheet_instances")
    out.append("\t\t(path \"/\" (page \"1\"))")
    out.append("\t)")
    out.append("\t(embedded_fonts no)")
    out.append(")")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# BOM / report
# ---------------------------------------------------------------------------

_TYPE_NAMES = {
    "R": "Resistor", "C": "Capacitor", "L": "Inductor", "V": "Voltage source",
    "I": "Current source", "D": "Diode", "LED": "LED", "ZENER": "Zener diode",
    "NPN": "NPN transistor", "PNP": "PNP transistor", "NMOS": "N-MOSFET",
    "PMOS": "P-MOSFET", "OPAMP": "Op-amp", "SW": "Analog switch",
    "E": "VCVS", "G": "VCCS",
}


def _bom_value(comp: dict[str, Any]) -> str:
    ctype = comp["type"]
    if ctype in ("R", "C", "L"):
        return _fmt(comp["value"])
    if ctype in ("V", "I"):
        waveform = comp.get("waveform")
        if waveform:
            return f"{str(waveform.get('type', 'pulse')).upper()} source"
        return f"{_fmt(float(comp.get('dc', comp.get('value', 0.0)) or 0.0))} V" if ctype == "V" else \
               f"{_fmt(float(comp.get('dc', comp.get('value', 0.0)) or 0.0))} A"
    if ctype in ("D", "LED", "ZENER"):
        return f"{comp.get('model', 'generic')}"
    if ctype in ("NPN", "PNP", "NMOS", "PMOS", "SW", "OPAMP"):
        return f"{comp.get('model', 'generic')}"
    return _fmt(comp["value"])


def bom_rows(spec: dict[str, Any]) -> list[dict[str, str]]:
    groups: dict[tuple[str, str, str, str], list[str]] = {}
    for comp in spec["components"]:
        key = (
            comp["type"],
            _bom_value(comp),
            comp.get("footprint", ""),
            comp.get("notes", ""),
        )
        groups.setdefault(key, []).append(comp["ref"])
    rows = []
    for (ctype, value, footprint, notes), refs in sorted(groups.items(), key=lambda kv: kv[1][0]):
        rows.append({
            "References": " ".join(refs),
            "Qty": str(len(refs)),
            "Type": _TYPE_NAMES.get(ctype, ctype),
            "Value": value,
            "Footprint": footprint,
            "Notes": notes,
        })
    return rows


def bom_csv(spec: dict[str, Any]) -> str:
    rows = bom_rows(spec)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["References", "Qty", "Type", "Value",
                                             "Footprint", "Notes"], lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def build_report(spec: dict[str, Any], files: dict[str, str],
                 warnings: list[str], *, verification: dict[str, Any] | None = None,
                 pcb: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": spec["name"],
        "description": spec.get("description", ""),
        "topology": spec.get("topology", "custom"),
        "generated": date.today().isoformat(),
        "ground": spec["ground"],
        "supplies": spec.get("supplies", []),
        "environment": spec.get("environment", {}),
        "analyses": spec.get("analyses", []),
        "assumptions": spec.get("assumptions", []),
        "warnings": warnings,
        "components": spec["components"],
        "bom": bom_rows(spec),
        "files": files,
        "verification": verification,
        "pcb": pcb,
        "simulation_status": model_status(spec),
    }


def report_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# {report['name']}",
        "",
        report.get("description") or "",
        "",
        f"- Topology: `{report['topology']}`",
        f"- Ground: `{report['ground']}`",
        f"- Generated: {report['generated']}",
        f"- Simulation status: **{report['simulation_status']}**",
        "",
    ]
    if report["supplies"]:
        lines.append("## Supplies")
        lines.append("")
        for supply in report["supplies"]:
            lines.append(f"- `{supply.get('name')}` = {supply.get('voltage')} V")
        lines.append("")

    lines += [
        "## Components",
        "",
        "| Ref | Type | Value | Pins | Notes |",
        "| --- | --- | --- | --- | --- |",
    ]
    for comp in report["components"]:
        pins = ", ".join(f"{k}={v}" for k, v in sorted(comp["pins"].items()))
        value = _bom_value(comp)
        lines.append(
            f"| {comp['ref']} | {comp['type']} | {value} | {pins} | "
            f"{comp.get('notes', '') or comp.get('footprint', '')} |"
        )
    lines.append("")

    lines += [
        "## Bill of materials",
        "",
        "| Refs | Qty | Type | Value | Footprint |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report["bom"]:
        lines.append(
            f"| {row['References']} | {row['Qty']} | {row['Type']} | "
            f"{row['Value']} | {row['Footprint']} |"
        )
    lines.append("")

    lines += ["## Analyses", ""]
    for analysis in report["analyses"]:
        detail = ", ".join(f"{k}={v}" for k, v in analysis.items() if k != "type")
        lines.append(f"- `{analysis.get('type')}`" + (f" ({detail})" if detail else ""))
    lines.append("")

    if report["assumptions"]:
        lines += ["## Assumptions", ""]
        lines += [f"- {a}" for a in report["assumptions"]]
        lines.append("")

    if report["warnings"]:
        lines += ["## Warnings", ""]
        lines += [f"- {w}" for w in report["warnings"]]
        lines.append("")

    verification = report.get("verification")
    lines += ["## Verification", ""]
    if verification:
        status = "PASS" if verification.get("ok") else "FAIL"
        lines.append(f"Status: **{status}**")
        lines.append("")
        for check in verification.get("checks", []):
            mark = ("PASS" if check.get("ok") is True
                    else "FAIL" if check.get("ok") is False else "SKIP")
            lines.append(f"- [{mark}] {check.get('name')}: {check.get('detail', '')}")
        lines.append("")
    else:
        lines.append(
            "Not run yet. Run `python3 scripts/verify.py <spec.json>` after generation. "
            "Generic models are placeholders and do not constitute a verified design."
        )
        lines.append("")

    pcb = report.get("pcb")
    if pcb and pcb.get("enabled", True):
        lines += [
            "## PCB handoff",
            "",
            f"- Ready for `--no-ask`: **{'yes' if pcb.get('ready') else 'no'}**",
            f"- Board: {pcb['board']['width_mm']:g} x "
            f"{pcb['board']['height_mm']:g} mm, "
            f"{pcb['board']['layers']} layer(s)",
            f"- Profile: `{pcb['profile']}`",
        ]
        if pcb.get("missing_footprints"):
            lines.append("- Missing footprints: " +
                         ", ".join(f"`{ref}`" for ref in pcb["missing_footprints"]))
        if pcb.get("needs_pin_map"):
            lines.append("- Pin maps still needed: " +
                         ", ".join(f"`{ref}`" for ref in pcb["needs_pin_map"]))
        if pcb.get("excluded"):
            lines.append("- Excluded simulation-only parts: " +
                         ", ".join(f"`{ref}`" for ref in pcb["excluded"]))
        lines += [
            "",
            "The PCB overlay, pin map and node aliases are written for "
            "`pcb-design-skill`. The exact command is in "
            f"`{pcb['files']['handoff']}`. Footprints and package pinouts are "
            "not guessed here.",
            "",
        ]

    lines += ["## Files", ""]
    for kind, path in report["files"].items():
        lines.append(f"- `{kind}`: `{path}`")
    lines.append("")
    lines.append(
        "> The generated SPICE netlist is the electrical source of truth. "
        "The schematics are drawn from the same component list and use net labels "
        "at every pin instead of routed wires."
    )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def generate(spec_path: str | Path, outdir: str | Path,
             formats: list[str] | None = None,
             *, asc_version: str = "4", pcb_board: str | None = None,
             pcb_profile: str | None = None, pcb_layers: int | None = None,
             pcb_skill: str | Path | None = None) -> dict[str, Any]:
    raw = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    validation = validate_spec(raw)
    if not validation["ok"]:
        raise ValueError("invalid design spec: " + "; ".join(validation["errors"]))
    spec = validation["normalized"]
    formats = formats or [f for f in spec["deliverables"] if f in ALL_FORMATS]
    wanted = set(formats)
    if any(value is not None for value in
           (pcb_board, pcb_profile, pcb_layers, pcb_skill)):
        # Supplying PCB options is an explicit request for the handoff.
        wanted.add("pcb")
    if "pcb" in wanted:
        # The PCB importer needs the connectivity source.
        wanted.add("spice")
    formats = [f for f in ALL_FORMATS if f in wanted]
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)

    files: dict[str, str] = {}
    name = spec["name"]

    if "spice" in formats:
        path = out / f"{name}.cir"
        path.write_text(spice_netlist(spec), encoding="utf-8")
        files["spice"] = path.name
    if "ltspice_asc" in formats:
        models = out / f"{name}.models"
        models.write_text(
            ModelBook(spec).text(header=f"* models for {name} (generic unless supplied)"),
            encoding="utf-8",
        )
        files["models"] = models.name
        path = out / f"{name}.asc"
        path.write_text(ltspice_asc(spec, version=asc_version), encoding="utf-8")
        files["ltspice_asc"] = path.name
    if "kicad_net" in formats:
        path = out / f"{name}.net"
        path.write_text(kicad_netlist(spec, source=f"{name}.kicad_sch"), encoding="utf-8")
        files["kicad_net"] = path.name
    if "kicad_sch" in formats:
        path = out / f"{name}.kicad_sch"
        path.write_text(kicad_schematic(spec), encoding="utf-8")
        files["kicad_sch"] = path.name
    if "bom" in formats:
        path = out / f"{name}-bom.csv"
        path.write_text(bom_csv(spec), encoding="utf-8")
        files["bom"] = path.name
    pcb_summary = None
    if "pcb" in formats:
        import pcb_handoff  # noqa: PLC0415

        pcb_summary = pcb_handoff.write_handoff(
            spec, out, board=pcb_board, profile=pcb_profile,
            layers=pcb_layers, pcb_skill=pcb_skill,
        )
        for kind in ("overlay", "pin_map", "node_aliases", "handoff"):
            if kind in pcb_summary.get("files", {}):
                files[f"pcb_{kind}"] = pcb_summary["files"][kind]

    verification = None
    vpath = out / f"{name}-verification.json"
    if vpath.exists():
        try:
            verification = json.loads(vpath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            verification = None

    warnings = list(validation["warnings"])
    if pcb_summary:
        for warning in pcb_summary.get("warnings", []):
            if warning not in warnings:
                warnings.append(warning)
    report = build_report(spec, files, warnings,
                          verification=verification, pcb=pcb_summary)
    if "report" in formats:
        path = out / f"{name}-report.md"
        path.write_text(report_markdown(report), encoding="utf-8")
        files["report"] = path.name
        jpath = out / f"{name}-report.json"
        jpath.write_text(dumps(report) + "\n", encoding="utf-8")
        files["report_json"] = jpath.name
        report["files"] = files
    return {"ok": True, "spec": spec, "files": files, "report": report,
            "pcb": pcb_summary, "warnings": warnings}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="generate.py",
        description="Generate SPICE, LTspice and KiCad deliverables from a design spec.",
    )
    parser.add_argument("spec")
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument("--formats", default=None,
                        help=(f"comma-separated subset of {','.join(ALL_FORMATS)}; "
                              "default: the spec's deliverables"))
    parser.add_argument("--ltspice-version", default="4", choices=["4", "4.1"],
                        help="LTspice .asc Version line (default 4)")
    parser.add_argument("--pcb-board", metavar="WxH[xL]",
                        help="PCB board size in mm, e.g. 50x40 or 50x40x2")
    parser.add_argument("--pcb-layers", type=int,
                        help="PCB copper layer count (overrides pcb.board.layers)")
    parser.add_argument("--pcb-profile", help="pcb-design-skill profile name")
    parser.add_argument("--pcb-skill", help="path to the pcb-design-skill directory")
    ns = parser.parse_args(argv)

    formats = None
    if ns.formats:
        formats = [f.strip() for f in ns.formats.split(",") if f.strip()]
        unknown = [f for f in formats if f not in ALL_FORMATS]
        if unknown:
            print(f"error: unknown format(s): {', '.join(unknown)}", file=sys.stderr)
            return 2
    try:
        result = generate(
            ns.spec, ns.out, formats, asc_version=ns.ltspice_version,
            pcb_board=ns.pcb_board, pcb_profile=ns.pcb_profile,
            pcb_layers=ns.pcb_layers, pcb_skill=ns.pcb_skill,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for kind, path in result["files"].items():
        print(f"wrote {kind}: {Path(ns.out) / path}")
    for warning in result["warnings"]:
        print(f"warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
