# More speech samples, composed sentences and noise

This experiment implements the requested stress test: concatenate complete recordings from
one speaker, insert a held-out target among unrelated speech, add noise between the parts and
over speech, then try to recognize only the target span from a continuing stream.

## Prepared data

- Pinned TORGO revision and the original independent enrollment/test take split are preserved;
  see [TORGO evaluation](TORGO_EVALUATION.md). Original files/manifests are not overwritten.
- Downloaded **36 additional recordings**, twelve for each completed-profile speaker F03, M02,
  M03. The expanded cache contains 173 distinct source recordings. HeadMic only; alternative
  microphone channels of the same take are never treated as independent samples.
- Additional filler sources are selected by deterministic filename hash, exclude every original
  enrollment/test take, and exclude transcripts containing an enrolled keyword. No acoustic
  matching score affects selection. Complete 0.3–5 s recordings are used, rather than the
  earlier half-second context crops.
- The same two enrollment takes per keyword remain unchanged. M01/M05 retain their original
  clipping-related enrollment failures. More unrelated context cannot manufacture additional
  independent positive word recordings.
- Built **115 annotated streams**, **17.72 minutes** total, longest 15.56 s. Target position
  rotates among three unrelated recordings; gaps vary deterministically from 120–350 ms, and
  one second of trailing room/noise context allows streaming look-ahead.
- Repeated-target streams test tracking of two occurrences. They reuse one take intentionally,
  so those occurrences are not new independent positives. There are **22 independent target
  recordings** across all noise variants and repetitions.
- Each base composition has clean, gap-noise-only, 20 dB background-SNR and 10 dB background-SNR
  variants. Separate target-free speech and noise-only streams test false acceptance. The
  synthetic ambient noise combines hiss, correlated noise and 50 Hz hum, with extra gap bursts.
  No voice is synthesized or modified to imitate a disability.
- SNR is measured over source-recording spans (including their endpoint padding), and stored
  per stream. A common gain on signal plus noise avoids introducing clipping while preserving
  SNR. This does not repair clipping already present in a source.
- Every stream includes source transcripts, exact target/sample timestamps, noise seed/settings
  and a WAV checksum. These are artificial sentence-like compositions with splice boundaries,
  not natural coarticulated sentences. Words remain YES/NO/SIP/SIGH/LEAK; none are relabeled
  WATER/PAIN. The targets have already appeared in development evaluation, so this is not a
  fresh final accuracy test. Noise variants are not independent human recordings.

## Replay and listening

All WAVs and the player stay in ignored `data/evaluation/torgo_noisy/`, about 51 MiB locally.
No audio is committed or publicly redistributed. The [original dataset use conditions](TORGO_EVALUATION.md)
still apply. Preparation needs the optional laptop HF/PyArrow/SoundFile/SciPy packages; replay
uses the existing offline NumPy keyword implementation. No microphone or live app is accessed.

```bash
python roles/speech/evaluation/noisy_streams.py prepare
python roles/speech/evaluation/noisy_streams.py evaluate \
  --output roles/speech/docs/validation/noisy_streams_laptop.json
python -m pytest -q tests roles/speech/integration/test_integrated_recognition.py
```

Open `data/evaluation/torgo_noisy/preview.html` locally to hear clean/noisy versions side by side;
brackets mark target transcripts. All 36 audio links were checked against existing files.
Source cache is `bundle/`, feature-only experimental profiles are `profiles/`, composed WAVs
are `streams/` and complete annotations are `streams.json`. Production profiles stay separate.

Replay feeds 50 ms chunks through the five-second rolling detector; it does not classify the
entire long stream as one word. Events count as correct only for the correct label with
interval-over-union >=0.3. Duplicates, wrong labels and accepted spans outside the targets count
as false accepts. The summary groups by noise condition and reports accepted recall, false
accepts per hour and real-time factor. Nearest-label localization before rejection is a
separate diagnostic, never accepted recognition accuracy. All thresholds stay unchanged.

## Verification and limits

121 tests pass locally, including deterministic source selection, target sample preservation,
exact annotation timing, reproducible SNR, noise mixing without clipping and existing device
integration regressions. This expanded noisy replay runs on the laptop; it is not a new UNO Q
benchmark. The previous board streaming real-time factor was 3.44 in its shared-board setup;
see [keyword-in-phrase limits](KEYWORDS_IN_PHRASES.md). Nothing enables this path live.

## Actual laptop results

All 115 streams were replayed with unchanged profiles/thresholds. Each non-noise-only condition
contains 25 target-bearing streams (28 target occurrences, including repeated-take stress tests)
and three target-free speech streams. The noise-only condition has three additional negatives.

| Condition | Target occurrences | Correct accepted events | Occurrences with a correct-label overlapping proposal before rejection |
|---|---:|---:|---:|
| Clean | 28 | 0 | 18 |
| Noise in gaps only | 28 | 0 | 17 |
| Background, 20 dB SNR | 28 | 0 | 18 |
| Background, 10 dB SNR | 28 | 0 | 17 |

No accepted events occurred, including on negatives. Therefore accepted recall is **0%**, and
precision among accepted events is undefined. Zero false accepts is not a useful rejection or
speaker-identity result when every real target is rejected too. The last column counts whether
ANY of the repeated-window proposals has the correct label and overlaps the target; it can
coexist with many wrong proposals and must not be called recognition accuracy.

The clean condition fails too, so noise is not the sole reason for the failed recognition.
Calibration/positive sensitivity and distinctive personal templates remain blockers. Increasing
a global threshold based on these test outcomes would contaminate evaluation and could cause
false accepts; this run does not change the production recognizer.

Laptop streaming real-time factor was approximately 0.24–0.26, peak process RSS 61.4 MiB.
These are laptop replay results, not a claim that the UNO Q can keep up. Full metrics, composed-stream
checksums, target annotations and measured noise settings are in
[validation/noisy_streams_laptop.json](validation/noisy_streams_laptop.json).
