---
name: circuit-design-skill
description: Turn natural-language electronics requirements into complete, evidence-led circuit designs and coordinated KiCad projects: schematic, PCB, footprints, BOM and SPICE netlist. Conduct interactive requirements intake, use only common and explicitly recorded defaults for missing non-critical details, research real components and packages, calculate and simulate the design, and verify electrical, thermal, safety and board constraints. Use for end-to-end analog, digital, mixed-signal and power-circuit design, generation, simulation and verification.
license: MIT
---

# Circuit Design

Act as an end-to-end electronics design engineer. Starting from a natural-language description, elicit the missing requirements, propose a practical architecture, select real parts, calculate and optimize values, generate the editable KiCad project, simulate the circuit, and deliver a traceable bill of materials and SPICE netlist.

**The normalized circuit specification is the design contract; the generated SPICE netlist is the electrical simulation source of truth.** KiCad schematic, PCB, BOM and SPICE outputs must derive from one consistent design. A rendered SVG is only a view of the editable schematic.

The normal deliverable set is a complete project folder containing a KiCad project (`.kicad_pro`), schematic (`.kicad_sch`), PCB (`.kicad_pcb`), BOM (`.csv`), SPICE netlist (`.cir`), required models, simulation outputs/logs, verification report and research/assumption records. If a backend cannot generate or verify one of these, state the exact missing artifact and blocker; never label a partial handoff a complete project.

Treat the model's internal knowledge of electronics and physics as a source of
hypotheses, not as evidence. Before a number reaches the schematic, trace it to
a datasheet, an application note, a standard, or a measurement.

## Non-negotiables

1. **Plan before you draw.** Write the requirements (with acceptance limits),
   the architecture, the budgets, the risks, and the part decisions before
   generating a schematic. Use `references/design-process.md` and the templates
   in `templates/`.
2. **Interactive intake; bounded assumptions.** Ask the user for functional,
   electrical, mechanical, manufacturing and preference specifications using
   `references/intake.md`. Ask only questions that materially affect topology,
   safety, performance, cost or usability. For unanswered non-critical details,
   use conventional, widely available defaults only (for example common supply
   rails, standard E-series values, ordinary two-layer FR-4, and hand-solderable
   packages); record each assumption, rationale and confidence in the spec and
   report. Never invent a safety limit, interface contract, load, supply, pinout,
   isolation requirement or performance target. If a missing detail could make
   the design unsafe or fundamentally wrong, stop and ask. Summarize important
   assumptions and ask the user to correct them, but do not require a separate
   confirmation turn for every ordinary default. For clone/variant designs,
   lock the exact target revision and source hierarchy.
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
9. **Generate and verify the board, not just a handoff.** The intended final
   deliverable includes a real `.kicad_pcb`, not only a JSON overlay. Use the
   sibling `pcb-design-skill` to place, route and validate the board. Run ERC,
   DRC, unconnected-net, netlist-parity and applicable DFM/clearance checks.
   Report each gate independently. If the PCB backend is unavailable or a gate
   fails, include the best editable intermediate artifact and explicitly mark
   the project incomplete; never claim fabrication readiness.
10. **Pin numbers are logical, not physical.** See the warning in
    `references/kicad-format.md` before connecting a footprint.
11. **Probe capability, not presence.** A binary on `PATH` may still be
    unusable (wrong architecture, missing shared library, too old). Run
    `scripts/env_probe.py` before trusting a stage. If the local machine cannot
    run it, verify on CI and record the backend; never report a local `SKIP` as
    a local `PASS` because CI passed.
12. **Images must preserve engineering truth.** Render images from the
    editable KiCad schematic using the official KiCad CLI. Do not use an image
    generation model to redraw circuit connectivity. Prefer SVG; label it as
    a schematic rendering, not a PCB layout or proof of operation.
13. **Audio targets come from the audio skill.** For audio and sound work,
    requirements, perceptual limits and measurement conditions come from
    `audio-engineering-skill`, not from this skill's memory. This skill owns
    the implementation and verification. See `references/audio-handoff.md`.

## Schematic image export

After generating a KiCad schematic, render it with KiCad 9+:

```bash
python3 scripts/render_schematic.py out/design.kicad_sch --out out/images/
```

The renderer invokes `kicad-cli sch export svg`, verifies that SVG files were
created and parses each output as XML. The SVG is a visual representation of
the editable KiCad schematic; it is not a PCB layout, an independent
connectivity source, or evidence that the circuit operates.

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

Treat every natural-language request as a request for a complete, build-oriented design unless the user explicitly limits scope. Conduct the short conversational intake in `references/intake.md`; do not make the user fill out an engineering form or know component terminology.

The standard deliverable set is mandatory: a native KiCad project (`.kicad_pro`), editable schematic (`.kicad_sch`), PCB (`.kicad_pcb`), researched footprints and physical pin maps, BOM (`.csv`), SPICE netlist (`.cir`), simulation results/logs, and a verification report. Include models and provenance, rendered schematic, and fabrication outputs when their relevant gates pass. Ask for missing board dimensions, layer count, connectors, mounting, fabrication or assembly preferences needed to complete the board. Do not silently downgrade the request to a PCB overlay or handoff: if the native board workflow is unavailable, report the exact missing artifact and mark the project incomplete.

Ask what the circuit must do, its inputs/outputs, supply and load, performance targets, environment/safety constraints, and build preferences. Offer common choices in plain language (for example through-hole vs SMD, low-cost vs high-performance, compact vs easy-to-hand-solder). Use conventional defaults only for non-critical omissions, record them, and ask before resolving anything that affects safety, topology, interface compatibility, or acceptance.

For a fast path, scaffold a known topology and then edit the JSON:

```bash
python3 scripts/design_spec.py scaffold --topology rc_lowpass \
  --param r=1k --param c=100n --out specs/rc.json
```

Supported scaffolds: `rc_lowpass`, `rc_highpass`, `divider`, `sallen_key_lp`,
`sallen_key_hp`, `bjt_ce`, `led`, `i2c`, `opamp_noninverting`, `opamp_inverting`,
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

### 4. Optimize, then generate

For supported first-order RC low-pass designs, search standard E-series values
against the target cutoff and exact independent R/C tolerance corners:

```bash
python3 scripts/optimize.py specs/rc.json --target-fc 1.59k \\
  --r-min 1k --r-max 100k --c-min 10n --c-max 1u \\
  --r-tol 1 --c-tol 10 --max-error-percent 5 \\
  --out-spec specs/rc-optimized.json --require-feasible
```

The optimizer ranks discrete candidates by worst-case cutoff error and records
the search method in the output spec. It currently supports `rc_lowpass` only
and assumes an ideal source and unloaded output. It does not optimize loaded
filters, active filters or nonlinear/power topologies. Simulate the optimized
spec with the actual source/load and verify datasheet operating limits before
accepting it. See `references/optimization.md`.

### 5. Generate

For KiCad or PCB outputs, **research footprints before assigning them**. Follow
`references/footprint-research.md`: search the exact MPN and datasheet package
drawing first; for generic parts, search for the component class, power rating
and KiCad footprint (for example, `KiCad common footprint 0.5 W axial resistor`).
Prefer manufacturer mechanical drawings, then the official KiCad library/KLC;
use forums only as secondary evidence of common practice. Match body size, lead
pitch, pad/drill dimensions, orientation and pin numbering. Record the source
URL and selected footprint in the spec/research log. If exact fit is uncertain,
mark it provisional or leave it unassigned—do not present a generic default as
datasheet-verified.

For ICs and all semiconductors, first enumerate the exact manufacturer's
available package variants for the selected MPN, then choose the most
DIY-friendly package that meets electrical and thermal requirements. Prefer
through-hole if that exact part is offered; otherwise prefer larger, widely
spaced hand-solderable leads (e.g. SOIC/SOP) over fine-pitch or leadless
packages. Never assume a generic transistor is TO-92 or a generic op-amp is
DIP-8. Match the chosen package's mechanical drawing and pinout to the KiCad
footprint. If no manufacturer package evidence is available, leave it
unassigned and request clarification. See the dedicated semiconductor rules
in `references/footprint-research.md`.

For a 0.5 W through-hole axial resistor, a common candidate is
`Resistor_THT:R_Axial_DIN0309_L9.0mm_D3.2mm_P12.70mm_Horizontal`, whose KiCad
library description identifies a DIN0309 9.0 x 3.2 mm body and 12.70 mm pitch.
Confirm those dimensions against the actual resistor datasheet; 0.5 W alone
does not uniquely determine body size or lead spacing.

After research, use the assembly-aware wrapper. It asks whether the design is
primarily SMD or through-hole, fills passive defaults only, and deliberately
leaves semiconductors without explicit researched footprints unassigned:

```bash
python3 scripts/generate_with_footprints.py specs/rc.json --out out/
# Non-interactive use:
python3 scripts/generate_with_footprints.py specs/rc.json --out out/ --assembly smd
python3 scripts/generate_with_footprints.py specs/rc.json --out out/ --assembly through-hole
```

Through-hole is the preferred default (press Enter at the prompt). The wrapper
provides offline fallback mappings for common passives only. It intentionally
does not auto-assign diode, LED, zener, BJT, MOSFET, op-amp or other IC
footprints: these must be researched against the exact manufacturer's available
package options and selected using the DIY-first ranking above. The wrapper
prints a reminder for semiconductor refs missing explicit footprints. Existing
explicit, research-backed footprints are preserved. Logical SPICE pins are not
physical package pads; pin maps remain a separate, datasheet-backed decision.
See `references/footprint-research.md`.

```bash
python3 scripts/generate_with_footprints.py specs/rc.json --out out/
python3 scripts/generate_with_footprints.py specs/rc.json --out out/ --formats spice,ltspice_asc,kicad_sch
python3 scripts/generate_with_footprints.py specs/rc.json --out out/ --ltspice-version 4.1
python3 scripts/generate_with_footprints.py specs/rc.json --out out/ --pcb-board 50x40
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
| `<name>-pcb.json` | Intermediate PCB handoff overlay; not a native board |
| `<name>-pinmap.json` | SPICE pin -> footprint pad map |
| `<name>-node-aliases.json` | SPICE node -> PCB net aliases |
| `<name>-pcb-handoff.md` | Exact PCB-skill command and remaining gaps |

The `.asc` uses a deterministic grid layout. KiCad also supports explicit
`placement: {x_mm, y_mm}` overrides per component, aligned to its 1.27 mm
grid; these overrides affect the KiCad drawing only. The `.kicad_sch` default
layout places one component per cell, with a net label at every pin. This is
intentional: it avoids fragile autorouting and makes the connectivity exact.
Use placement overrides to organize the KiCad drawing into functional blocks;
the LTspice `.asc` retains its own deterministic grid. Clean up the presentation
in LTspice or KiCad if you need a publication-quality drawing.

### 6. PCB generation and handoff

A PCB is part of the standard deliverable set, not an optional afterthought. Ask for board size, layer count, connector placement, mounting, stackup and fabrication constraints when these are not supplied. Use only ordinary, explicitly recorded defaults for non-critical manufacturing choices; never guess a mechanical envelope, isolation spacing, impedance requirement or connector pinout. Generate a native `.kicad_pcb` and matching `.kicad_pro` through the sibling `pcb-design-skill`, using the schematic netlist, researched footprints and datasheet-backed pin maps. The JSON overlay is an intermediate handoff artifact only and does not satisfy the PCB deliverable.

If the sibling PCB workflow is unavailable, still generate all supported electrical artifacts and the complete PCB handoff package, but mark `.kicad_pcb`/`.kicad_pro` as NOT GENERATED and the project as INCOMPLETE. Never describe the handoff overlay as a board or claim fabrication readiness.

```bash
python3 scripts/generate_with_footprints.py specs/rc.json --out out/ --pcb-board 50x40
python3 scripts/pcb_handoff.py specs/rc.json --out out/ --board 50x40
```

The circuit spec may carry a `pcb` block with `profile`, `board`, `rules`,
`netclasses`, `footprints`, `pin_map`, `node_aliases`, `placement`, `routing`
and `extra_components`. See `references/pcb-handoff.md`.

The handoff writes the overlay, a pin map and node aliases, then prints the exact command for `pcb-design-skill`. This is an intermediate stage only: continue through native board generation, placement, routing and validation. It never guesses a footprint or package pinout. Missing footprints and pin maps are blockers, not acceptable final omissions. Logical SPICE pins are not physical pads (NPN 1/2/3 = C/B/E here), so a pin map from the real datasheet is mandatory for multi-pin parts. An op-amp `U1` is imported by SPICE as `XU1`; the handoff maps the reference and says so.

Do not claim a board is manufacturable until the PCB skill's DRC, DFM,
unconnected and netlist-parity gates pass.

### 7. Verify

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

### 8. Report

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
scripts/optimize.py          discrete E-series RC low-pass optimizer
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
references/optimization.md   discrete search method, assumptions and limits
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
