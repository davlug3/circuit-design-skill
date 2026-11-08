# Audio Handoff

Audio-specific requirements and target performance come from the sibling
[`audio-engineering-skill`](https://github.com/davlug3/audio-engineering-skill).
This skill owns the electrical implementation: component sizing, netlist,
simulation, schematic and verification.

The split is deliberate:

- **audio skill** — what the circuit must achieve, why, the conditions, the
  measurement method and the perceptual interpretation;
- **circuit skill** — how to make the electrons do it, and what was simulated
  or verified.

Do not restate audio targets from memory here. If a spec contains audio
requirements, they must carry a source from the audio skill's registry.

## Contract version 1

The audio skill emits `handoff.json`:

```json
{
  "handoff_version": 1,
  "application": "microphone preamplifier",
  "conditions": {"input_vrms": 0.002, "frequency_hz": 1000, "load_ohm": 10000},
  "requirements": [
    {"id": "A1", "text": "Flat gain", "acceptance": "40 +/-0.5 dB, 20 Hz-20 kHz", "source": "S041"},
    {"id": "A2", "text": "Input-referred noise", "acceptance": "<= 1.0 uV RMS, 20 Hz-20 kHz, 150 Ohm source", "source": "S045"}
  ],
  "metrics": [
    {"measure": "gain_db", "target": 40.0, "tolerance": 0.5, "requirement": "A1"},
    {"measure": "ein_uv", "target": 1.0, "tolerance": 0.0, "requirement": "A2"}
  ],
  "sources": [
    {"id": "S041", "title": "RaneNote 145: Audio Specifications", "url": "https://www.ranecommercial.com/legacy/note145.html", "accessed": "2026-11-08"},
    {"id": "S045", "title": "Noise in Audio Amplifiers", "url": "https://sound-au.com/noise.htm", "accessed": "2026-11-08"}
  ]
}
```

Source ids refer to the sibling audio registry. They must be `verified` there,
and the condition in each acceptance limit must be carried into the analysis or
metric block. The examples above use S041 and S045, which are verified in the
audio registry at the time of writing.

Merge mapping:

| Handoff | Design spec |
|---|---|
| `requirements[]` | `design.requirements[]` |
| `conditions` | the relevant analysis or `metrics.conditions` |
| `metrics[]` | `metrics.metrics[]` |
| `architecture` | `design.architecture` |
| `risks[]` | `design.risks[]` |
| `sources[]` | `design.sources[]` |

The spec must reject a metric whose `requirement` id is absent.

## Status

- Contract defined and published by the audio skill.
- The generic `metrics` verification stage (gain, bandwidth, THD, noise) is
  **not implemented yet**. Until it is, audio targets are planning data, not a
  verified result. Do not report them as measured or simulated.
- The audio skill's `source_check.py` validates the handoff sources before it
  reaches this skill.

## Locating the sibling

The repository is
[`davlug3/audio-engineering-skill`](https://github.com/davlug3/audio-engineering-skill).
When installed as a sibling directory, it is normally
`../audio-engineering-skill`. Future integration may use an
`AUDIO_ENGINEERING_SKILL` environment variable, following the PCB skill's
pattern. No runtime import is required: the handoff is plain JSON.

## Non-goals

- This skill does not decide what sounds good.
- A simulation is not a measurement and does not prove a perceptual claim.
- Audio targets without conditions (level, frequency, bandwidth, load,
  weighting) are rejected.
