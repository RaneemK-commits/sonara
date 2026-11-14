# Personal word candidate deployment

The feature-only candidate is experimental. It preserves weighted MFCC features,
80 ms endpoint padding, 20 ms matching steps, source-family aggregation and fixed
0.8 distance / 0.12 margin limits from the personal-session development experiment.
The five request words and YES/NO are separate contexts. Request context is default.
It is separate from standard profiles. The human-authorized live override described below
connects it to Recognizer without modifying the saved standard patient selector.

All three enrollment sessions contain 15 real examples per word in total. Two mild
speed/gain variants per real source change pitch and duration together; these are
not independent examples. Family-min distances are averaged across the two nearest
real-source families. Calls use batches of 16 with at most 400 stored references.

## Evidence and limitations

Session-held-out development: baseline nearest request labels 74/75; augmented weighted
candidate 75/75. Confirmation nearest labels 28/30. Fixed rejection accepts only 1/75
requests and 4/30 confirmations in the candidate. Fourteen similar-word test recordings
produce zero request false accepts, but snow is falsely accepted as NO. These are small
personal development results, not general accuracy. Final known-word test audio has not
been used to tune this candidate. Keep physical Confirm/Cancel and do not enable voice
confirmation based on these results.

The saved export reproduces all 28 study negative/context scores. Feature-only artifacts
stay out of Git. No raw personal audio was transferred to the board.

## Laptop commands

Guided recording (Enter starts/stops, Enter keeps, r repeats, q quits):

```bash
.venv/bin/python roles/speech/evaluation/record_demo.py --profile new_session --device default --keep-audio
```

Only collect similar-word WAVs without recognition:

```bash
.venv/bin/python roles/speech/evaluation/record_demo.py --profile new_session --device default --record-only --similar-only
```

Reproduce development comparison:

```bash
.venv/bin/python roles/speech/evaluation/personal_sessions.py
```

Build a new feature-only candidate in a fresh directory:

```bash
.venv/bin/python roles/speech/evaluation/export_personal.py \
  --candidate data/candidates/new_candidate \
  --sessions data/profiles/laptop_session_02 data/profiles/laptop_session_03 data/profiles/laptop_session_04
```

Score a new 16 kHz mono WAV, with UNKNOWN rejection and closest-label diagnostics:

```bash
.venv/bin/python roles/speech/evaluation/export_personal.py \
  --candidate data/candidates/lukas_requests_v1 --wav /path/to/new.wav --context requests
```

`--context confirmation` is for offline diagnostics only; it has the known snow/NO failure.

## UNO Q installation

Separate copy: `/home/arduino/sonara-speech-personal-20261114/source`.
Candidate: sibling directory `../candidate`. Uses existing board Python dependencies.
The initial deployment was isolated. The later live adapter activation is documented below. To score a WAV on the board:

```bash
cd /home/arduino/sonara-speech-personal-20261114/source
/home/arduino/sonara/.venv/bin/python roles/speech/evaluation/export_personal.py \
  --candidate ../candidate --wav /path/to/new.wav --context requests
```

This deployment supports offline candidate testing. Live controller integration requires
separate calibration and device-owner changes; no accepted result dispatches a request here.
Recording CLI requires the production microphone owner to be stopped first.


## Live activation on UNO Q

Human explicitly requested live integration. Recognizer now supports the optional environment
variable `SONARA_PERSONAL_CANDIDATE`. Board service drop-in:
`/home/arduino/.config/systemd/user/sonara.service.d/50-personal-requests.conf` points to
`/home/arduino/sonara-speech-personal-20261114/candidate`.

The running app reports `personal_requests_demo`. Talk uses request context only. Confirmation
continues through physical/touch controls; no YES/NO candidate output is passed to the controller.
The existing standard profile selection is preserved for rollback. Runtime activation does not
improve the measured rejection rates: the same 0.8/0.12 limits remain.

To roll back this override on the board:

```bash
mv ~/.config/systemd/user/sonara.service.d/50-personal-requests.conf    ~/50-personal-requests.conf.disabled
systemctl --user daemon-reload
systemctl --user restart sonara.service
```

Without the environment variable, Recognizer uses the original profile path and selector.
Previous live recognizer and DTW files were backed up in
`/home/arduino/sonara-personal-live-backup-20261114`.


## Live request-limit adjustment

At the human's request the board drop-in now also sets:

```ini
Environment=SONARA_PERSONAL_REQUEST_THRESHOLD=0.85
Environment=SONARA_PERSONAL_REQUEST_MARGIN=0.10
```

Defaults remain 0.8/0.12 if these variables are absent. The live API reports effective settings.
Rescoring the existing development request trials changes accepted correct predictions from
1/75 to 4/75, with zero wrong labels; all 14 similar-word negatives still reject. These settings
were selected using those results, so this is tuning evidence, not independent validation.
Reducing margin to 0.08 admits a negative (walker); 0.06 admits two. Genuine-request acceptance
remains low even with this update. Physical confirmation is required and voice YES/NO remains
excluded. Prior code/settings for this adjustment are backed up in
`/home/arduino/sonara-personal-limits-backup-20261114`.


## Rejected-word boundary retry

A real USB-mic WATER clip contained a long noisy lead-in. Default trimming kept all 3 s and
failed the margin test. The candidate now retries one focused span only after request rejection:
ignore energy spikes shorter than 60 ms, retain 80 ms endpoint padding, preserve internal pauses,
and require a substantial shortening. The original and retry nearest labels must agree. All
original thresholds remain enforced; this is not automatic nearest-label acceptance.

The recorded board WATER regression changes from rejected (margin 0.0158) to accepted (0.053).
This clip informed development, so it is not independent validation. It took 10.55 s on the
shared board, including both matching passes. Four of five known laptop tests still accept
correctly; PAIN remains rejected. The current margin 0.05 also admits walker/fool/paint among
14 negative examples; this retry adds none, but does not resolve those existing false accepts.

Runtime margin 0.05 comes from the separate `60-demo-margin.conf` override; it supersedes the
0.10 setting documented in the earlier deployment. Distance remains 0.85. No voice YES/NO.

Human-authorized diagnostics temporarily save at most ten clips under the board's ignored
`data/speech_diagnostics_20261114`. Remove/move `90-speech-diagnostics.conf` out of the user service
drop-in directory and restart Sonara to disable capture. Diagnostic audio never enters Git.


## Current supervised MVP policy: closest label, single pass

At explicit human request, board `85-closest-label-demo.conf` sets distance 0.85 and margin zero.
The API labels this `closest_with_distance_gate`. This avoids margin-based rejection of FOOD
and WATER and skips the boundary retry, guaranteeing at most one template-matching pass.
Audio validation and the absolute distance limit still apply. It does not automatically send
requests: the patient must confirm the spoken proposal. Voice YES/NO is still excluded.

This is a usability tradeoff for supervised demonstrations: rescoring the earlier development
request scores increases correct accepts from 47/75 (margin 0.05) to 75/75 (zero), but accepts
all 14 similar-word negatives instead of three. These reused recordings do not establish general
accuracy. Incorrect suggestions must be cancelled. No speaker-authentication claim.

Single pass is less work than retrying, but 225 request references remain. Earlier first-pass
processing took about 6–8 s on the shared board; this update does not establish subsecond latency.
Remove/move `85-closest-label-demo.conf` and restart to restore the underlying margin setting.
Live app sources are backed up in `/home/arduino/sonara-closest-demo-backup`.
