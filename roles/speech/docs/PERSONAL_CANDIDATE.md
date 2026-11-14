# Personal word candidate deployment

The feature-only candidate is experimental. It preserves weighted MFCC features,
80 ms endpoint padding, 20 ms matching steps, source-family aggregation and fixed
0.8 distance / 0.12 margin limits from the personal-session development experiment.
The five request words and YES/NO are separate contexts. Request context is default.
It never loads into the production Recognizer or changes the active patient.

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
The live `/home/arduino/sonara` application, firmware, microphone owner and active profile
were not modified. To score a WAV on the board:

```bash
cd /home/arduino/sonara-speech-personal-20261114/source
/home/arduino/sonara/.venv/bin/python roles/speech/evaluation/export_personal.py \
  --candidate ../candidate --wav /path/to/new.wav --context requests
```

This deployment supports offline candidate testing. Live controller integration requires
separate calibration and device-owner changes; no accepted result dispatches a request here.
Recording CLI requires the production microphone owner to be stopped first.
