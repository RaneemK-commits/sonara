# Voice pipeline improvements

Branch: `speech/voice-pipeline-improvements`, based on integrated main `6cd70b5`.
Device-owned controller/server/config, the working speaker route and MCU firmware are unchanged.

## Changes

- Match templates in batches of at most 16. The batched DTW shares the Python row loop while
  preserving each template's band, recurrence, tie-breaking and path-length normalization.
  No feature downsampling, threshold change or approximate matching is involved. At most 100
  templates, 600 frames and 128 dimensions remain supported. Randomized reference comparisons
  and paired benchmarks observed zero score difference and unchanged predictions.
- Seed energy VAD from a bounded ten-second history of idle microphone RMS values (10th
  percentile, at least ten blocks). Recording frames never enter that history. This helps avoid
  treating steady ambient noise as a new onset. Manual recording boundaries remain available.
  Noise history contains scalar energies, no retained audio. Quiet-speech and exception-recovery
  tests pass; live patient/noise robustness is still unmeasured.
- Keep the current patient selected if an explicit profile switch fails. A corrupt active
  selector fails closed instead of falling back to a different patient. Validate profile ID
  against its directory. Retry repaired files even when original timestamps are restored.
- Rejections log best intent, distance, absolute threshold, runner-up margin, required margin,
  frame/template counts and processing time to the process logging stream (stderr by default).
  Calibration diagnostics now distinguish insufficient examples, overlapping intents, distance
  rejection and insufficient margin. CLI enrollment prints those reasons; matching thresholds
  remain unchanged. A read-only `roles/speech/evaluation/diagnose_profile.py` reports LOO
  separation without retaining audio or modifying the profile.
- Evaluation imports no longer require Unix `resource` on Windows. Linux reports measured RSS;
  unsupported platforms report JSON null. Windows import behavior is simulated in tests; no
  physical Windows run was available.

## Actual UNO Q measurements

CPU-only, ARM64 Python 3.13.5 / NumPy 2.2.6, 25 synthetic templates (five per intent).
Capture and TTS are excluded. These are latency measurements, not speech accuracy.

| Fixture | Paired scalar matching | Paired batched matching | Speedup | Full recognition mean / p95 |
|---|---:|---:|---:|---:|
| 0.6 s, 59 frames, 30 runs | 502.5 ms | 169.3 ms | 2.97× | 138.6 / 159.5 ms |
| 5 s, 499 frames, 5 runs | 5001.3 ms | 2949.0 ms | 1.70× | 2876.2 / 2892.6 ms |

Matching and full recognition are separate runs on a shared board; their means must not be
subtracted or interpreted as component timings from one run. Peak process RSS was approximately
36–47 MiB. Long utterances still exceed the 500 ms target. Do not claim bounded sub-500 ms latency.
The earlier German diagnostic still rejected all 40 unrelated five-second windows; that does
not establish held-out intent accuracy or speaker identification.

Machine-readable reports: `validation/improved_board_*.json` and
`validation/improved_laptop_matching_*.json`. Reports specify counts, versions and run numbers.

## Reproduce

Use an isolated profile and a separate held-out WAV. Never overwrite a patient's profile with
synthetic fixtures. The matching comparison alternates scalar/batched order and verifies scores
before timing:

```bash
python roles/speech/evaluation/benchmark_matching.py \
  --profile data/profiles/BENCHMARK_PROFILE --wav HELD_OUT.wav \
  --runs 30 --output results/paired_matching.json
python scripts/benchmark.py --profile BENCHMARK_PROFILE --wav HELD_OUT.wav \
  --runs 30 --output results/processing.json
python -m pytest -q tests roles/speech/integration/test_integrated_recognition.py
```

The board measurements used `/tmp/sonara-voice-improvements/source` with dependencies from
`/tmp/sonara-mfcc-validation/deps`. The running `/home/arduino/sonara` app was not redeployed.
Patient confirmation remains mandatory before any caregiver request. Speech matching is not
speaker authentication; evaluate same-word impostors before considering a separate identity gate.
