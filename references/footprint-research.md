# Footprint research workflow

Footprint selection is research-first. Do not choose a footprint merely because
it is a familiar KiCad default or because the symbol has a familiar name.

## Research sequence

For each physical component that will appear on a PCB:

1. Identify the exact manufacturer part number (MPN). If it is unknown, use the
   component's electrical class and stated ratings, but mark the package as
   provisional and ask for the MPN when package compatibility matters.
2. Search the web using the MPN plus `datasheet package dimensions lead spacing`.
   For generic parts, use queries such as:
   - `KiCad common footprint 0.5 W axial resistor through hole`
   - `0.5W resistor DIN0309 body dimensions lead pitch datasheet`
   - `KiCad [part number] footprint package`
3. Prefer sources in this order:
   - Manufacturer datasheet and official mechanical drawing for the exact MPN.
   - Official KiCad footprint library and KiCad Library Convention (KLC).
   - Distributor drawings or reputable application notes.
   - Community discussions only to understand common practice; never treat a
     forum post as proof of package dimensions.
4. Search the official KiCad library for the footprint whose body dimensions,
   lead pitch, pad/drill sizes and orientation match the source drawing.
5. Record the selected footprint on that component in the design spec. Include
   the MPN, source URL, relevant dimensions/rating, and why the footprint
   matches in the design decision or research log. Preserve source URLs.
6. If sources disagree, prefer the manufacturer drawing for the exact part.
   If no exact match can be established, do not silently claim a match: select
   a clearly labelled provisional footprint or leave it unassigned and ask.
7. Before fabrication, verify the footprint's pad numbering against the
   datasheet pinout and inspect the KiCad 3D/mechanical view.

## Example: 0.5 W through-hole axial resistor

A useful search is `KiCad common footprint for 0.5W axial resistor`.
KiCad's `Resistor_THT:R_Axial_DIN0309_L9.0mm_D3.2mm_P12.70mm_Horizontal`
footprint describes a DIN0309 body of 9.0 x 3.2 mm, 12.70 mm lead pitch and
0.5 W (1/2 W) resistor use. This is a sensible starting candidate for a
typical DIN0309 0.5 W resistor, not a universal fit for every 0.5 W part:
verify the exact manufacturer's body dimensions and lead spacing first.

A smaller DIN0207 footprint is not interchangeable merely because it is also
an axial resistor. Power rating, body series and lead pitch must match the
actual component and assembly needs.

## Recording the result

Prefer a component-level explicit footprint in the normalized spec, for example:

```json
{
  "ref": "R1",
  "type": "R",
  "value": "10k",
  "power_w": 0.5,
  "manufacturer_part": "exact MPN if known",
  "footprint": "Resistor_THT:R_Axial_DIN0309_L9.0mm_D3.2mm_P12.70mm_Horizontal"
}
```

The `power_w` and `manufacturer_part` fields are descriptive metadata; the
`footprint` field is the explicit, research-backed selection consumed by the
generator. The assembly wrapper preserves it and only supplies offline fallback
footprints for components that still have no footprint.

## Source examples

- [KiCad Library Conventions: axial resistor naming](https://klc.kicad.org/footprint/f3.2/)
- [KiCad footprint library example: DIN0309 0.5 W, 12.70 mm pitch](https://github.com/KiCad/kicad-footprints/blob/master/Resistor_THT.pretty/R_Axial_DIN0309_L9.0mm_D3.2mm_P12.70mm_Horizontal.kicad_mod)
- [KiCad forum discussion: DIN0207 and common 10.16 mm pitch](https://forum.kicad.info/t/beginner-question-selecting-resistor-footprint/62620)

These examples illustrate library conventions and common practice; they do
not replace the exact component manufacturer's drawing.
