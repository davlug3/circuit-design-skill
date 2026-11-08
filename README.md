# circuit-design-skill

Design analog, digital, mixed-signal and power circuits from a structured
intake, with every calculation in Python. Generate a SPICE netlist, an LTspice
schematic, a KiCad 9 schematic and netlist, a BOM and a verification report.

The generated SPICE netlist is the electrical source of truth. The LTspice and
KiCad drawings are generated from the same component list, so the picture and
the netlist cannot silently disagree.

## Why this exists

Most circuit mistakes are not exotic. They are:

- a divider loaded by the thing it drives;
- an op-amp without enough GBW or slew rate;
- a Sallen-Key high-pass with the wrong Q formula;
- an inductor that saturates at the peak current;
- a schematic whose pin numbers do not match its netlist;
- a simulation with a generic transistor presented as a verified design.

This skill makes those mistakes visible: it asks for the requirements, does the
arithmetic in Python, emits files from one component list, and re-reads the
files to check them.

## Requirements

- Python 3.10+ (tested on 3.14)
- Standard library only: no numpy, scipy, KiCad, LTspice or ngspice required
- Optional: `kiutils` for KiCad schematic parsing
- Optional: `ngspice` for nonlinear simulation

## Quick start

```bash
# 1. Scaffold a design
python3 scripts/design_spec.py scaffold --topology rc_lowpass \
  --param r=1k --param c=100n --out specs/rc.json

# 2. Validate and inspect it
python3 scripts/design_spec.py validate specs/rc.json
python3 scripts/design_spec.py explain specs/rc.json

# 3. Generate everything
python3 scripts/generate.py specs/rc.json --out out/

# 4. Verify it
python3 scripts/verify.py specs/rc.json --out out/

# 5. Optional PCB handoff for pcb-design-skill
python3 scripts/generate.py specs/rc.json --out out/ --pcb-board 50x40
```

Outputs in `out/`:

| File | Purpose |
|---|---|
| `rc_lowpass.cir` | Self-contained SPICE netlist (models inline) |
| `rc_lowpass.models` | Model cards for the LTspice include |
| `rc_lowpass.asc` | LTspice schematic |
| `rc_lowpass.net` | KiCad netlist |
| `rc_lowpass.kicad_sch` | KiCad 9 schematic |
| `rc_lowpass-bom.csv` | Bill of materials |
| `rc_lowpass-report.md` / `.json` | Design report |
| `rc_lowpass-verification.json` | Verification evidence |
| `rc_lowpass-pcb.json` | PCB overlay (when `pcb` or `--pcb-board` is requested) |
| `rc_lowpass-pinmap.json` | SPICE pin -> footprint pad map |
| `rc_lowpass-node-aliases.json` | SPICE node -> PCB net aliases |
| `rc_lowpass-pcb-handoff.md` | Exact PCB-skill command and gaps |

## Calculators

```bash
python3 scripts/circuit_calc.py list
python3 scripts/circuit_calc.py divider --vin 12 --r1 10k --r2 4k7 --json
python3 scripts/circuit_calc.py buck --vin 12 --vout 5 --iout 2 --fsw 500k
python3 scripts/circuit_calc.py sallen-key --topology highpass --fc 1k --q 0.7071
```

26 commands across passives, analog, devices, power and digital/interface.
Every command returns the same JSON envelope with formulas, assumptions,
warnings and notes.

## Design intake

The questions are in `references/intake.md`. If the user cannot answer, the
skill proposes a default and records it in the spec's `assumptions`. It does
not hide assumptions in the netlist.

## Verification levels

| Level | Proves | Does not prove |
|---|---|---|
| Spec | Pins, nets and references are consistent | Electrical behaviour |
| Netlist agreement | SPICE, LTspice and KiCad describe the same nodes | Accuracy |
| PCB handoff | Overlay, pin map and aliases agree; sibling validator accepts | Layout, DRC, DFM, real pads |
| MNA | Exact linear DC/AC solution | Nonlinear devices, parasitics |
| ngspice | The netlist runs and converges | Real devices with generic models |
| Bench | The physical circuit works | All units and temperatures |

`verify.py` reports `PASS`, `FAIL` or `SKIP`. A skipped check is never a pass.
Generic models are labelled "unverified" in the report.

## Topologies with scaffolds

`rc_lowpass`, `rc_highpass`, `divider`, `sallen_key_lp`, `sallen_key_hp`,
`bjt_ce`, `led`, `i2c`, `opamp_noninverting`, `zener_regulator`, `buck`.

Any other topology can be described with an explicit component list. The spec
is the contract; see `schemas/design-spec.schema.json`.

## Important limitation: logical pin numbers

The embedded KiCad symbols use **SPICE pin order** (NPN: 1=C, 2=B, 3=E;
MOSFET: 1=D, 2=G, 3=S; diode: 1=A, 2=K), not the standard KiCad `Device:`
numbering. This guarantees the schematic, KiCad netlist and SPICE netlist agree.

For PCB layout, map each logical pin to the real footprint pad. Do not assume
logical pin 1 is package pin 1. See `references/kicad-format.md`.

## PCB handoff

The sibling `pcb-design-skill` imports the SPICE netlist for connectivity and
a JSON overlay for board mechanics. `pcb_handoff.py` writes that overlay plus a
pin map and node aliases, and prints the exact command:

```bash
python3 scripts/pcb_handoff.py specs/rc.json --out out/ \
  --board 50x40 --profile 2layer-low-speed
```

Add a `pcb` block to the circuit spec for footprints, rules, netclasses,
placement and pin maps. Board dimensions are required; footprints and package
pinouts are never guessed. Missing ones are reported and left for the PCB
skill's visual picker. An op-amp `U1` becomes SPICE element `XU1`; the handoff
maps the reference explicitly. A MOSFET's SPICE line has a fourth bulk node
tied to source, so its pin map needs `b` as well as `d`/`g`/`s`; for a 3-pad
package, map `b` to the same pad as `s`. See `references/pcb-handoff.md`.

`verify.py` checks the handoff for internal agreement. When every footprint is
present and the sibling skill is installed, it also runs the sibling's own spec
validator. That is a structural/rules check, not DRC or a manufactured board.

## Scope and safety

This skill produces schematics, netlists and calculations. It does not replace
a datasheet, a bench measurement, ERC/DRC, or a safety review. Stop and ask for
mains, high voltage, isolation, lithium charging, medical/automotive safety, RF
power, or anything where a wrong pin assignment could destroy hardware.

For PCB layout, use `pcb-design-skill` with the generated overlay, pin map and
node aliases. The PCB skill's DRC, DFM and unconnected gates, not this skill,
decide whether the board is manufacturable.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

The tests cover value parsing, the calculators, the MNA solver, generation,
verification and the PCB handoff. The KiCad parse test is skipped when
`kiutils` is not installed; the sibling-PCB integration test is skipped when
`pcb-design-skill` is not installed.

## License

MIT. See `LICENSE`.
