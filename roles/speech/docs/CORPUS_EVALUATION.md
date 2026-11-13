# German corpus diagnostic — 2026-11-13

Executed with [B-Czarnetzki/dysarthric_german](https://huggingface.co/datasets/B-Czarnetzki/dysarthric_german),
pinned to revision `f7af95b7d3a71164499592411e31c4bb019acdfe`.
The publisher labels the corpus as dysarthric German. Its dataset card does not document
speaker identity, clinical provenance, or a license. This run is a local software diagnostic,
not validation of the corpus's clinical claims or of Sonara's patient recognition accuracy.
Raw corpus audio is kept under ignored `data/evaluation/`, not committed in this repository.

## Suitability audit

The published train/test splits contain 1,147/125 recordings, totaling 1,272. Projecting only
Parquet text/path columns found **1,270 distinct normalized transcripts**: 1,268 occur once,
two occur twice, and none occur three times. The schema contains only `path`, `audio`, `text`.
There is no speaker ID. Therefore this corpus cannot supply five independent enrollment takes
and three held-out examples of the same phrase from a documented speaker.

The original dataset is approximately 727 MB. Hugging Face streaming, column projection and
Parquet filters were used on the laptop. Only selected raw recordings were retained (about
46 MiB total local working data including the exported bundle at preparation time). No Torch,
TorchCodec, pretrained recognition weights or new recognition runtime was required. Optional
laptop tools were Datasets 5.2.0, SoundFile 0.14.0, SciPy 1.18.1 and PyArrow 26.0.1.

## Protocol

1. Audit transcripts before matching. Keep the upstream revision and official split identities.
2. Consider the 64 shortest training transcripts, ordered by length then source path.
3. Remove DC and conservatively trim endpoint silence with Sonara's energy trimmer. Preserve
   internal pauses. Reject any reference whose complete trimmed vocalization exceeds five seconds.
4. Four candidates met the duration/quality requirements. Use **one take per distinct phrase**,
   with evaluation-only labels `PHRASE_01`–`PHRASE_04`. These are not mapped to WATER/HELP/etc.
5. Calibrate solely on these references. With no repeated positives, the production classifier
   correctly reports `requires_more_recordings` and uses conservative sparse-data thresholds.
6. Select the first 40 official test rows, without consulting matching scores. All 40 trimmed
   vocalizations exceed five seconds, so take **one labeled five-second UNKNOWN window per source**.
   These are excerpts, not 40 complete short utterances.
7. Verify source/PCM/WAV hashes, prevent source reuse between enrollment and test, and keep all
   profile writes inside a temporary evaluation directory. No live controller is invoked.
8. Replay each reference only as an enrollment self-match sanity check. Report independent
   known-intent accuracy as **null**, rather than counting those replays as test accuracy.

Complete reference spans after endpoint trimming:

| Evaluation label | Source file | Duration |
|---|---|---:|
| PHRASE_01 | dysarthric_speech_280.wav | 4.589 s |
| PHRASE_02 | dysarthric_speech_326.wav | 3.701 s |
| PHRASE_03 | dysarthric_speech_356.wav | 3.320 s |
| PHRASE_04 | dysarthric_speech_1267.wav | 4.893 s |

The 44-file portable bundle plus its manifest occupies **6,958,056 bytes**. It was streamed
from the laptop over SSH to `/tmp/sonara-mfcc-validation/real-corpus/bundle` on the owner's UNO Q.
Only standard PCM WAVs, the manifest and the NumPy-only evaluator were needed on the board.
The other agent's `~/sonara` checkout, port 8000 service and patient profiles were untouched.
This is digital WAV testing, rather than acoustic playback into the attached microphone.

## Observed results

| Measurement | Laptop, x86-64 | UNO Q, ARM64 |
|---|---:|---:|
| Valid UNKNOWN inputs | 40 | 40 |
| Invalid inputs | 0 | 0 |
| False acceptances observed | 0/40 | 0/40 |
| Rejected as UNKNOWN | 40/40 | 40/40 |
| Mean processing time | 83.3 ms | 1191.7 ms |
| p95 processing time | 86.7 ms | 1422.3 ms |
| Maximum processing time | 90.5 ms | 1434.2 ms |
| Peak evaluator process RSS | 52.4 MiB | 43.1 MiB |
| Template storage | 0.245 MiB | 0.245 MiB |

Both machines matched all four enrollment recordings to themselves. That is an expected
self-match check, not four correct held-out predictions. Every independent query in this
protocol is UNKNOWN. An always-rejecting classifier would also reject them all, so these results
cannot establish useful true-acceptance behavior or a reliable false-acceptance rate.

Timing excludes download, resampling, endpoint adaptation and SSH transport. It includes the
production recognizer's validation, MFCC extraction, DTW and rejection on prepared five-second
inputs. The board was shared with ongoing device development; timings are observations, not
controlled hardware guarantees. This run **does not meet the 500 ms target on these long inputs**.
No thresholds or feature settings were tuned using the test recordings. No caregiver requests
were created, and the running patient's voice profile was not replaced.

The source remains the same MFCC + DTW implementation previously covered by the regression suite.
New automated tests check complete-reference preservation, long UNKNOWN window labeling,
internal-pause preservation, source/hash leakage rejection and bundle path/checksum validation.
The expanded suite passed **53/53 on the laptop (5.40 s)** and **53/53 on the UNO Q (35.56 s)**.
The board emitted the existing upstream Starlette/httpx test-client deprecation warning.

Machine-readable reports:

- [Laptop real-corpus report](validation/dysarthric_german_laptop.json)
- [UNO Q real-corpus report](validation/dysarthric_german_board.json)

The local, ignored preparation directory contains the revision metadata, transcript audit,
source audio cache and portable `bundle/manifest.json`, including source IDs and segment bounds.

## Reproduce on the laptop

```bash
pip install -e '.[corpus-eval]'
python roles/speech/evaluation/prepare_real_corpus.py --output data/evaluation/dysarthric_german --queries 40
python roles/speech/evaluation/evaluate_real_corpus.py data/evaluation/dysarthric_german/bundle \
  --output results/dysarthric_german_laptop.json
pytest -q
```

On the board, use its isolated NumPy environment with the same bundle:

```bash
cd /tmp/sonara-mfcc-validation/source
PYTHONPATH=/tmp/sonara-mfcc-validation/deps python3 roles/speech/evaluation/evaluate_real_corpus.py \
  /tmp/sonara-mfcc-validation/real-corpus/bundle \
  --output /tmp/sonara-mfcc-validation/dysarthric_german_board.json
```

For personalized recognition accuracy, collect repeated natural pronunciations from a known
speaker with separate enrollment, held-out known phrases and UNKNOWN recordings, then use
`scripts/evaluate.py`. This corpus is useful for input handling, rejection stress checks and
real-audio timing, but does not replace that collection.
