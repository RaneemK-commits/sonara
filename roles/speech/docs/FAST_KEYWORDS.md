# Faster personal keywords and optional synthetic testing

The tools now support five real word recordings, explicit synthetic variants, bounded
coarse-to-fine keyword matching and direct enrollment/testing commands. **Independent real-speech
recognition is still poor in the two-take TORGO experiment. This is not a validated live bedside
recognizer.** No controller, server, UI, MCU, speaker route or active patient profile is changed.

## Enrollment that can be used without writing Python

Normal keyword enrollment requires at least **five real takes per request**. Use your natural,
consistent sound with small ordinary differences in timing/loudness. Do not force a different
pronunciation. Synthetic variants do not count as additional real takes.

```bash
# Stop the local Sonara server before direct CLI mic capture; it owns the same mic.
python scripts/enroll.py --keyword-profile --profile patient_001 \
  --intents WATER PAIN --takes 5 --keyword-scan-s 1.25

# Optional experiment: five real takes plus two synthetic variants per word.
python scripts/enroll.py --keyword-profile --profile experiment_001 \
  --intents WATER PAIN --takes 5 --synthetic-variants 2

# WAV import: ROOT/WATER/*.wav and ROOT/PAIN/*.wav, five independent files each.
python scripts/enroll.py --keyword-profile --profile wav_demo \
  --intents WATER PAIN --takes 5 --from-dir data/enrollment
```

Fixed recording defaults to three seconds; conservative endpoint trimming (180 ms padding)
extracts the word. Internal pauses remain. `--preserve-word-boundaries` disables trimming for
explicit manual boundaries; `--automatic` uses energy VAD for capture. Validity/duplicate and
per-word progress feedback appear immediately. WAV import skips corrupt/duplicate files by
quality checks and continues until it has five valid takes, with explicit skipped-file messages. Mic capture refuses to compete with a listening
local Sonara server; WAV import needs no mic. `--keep-audio` is the only raw-retention opt-in.

Profiles go to `data/keyword_profiles/ID/` (`--keyword-dir` overrides the root). Existing profiles
require explicit `--keyword-overwrite`; the active production profile is never switched. Request
intents only: ambient YES/NO must not confirm/cancel requests. Version 2 keyword profiles persist
unnormalized MFCC features (not raw audio), source-family IDs, matching settings, calibration and augmentation metadata.
Version 1 keyword profiles retain their original frame rate/weights/cadence when loaded.

Synthetic augmentation is **off by default**. `--synthetic-variants N` adds up to five variants,
with at most ten templates per word total. `balanced20` offers 20 dB noise/gain/speed variants;
`--augmentation-policy mild35` selects the earlier gentler gain/speed/35 dB experiment. Speed
resampling also changes pitch by about 5%; no vocoder or neural package is used. Invalid optional
variants are skipped rather than discarding good quiet recordings. Actual counts are reported.

Each variant retains its real parent. Shared scaling is fitted on real parents only. Scoring
uses the nearest independent source families, so siblings cannot vote twice. Calibration leaves
the entire parent family out and evaluates only real parent queries. Two real + three synthetic
references therefore still report **two independent recordings**, with insufficient calibration.
`--allow-few-shot` is an explicit WAV-import-only experimental exception to the five-take rule.

## Runtime and efficiency

New profiles default to 30 ms effective matching steps, 0.75 s scan cadence and two proposals.
MFCCs are still extracted every 10 ms with 39 dimensions. A bounded batch of at most 16 references
shares the subsequence-DTW Python row loop. This batching alone is exact against scalar reference
checks. Coarser alignment is approximate and can change decisions; that is measured separately.

The coarsest-only mode failed an existing generated-word acceptance test. The default now
refines each proposed neighborhood with 20 ms alignment, preserves a small boundary pad and
re-extracts the candidate word as in enrollment. All intents are rescored on that same crop.
The test was retained and now passes. Overlapping refined proposals are suppressed.

A 64-entry cache stores only crop digests and prediction scores, not voice recordings. It can
reuse identical overlapping-window crops without repeating DTW. Threshold/margin/matching-limit
changes invalidate the cache; pause/reset clears it. Input audio remains a bounded five-second
buffer. `--keyword-detail` selects 20 ms matching / 0.5 s scans for a faster CPU or closer analysis.
Use `--keyword-scan-s 1.25` for the tested lower-CPU UNO Q cadence. The public API can select
other strides/cadences; fewer scans/coarser alignment have recall and reaction-delay costs.

No extra runtime dependency was added: NumPy and the existing optional capture/TTS components
remain sufficient. Blocking matching belongs on the shared audio worker. Existing `always_on`
still uses the original utterance recognizer; it does not silently enable this new detector.

## Measured recognition comparisons

All primary comparisons reuse the [115-stream development corpus](NOISY_STREAMS.md): 112 target
occurrences but only **22 independent target recordings**, because noise variants and repeated
words share sources. Three profiles have two real enrollment takes per word; two other profiles
retain clipping failures. No query enters fitting or threshold calibration. All cutoffs remain
capped at 0.8 with margin 0.12; no threshold is raised to make the test pass.

| Development arm | Correct accepted occurrences /112 | False accepted events |
|---|---:|---:|
| Original whole-window keyword path | 0 | 0 |
| Batched 20 ms, equal feature weights | 0 | 0 |
| 20 ms, static/delta/delta2 weights 1/.5/.25 | 4 | 0 |
| Same + mild synthetic enrollment | 2 | 0 |
| Same + 20 dB noise enrollment variants | 3 | 0 |
| Coarse 30 ms / 0.75 s, no refinement | 2 | 0 |
| Refined 30 ms / 0.75 s, two proposals (new default) | 1 | 0 |
| Refined 40 ms / 0.75 s + noise variants | 3 | 0 |

These are poor recall results. The few successes are correlated across noise conditions, not
four/three/one new human utterances. Synthetic enrollment did not outperform the unaugmented
20 ms arm overall, so it stays optional. Fast mode trades some recall for CPU cost; it does not
establish improved real-speech accuracy. Zero false accepts alongside almost all targets being
rejected is not a reliable open-set error-rate guarantee.

Reports: `validation/keyword_ablation_laptop.json`, `keyword_noise_augmentation_laptop.json`,
`keyword_balanced_ablation_laptop.json` and `keyword_refined_ablation_laptop.json`.

## Synthetic robustness demo, kept separate

A second diagnostic perturbs an **enrollment-source** word by 2% speed/pitch and gain, places it
inside unrelated complete recordings and adds noise. These are not independent human tests.
The mild-augmentation / 20 ms model recovered 15/15 clean and 15/15 gap-noise targets, 1/15 at
20 dB overlapping noise, and 0/15 at 10 dB. No false events occurred. Do not advertise the clean
15/15 as recognition accuracy: the parent word is already in enrollment.

```bash
python roles/speech/evaluation/synthetic_keyword_demo.py
# Local listening page: data/evaluation/synthetic_keyword_demo/preview.html
```

The gallery carries an explicit seen-source warning. Audio remains ignored/local. The diagnostic
is saved in `validation/synthetic_keyword_demo.json` and is separate from all independent-source
counts above. No synthetic impaired voice or large pretrained model is generated/downloaded.

## Evaluate fresh personal phrases

Record at least three NEW natural phrases per request, plus unrelated speech, environmental
noise and other speakers saying the same words. Use a separate continuous-negative calibration
set and an untouched final test set. See [annotated stream format](KEYWORDS_IN_PHRASES.md).

```bash
python roles/speech/evaluation/evaluate_keyword_streams.py \
  --profile data/keyword_profiles/patient_001 \
  --manifest data/heldout_phrases/streams.json --output results/personal_streams.json
python roles/speech/evaluation/keyword_ablation.py --variants refined_30ms
python roles/speech/evaluation/keyword_impostors.py
python -m pytest -q tests roles/speech/integration/test_integrated_recognition.py
```

The two refined modes each rejected 60/60 corpus same-word/different-speaker trials in
`validation/keyword_impostors_laptop.json`. This is not speaker authentication; sensitivity
is far too low and the negative sample small. Event times use the audio clock, not physical
notification latency. Patient confirmation remains mandatory before any caregiver request.

Existing touchscreen setup still saves regular utterance profiles. Live keyword activation
needs device-owner integration: single microphone owner, bounded worker, drop/profile-change
checks, pause/reset during TTS/enrollment/pending confirmation, and accepted request candidates
queued through the existing confirmation flow. Do not enable this on the basis of synthetic
successes or assume five recordings guarantees usable recognition.

## Actual UNO Q speed and test results

138 tests passed locally and on the UNO Q. Tests cover five-real-take enforcement, synthetic
parent exclusion, feature/profile persistence, exact scalar/batch agreement, maintained generated
WATER acceptance, crop-cache reuse/invalidation and unchanged controller confirmation behavior.
The hardware unit suite has one upstream test-client deprecation warning.

Two representative public-corpus replay clips were benchmarked in isolation from microphone/TTS
operations, at `nice -n 10` alongside the live app. The original 10 ms scalar mode vs batched/
weighted 20 ms mode was compared in two alternating paired runs: **3.24× and 4.57× faster**.
That 20 ms mode still had real-time factors 1.32/1.39, so it did not keep up in this setup.

The corrected refined 30 ms mode at 0.75 s cadence measured real-time factors 0.57/1.14; the
longer case still fell behind. At the explicitly lower scan frequency of 1.25 s, a separate
one-run-per-case replay produced:

| Mode | 5.56 s clip: processing / audio time | 11.89 s clip: processing / audio time |
|---|---:|---:|
| Refined 30 ms, 10 references | 0.337 | 0.700 |
| Refined 40 ms + synthetic variants, 25 references | 0.366 | 0.860 |

Both lower-cadence replays finished faster than their input audio. This is not a guarantee for
long-running capture, longer templates, more classes or concurrent hardware load. Reducing scan
frequency lowers total work, not the time of an individual scan. Calls producing proposals had
p95 processing times approximately 486/1119 ms (30 ms mode) and 540/1363 ms (25-reference mode).
The 500 ms processing target is still missed by the longer cases. Detection also waits for
scan cadence; do not describe these as instant responses or wall-clock notification latency.

The lower-cadence mode had 2/112 accepted target occurrences and zero false accepted events in
the 115-stream development replay, still very poor recall. No claim of usable recognition
accuracy is justified. The next validation gate is five NEW consistent personal WATER/PAIN
recordings plus independent natural phrase and negative-stream tests, not counting synthetic
copies as new human speech.

Raw hardware data: `validation/keyword_speed_board.json`, `keyword_speed_refined_board.json`,
`keyword_speed_paced_board.json`; laptop paired timings: `keyword_speed_laptop.json`.
`keyword_paced_ablation_laptop.json` records the lower-cadence recognition comparison. The
persistent validation copy is `/home/arduino/.cache/sonara-speech-validation`, separate from the
live repository. No service, audio recovery unit, HDMI routing, local.toml or MCU was modified.
