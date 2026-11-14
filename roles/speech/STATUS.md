# Speech STATUS

## Supervised closest-label MVP mode (human requested)

- Human explicitly requested closest-label matching to stop repeated FOOD/WATER margin rejects.
  Board now uses 85-closest-label-demo.conf: distance 0.85, required margin 0. No voice YES/NO.
  Audio validation, distance rejection and patient confirmation remain. API exposes decision_policy
  closest_with_distance_gate. Defaults without override still use conservative margin rejection.
- Demo mode runs exactly one matching pass, even if distance rejects; focused-boundary retry is
  retained only when a positive margin is configured. This avoids the second DTW pass. Original
  225 request references remain, so earlier 6–8 s first-pass latency is still a material limitation.
- Earlier development scores (before boundary retry) at 0.85: margin 0.05 accepts 47/75 correct
  requests, margin zero accepts 75/75. Negative false accepts increase from 3/14 to 14/14. These
  are reused development recordings, not independent general accuracy. Do not describe as robust
  UNKNOWN rejection or use unsupervised. Wrong spoken proposals must be cancelled by the user.
- Eleven related tests cover explicit policy reporting, single-pass behavior, distance/audio
  rejection and unchanged conservative defaults. Initial closest-mode deployment passed ten tests
  on board (4.00 s); follow-up single-pass deployment is documented in main merge verification.
- Other-agent playback changes and README draft were excluded. Live device/controller/server
  sources remain unchanged. Remove 85-closest-label-demo.conf and restart to restore underlying
  margin policy. Backups: /home/arduino/sonara-closest-demo-backup.

## Live WATER boundary retry and opt-in diagnostics

- Diagnosed a real board WATER attempt (same speaker as laptop enrollment). Mic captured speech,
  but old trim retained all 3 s; margin was 0.0158. Laptop held-out WATER passed at margin 0.075.
- Added one bounded request-only retry after rejection: energy spans must persist >=60 ms;
  discard isolated endpoint spikes, retain 80 ms padding and internal pauses. Retry only when
  cropped span >=0.15 s and <=75% of original duration. Both passes must agree on closest label;
  retry still needs full distance/margin checks. Confirmation context has no retry.
- Same saved board WAV now accepts WATER at margin 0.053, distance 0.6302. Replay processing
  10.55 s on shared UNO Q: functional recovery for this clip, NOT a latency fix or fresh accuracy.
  The clip was used to develop the change, so this replay is a regression check.
- Five laptop known tests preserve four correct accepts, one PAIN rejection. At current board
  margin 0.05 the 14 negatives still have three false accepts (walker/fool/paint); retry adds none.
  Separate aggressive retraining experiments harmed WATER; those candidates were not deployed.
- Another session lowered runtime margin to 0.05 via 60-demo-margin.conf; preserved that and
  distance 0.85. No more limit changes in this fix. Physical/touch confirmation remains required.
- Explicit human opt-in enabled SONARA_SPEECH_DIAGNOSTICS; <=10 WAV/JSON pairs stay locally in
  board data/speech_diagnostics_20261114, private directory, excluded from Git. No board raw audio
  was transferred. Remove 90-speech-diagnostics.conf and restart to disable further retention.
- Local isolated suite: 161 passed (6.06 s); board: 9 related tests passed (3.58 s). Live health
  verified IDLE/ready with microphone available. Human fresh retry requested after deployment.

## Live rejection limits adjusted at human request

- Added explicit SONARA_PERSONAL_REQUEST_THRESHOLD / SONARA_PERSONAL_REQUEST_MARGIN environment
  overrides, validated at startup and exposed in /api/profiles calibration diagnostics. Defaults
  remain 0.8/0.12; board service override now uses 0.85/0.10 for request context only.
- Development rescore of augmented candidate: correct accepted requests rise from 1/75 to 4/75;
  no wrong accepted request labels; 0/14 similar-word false accepts at both settings. Choosing
  settings on these recordings makes this development tuning, not an independent accuracy claim.
  Looser 0.90/0.08 admits walker; 0.95/0.06 admits two negatives. Calibration remains unresolved.
- Deployed adapter update and restarted live app from IDLE. Health and /api/profiles verify
  personal_requests_demo ready, distance_threshold=0.85, required_margin=0.1, mic available.
  Voice YES/NO stays disabled; physical/touch confirmation and existing timeout remain intact.
- Five integration tests passed on board before restart (2.58 s). Local regression verifies
  accepting requires both limits, invalid settings fail startup, and default behavior is preserved.
- Prior code and service drop-in backed up at /home/arduino/sonara-personal-limits-backup-20261114.

## Live personal request integration (human authorized)

- Added explicit SONARA_PERSONAL_CANDIDATE override to Recognizer. Request-only scoring;
  version/checksum failures reject instead of falling back to a different patient. Profile API
  reports personal_requests_demo and warns calibration remains unresolved. Switching standard
  profiles requires disabling the override. Legacy behavior unchanged when override is absent.
- Activated on UNO Q via user-service drop-in 50-personal-requests.conf. Backups of the prior
  live recognizer/DTW are in /home/arduino/sonara-personal-live-backup-20261114. Device-owned
  controller/server/config and concurrent playback edits were not changed.
- Live health verified: IDLE, recognizer_ready=true, personal_requests_demo active, microphone
  available, one room and one caregiver screen connected. No request sent during deployment.
- 156 tests passed in isolated local release (6.28 s); four candidate/integration tests passed
  against live board code (1.95 s). Human microphone recognition with new adapter remains
  unverified. Absolute 0.8 / margin 0.12 remain restrictive; activation is not an accuracy fix.

## Personal sessions and isolated UNO Q candidate

- Added Enter-to-start/Enter-to-stop recording CLI, repeat/discard/quit controls, recording-only
  collection, similar-word prompts and separate repeatable test-run folders. No active profile
  selection changes. Local recordings remain ignored; no personal audio goes into Git.
- Compared 105 real enrollment recordings across sessions 02/03/04, holding out each complete
  session. Separate request and confirmation vocabularies. Weighted/augmented candidate gets
  nearest labels correct on 75/75 request and 28/30 confirmation development trials, but fixed
  rejection accepts only 1/75 and 4/30. Fourteen similar-word negatives reject in request context;
  confirmation incorrectly accepts snow as NO. No production-readiness claim.
- Exported feature-only candidate with 315 references from 105 independent parents. Source-family
  aggregation prevents augmented siblings voting twice. Round-trip scores match all 28 study
  negative/context comparisons. No thresholds were tuned on the negative test recordings.
- Local isolated release suite: 155 passed (6.39 s), excluding concurrent playback edits.
  Eight new CLI/candidate tests also pass on UNO Q (2.07 s). Candidate deployed separately at
  /home/arduino/sonara-speech-personal-20261114/{source,candidate}; production service and active
  patient_001 remain unchanged. Physical capture/live recognition with this candidate unverified.
- Documentation: docs/PERSONAL_CANDIDATE.md. Personal results stay in ignored data/profiles;
  candidate binary stays in ignored data/candidates. GitHub contains source/tests only.

## Keyword review after device handoff

- Fixed `KeywordSpotter.feed`: every scheduled scan runs at the same audio-clock position
  for 30 ms, 50 ms or 1 s delivery chunks, including after the five-second buffer rolls.
  Previously a large chunk could skip scans and change recognition results.
- Invalid nonnumeric input now resets streaming state; invalid standalone windows return no
  events. Whole chunks are validated before processing, so a corrupt tail cannot emit a match.
- Isolated speech snapshot: 147 passed. Combined snapshot using pushed device branch
  `codex/device-room-state` at 4aac904: 152 passed. These exclude concurrent uncommitted TTS
  edits. Nine new streaming tests also pass on the UNO Q (7.17 s), using only its isolated
  validation copy; live service, microphone and device-owned files remain untouched.
- No new accuracy/latency claim: earlier corpus measurements used 50 ms chunks with aligned
  scan cadences. Keyword mode remains experimental and disabled pending useful independent
  recognition results and fresh personal enrollment. The two-proposal budget can miss dense
  sequences of known keywords; this fix only makes delivery chunk size deterministic.

## Parallel task: playback lifecycle for device display

- Added optional `Speaker(..., on_playback=callback)` in `sonara/tts.py`, with immutable
  started/finished/failed/cancelled events carrying key and unique per-call utterance ID.
- `say`/`say_now` signatures unchanged. Queue replacement cancels pending phrases without
  interrupting active playback. Disabled audio is cancelled; backend/missing-WAV failures
  no longer claim success. `wait_idle` returns False on timeout without cancelling anything.
- Callbacks are serialized on the speaker worker outside locks; device must forward events
  to its owning event loop. See additive CONTRACT section for complete timing/semantics.
- Full local suite: 141 passed in 5.11 s outside sandbox (sandbox run stalled).
  No live audio/hardware validation. Local edits only; no board post, commit or push.
- Decision: keep this task separate from concurrent keyword/model/enrollment work;
  retain existing None returns from say/say_now and expose timeout information via wait_idle.

## Synthetic enrollment and faster keyword testing

- Five real takes per request are now required for normal keyword enrollment. Optional synthetic
  gain/speed/noise variants are explicit, capped, tracked by real parent and excluded as siblings
  from calibration. Two real + three synthetic remain two independent sources, not five.
- New keyword profiles: weighted 39-D MFCC, exact bounded batched subsequence proposals, effective
  30 ms matching, 0.75 s cadence, two coarse-to-fine proposals and 64 cached crop decisions.
  Legacy keyword profiles preserve stored matching settings. Core utterance recognition unchanged.
- Added `scripts/enroll.py --keyword-profile --intents WATER PAIN --takes 5`, WAV import, optional
  variants, overwrite/raw-retention opt-ins, quiet/progress feedback and invalid-file skipping.
  Saved profiles do not switch the active patient or activate live keyword recognition.
- Added source-independent ablations, seen-parent synthetic demo, impostor checks and paired
  laptop/UNO Q speed tests. Dataset remains a development set, not a fresh clinical estimate.
- 138 recognition/integration tests pass locally and on the UNO Q. Pure batching matches scalar
  references. The corrected fast matcher retains the generated WATER acceptance test; cache
  reuse and threshold invalidation are tested. Device unit suite has one upstream warning.
- Paired 20 ms processing is 3.24x/4.57x faster than old scalar, but long clips still lag. With
  CLI `--keyword-scan-s 1.25`, the tested refined 30 ms cases have RTF 0.337/0.700; 25-reference
  refined 40 ms cases have RTF 0.366/0.860. Fewer scans add delay. Long per-call times still miss
  the 500 ms target; these two shared-board clips are not a worst-case/continuous guarantee.
- Accuracy unresolved: 20 ms weighted arm gets 4/112 correlated target occurrences; optional
  variants get 2–3/112. New default refined 30 ms gets 1/112; 1.25 s cadence gets 2/112. Zero
  false accepted events does not imply reliable rejection while recall is this low.
- Seen-parent synthetic diagnostic: 15/15 clean + 15/15 gap-noise successes, only 1/15 with
  20 dB overlapping noise and 0/15 at 10 dB. This is NOT independent recognition accuracy.
- Two refined modes each reject 60/60 corpus impostor trials; no speaker-authentication claim.
- Read docs/FAST_KEYWORDS.md for commands, measured limits and validation JSONs. All audio stays
  local/ignored. No live app, caregiver path, device config, recovery unit or hardware changed.
- User asked to return to this task after the device capture FYI. On-demand capture draft is
  parked separately at /tmp/sonara-on-demand-capture-draft; it is not part of this change.

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
