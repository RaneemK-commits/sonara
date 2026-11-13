# Environmental impact: Software Carbon Intensity (SCI)

The judging organisation is the Green Software Foundation, so we report Sonara's footprint with
their **SCI specification** (ISO/IEC 21031:2024): https://sci.greensoftware.foundation/

## The formula
```
SCI = ((E × I) + M) per R
E = energy used by the software for the functional unit (kWh)
I = location-based grid carbon intensity (gCO2eq/kWh), no market-based instruments (RECs, PPAs…)
M = embodied hardware emissions allocated to the software = TE × (TiR / EL) × (RR / ToR)
R = functional unit
```
Offsets and green-energy certificates **do not** reduce an SCI score. Only real reductions in
energy or hardware do. We must disclose the score, the software boundary, and the method (measured vs calculated).

## Our choices (draft)
| Item | Proposal |
|---|---|
| **R** (functional unit) | **one patient interaction**: utterance → recognised → spoken aloud (→ request dispatched/acknowledged when sent) |
| **Boundary** | UNO Q board (always-on idle share + active inference/TTS/server), USB mic + speaker, room display, caregiver phone browser share, Wi-Fi router share. One-off: model download, TTS pre-generation, enrollment. *No cloud.* |
| **E** | **Calculated** (we have no power meter): board power model `P = P_idle + (P_max − P_idle) × CPU_util`, times stage latencies from `scripts/benchmark.py`, plus idle energy per day ÷ interactions per day. Disclose this as calculated, not measured. |
| **I** | Location-based average grid intensity for the hackathon's country/region (source: Ember or Electricity Maps annual average), stated with year. |
| **M** | Embodied carbon of UNO Q + display + peripherals. No LCA published for the UNO Q, so estimate from comparable single-board-computer LCAs and **disclose the assumption**. TiR/EL = interaction time ÷ expected lifespan (e.g. 5 years). RR/ToR = 1 for the board (dedicated). |

## How we show "environment friendliness" (the SCI way)
SCI rewards **comparisons with the same method**. Run `benchmark.py` for each variant and compute SCI per interaction:

| Variant | Design choice it justifies |
|---|---|
| VAD-gated vs always-running model | Model sleeps until there is speech |
| Embedding model vs Whisper-tiny ASR | Small personalised model needs far less compute |
| Pre-synthesised vs live Piper TTS | Synthesise once, play many times |
| On-device vs cloud ASR+TTS round-trip | Optional, only if we find a credible published energy figure for the cloud path; otherwise leave it out |
| int8 vs float model (if time) | Quantisation |

Embodied carbon (M) argument: reuse a ~€50 low-power board and the existing display instead of a
laptop/tablet per bed. Hardware is usually the biggest share for edge devices, so report M honestly.

## Still needed
- Hackathon **location** → grid intensity I.
- UNO Q power figures (datasheet idle/load) for the E model. Verify against Arduino docs on board day.
- If anyone can borrow a USB-C power meter, switch E from "calculated" to "measured".
