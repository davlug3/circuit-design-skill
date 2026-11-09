# Plain-language golden workflow: 12 V to 5 V at 2 A

This example demonstrates how an AI agent should turn a short user request into a reviewable circuit-design specification and generated artifacts.

## User prompt

> Build a 5 V power supply from a 12 V DC input, capable of supplying 2 A. Generate SPICE and KiCad files.

## Clarifications and locked assumptions

The prompt does not specify input range, output tolerance, isolation, ripple, transient response, ambient temperature, protection, size, cost, or a preferred controller. A responsible agent must ask about these or propose explicit defaults and obtain confirmation before treating the design as implementation-ready.

For this runnable golden example only, the following defaults are recorded:

- Nominal 12 V input and 5 V / 2 A output (10 W).
- Non-isolated asynchronous buck power stage.
- 500 kHz switching frequency and 30% nominal inductor ripple.
- Continuous-conduction mode, ideal switch and diode, idealized PWM drive.
- Generic switch/diode models; no vendor component has been selected.
- Feedback compensation, current limiting, startup behavior, EMI and thermal design are outside this example.

These assumptions make the specification reproducible; they are not silently inferred requirements or a production design.

## Artifact mapping

The machine-readable design contract is [buck-5v.json](buck-5v.json). It records the requirements, architecture, decisions, risks and source brief alongside the circuit components. The existing generator derives all deliverables from that single component list.

Run from the repository root:

```bash
python3 scripts/design_spec.py validate examples/buck-5v.json
python3 scripts/design_spec.py explain examples/buck-5v.json
python3 scripts/generate.py examples/buck-5v.json --out out/plain-language-buck
python3 scripts/verify.py examples/buck-5v.json --out out/plain-language-buck --require design
python3 scripts/render_schematic.py out/plain-language-buck/buck.kicad_sch --out out/plain-language-buck/images
```

The generated outputs include a SPICE netlist, LTspice schematic, KiCad schematic and netlist, BOM, report and (when KiCad CLI is available) an SVG rendering.

## What this example proves—and does not prove

Automated regression tests prove that the prompt's declared values are represented in the spec, the design record is complete, the artifacts are generated, and the available structural/sizing checks pass. A generic-model transient simulation is a model result, not evidence that a real converter meets its requirements.

Before hardware use, select actual controller and semiconductor parts from current datasheets; calculate worst-case voltage, current, power and thermal stresses; design compensation and protection; use vendor models where available; and validate startup, load transients, fault behavior, EMI and temperature on hardware. KiCad schematic generation is not PCB DRC or fabrication approval.
