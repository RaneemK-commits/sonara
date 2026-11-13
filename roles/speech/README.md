# Sonara — giving every voice a way through

Sonara is an offline bedside communication MVP for the Arduino UNO Q (4 GB, ARM64 Debian).
It recognizes a small vocabulary of **one person's enrolled acoustic patterns**, including
nonstandard pronunciations. It does not transcribe unrestricted speech or train a neural network.
Piper speaks the selected phrase; a separate patient confirmation is required before a caregiver
request enters SQLite and the existing WebSocket acknowledgment/completion flow.

```
Device microphone / WAV (16 kHz mono float32)
  → energy VAD or manual recording boundaries → DC removal / audio validation
  → MFCC + delta + acceleration (T × 39) → CMVN
  → banded DTW against personal templates → mean of two nearest per intent
  → absolute/per-intent threshold AND runner-up margin → intent or UNKNOWN
  → existing controller → Piper → patient confirmation → caregiver request
```

Recognition requires NumPy, CPU and personal templates only. No speech model weights, neural
embedding runtime, cloud service, or model selection switches are used. Piper's optional TTS
package owns any ONNX dependencies needed for output speech. Existing voice assets are preserved.

## Run locally

Python 3.11+ is required. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,audio]'
python -m sonara --no-audio --mcu none
```

Open `http://localhost:8000/room` and `/caregiver`. The no-audio mode supports phrase tiles,
confirmation, cancellation and caregiver status updates. Voice setup reports that no microphone
is attached. The caregiver token is configured in `config/sonara.toml`.

For audio and offline output speech:

```bash
pip install -e '.[audio,tts]'
python scripts/download_models.py       # Piper voice only; requires internet once
python scripts/pregenerate_tts.py       # produces local playback WAVs
python -m sonara --mcu none
```

No download happens during recognition. Missing microphone support leaves phrase tiles usable.
Missing Piper prompt WAVs are reported rather than replaced with a cloud voice.

## Touchscreen enrollment

1. Open `/room` and choose **Set up my voice** (opens automatically without an enrolled profile).
2. Create a profile ID or edit an existing profile. Saved profiles can also be loaded or deleted.
3. Choose an intent. The intended sentence is displayed; say it in your own natural way.
4. Press **Record pronunciation**. Speak when the recording message appears. The default is a
   fixed three-second recording using the **Sonara device's attached microphone**, not the browser's.
   Change the duration up to five seconds, or uncheck fixed duration to use automatic VAD.
5. Keep each valid take or discard/repeat it. Capture five takes for each of the five request intents.
   `YES` and `NO` are optional; the Send and Cancel buttons always remain available.
6. Delete the last poor take or redo an intent as needed. Save/recalibrate and **Test recognition**
   using new takes and unrelated speech. Tests never create caregiver requests.
7. Finish to activate the profile and return to normal Talk / Send / Cancel operation.

Audio validation rejects empty, nonfinite, silent/DC-only, overlong or heavily clipped recordings.
Quiet valid audio gets feedback. Automatic energy VAD preserves internal pauses in an utterance,
with 180 ms endpoint padding; capture ends after 1.2 s of silence by default. Longer pauses may
require fixed boundaries. `[audio] manual_duration_s = 3.0` also enables fixed recording for Talk.

A single persistent microphone stream serves enrollment and recognition. Minimal Debian images can
use the built-in `arecord` adapter by setting a device such as
`device = "alsa:plughw:CARD=Set,DEV=0"`; this needs `alsa-utils` and NumPy, without PortAudio. Enrollment pauses Talk
and always-on recognition, and a shared lock prevents concurrent capture. Blocking work runs in
FastAPI's worker threads or the controller worker, with bounded audio and command queues.
Closing voice setup resumes normal operation; closing the browser while enrolling leaves Talk
paused until setup is reopened and closed or finished. Manual phrase tiles require closing setup.

## Profiles and calibration

```
data/profiles/<profile_id>/
  metadata.json
  templates.npz
  recordings/             # only with explicit local retention opt-in
```

Metadata contains version, profile ID, timestamps, feature configuration, counts, DTW parameters,
thresholds and calibration diagnostics. NPZ contains float32 feature sequences, not raw audio.
A checksum and metadata-last replacement detect incomplete saves; corrupt profiles fail closed.
Profiles reload on changes and can be switched while the server runs. `active.txt` remembers the
selected profile. Older embedding profiles must be re-enrolled; they are never silently converted.

Default scoring uses the mean of each intent's two closest templates. Acceptance requires both
an absolute distance limit (initial cap 0.8) and a runner-up margin (0.12). Per-intent limits are
calibrated using leave-one-out positives, cross-intent negatives, and optional enrollment-only
UNKNOWN examples. A positive 90th percentile plus slack is capped by a negative 10th percentile
minus a safety factor and the conservative fallback. No template is compared to itself.
Missing calibration never implies an infinite threshold. An explicit threshold of zero rejects all.

Small or poorly separated datasets report `requires_more_recordings`. Even a satisfactory
calibration diagnostic **does not guarantee UNKNOWN rejection**. Distances and display closeness
are not probabilities. Record additional varied examples and verify with held-out human audio;
confirmation remains mandatory. Repeated identical samples are refused.

CLI enrollment remains available (stop the running server before independent CLI mic capture):

```bash
python scripts/enroll.py --profile patient_001 --takes 5
python scripts/enroll.py --profile patient_001 --intents WATER --replace
python scripts/enroll.py --profile patient_001 --from-dir data/enrollment --takes 5
python scripts/enroll.py --profile patient_001 --delete-intent WATER
```

Import directories contain `INTENT/*.wav`. Use `--keep-audio` only for consented local development
or evaluation. The UI has a separate explicit retention checkbox. Profile deletion removes retained
audio too; UI sample/intent deletion removes its retained WAV. WAVs are never served to browsers.

## Run on the UNO Q

Copy the repository to the board, then use the same virtual environment installation as above.
On Debian, the audio environment may require `python3-venv`, `libportaudio2`, and `alsa-utils`.
Use `arecord -l` to identify the attached capture device. The tested board USB headset uses
`[audio] device = "alsa:plughw:CARD=Set,DEV=0"`. With PortAudio installed, use
`python -m sounddevice` and set `device` to its PortAudio index/name in `config/sonara.toml`; use `sample_rate = 16000`.

Set `[hardware] mcu = "unoq"` for the Arduino Bridge controls, or `--mcu none` to test without the
MCU. Change `caregiver_token`. Generate Piper prompts before disconnecting the network. Run:

```bash
python -m sonara
```

Open `http://localhost:8000/room` in the board's kiosk browser, and
`http://<board-ip>:8000/caregiver` on the trusted local network. Do not expose the demo server
on the public internet. Onboard through the touchscreen before using Talk.

## Evaluate real recognition

Keep enrollment and held-out recordings physically separate:

```
data/evaluation/person/
  enrollment/WATER/*.wav          # five independent examples per enrolled intent
  enrollment/HELP/*.wav          # also FOOD, PAIN, BATHROOM
  test/WATER/*.wav                # at least three NEW examples per enrolled intent
  test/HELP/*.wav
  test/_UNKNOWN/*.wav             # unrelated speech and background noises
  calibration_unknown/*.wav       # optional separate enrollment-only negative examples
```

```bash
python scripts/evaluate.py data/evaluation/person --enroll-counts 5
python scripts/evaluate.py data/evaluation/person --enroll-counts 3 5 --bands 0.1 0.2 0.35
python scripts/benchmark.py --profile patient_001 --wav data/evaluation/person/test/WATER/01.wav --runs 30
pytest -q
```

Evaluation uses deterministic sorted enrollment prefixes and an unchanged test set, checks decoded
audio hashes for duplicates across splits, and never tunes thresholds on test audio. It reports
correct intent rate, precision among accepted predictions, rejection, wrong-known and UNKNOWN
false acceptance, a confusion matrix, processing latency, template memory and peak process RSS.
Ablations vary enrollment count and DTW band; the deployment defaults remain fixed. Mean-vector
matching is omitted because CMVN makes each feature's mean nearly zero, discarding the sequence
information needed here. PCM 16-bit WAVs are supported; 16 kHz mono is recommended.
Use `--simulated` for acted speech. Human recordings are still not clinical validation.

A reproducible **non-speech** fixture generator is included for software checks only:

```bash
python roles/speech/evaluation/synthetic_dataset.py /tmp/sonara-fixtures
python scripts/evaluate.py /tmp/sonara-fixtures --synthetic
```

A streamed public German corpus diagnostic is also available:

```bash
pip install -e '.[corpus-eval]'                 # optional laptop tools; not needed on the board
python roles/speech/evaluation/prepare_real_corpus.py --queries 40
python roles/speech/evaluation/evaluate_real_corpus.py data/evaluation/dysarthric_german/bundle --output results/corpus.json
```

This corpus lacks speaker IDs and enough repeated phrases for personalized accuracy evaluation.
The diagnostic uses four complete single-take reference phrases and separate real-speech UNKNOWN
windows, with no synthetic enrollment copies. Results and protocol are in
[docs/CORPUS_EVALUATION.md](docs/CORPUS_EVALUATION.md).

See [docs/VALIDATION.md](docs/VALIDATION.md) for executed results and board verification status,
and [docs/DESIGN.md](docs/DESIGN.md) for algorithm and integration details.

## Main files

| Files | Responsibility |
|---|---|
| `sonara/models/features.py`, `embedder.py` | MFCC frontend and configuration |
| `sonara/models/dtw.py`, `classifier.py` | bounded sequence matching, rejection, calibration, persistence |
| `sonara/recognizer.py`, `audio/` | audio validation, segmentation, microphone/WAV handling, live reload |
| `sonara/models/enrollment.py`, `server/app.py`, `web/room/` | device-side onboarding service, API and touchscreen flow |
| `sonara/controller.py` | deterministic speech/confirmation/request integration |
| `scripts/enroll.py`, `evaluate.py`, `benchmark.py` | import/CLI enrollment and reproducible measurements |
| `tests/` | numerical reference, profile, enrollment, controller and caregiver regressions |

SQLite persistence, caregiver WebSockets, receipt/acknowledgment/completion, notification behavior
and Piper output are retained. `DISPLAYED` still needs a caregiver-screen receipt;
`ACKNOWLEDGED` still needs a caregiver click. A successful recognition never means help is coming.
This prototype is not a medical device or a replacement for a nurse-call system.

Piper voice provenance: `en_US-lessac-medium` from `rhasspy/piper-voices`; inspect its model card
for licensing. `download_models.py` prints source URLs and checksums. License: MIT.
