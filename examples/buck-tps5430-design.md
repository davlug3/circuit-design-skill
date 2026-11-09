# Hardware-backed buck reference: TPS5430, 12 V to 5 V / 2 A

This is a component-level design study for the plain-language buck example. It
uses the Texas Instruments TPS5430 and the manufacturer's 12 V to 5 V reference
application as the starting point. It is deliberately separate from
`buck-5v.json`, which remains an ideal-switch topology/generator fixture.

**Status: reference design selected; not released for hardware.** The TI
application circuit is specified for 10.8 V to 19.8 V input, 5 V output and up
to 3 A. The user target is 12 V nominal and 2 A. Reusing that reference is a
credible starting point, not proof that the modified 2 A design meets its
thermal, ripple, transient or tolerance requirements.

## Requirements and boundaries

| ID | Requirement / condition | Acceptance or status |
|---|---|---|
| R1 | Nominal input 12 V DC | The TI reference range is 10.8–19.8 V; confirm the actual source range before release |
| R2 | Output 5.0 V at 2.0 A continuous | 2.5 Ω nominal load; 10 W output |
| R3 | Non-isolated step-down | TPS5430 asynchronous buck topology |
| R4 | Switching frequency | Fixed 500 kHz nominal; device data gives 400–600 kHz |
| R5 | Output ripple | Adopt 30 mV p-p as a provisional target from TI's reference design; define measurement bandwidth/probe method |
| R6 | Input ripple | Adopt 300 mV p-p as the reference design condition; confirm source impedance and input cabling |
| R7 | Ambient and thermal | **Open:** define maximum ambient, copper stack-up, airflow and allowable junction margin |

The following are intentionally not specified yet: input surge/transient
profile, output tolerance, load-step profile, startup delay, short-circuit
duration, conducted/radiated EMI limits, connector/cable losses, board outline,
altitude and production temperature range. Do not silently turn these into
requirements.

## Controller choice

**U1: Texas Instruments TPS5430DDA**, 8-pin HSOP/PowerPAD package.

Reasons:
- Recommended input range 5.5–36 V; the TI reference application uses
  10.8–19.8 V input.
- Up to 3 A continuous output rating, leaving nominal current headroom over
  the 2 A requirement (this is not a thermal guarantee).
- Integrated 100 mΩ typical high-side MOSFET, internal compensation,
  undervoltage lockout, slow start, overcurrent limiting and thermal shutdown.
- Fixed 500 kHz switching frequency.
- TI provides an official PSpice transient model and a reference application.

The device is active in TI's product listing, but confirm the exact orderable
suffix, package, lifecycle and supply before procurement.

## Starting power-stage values

These values are taken from TI datasheet Rev. K, section 7.2.1, the
manufacturer's 12 V input / 5 V output application circuit:

| Ref | Starting value / part | Design note |
|---|---|---|
| U1 | TPS5430DDA | Exposed thermal pad must be soldered to PCB ground |
| C1 | 10 µF ceramic, 25 V | TI recommends X5R/X7R; confirm effective capacitance and ripple-current rating |
| C2 | 10 nF | BOOT-to-PH bootstrap capacitor |
| D1 | Diodes Inc. B340A | TI reference choice; 40 V reverse rating, 3 A forward-current rating, ~0.5 V forward drop in the cited design |
| L1 | 15 µH | TI reference value; select an exact orderable part with saturation and RMS current ratings |
| C3 | 220 µF | TI reference value; exact technology/ESR and ripple rating must match the datasheet design assumptions |
| R1 | 10 kΩ | VOUT to VSENSE |
| R2 | 3.24 kΩ | VSENSE to GND; TI's standard value for 5 V |

Feedback set point using the datasheet's 1.221 V nominal reference:

`VOUT = 1.221 × (1 + 10 kΩ / 3.24 kΩ) = 4.9895 V`

This is the nominal resistor/reference calculation, not a guaranteed output
tolerance. Use the full reference-voltage limits, resistor tolerances,
temperature coefficients and board leakage in the worst-case calculation.

## First-order checks

- Nominal output power: `5 V × 2 A = 10 W`.
- Nominal resistive load: `5 V / 2 A = 2.5 Ω`; load dissipation is 10 W, so a real
  load or electronic load must be rated accordingly.
- Nominal duty estimate: `5 V / 12 V = 41.7%` (ideal CCM approximation).
- At the TI reference's 19.8 V maximum input and 15 µH / 500 kHz, ideal
  inductor ripple is approximately
  `ΔIL = VOUT × (1 − VOUT/VIN) / (L × fSW) = 0.50 A p-p`.
  At 2 A average load, the ideal peak inductor/diode current is approximately
  `2 A + 0.99 A / 2 = 2.25 A`. Recalculate using actual inductance under bias,
  switching-frequency limits, diode drop, parasitics and tolerances.
- With 300 mV p-p input ripple, TI's reference calculation gives capacitor
  voltage peak of approximately `VIN(max) + ΔVIN/2`; at 19.8 V this is
  approximately 19.95 V. A 25 V capacitor is not automatically approved:
  include source transients, derating and effective capacitance.
- TI's datasheet gives a 40 V absolute maximum for TPS5430 VIN and PH in
  steady state, and a 36 V recommended maximum VIN. Absolute maximum is not
  an operating target. PH ringing must be measured and kept within its own
  limits.

These arithmetic checks do not establish diode thermal margin, inductor
saturation margin, capacitor ripple life, controller junction temperature,
loop stability, EMI or safe operation during faults.

## Vendor simulation model

TI's product page lists **TPS5430 PSpice Transient Model (SLVMAC8.ZIP)** and
an **unencrypted PSpice transient model (SLVMCU8.ZIP)**. Use the official
download, preserve its original header and licence/terms, record the exact
download URL, revision and SHA-256, and inspect its subcircuit pin order before
integrating it.

The model has not been copied into this repository and is not yet wired into
the generic component generator. This avoids redistributing a vendor file
without confirming its terms and avoids claiming that a PSpice model is
automatically compatible with ngspice/LTspice. The next integration step is
to test the unencrypted model with the supported simulator(s), document any
compatibility edits as a separate derived artifact, and compare model behavior
against TI's published reference waveforms.

## Operating-limit and verification gates

Before claiming a hardware-ready design, complete the following with sourced
part numbers and actual PCB conditions:

1. **VIN / PH:** verify the complete input transient envelope, VIN recommended
   operating range, PH steady-state and switching overshoot against the TI
   datasheet. Capture PH with a suitably rated, low-inductance probe.
2. **Inductor:** calculate worst-case peak and RMS current at input/load/
   temperature extremes. Select a part whose saturation current exceeds the
   worst-case peak with margin, and whose RMS/thermal rating is adequate.
3. **Catch diode:** verify reverse voltage including PH ringing, average and
   peak current, surge rating, forward loss and junction temperature. The
   reference B340A selection is not a substitute for checking its exact
   datasheet and thermal footprint.
4. **Capacitors:** verify effective capacitance under DC bias, voltage rating,
   ripple current, ESR, temperature and lifetime.
5. **U1 thermal:** use the actual copper layout, thermal vias, board stack-up,
   ambient and measured loss. Do not use the JESD 51-7 comparison RθJA as a
   board-specific thermal prediction; TI explicitly warns against that use.
6. **Regulation:** verify output tolerance using the full VREF range and
   resistor tolerances; verify line/load regulation and load-step response.
7. **Stability:** verify the selected output capacitor ESR range and loop
   stability using the datasheet guidance and measurement/model evidence.
8. **Protection / EMI:** test startup, shutdown, overload, short circuit,
   recovery, conducted emissions and radiated emissions against requirements.

## Bench test plan

| ID | Test point / quantity | Method and conditions | Acceptance |
|---|---|---|---|
| T1 | VIN at U1 / input ripple | Measure at 10.8 V, 12 V and 19.8 V input with rated load | Within confirmed input range; ripple ≤300 mV p-p if retained as a requirement |
| T2 | VOUT / DC regulation | Measure 0 A, intermediate load and 2 A after thermal soak | 5.0 V within the output tolerance once that tolerance is agreed |
| T3 | VOUT / ripple | Short ground spring or coaxial probe, stated bandwidth limit, 2 A load | ≤30 mV p-p if retained as a requirement |
| T4 | PH / overshoot and ringing | Differential/isolated probe with adequate bandwidth and voltage rating | Within datasheet PH limits, including transients |
| T5 | U1, D1, L1 temperature | Thermocouple/thermal camera after thermal equilibrium at maximum ambient and load | Junction estimates and component temperatures below derated limits |
| T6 | Load transient | Electronic-load step with specified slew rate and endpoints | Recovery, overshoot and undershoot within agreed limits |
| T7 | Startup / fault recovery | Capture VIN, VOUT and input current during enable, overload and short-circuit recovery | No latch-up or component overstress; behavior matches agreed system requirements |

Record equipment model, calibration status, probe setup, board revision,
ambient, input source impedance, load, raw captures and actual readings. A
written test plan is not evidence that tests have been run.

## Release decision

**Not approved for PCB release or hardware construction yet.** The controller
and TI reference circuit are selected, but exact passives, thermal design,
input transients, output tolerance, vendor-model compatibility, PCB layout and
bench results remain open. Keep the original ideal buck fixture labelled as a
generator test; use this document as the evidence checklist for the physical
design.

## Sources

- Texas Instruments, *TPS543x 3A, Wide Input Range, Step-Down Converter*,
  datasheet SLVS632K, Rev. K (January 2024), especially sections 4, 5, 7.2.1
  and 7.4: https://www.ti.com/lit/ds/symlink/tps5430.pdf
- Texas Instruments TPS5430 product page and model downloads:
  https://www.ti.com/product/TPS5430
