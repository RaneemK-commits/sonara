# Speech STATUS

## Expanded noisy-stream experiment

- User requested more TORGO samples assembled into sentence-like streams with intervening noise.
- Downloaded 36 new full filler recordings (12 per completed speaker), with no original
  enrollment/test source or alternate-microphone leakage. Expanded source cache: 173 takes.
- Built 115 annotated streams / 17.72 minutes / 51 MiB under ignored data/evaluation/torgo_noisy.
  Target positions vary; repeated targets, target-free speech and noise-only controls included.
  Clean/gap-noise/20 dB/10 dB variants share the same 22 independent target recordings; variants
  and repeated takes are not new independent positives. No natural-sentence/clinical claims.
- All 115 streams replayed locally in 50 ms chunks. Accepted recall remains 0%. Correct-label
  overlapping pre-rejection proposals cover 18/28 clean, 17/28 gap-noise, 18/28 at 20 dB and
  17/28 at 10 dB occurrences. Zero false accepts is not useful evidence with all positives rejected.
- 121 tests pass locally (5.79 s). Noise/timestamp/source-split checks pass, 36 local player
  links verified. Laptop real-time factor 0.24–0.26, RSS 61.4 MiB; no new board benchmark.
- Local listening gallery: data/evaluation/torgo_noisy/preview.html. Raw/generated audio stays
  ignored and is not committed. See docs/NOISY_STREAMS.md and validation/noisy_streams_laptop.json.
- No production/controller/server/config/UI changes or live microphone use in this experiment.

## Main objective: keywords inside longer phrases

- User clarified WATER/PAIN-like personal keywords inside “I need water please”, not just
  pause-separated utterances. Production whole-utterance recognition does not solve this.
- Added experimental shared-scaling MFCC + subsequence DTW localization, same-span all-intent
  rescoring, repeated-word proposals, bounded rolling feed and duplicate accepted-event suppression.
- New keyword profiles require fresh raw-MFCC enrollment and are separate from active CMVN profiles.
  Endpoint trimming preserves 180 ms padding; manual word boundaries remain available.
- Added persistent-stream chunk read/overrun APIs for the device worker; no new microphone opened,
  no controller/server/config/UI changes and no runtime activation.
- Added artificial composed-TORGO comparison and generic annotated natural WAV-stream evaluator.
  Corpus compositions are not natural phrases and are not WATER/PAIN recordings.
- 116 tests pass locally (6.09 s) and on UNO Q (38.42 s; one upstream test-client warning).
  Initial replay was interrupted by a board reboot; restored the isolated copy with the existing
  board .venv. An omitted static-web test fixture was fixed and integration tests rerun unchanged.
  No failing tests were deleted. Generated-audio checks accept an embedded WATER pattern and
  reject noise; those are software checks, not real speech accuracy.
- Laptop comparison: 15 composed positive clips and 30 negatives, all predictions rejected.
  Before rejection, stream proposals localize the correct best label in 12/15 clips; that is not
  recognition accuracy. Shared-scale whole-recording best labels also get 12/15; no measured
  accuracy improvement from subsequence matching is established. Board decisions and timestamps
  agree with the laptop. Shared-board/lower-priority replay: 84.22 s input, streaming real-time
  factor 3.442, mean total processing per clip 6.44 s, RSS 51 MiB. This cannot keep up in this
  setup; do not activate it live. Incremental matching/feature extraction needs work in addition
  to sensitivity and continuous-negative calibration. Reports and reproduction commands are
  in docs/KEYWORDS_IN_PHRASES.md. Fresh WATER/PAIN natural phrases are still unavailable.
- Current production pipeline remains untouched. NEED device/UI integration only after validation:
  single microphone owner, bounded worker, reset on drops/TTS/enrollment/profile reload, pause
  pending confirmation, request keywords only and mandatory patient confirmation.
- Read docs/KEYWORDS_IN_PHRASES.md and new CONTRACT section for APIs and evaluation commands.

## Earlier pipeline follow-up

- Follow-up branch `speech/voice-pipeline-improvements`, based on integrated main `6cd70b5`.
- Core MFCC/enrollment device hooks were integrated by device (`f4ca596`, `f157554`).
- Follow-up changes only speech-owned files: exact batched DTW, idle-noise VAD initialization,
  safe profile-switch/recovery behavior, Windows-compatible evaluation imports, recognition logs,
  actionable enrollment calibration diagnostics and isolated English TORGO evaluation.
- Controller/server/config/MCU/UI/audio-output route are unchanged. No running app was redeployed.
- Need device to integrate this branch and collect fresh, consistent enrollment plus independent
  held-out recordings. All-rejected live recognition is diagnosed, NOT resolved by relaxing safety.

## Verified

- 94 tests passed locally (5.86 s) and on UNO Q (28.97 s); one upstream test-client deprecation
  warning on board. Windows resource-unavailable behavior is simulated, not an actual Windows run.
- Paired UNO Q matching, 25 templates: 0.6 s scalar 502.5 → batched 169.3 ms (2.97×),
  5 s 5001 → 2949 ms (1.70×), no observed score/prediction difference. Full short synthetic
  recognition 138.6 ms mean / 159.5 p95; five-second recognition remains ~2.88 seconds.
- Read-only live-profile diagnosis: 14/25 nearest intents correct in leave-one-out enrollment
  comparisons; several positive/cross-intent distributions overlap. This is not held-out accuracy.
  Feature-only self-query timing (not accuracy): 299 frames × 25 templates, three runs each,
  scalar matching ~3.11 s vs batched ~1.44 s on shared board. Timing report remains private in /tmp.
- English TORGO: all five speakers meeting fixed-word repetition eligibility were selected.
  Two profiles fail preselected enrollment clipping checks. Three completed profiles:
  22 known tests all rejected, nearest intent correct 17/22; 30 other-word UNKNOWN and 60
  same-word impostors all rejected. Zero accepts is NOT successful speaker verification.
- TORGO laptop/board predictions agree, same manifest checksum. Board processing mean 561.1 ms,
  p95 988.5 ms, RSS 46.0 MiB. Calibration remains insufficient; no test-dependent threshold tuning.
- Detailed evidence: docs/VOICE_PIPELINE_IMPROVEMENTS.md, docs/TORGO_EVALUATION.md and validation JSONs.

## Board isolation

- Device owner's `/home/arduino/sonara`, port 8000, patient profiles, microphone, firmware and
  working Creative Pebble/monitor audio route were not modified by these follow-up tests.
- Temporary test copy: `/tmp/sonara-voice-improvements/source`; dependencies under
  `/tmp/sonara-mfcc-validation/deps`. No extra corpus dependencies installed on the board.
- English bundle is 137 public-corpus complete takes (~9 MiB), laptop ignored data directory and
  isolated board /tmp only. No raw patient audio leaves the board. No audio/weights committed.

## Decisions / limitations

- Keep fixed feature/scoring/rejection settings for paired comparisons and frozen TORGO tests.
  Current 0.8 fallback cap rejects independent real speech; overlapping enrollment also prevents
  reliable separation. Raising the cap until tests accept would be unsafe and leak test information.
- Two TORGO enrollment takes per word is a dataset limitation, not the recommended onboarding
  quantity. Corpus words are YES/NO/SIP/SIGH/LEAK, not relabeled bedside requests.
- Live 3 s clips cannot be compared with the 0.6 s synthetic latency benchmark; long sequences
  need further reduction/optimization after reliable personal segmentation and enrollment.
- Manual boundaries remain available. Idle-noise VAD change has automated tests, not live
  patient/noise validation. User cancelled button testing; buttons/MCU remain device-owned.
- No speaker-authentication gate or clinical claim. Confirmation remains mandatory.
- User will copy the hub message. Do not post comments or merge/push main automatically.
