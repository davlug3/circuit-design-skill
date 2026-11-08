---
name: circuit-design-skill
description: Design analog, digital, mixed-signal and power circuits from a structured intake, with every calculation in Python. Use when asked to design or size a circuit, choose component values, check op-amp/filter/converter/transistor behaviour, produce an LTspice .asc/.cir, a SPICE netlist, or KiCad .kicad_sch/.net files, or verify that a schematic and netlist agree. Includes design-intake questions, closed-form calculators, a pure-Python MNA solver, and evidence-based verification.
license: MIT
---

# Circuit Design

Design a circuit the way an engineer does: establish the requirements, choose
a topology, calculate the values, draw it, simulate it, and state what was and
was not verified.

**The generated SPICE netlist is the electrical source of truth.** The LTspice
and KiCad drawings are generated from the same component list, so they cannot
silently disagree with it.

## Non-negotiables

1. **Ask before guessing.** Use the intake questions in
   `references/intake.md`. If the user cannot answer, propose a default and
   record it in `assumptions`.
2. **Every calculation is Python.** Do not do arithmetic in prose that the
   scripts could do. Use `scripts/circuit_calc.py` or the MNA solver.
3. **Physics first.** Check headroom, polarity, power, thermal, tolerance and
   absolute maximum ratings. A netlist that runs is not a safe circuit.
4. **State the model.** A generic diode/BJT/MOSFET is a placeholder. Say
   "unverified (generic models)" until vendor models are supplied.
5. **Verify, then claim.** Run `scripts/verify.py`. A check that did not run is
   `SKIP`, not `PASS`. Never say "this should work".
6. **Do not claim ERC/DRC/fab compliance.** This skill produces schematics and
   netlists, not a manufactured board. Hand off to `pcb-design-skill` for
   layout, DRC and fabrication; see `references/pcb-handoff.md`.
7. **Pin numbers are logical, not physical.** See the warning in
   `references/kicad-format.md` before connecting a footprint.

## Workflow

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
```

26 commands:

| Group | Commands |
|---|---|
| Passive | `ohms`, `divider`, `rc`, `rl`, `rlc`, `eseries`, `tolerance`, `db` |
| Analog | `sallen-key`, `opamp`, `noise`, `current-mirror` |
| Devices | `bjt-bias`, `mosfet-bias`, `led`, `zener`, `crystal` |
| Power | `ldo`, `buck`, `boost`, `battery`, `thermal`, `trace` |
| Digital/interface | `i2c`, `adc`, `logic` |

Every command returns the same envelope: `ok`, `inputs`, `results`,
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
- `ngspice` runs the netlist if it is installed.

Read `references/verification.md` for what each check proves and what it does
not.

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
scripts/circuit_common.py    value parsing, E-series, result envelope
scripts/circuit_calc.py      26 calculators and CLI
scripts/mna.py               pure-Python linear MNA solver
scripts/design_spec.py       validate / normalize / scaffold
scripts/symbols.py           LTspice and KiCad symbol geometry
scripts/generate.py          .cir, .asc, .net, .kicad_sch, BOM, report
scripts/pcb_handoff.py       overlay, pin map, node aliases, handoff document
scripts/verify.py            structural, MNA, PCB and ngspice checks
references/                  intake, topologies, analog, digital, power,
                             physics/reliability, LTspice, KiCad, PCB handoff,
                             verification
examples/                    ready-to-run specs, including rc-lowpass-pcb.json
tests/                       unit and end-to-end tests
```

## Environment

Python 3.10+ standard library only. No numpy/scipy, no KiCad, no LTspice and
no ngspice are required to generate and structurally verify files. `kiutils`
is optional and only used for schematic parsing; `ngspice` is optional and only
used for simulation.

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

See the `references/` files for the specific equations and caveats.
