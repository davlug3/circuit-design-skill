# Real device models

A generic BJT, diode or MOSFET card is a smoke-test stand-in. It is not the
part on the BOM, and a simulation using it must not be presented as a
validated design. This skill therefore separates three states and will only
call a model *vendor* when provenance is recorded.

| Status | Meaning |
|---|---|
| `unverified (generic models)` | At least one semiconductor falls back to a generated placeholder |
| `declared models (no vendor provenance)` | Models are supplied, but with no vendor/part/source |
| `vendor models supplied` | Every semiconductor resolves to a model with vendor/part/source |
| `model errors (see validation)` | A file is missing, its hash mismatches, or the named model is absent |

`verify.py --require models` fails when the status is not `vendor models
supplied`, so a CI run can gate on real models.

## Where the model comes from

Download the model from the manufacturer's product page (`.lib`, `.mod`,
`.cir`) or use a model library whose licence allows redistribution. Record:

- `vendor` — the manufacturer;
- `part` — the exact orderable part (not a family nickname);
- `source` — the URL or document the file came from;
- `sha256` — the hash of the file you actually used.

Do not commit a vendor file to a public repository unless its licence permits
it. Point `file` at a path inside the project and keep the hash, so a different
revision is detected.

```bash
sha256sum models/2N3904.lib
```

## Finding a model

`catalog/models.json` is a small, curated list of parts whose models are
published at a stable URL. It records the SPICE model name (which often differs
from the orderable part), the vendor, the source URL, the licence note, and the
node order for a `.subckt`.

```bash
# What is available?
python3 scripts/model_fetch.py --list

# Fetch, validate, hash and write models/<part>.lib
python3 scripts/model_fetch.py --part 2N3904 --out models/

# Fetch and install directly into a spec (sets Q1.model = 2N3904)
python3 scripts/model_fetch.py --part 2N3904 \
  --write-spec specs/ce.json --ref Q1

# Direct URL or a manually downloaded file
python3 scripts/model_fetch.py --url https://example.com/part.lib \
  --part XYZ --vendor Acme --name XYZ
python3 scripts/model_fetch.py --file ~/Downloads/part.lib \
  --part XYZ --vendor Acme --source https://example.com/part.lib
```

The fetcher:

- downloads the file (5 MB limit) and decodes it as text;
- extracts the requested `.model` or `.subckt` with the same parser the
  generator uses, and refuses a file that does not define it;
- refuses a `.subckt` unless the node order is known (`--subckt-pins` or the
  catalog entry);
- checks the expected device type when it is given (for example `NPN`, `D`,
  `NMOS`);
- writes `models/<part>.lib` (or the `--out` directory), computes the SHA-256
  of the bytes actually written, and emits a `models` entry;
- with `--write-spec`, assigns the model to `--ref` (or the only unassigned
  semiconductor), validates the updated spec, and writes it only if valid.

The hash is computed over the file bytes, so the spec's `sha256` and the
resolver's check agree. Re-running against an existing file with different
content fails unless `--force` is used; that is deliberate, because a changed
model changes the simulation.

If a vendor site presents an expired or otherwise invalid TLS certificate, the
fetcher reports the certificate error and stops. Do not disable verification
globally: download the file with a browser or another trusted client, verify
its origin, and use `--file` with `--source`.

The catalog is a convenience, not an endorsement. A model can be syntactically
valid and still be wrong for your part, grade, package or temperature. Read the
header, check the source's terms, and keep third-party model files out of a
public repository unless their licence allows redistribution. Onsemi MODPEX and
some Zetex models, for example, restrict commercial use and redistribution.

## Spec forms

### 1. Inline card with provenance

```json
"models": {
  "2N3904": {
    "card": ".model 2N3904 NPN(IS=6.734f BF=416.4 VAF=74.03 ...)",
    "vendor": "onsemi",
    "part": "2N3904",
    "source": "https://www.onsemi.com/.../2N3904.lib"
  }
}
```

### 2. Vendor file

```json
"models": {
  "2N3904": {
    "file": "models/2N3904.lib",
    "name": "2N3904",
    "vendor": "onsemi",
    "part": "2N3904",
    "source": "https://www.onsemi.com/.../2N3904.lib",
    "sha256": "4f0c…"
  }
}
```

`file` is resolved relative to the spec's directory. Only the named
`.model`/`.subckt` block is inlined; the rest of the library is ignored.
`name` defaults to the key in `models`.

### 3. Subcircuit (common for MOSFETs)

A vendor MOSFET model is often a `.subckt`, not a `.model`. The device must
then be emitted as an `X` instance, and the node order must be explicit:

```json
"models": {
  "BSS138": {
    "file": "models/BSS138.lib",
    "vendor": "onsemi",
    "part": "BSS138",
    "source": "https://www.onsemi.com/.../BSS138.lib",
    "sha256": "9ab1…",
    "subckt_pins": ["D", "G", "S"]
  }
}
```

`subckt_pins` is the subcircuit's node order (pin names or aliases are
accepted). It may also be set on a component to override the declaration for
that instance. Without it, validation fails: guessing a MOSFET pin order is
how a correct schematic becomes a dead board.

Generated netlist for the example above:

```
XM1 DRAIN GATE 0 BSS138
```

**Package pins are not SPICE nodes.** The catalog's 1N4148 model uses SPICE
node 1 = anode and node 2 = cathode, while the SOD-27 package is pin 1 =
cathode and pin 2 = anode. Record a datasheet pin map for the PCB handoff and
never copy `subckt_pins` into a footprint pad map.

## What the generator does

- Inlines the resolved card into `<name>.cir`, so the netlist stays
  self-contained.
- Writes a provenance comment above the card:
  `* model provenance: vendor=…; part=…; file=…; sha256=…; source=…`.
- Replaces the "generic placeholders are UNVERIFIED" header with
  `* Models: vendor models supplied.` when every device is backed.
- Adds a **Device models** table to the Markdown report with ref, type, kind,
  vendor, part and hash prefix.

## LTspice schematic export

A subcircuit device is written as an `X` instance (`SYMATTR Prefix X`) with the
model name as `Value`. LTspice orders subcircuit nodes by the symbol's pins,
not by the order they appear in the `.asc`, so `subckt_pins` must match the
symbol's natural order (`D G S` for the MOSFET symbol, `C B E` for the BJT,
`A K` for the diode, and so on). The generator refuses the export otherwise
rather than producing a silently mis-wired schematic. A 4-terminal subcircuit
cannot be represented by the built-in 3-pin symbols.\n\n## What this still does not prove

- The vendor model matches the physical part on your reel (process corner,
  package parasitics, thermal behaviour).
- The model file was not tampered with before you hashed it; the hash proves
  only that the file did not change afterwards.
- Simulation accuracy against a bench measurement.

Supply the model, record the provenance, run `verify.py --require models
--require simulate`, and read the datasheet before trusting the number.
