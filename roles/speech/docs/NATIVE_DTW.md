# Faster matching and guarded request recognition

The live UNO Q keeps the full personalized reference set. Optional native C DTW replaces
Python-loop overhead with the same banded RMS-Euclidean recurrence, path-length normalization
and tie preference. NumPy remains the portable default when no library is configured.
No neural model, network service or additional Python package is introduced.

## Verified on the board

Same saved 3-second WATER recording, full 225 request templates, shared Cortex-A53 CPU:

| Engine | Processing time |
|---|---:|
| NumPy | 7,412.8 ms (one run) |
| Native | 731.4 / 721.3 / 810.7 ms |

Scores agree within 1e-9 and the recognized label is unchanged. This is roughly a tenfold
speedup on that clip, not a worst-case guarantee. Ten saved board clips processed in about
0.56–0.74 seconds in the subsequent replay. Capture time and spoken playback are additional.
The synthetic steady-noise check rejects before DTW in about 4 ms.

Nineteen native/reference tests cover variable lengths, bands, ties, repeats and invalid input.
Twelve further numerical comparisons passed on ARM64. The deployed board suite passed 34
related tests; the final isolated local release suite passed 186 tests. A human confirmed that
fresh silence is rejected and HELP/FOOD work after the stronger guard update.

## Recognition policy

Single-pass matching with nearest-label ranking, subject to:

- Padded-utterance speech activity: sustained energy above the local noise floor.
- Current microphone/speaker level floor: 0.003 RMS.
- Absolute DTW limit: 0.75.
- Minimum winner gap: 0.01 for requests, 0.025 for FOOD.
- Physical/touch confirmation before caregiver dispatch; no voice YES/NO.

The first ratio-only gate admitted a real idle HELP clip at distance 0.787. The stronger level
and distance gates were added after that failure. The new cap retains all 75 nearest-correct
request development scores; adding the per-intent gaps accepts 73/75. These reused recordings
informed selection and do not establish independent accuracy. Soundalike/other-speaker rejection
remains incomplete. Quiet or sustained low-dynamic vocalizations may need different enrollment,
microphone placement and profile-specific gate settings.

## Build and reproduce

A local C compiler is needed only to build the optional library. Build on the target CPU;
do not copy an x86 library onto ARM64. There is no runtime compilation.

```bash
python roles/speech/evaluation/build_native_dtw.py --output data/native/libsonara_dtw.so
python roles/speech/evaluation/guard_personal.py \
  --source data/candidates/lukas_requests_v1 --output data/candidates/my_guarded_profile
SONARA_DTW_LIBRARY="$PWD/data/native/libsonara_dtw.so" \
python roles/speech/evaluation/export_personal.py \
  --candidate data/candidates/my_guarded_profile --wav /path/to/new.wav --threshold .75 --margin 0
```

The guarded-profile builder keeps all reference features and source families; it adds policy
metadata only. Candidate format v2 retains compatibility with v1 feature archives. Templates,
recordings and compiled libraries remain outside Git.

Paired benchmark (local private JSON output):

```bash
python roles/speech/evaluation/benchmark_native_dtw.py \
  --candidate data/candidates/my_guarded_profile --library data/native/libsonara_dtw.so \
  --wav /path/to/new.wav --output data/native/benchmark.json
```

## Current live deployment

Service drop-in `~/.config/systemd/user/sonara.service.d/95-native-guarded.conf` sets:

```ini
[Service]
Environment=SONARA_PERSONAL_CANDIDATE=/home/arduino/sonara-native-final-guards/candidate
Environment=SONARA_DTW_LIBRARY=/home/arduino/sonara-native-guarded-v2-package/libsonara_dtw.so
Environment=SONARA_PERSONAL_REQUEST_THRESHOLD=0.75
```

Earlier demo override keeps the global margin at zero; profile-specific gaps still apply.
`/api/profiles.calibration` exposes `dtw_engine`, `speech_min_rms`, `intent_margins`, reference
count and `decision_policy=guarded_closest`. To fall back to NumPy while retaining recognition
guards, clear `SONARA_DTW_LIBRARY` in a later service override, reload systemd and restart.

Backups: `/home/arduino/sonara-native-guarded-backup` and
`/home/arduino/sonara-native-final-guards` (prior code/settings). No controller, server, capture,
MCU or unrelated playback edits were deployed by this change.

## Rejected smaller models

Balanced three-medoid references reduced matching to about 0.58 s and scored well on laptop
recordings, but mislabeled both known board WATER clips as FOOD. Aggressive boundary cropping
and coarse matching also introduced word confusions. These profiles were not activated. The
medoid helper remains an evaluation tool, not the recommended production profile builder.
