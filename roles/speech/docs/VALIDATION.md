# Executed validation — 2026-11-13

Initial development had no user enrollment/test recordings. The results below therefore use
synthetic signals and ambient device-microphone checks. A later public German corpus run now
also covers real-audio rejection and timing; see [CORPUS_EVALUATION.md](CORPUS_EVALUATION.md).
**There is still no measured held-out personalized human/patient recognition accuracy or clinical
validation.** The public corpus lacks sufficient repeated phrases and speaker identity.

## Automated checks

- Desktop: **50 passed** in **5.35 s**; Python 3.14.4, NumPy 2.5.4, x86-64 Linux.
- Owner's Arduino UNO Q: **50 passed** in **22.67 s**; Python 3.13.5, NumPy 2.2.6, ARM64 Linux.
- One upstream warning: Starlette deprecates its httpx-based test-client transport. No failing tests.
- Original caregiver/controller tests remain, including receipt → acknowledgment → completion,
  honest delivery timeout, cancellation and mandatory confirmation.
- Added numerical MFCC tests, 20 reference DTW length/band combinations, invalid/silent/clipped
  audio, unknown/ambiguous rejection, zero thresholds, sparse calibration, versioned persistence,
  corruption, profile isolation/reload, device capture bounds, enrollment APIs, microphone
  exclusion, safe missing-mic behavior, retained TTS playback and early/stale confirmations.
- Real browser check: all five request intents enrolled with five synthetic-device takes each,
  draft recognition tested, profile finished/activated, zero caregiver requests and no JavaScript
  runtime errors. The browser microphone was never used. A missing favicon produced a benign 404.

## Processing benchmarks

Capture and TTS are excluded; each recognition includes validation/trimming, MFCC and matching.
Each profile contains five intents × five templates; DTW band is 0.2. These are synthetic fixtures.

| Hardware | Clip duration | Runs | Mean | p95 | Peak process RSS | Template memory |
|---|---:|---:|---:|---:|---:|---:|
| x86-64 desktop | 0.6 s | 30 | 35.6 ms | 36.0 ms | 46.1 MiB | 0.219 MiB |
| x86-64 desktop | 5.0 s | 10 | 506.0 ms | 521.6 ms | 51.4 MiB | 1.856 MiB |
| Arduino UNO Q | 0.6 s | 30 | 298.1 ms | 351.2 ms | 37.3 MiB | 0.219 MiB |
| Arduino UNO Q | 5.0 s | 10 | 4143.3 ms | 4306.2 ms | 43.0 MiB | 1.856 MiB |

The board's kernel reports `7.0.0-g122c2c22d838`, architecture `aarch64`; RAM is 3667 MiB.
CPU governor was `schedutil`, sampled CPU frequency 2,016,000 kHz and thermal-zone-0 value 44.5°C.
These are contextual samples rather than controlled power/thermal measurements. No energy was
measured. The initial 542 ms short-clip result overlapped the test suite and is excluded from
the final benchmark table. The final short run was isolated from test/evaluation workloads.

**The <500 ms target is met for the tested short fixture, not the full 0.3–5 second range.**
Long sequences still need optimization or a validated lower temporal resolution before making
any universal low-latency claim. The five-second synthetic profile also correctly reports
insufficient calibration quality and rejects its held-out WATER fixture under conservative limits.

## Held-out synthetic WAV evaluation

Fixture generation uses independent deterministic seeds for five enrollment WAVs and three
held-out WAVs per intent, plus three noise WAVs in test/_UNKNOWN. Decoded-audio hashes detect
reused recordings. No held-out sample enters calibration.

Both the desktop and board runs identified **15/15 held-out known tone sequences** and rejected
**3/3 noise clips**, with no wrong-known acceptances, for enrollment counts 3/5 and DTW bands
0.1/0.2/0.35. The data are simple artificial frequency sequences, not conventional or impaired
speech. These small counts establish software behavior only; they do not establish speech
accuracy or rejection reliability. The full confusion matrices, manifests, calibration details,
latency distributions and memory measurements are in the reports below.

## Hardware audio

The board has no system pip, Sonara Python dependencies or PortAudio library. Testing installed
ARM64 wheels into `/tmp/sonara-mfcc-validation/deps`, leaving system packages and existing
Arduino apps unchanged. The production ALSA adapter uses the installed `arecord` utility and
`device = "alsa:plughw:CARD=Set,DEV=0"` for the attached USB headset capture device.

A one-second real capture returned exactly **16,000 finite float32 samples**, peak 0.02057 and
RMS 0.00493; startup + capture + close took 1343 ms. Audio remained in memory and was discarded.
Recognition with an empty profile returned UNKNOWN. This verifies audio capture, not speech
recognition. Piper 1.8.0 generated all **16 fixed prompt WAVs** on the desktop (8.1 s total synthesis).
The prompts were copied to the board; `aplay` successfully played the 0.64-second Listening
prompt and its SHA-256 matched the source. Recognition still needs no ONNX runtime; the board
plays these files through ALSA. A person at the board must still verify acoustic intelligibility
and MCU controls/LEDs.

The actual board server also passed an HTTP smoke test: manual device capture, Keep/persist,
draft Test, and deletion of a temporary profile. A health request completed in **112 ms** while
the capture was in progress. No caregiver requests were created, and no raw audio was saved.
Ambient sound was used, with no claim that it represented WATER or any other spoken intent.
The temporary server uses a separate empty profile store from synthetic benchmarks and listens
on `http://192.168.1.242:8012/room` while its validation process is running.

## Reproduce and inspect

```bash
pytest -q
python roles/speech/evaluation/synthetic_dataset.py /tmp/sonara-fixtures
python scripts/evaluate.py /tmp/sonara-fixtures --synthetic --enroll-counts 3 5 --bands 0.1 0.2 0.35
python scripts/enroll.py --profile synthetic_test --from-dir /tmp/sonara-fixtures/enrollment
python scripts/benchmark.py --profile synthetic_test --wav /tmp/sonara-fixtures/test/WATER/10.wav --synthetic
```

Use a separate profile directory/configuration for fixtures. Do not activate synthetic profiles
for patient operation. On the board, the validation checkout is
`/tmp/sonara-mfcc-validation/source`; these temporary files disappear on reboot. The owner-provided
mDNS hostname changed from `OhmNoobsBoard-2.local` to `OhmNoobsBoard-3.local` during testing;
the verified LAN address was `192.168.1.242`.

Machine-readable reports:

- [UNO Q short processing benchmark](validation/uno_q_benchmark_short.json)
- [UNO Q long processing benchmark](validation/uno_q_benchmark_long.json)
- [UNO Q held-out synthetic evaluation and ablations](validation/uno_q_evaluation.json)
- [Piper prompt durations and voice/prompt checksums](validation/piper_prompts.json)
- [UNO Q microphone check](validation/uno_q_microphone.json)
- [UNO Q live HTTP/device-capture smoke test](validation/uno_q_live_api.json)
- [Desktop short benchmark](validation/desktop_benchmark_short.json)
- [Desktop long benchmark](validation/desktop_benchmark_long.json)
- [Desktop synthetic evaluation](validation/desktop_evaluation.json) (baseline before the allocation
  optimization; final mathematical results are unchanged, and final timing is in the benchmark reports)

## Remaining work requiring real data or hardware observation

Record each user's natural vocalization five times per intent, then collect at least three
independent held-out takes and unrelated speech/noise. Measure false accepts and rejects in the
actual bedside environment. Re-enroll confusing intents; enrollment diagnostics are not a safety
guarantee. Verify speaker output, MCU buttons/LEDs and the complete patient/caregiver interaction
with people at the board. Maintain the physical nurse-call fallback. Test the deployment after
reboot using persistent storage, since the validation directory deliberately uses /tmp.
