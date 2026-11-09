---
name: circuit-design-skill
description: Design analog, digital, mixed-signal and power circuits from requirements to verified files. Use when planning a design, comparing architectures, choosing parts, sizing components, checking op-amp/filter/converter/transistor behaviour, finding and ingesting real SPICE models, producing an LTspice .asc/.cir, a SPICE netlist, or KiCad .kicad_sch/.net files, or verifying that a schematic and netlist agree. Includes intake questions, a planning and evidence workflow, part-selection decision records, open-web research guidance, closed-form calculators, a pure-Python MNA solver, model provenance, and evidence-based verification.
license: MIT
---

# Circuit Design

Design a circuit the way an engineer does: establish the requirements, choose
a topology, calculate the values, draw it, simulate it, and state what was and
was not verified.

**The generated SPICE netlist is the electrical source of truth.** The LTspice
and KiCad drawings are generated from the same component list, so they cannot
silently disagree with it.

Treat the model's internal knowledge of electronics and physics as a source of
hypotheses, not as evidence. Before a number reaches the schematic, trace it to
a datasheet, an application note, a standard, or a measurement.

## Non-negotiables

1. **Plan before you draw.** Write the requirements (with acceptance limits),
   the architecture, the budgets, the risks, and the part decisions before
   generating a schematic. Use `references/design-process.md` and the templates
   in `templates/`.
2. **Ask before guessing.** Use the intake questions in
   `references/intake.md`. If the user cannot answer, propose a default and
   record it in `assumptions`. Before generating artifacts, restate locked
   defaults/assumptions and get explicit confirmation (e.g. `defaults
   confirmed` or a list of changes). For clone/variant designs, lock the target
   revision/topology, primary anchor source, known source conflicts, and
   allowed substitutions.
3. **Every calculation is Python.** Do not do arithmetic in prose that the
   scripts could do. Use `scripts/circuit_calc.py` or the MNA solver.
4. **Physics first.** Check headroom, polarity, power, thermal, tolerance and
   absolute maximum ratings. A netlist that runs is not a safe circuit. Use
   exact tolerance-corner analysis for supported scalar equations, then verify
   worst-case component stresses against sourced datasheet limits. Do not treat
   nominal values or first-order RSS estimates as guaranteed worst cases.
5. **Cite the evidence.** Every critical parameter, formula, derating rule and
   part choice needs a source a reviewer can open: datasheet revision, app
   note, standard clause, or measurement. See
   `references/electronics-research.md`. "The model remembers it" is not a
   source.
6. **Record the decision.** A part or architecture choice is not complete until
   the alternatives, the operating point, the rationale and the residual risk
   are written down. See `templates/decision-record.md` and
   `references/part-selection.md`.
7. **State the model.** A generic diode/BJT/MOSFET is a placeholder. Say
   "unverified (generic models)" until a real model with vendor, part and
   source is recorded in `models`. Prefer a fetched, hashed model over a typed
   one. See `references/models.md`; a `.subckt` model also needs an explicit
   `subckt_pins` node order.
8. **Verify, then claim.** Run `scripts/verify.py`. A check that did not run is
   `SKIP`, not `PASS`. Never say "this should work".
9. **Do not claim ERC/DRC/fab compliance.** This skill produces schematics and
   netlists, not a manufactured board. Hand off to `pcb-design-skill` for
   layout, DRC and fabrication; see `references/pcb-handoff.md`.
10. **Pin numbers are logical, not physical.** See the warning in
    `references/kicad-format.md` before connecting a footprint.
11. **Probe capability, not presence.** A binary on `PATH` may still be
    unusable (wrong architecture, missing shared library, too old). Run
    `scripts/env_probe.py` before trusting a stage. If the local machine cannot
    run it, verify on CI and record the backend; never report a local `SKIP` as
    a local `PASS` because CI passed.
12. **Audio targets come from the audio skill.** For audio and sound work,
    requirements, perceptual limits and measurement conditions come from
    `audio-engineering-skill`, not from this skill's memory. This skill owns
    the implementation and verification. See `references/audio-handoff.md`.

## Workflow

### 0. Plan, research, choose

Do this before intake or scaffolding. It is the cheapest place to fix a design.

1. **Frame** the problem: function, environment, supplies, load, mechanical
   limits, lifecycle, compliance, and acceptance measurements.
2. **Research** the candidate technologies and parts. Start from datasheets and
   vendor application notes; use standards for compliance claims. Log the
   revision and access date. See `references/electronics-research.md`.
3. **Architect**: block diagram, interface contracts, power tree, grounding,
   protection, test points. Compare at least one alternative and record why it
   was rejected. See `references/design-process.md`.
4. **Budget**: power, thermal, tolerance, timing, noise, cost, area. Put the
   numbers in Python, not in prose.
5. **Select parts**: gate on must-haves, score the survivors, verify the winner
   at the worst-case operating point, and write a decision record. See
   `references/part-selection.md`.
6. **Record** the result in the spec's `design` object:

   ```json
   "design": {
     "requirements": [{"id": "R1", "text": "5 V +/-2% at 0-1 A", "acceptance": "measure at 0 A and 1 A", "source": "brief rev A"}],
     "architecture": {"summary": "buck converter", "blocks": ["input", "buck", "output"], "budgets": {"efficiency": "> 85%"}},
     "decisions": [{"id": "D1", "decision": "buck instead of linear", "alternatives": ["LDO"], "rationale": "1.5 W would overheat an LDO", "sources": ["TPS datasheet, thermal section"]}],
     "risks": [{"id": "K1", "risk": "inductor saturation at startup", "severity": "high", "mitigation": "soft-start and 1.5x Isat margin", "verification": "startup transient at 40 C"}],
     "sources": [{"title": "TPS datasheet", "document": "SBVS123", "revision": "C", "accessed": "2026-11-08"}]
   }
   ```

   `python3 scripts/verify.py --require design` fails a spec with no complete
   record. Start from `templates/design-plan.md`,
   `templates/decision-record.md` and `templates/research-log.md`.

### 1. Intake

Ask the questions in `references/intake.md`. The minimum viable set:

- What must it do, and what are the input and output?
- What supply voltage(s) are available?
- What load must it drive?
- What accuracy, bandwidth or current is required?
- Which deliverables: SPICE, LTspice `.asc`, KiCad `.kicad_sch`/`.net`, BOM,
  report, PCB handoff?

For a fast path, scaffold a known topology and then edit the JSON:

```bash
python3 scripts/design_spec.py scaffold --topology rc_lowpass \
  --param r=1k --param c=100n --out specs/rc.json
```

Supported scaffolds: `rc_lowpass`, `rc_highpass`, `divider`, `sallen_key_lp`,
`sallen_key_hp`, `bjt_ce`, `led`, `i2c`, `opamp_noninverting`,
`zener_regulator`, `buck`.

### 2. Spec

The spec is a JSON object validated against
`schemas/design-spec.schema.json`. The component list is authoritative;
`topology` and `parameters` drive the calculators and the scaffold.

```bash
python3 scripts/design_spec.py validate specs/rc.json
python3 scripts/design_spec.py explain  specs/rc.json
python3 scripts/design_spec.py normalize specs/rc.json --out specs/rc.normalized.json
```

Rules:

- `ground` must be a net connected to at least one component.
- At least one independent source (`V` or `I`) is required.
- Every component needs `ref`, `type` and `pins`; `value` defaults to `0`.
- Pin names accept aliases: `A`/`K`, `C`/`B`/`E`, `D`/`G`/`S`, `IN+`/`IN-`,
  `V+`/`V-`, `OUT`.
- A one-pin net is reported as floating; that is usually a wiring mistake.

### 3. Calculate

```bash
python3 scripts/circuit_calc.py <command> [--json] [--param value ...]
python3 scripts/circuit_calc.py list

# Exact worst-case corners plus sensitivity/RSS for an RC cutoff
python3 scripts/circuit_calc.py tolerance --mode rc_fc \\
  --components '{"r":{"value":1000,"tol":1},"c":{"value":1e-7,"tol":10}}' --json
```

26 commands:

| Group | Commands |
|---|---|
| Passive | `ohms`, `divider`, `rc`, `rl`, `rlc`, `eseries`, `tolerance`, `db` |
| Analog | `sallen-key`, `opamp`, `noise`, `current-mirror` |
| Devices | `bjt-bias`, `mosfet-bias`, `led`, `zener`, `crystal` |
| Power | `ldo`, `buck`, `boost`, `battery`, `thermal`, `trace` |
| Digital/interface | `i2c`, `adc`, `logic` |

The tolerance command enumerates every min/max combination (up to 16 variables),
reports the exact range and corner assignments, and retains first-order
sensitivity/RSS as separate estimates. It does not model temperature drift,
aging or correlated tolerances unless those effects are included in the input
ranges. Every command returns the same envelope: `ok`, `inputs`, `results`,
`formulas`, `assumptions`, `warnings`, `notes`. Use `--json` when you need to
feed the result into a spec.

Formulas and design notes live in `references/topologies.md`,
`references/analog.md`, `references/digital.md`, `references/power.md` and
`references/physics-reliability.md`.

### 4. Generate

```bash
python3 scripts/generate.py specs/rc.json --out out/
python3 scripts/generate.py specs/rc.json --out out/ --formats spice,ltspice_asc,kicad_sch
python3 scripts/generate.py specs/rc.json --out out/ --ltspice-version 4.1
python3 scripts/generate.py specs/rc.json --out out/ --pcb-board 50x40
```

Every semiconductor needs a real model before the simulation means anything:
supply a vendor `.lib`/`.mod` file (or full card) in `models`, with `vendor`,
`part` and `source`. A `.subckt` model also needs `subckt_pins`; the generator
then emits an `X` device in that node order. See `references/models.md`.

To find and ingest a published model, use the catalog and the fetcher:

```bash
python3 scripts/model_fetch.py --list
python3 scripts/model_fetch.py --part 2N3904 --out models/
python3 scripts/model_fetch.py --part 2N7002 --write-spec specs/switch.json --ref M1
```

The fetcher downloads the file, extracts the requested `.model` or `.subckt`,
refuses a file that does not define it, records the SHA-256 and provenance, and
writes a `models` entry the resolver accepts. It does not certify that the model
matches your physical part, and it does not bypass a vendor's licence: read the
file header, do not commit restricted vendor models, and prefer `--file` with
`--source` when a site's TLS certificate is broken.

Without `--formats`, the spec's `deliverables` list is used. Outputs:

| File | Purpose |
|---|---|
| `<name>.cir` | Self-contained SPICE netlist; the simulation source of truth |
| `<name>.models` | Model cards for the `.asc` include |
| `<name>.asc` | LTspice schematic, net labels at every pin |
| `<name>.net` | KiCad netlist |
| `<name>.kicad_sch` | KiCad 9 schematic with embedded symbols |
| `<name>-bom.csv` | Bill of materials |
| `<name>-report.md` / `.json` | Design report |
| `<name>-pcb.json` | PCB overlay (when `pcb` or `--pcb-board` is requested) |
| `<name>-pinmap.json` | SPICE pin -> footprint pad map |
| `<name>-node-aliases.json` | SPICE node -> PCB net aliases |
| `<name>-pcb-handoff.md` | Exact PCB-skill command and remaining gaps |

The `.asc` and `.kicad_sch` are laid out on a grid, one component per cell,
with a net label at every pin. This is intentional: it avoids fragile
autorouting and makes the connectivity exact. Clean up the presentation in
LTspice or KiCad if you need a publication-quality drawing.

### 5. PCB handoff

PCB files are opt-in: add `"pcb"` to `deliverables`, pass `--pcb-board
WIDTHxHEIGHT`, or add `pcb` to `--formats`. The handoff needs a board size; it
does not guess one.

```bash
python3 scripts/generate.py specs/rc.json --out out/ --pcb-board 50x40
python3 scripts/pcb_handoff.py specs/rc.json --out out/ --board 50x40
```

The circuit spec may carry a `pcb` block with `profile`, `board`, `rules`,
`netclasses`, `footprints`, `pin_map`, `node_aliases`, `placement`, `routing`
and `extra_components`. See `references/pcb-handoff.md`.

The handoff writes the overlay, a pin map and node aliases, then prints the
exact command for `pcb-design-skill`. It never guesses a footprint or a package
pinout: missing footprints and pin maps are listed for the PCB skill's visual
picker. Logical SPICE pins are not physical pads (NPN 1/2/3 = C/B/E here), so a
pin map from the real datasheet is mandatory for multi-pin parts. An op-amp
`U1` is imported by SPICE as `XU1`; the handoff maps the reference and says so.

Do not claim a board is manufacturable until the PCB skill's DRC, DFM,
unconnected and netlist-parity gates pass.

### 6. Verify

```bash
python3 scripts/verify.py specs/rc.json --out out/
python3 scripts/verify.py specs/rc.json --out out/ --json
# Require explicit, sourced component stress checks before calling the design accepted
python3 scripts/verify.py specs/rc.json --out out/ --require limits
```

The verifier re-reads the generated files and checks:

- SPICE device node lists match the spec;
- LTspice flags sit at the correct pin coordinates with the correct nets;
- KiCad netlist nets match the spec exactly;
- KiCad schematic pins have the correct global labels (via `kiutils`, if
  installed);
- the PCB overlay, pin map and node aliases agree with the netlist, and the
  sibling PCB validator accepts the overlay when all footprints are present;
- linear circuits solve in the independent MNA solver and match closed-form
  expectations;
- `ngspice` runs the netlist if it is installed and compatible;
- declared gain, bandwidth, THD, noise or RMS metrics are extracted from the
  ngspice rawfile and compared with their targets or limits (see
  `references/metrics.md`);
- every semiconductor resolves to a real, traceable model, or is reported as
  a generic placeholder (add `--require models` to make that a failure);
- every declared operating stress is within its sourced min/max datasheet limit; `--require limits` makes a missing or failing limits record a failure;
- the `design` record has requirements, an architecture, sourced decisions,
  risks and sources (add `--require design` to make a missing record a failure);
- KiCad ERC runs with `--erc` when `kicad-cli` is installed and compatible.

Read `references/verification.md` for what each check proves and what it does
not, and `references/metrics.md` for the metric block, analysis requirements
and limits.

#### When the local machine cannot run a check

```bash
# What can this machine actually do?
python3 scripts/env_probe.py --spec specs/rc.json

# Make the run fail unless simulation really passed here.
python3 scripts/verify.py specs/rc.json --out out/ --require simulate

# Machine is aarch64/Android with no ngspice or KiCad? Use CI.
python3 scripts/ci_dispatch.py --spec specs/rc.json --require simulate,erc \
  --watch --download out/ci
```

The probe runs each tool, not just `which`. It reports `MISSING` and
`INCOMPATIBLE` separately, and `recommended_backend` is `local`, `ci` or
`none`. The verifier's JSON records `provenance.backend`, so a CI result is
never mistaken for a local one.

CI dispatch requires a git repository with a pushed branch and the
`.github/workflows/design.yml` workflow; it refuses a dirty tree, an unpushed
commit or a spec outside the repository, because GitHub would verify a
different revision.

### 7. Report

The report states the design, the assumptions, the warnings, the analyses and
the verification evidence. Quote it; do not replace it with a vague summary.

## Design rules of thumb

These are starting points, not laws. Verify the ones that matter.

- Op-amp: `GBW >= 10*Gain*f_max`; `SR >= 2*pi*f_max*Vpeak`.
- Divider: divider current at least 10x the load current, or buffer it.
- RC filter: source and load impedances should be at least 10x away from `R`.
- Sallen-Key LP: `C1 = 2*C2` and equal `R` gives Butterworth `Q = 0.707`.
- Sallen-Key HP: `R2 = 2*R1` and equal `C` gives Butterworth `Q = 0.707`.
- Buck: ripple ratio `0.2–0.4`; inductor saturation above peak current.
- LDO: `P = (Vin-Vout)*Iout`; check the thermal pad and the capacitor ESR.
- I2C: `Rp(min) = (VDD-VOL)/IOL`; `Rp(max) = tr/(0.8473*Cb)`.
- ADC: `SNR = 6.02N + 1.76 dB`; settle to 0.5 LSB.
- Thermal: `Tj = Ta + P*(theta_jc + theta_cs + theta_sa)`; derate.
- Trace: IPC-2221 for temperature rise, then check voltage drop.

## Safety and scope

Stop and ask before proceeding with:

- mains, high voltage (> 60 V DC or > 30 V AC), or an isolation barrier;
- lithium battery charging;
- medical, automotive safety, or life-support use;
- RF power or antenna-facing circuitry;
- anything where a wrong pin assignment could destroy hardware.

This skill does not replace a datasheet, a bench measurement, ERC/DRC, or a
safety review.

## Files

```
SKILL.md
README.md
LICENSE
schemas/design-spec.schema.json
catalog/models.json          known fetchable model sources (part, model, vendor)
scripts/circuit_common.py    value parsing, E-series, result envelope
scripts/circuit_calc.py      26 calculators and CLI
scripts/mna.py               pure-Python linear MNA solver
scripts/design_spec.py       validate / normalize / scaffold / model resolution
scripts/symbols.py           LTspice and KiCad symbol geometry
scripts/generate.py          .cir, .asc, .net, .kicad_sch, BOM, report
scripts/model_fetch.py       find, validate, hash and ingest a SPICE model
scripts/pcb_handoff.py       overlay, pin map, node aliases, handoff document
scripts/ngspice_raw.py       ASCII rawfile parser: plots, variables, complex data
scripts/metrics.py           gain, bandwidth, THD, noise and RMS extraction
scripts/audio_handoff.py     merge an audio handoff and test-point map
scripts/verify.py            structural, MNA, metrics, ERC, model and design checks
scripts/env_probe.py         capability probe: ok / incompatible / missing
scripts/ci_dispatch.py       GitHub Actions dispatch with safety checks
.github/workflows/design.yml  unit tests, KiCad 9 + ngspice verification
references/                  planning and research, part selection, intake,
                             topologies, analog, digital, power,
                             physics/reliability, LTspice, KiCad, PCB handoff,
                             models, metrics, verification
templates/                   design plan, decision record, research log
examples/                    ready-to-run specs, including rc-lowpass-pcb.json,
                             rc-lowpass-metrics.json and the audio handoff
                             fixtures
tests/                       unit and end-to-end tests
```

## Environment

Python 3.10+ standard library only. No numpy/scipy, no KiCad, no LTspice and
no ngspice are required to generate and structurally verify files. `kiutils`
is optional and only used for schematic parsing; `ngspice` is optional and only
used for simulation; `kicad-cli` is optional and only used for ERC.

Presence is not capability. Run the probe first:

```bash
python3 scripts/env_probe.py
python3 scripts/env_probe.py --json --spec specs/rc.json
```

If the stages you need are `NOT READY`, dispatch the same spec to the GitHub
Actions workflow instead of claiming the check passed:

```bash
python3 scripts/ci_dispatch.py --spec specs/rc.json --require simulate,erc --watch
```

```bash
python3 -m unittest discover -s tests -v
```

## Sources

The format details were checked against vendor documentation, not memory:

- Analog Devices, *LTspice Schematic Reference* and *LTspice Help*.
- KiCad developer documentation, *Schematic file format* and *Netlist file
  format*; KiCad 9 demo files.
- TI, *Basic Calculation of a Buck Converter's Power Stage* (SLVA477C).
- TI, *Op Amps for Everyone* (SLOD006) and filter application notes.
- NXP, *UM10204 I2C-bus specification*.
- IPC-2221B, *Generic Standard on Printed Board Design*.
- KiCad Spice Library and PySpice example libraries as model mirrors; each
  fetched model keeps its own header and source URL. Check the source's terms
  before redistributing a model.

Design decisions are only as good as their evidence. For each project, add the
actual datasheet revisions, application notes, standards and measurements to
`design.sources`; do not rely on this list as a substitute. See
`references/electronics-research.md` for the source hierarchy and citation
format.

See the `references/` files for the specific equations and caveats.
