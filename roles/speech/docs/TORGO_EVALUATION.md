# English TORGO evaluation

This is an English corpus experiment using real dysarthric speech, not simulated disability.
It exposes a recognition failure: the current conservative production settings reject every
held-out known word in this subset. Do not present the rejection result as successful recognition
or speaker identification. No threshold was adjusted using held-out recordings.

## Source and reproducible protocol

- [HF mirror: abnerh/TORGO-database](https://huggingface.co/datasets/abnerh/TORGO-database),
  revision `6e9b33c1af30eb3878574a1c1f5e60a60bd6d9c5` (16,552 rows, one `train` split).
- [Official TORGO project](https://www.cs.toronto.edu/~complingweb/data/TORGO/torgo.html).
  Cite Rudzicz et al. (2012), *The TORGO database of acoustic and articulatory speech from
  speakers with dysarthria*. Follow the source's academic/nonprofit use conditions. No corpus
  WAVs are committed or publicly redistributed by this work.
- The script constructs its own deterministic split. There is no official held-out split here.
  The filenames recover speaker/session/microphone/take IDs. Simultaneous arrayMic/headMic
  channels are one source take, never independent enrollment and test examples.
- Fixed vocabulary: **YES, NO, SIP, SIGH, LEAK**. These words are corpus labels, not remapped
  to WATER/HELP/PAIN. Thus this does not measure Sonara's bedside request vocabulary.
- HeadMic only, metadata duration 0.3–5 s. All five dysarthric speakers with at least three
  eligible takes of every fixed word: F03, M01, M02, M03, M05. The initial three-speaker pilot
  was expanded using this metadata eligibility rule; no score-based speaker selection occurred.
- Per speaker/word: first two independent takes ordered by session/take ID enroll; next up
  to three are held out. All sessions are pooled, so this is not a session-independent study.
  TORGO lacks enough repeats for the requested five enrollment plus three tests per word.
- Ten different single-word same-speaker UNKNOWNs selected by deterministic filename hash;
  one same-word impostor trial per other eligible speaker and word (20 per profile).
- Whole utterances only, conservative endpoint trimming with padding, preserved internal
  pauses, 16 kHz mono PCM. No synthetic augmentation, random crops or alternate-channel copies.
  Invalid trials remain failures; invalid enrollment prevents evaluating that entire profile.
- Enrollment-only LOO/cross-intent calibration, production distance cap 0.8 and margin 0.12.
  Temporary isolated profiles, no microphone/TTS/controller/caregiver calls. Profile directories
  are independent so selecting one cannot contaminate the next speaker's enrollment.
- Source-take IDs, exported PCM digests and WAV digests are checked for reuse within each
  profile. The portable manifest fixes the exact takes before any score is measured.

## Results

Of five planned profiles, three enrolled successfully. M01 and M05 each failed enrollment due
one heavily clipped preselected take; their 75 planned queries were not run and are excluded
from the successfully enrolled subset below. No takes were silently replaced.

| Successfully enrolled subset | Result |
|---|---:|
| Independent held-out known words | 22 |
| Correct accepted intents | 0 / 22 (0%) |
| Known-word rejections | 22 / 22 (100%) |
| Wrong known-intent accepts | 0 / 22 |
| Accuracy among accepted known words | Undefined: none accepted |
| Nearest intent correct before rejection | 17 / 22 (77.3%) |
| Other-word UNKNOWN false accepts | 0 / 30 |
| Same-word other-speaker false accepts | 0 / 60 |

Every evaluated input passed audio-quality validation. All profile calibration diagnostics
require more recordings. Laptop mean processing latency was 30.7 ms / p95 56.2 ms, peak process
RSS 55.6 MiB. Machine-readable per-speaker results, confusion matrices, per-trial scores,
distances, margins, thresholds, invalid-enrollment reasons and timings are in
[validation/torgo_laptop.json](validation/torgo_laptop.json). The UNO Q produced identical accepted/rejected predictions and nearest-intent labels with the
same manifest checksum: mean processing **561.1 ms**, p95 **988.5 ms**, maximum **1359.7 ms**,
peak process RSS **46.0 MiB**. See [validation/torgo_board.json](validation/torgo_board.json).
The real-word subset therefore also exceeds the 500 ms target on average.

The zero false accepts are explained by rejecting everything. They do not establish useful
UNKNOWN rejection or protection against another speaker. The nearest-label result is diagnostic
only; it cannot be advertised as accepted recognition accuracy.

## What the failure means

Independent real-speech distances are typically above 0.8. The fixed fallback cap suppresses
all acceptance, and some enrollment positive/negative distances overlap. With only two takes
per class, calibration cannot justify relaxing rejection. More consistent and numerous personal
recordings are needed, with held-out negatives and an untouched test set. Raising a global
threshold until this corpus accepts is not a valid fix. The board's long fixed recordings also
need separate capture/background-noise diagnosis; dataset audio is not the board microphone.
A speaker identity gate remains unimplemented and unvalidated.

## Run locally, then offline on UNO Q

Preparation requires a networked laptop and optional evaluation dependencies. These packages
are not recognition runtime dependencies; no neural model or full corpus installation is needed.
Audio is cached only under ignored `data/evaluation/torgo/` (137 exported takes, about 9 MiB).
Parquet range reads fetch the containing audio row groups, so network transfer exceeds the final
subset size; metadata auditing reads filenames/text without decoding all corpus audio.

```bash
python -m pip install numpy soundfile scipy huggingface-hub pyarrow
python roles/speech/evaluation/torgo.py prepare
python roles/speech/evaluation/torgo.py evaluate \
  --output roles/speech/docs/validation/torgo_laptop.json
python -m pytest -q tests/test_speech_torgo.py
```

Prepare caches pinned metadata in `rows.json` and freezes `selection.json` before decoding.
The final portable bundle is `data/evaluation/torgo/bundle/`, including `manifest.json` and WAVs.
Transfer it only to your local test machine/board, not a public repository. Evaluation on the
board needs the checked-out source and its normal NumPy dependency, not HF/PyArrow/SciPy:

```bash
python roles/speech/evaluation/torgo.py evaluate \
  --directory /tmp/sonara-voice-improvements/torgo \
  --output /tmp/sonara-voice-improvements/torgo_board.json
```

Use an isolated checkout to keep the live app, patient profiles and microphone untouched.
This evaluates the MFCC/DTW path offline, not live microphone usability, confirmation, clinical
performance or a new neural network. MFCC templates are enrolled; no pretrained English model
or neural training is required.
