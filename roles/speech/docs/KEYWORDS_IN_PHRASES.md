# Main objective: personal keywords inside longer phrases

The target is recognizing the patient's enrolled WATER/PAIN/HELP sound inside speech such as
“I need water please.” Whole-recording intent classification does not solve this task. An
ongoing microphone stream also differs from isolated words separated by silence.

This branch adds an **experimental** keyword-in-phrase path and a reproducible comparison.
It does not activate continuous keyword recognition in the running application. Existing
`listen_mode="always_on"` still uses VAD-delimited whole-utterance recognition, not this new
keyword-in-phrase path. The current
real-speech experiment still rejects all candidates and is not a functioning bedside detector.

## Pipeline and implemented scope

```
16 kHz mono chunks (e.g. 50 ms)
  → rolling buffer, at most 5 s; scan every 0.5 s
  → MFCC + delta + acceleration, 39 dimensions
  → shared mean/variance fitted ONLY on that person's enrollment
  → free-endpoint subsequence DTW proposals with start/end frame positions
  → bounded nonmaximum suppression (up to 3 proposals by default)
  → all intents rescored on the SAME proposed span using banded DTW
  → absolute threshold + competing-intent margin → accepted candidate or UNKNOWN
  → duplicate accepted-event suppression across windows
```

`sonara/models/subsequence.py` uses D(0,j)=0 and D(i,0)=infinity to allow a template to start
inside a longer sequence. Costs are RMS Euclidean; non-diagonal steps pay 0.05. Alignment
costs are normalized by actual path length. Candidate spans must be 0.5–2 times the template
length, and the stream/template are bounded to 600 frames. It keeps one minimum-cost path per
cell; duration checks do not search alternative paths to a rejected endpoint. Workspace is
linear in stream frames. This proposal pass has free endpoints, not a global Sakoe–Chiba
band; final same-span rescoring uses the existing banded DTW. Up to three candidates per
reference allow repeated keywords in one window; the final bounded proposal limit still
limits event density and may miss additional words.

`sonara/models/keywords.py` provides `KeywordSpotter.scan()` (a bounded audio window) and
`feed()` (incremental chunks, absolute timestamps within the current stream session).
Rejected proposals remain visible for diagnostics. An accepted event is not a notification.
`reset()` discards buffered audio and detection history. No audio is written by the detector.
It is synchronous: use an audio worker, never the audio callback or FastAPI event loop.
The persistent `AudioCapture` exposes `read_chunk(timeout_s=.1)` and `dropped_blocks`. A worker
must own the shared audio lock, detect any counter change before/after processing, discard
results across an overrun, flush stale input and reset the detector. This API does not open a
second microphone or automatically activate a consumer. Reads during a manual/VAD capture
raise an error; locking remains necessary to avoid races between consumers.

Utterance CMVN changes a word's representation depending on the surrounding phrase. Therefore
this experiment uses unnormalized MFCCs at extraction and an enrollment-fitted shared scaler.
Existing CMVN profiles cannot be converted back to the needed raw features; re-enrollment is
required. The new feature-only profile uses `keyword.json` and `references/`, intentionally
separate from production `metadata.json`/`active.txt` profiles. Loading it as an ordinary
Recognizer profile is not supported. No existing profile is modified.

```python
from pathlib import Path
from sonara.models.keywords import KeywordSpotter

# Fresh, consented 16 kHz mono float32 recordings, natural personal pronunciation.
# Prefer at least five independent examples per request; arrays are temporary in RAM.
spotter = KeywordSpotter.enroll({"WATER": water_recordings, "PAIN": pain_recordings})
spotter.save(Path("data/keyword_profiles/patient_001"))
spotter = KeywordSpotter.load(Path("data/keyword_profiles/patient_001"))
for chunk in device_audio_chunks:
    for event in spotter.feed(chunk):
        print(event.to_dict())  # analysis only; no caregiver dispatch
```

## Comparison with the available real audio

Run:

```bash
python roles/speech/evaluation/compare_keywords.py --stream \
  --bundle data/evaluation/torgo/bundle \
  --output roles/speech/docs/validation/keyword_comparison_laptop.json
python -m pytest -q tests/test_speech_keyword_spotting.py
```

The input is the previously frozen [English TORGO subset](TORGO_EVALUATION.md). Three profiles
complete enrollment; M01/M05 retain their clipping failures. Per completed profile, the first
held-out recording of each of five words is embedded between <=0.5 s central segments of two
other-word recordings from that speaker. No artificial silence is inserted, but these are
**artificial compositions with splice artifacts**, not naturally coarticulated phrases.
Five unknown recordings and five same-word impostor recordings are additional negative trials.
The comparison has 15 positive composed clips and 30 negative clips. No phrase WAV is saved.
The words are YES/NO/SIP/SIGH/LEAK because those have repeated recordings; none are relabeled
as WATER/PAIN. Actual bedside keyword-in-phrase accuracy remains unmeasured.

Comparison arms:

1. Existing utterance-CMVN whole-recording classifier.
2. Shared-scaling whole-recording classifier, to separate scaling effects from localization.
3. Subsequence proposals + same-span rescoring over the complete bounded clip.
4. The same detector replayed in 50 ms chunks through rolling windows.

Whole-recording arms report intent correctness without claiming localization. Keyword arms
require correct intent and temporal intersection-over-union >=0.3 with the known inserted
span. Accepted wrong-label/out-of-span proposals count as false accepted events. Before-rejection
nearest-label/localization counts are diagnostic, never recognition accuracy. Timing for
keyword arms includes MFCC extraction and proposal/rescoring; real-time factor is total
processing time / audio duration. Streaming incurs repeated overlapping scans.

This corpus has already been inspected during development, so these are **exploratory results**,
not a fresh final test estimate. Shared scaling is fitted only on enrollment; query recordings
never enter template fitting or threshold calibration. No threshold is tuned to make these
queries pass. The two enrollment examples per keyword are insufficient for reliable calibration.

## What must happen before live integration

- Collect fresh per-patient WATER/PAIN/HELP enrollment words, new natural phrases containing them,
  and long unrelated speech/noise/TTS recordings. Include other speakers saying the same words.
- Keep enrollment, continuous-speech calibration negatives and untouched test sessions separated.
  Measure event recall, false alarms per hour, localization error, duplicate events and time to
  recognition. Word-only thresholds do not address the increased false-acceptance opportunity
  from repeatedly searching a stream.
- Verify real-time factor <1 on the board. A bounded buffer alone cannot fix CPU overload.
  Final proposal caps and duration ratios can miss slow, repeated or densely spaced words.
- Device owner must supply chunks from the one existing microphone owner, pause/reset during
  Piper output, enrollment and pending confirmation, discard stale audio on resume, and use a
  bounded worker queue that resets the detector on dropped audio. Do not open a second mic.
- Only request intents belong in a bedside keyword profile. YES/NO in this corpus experiment
  are dataset words, not permission for ambient speech to confirm/cancel a pending request.
- Accepted request candidates must enter the existing controller confirmation flow. No direct
  caregiver notification and no automatic ambient-voice confirmation.

A constant threshold increase or claiming the experimental subsequence matcher “solves” the
all-rejected problem would be misleading. Natural coarticulation, speaker identity, continuous
false acceptance and useful recognition sensitivity are still unvalidated.

## Track real WATER/PAIN phrases

After fresh keyword enrollment, record independent longer phrases and negative streams. Label
only the keyword span, not the full sentence, in a manifest next to the WAVs:

```json
{
  "streams": [
    {"file": "need_water.wav", "events": [
      {"intent": "WATER", "start_s": 1.2, "end_s": 1.8}
    ]},
    {"file": "unrelated_room_speech.wav", "events": []}
  ]
}
```

These are illustrative annotations, not measured recordings. Use mono PCM16 / 16 kHz WAVs,
up to ten minutes each. Include ordinary background before/after phrases; the evaluator does
not append artificial silence to flush the final word. It reads 50 ms chunks with bounded
memory and leaves raw WAVs in their existing local directory:

```bash
python roles/speech/evaluation/evaluate_keyword_streams.py \
  --profile data/keyword_profiles/patient_001 \
  --manifest data/heldout_phrases/streams.json \
  --output results/water_pain_streams.json
```

The report includes event recall/misses, precision, false accepted events per hour, duplicate
accepts, timestamps, detection delay relative to annotated keyword end, and real-time factor.
Wrong-label/out-of-span accepted events and duplicates count as false accepts. Silent/UNKNOWN
streams have undefined recall, not a perfect accuracy score. Duplicate WAV files and truncated
PCM are rejected. Independence from enrollment cannot be verified from feature-only profiles;
use genuinely new recordings and an untouched final test set. No corpus/helper audio is sent
to a cloud service.

Keyword enrollment conservatively trims endpoints by default (180 ms padding, internal pauses
preserved), so a fixed three-second take does not become a three-second word template dominated
by silence. Use `KeywordSpotter.enroll(..., trim_endpoints=False)` for explicit manual word
boundaries when trimming is unreliable. The prepared TORGO bundle disables this second trim
because it was already endpoint-trimmed; comparison arms therefore use the same input takes.
