# Personalized acoustic recognition

The production recognizer uses a single NumPy MFCC frontend and personal DTW templates.
The original project requirements remain in [PDR_v1.0.md](../../../docs/PDR_v1.0.md).

## Features

At 16 kHz, apply optional pre-emphasis (0.97), 400-sample Hamming windows and 160-sample hops.
Include the last partial window with zero padding. A 512-point RFFT supplies power spectra,
40 triangular Mel bands cover 20–8000 Hz, and floored log energies feed an orthonormal DCT-II.
Keep 13 coefficients, then concatenate regression deltas and delta-deltas using edge replication
(width 2). Default per-sequence CMVN uses a 0.01 standard-deviation floor to avoid amplifying
constant dimensions. Output is `(T, 39)` float32. Mean-only and no normalization are configurable;
a profile carries its exact feature configuration so enrollment and inference stay compatible.

DC removal and recording-quality checks precede MFCCs. Quiet continuous vocalizations are
preserved by capping the offline energy threshold relative to peak frame energy; endpoint
trimming never removes internal pauses. Streaming VAD remains a simple energy heuristic, not a
speech/noise discriminator. Fixed capture boundaries are available in both onboarding and Talk.

## DTW

Local distance is root mean square Euclidean distance across feature dimensions. The recurrence
chooses minimum accumulated diagonal, vertical or horizontal cost. A Sakoe–Chiba band has width
`max(abs(N-M), ceil(band * max(N,M)))`; zero is meaningful and `None` disables the band.
Normalize the final accumulated cost by the selected path's actual number of visited cells.
This is the minimum-total-cost path followed by normalization, not a minimum-average-cost solver.

Two reusable rolling cost/length rows bound workspace. Horizontal propagation within a row is implemented
with NumPy cumulative sums/minima and predecessor-origin indices, removing the Python inner
cell loop while retaining path lengths. Local distances are computed only inside the band.
The implementation reuses row/index buffers and computes squared norms with einsum to reduce
small-array allocation overhead. Inputs are limited to 600 frames and 128 dimensions; 5-second default MFCC uses 499 × 39.
This implementation is checked against a simple cell-by-cell reference for multiple lengths/bands.
There is no optional JIT/compiler dependency or approximate nearest-neighbor search.

## Templates and rejection

Compare against each enrolled template and average the two smallest distances per intent.
Acceptance requires a finite positive absolute threshold and a sufficient best/runner-up gap.
No profile returns UNKNOWN. Invalid recordings and corrupt selected profiles fail closed.
A one-intent profile uses its absolute threshold but cannot estimate ambiguity against missing
classes; enrollment diagnostics explicitly request more data. The touchscreen requires five
samples per request intent before its Finish control is enabled; the CLI/API permit partial
profiles for development and report incomplete calibration.

LOO calibration excludes the query template, uses aggregated own-class distances as positives,
and treats each other-class aggregated distance as a negative. Additional independent UNKNOWN
calibration examples may be supplied by evaluation tooling. The per-intent limit is the minimum
of the global fallback, 1.15 × positive p90, and 0.8 × negative p10 (with sparse-data fallbacks).
The margin is deliberately fixed instead of fitted to tiny samples. Poor separation and fewer
than three positives/negatives report insufficient quality. Even good separation in enrollment
does not establish a real false-acceptance rate; collect new human recordings to measure it.

Profiles store features in an NPZ without pickle and versioned JSON with configuration, counts,
matching/calibration settings, timestamps and a SHA-256. Metadata commits last. A loader rejects
mixed or partial generations, invalid shapes, oversized archives and invalid thresholds. It never
accepts a missing/zero threshold as infinity. The recognizer atomically swaps an in-memory profile
under a lock and monitors metadata/archive timestamps. Per-profile storage isolates patients.
A crash between NPZ/metadata replacement can require re-enrollment; the loader rejects that
profile rather than using inconsistent data. This small MVP does not implement multi-process
profile writers; stop the server before CLI enrollment into the same profile.

## Integration

The controller retains IDLE → LISTENING → PROCESSING → AWAIT_CONFIRM. UNKNOWN asks to repeat.
Accepted request phrases play locally, then await Send/voice YES. Requests still cannot dispatch
without confirmation. Queued physical/screen confirmation is associated with the pending
interaction so early or stale presses cannot send a different future result. Existing SQLite,
caregiver receipt, acknowledgment, completion, cancellation, timeout and hardware logic remain.

The controller and enrollment service share a microphone lock. An enrollment session pauses
normal recognition until closed/finished. The server uses synchronous FastAPI route functions
for blocking audio/matching operations, which run in its threadpool, keeping WebSockets and the
event loop responsive. A persistent `arecord` subprocess can supply the same queue on Debian images without PortAudio;
`alsa:` device names select this path explicitly, with no intermediate audio files. Its startup
and shutdown are bounded. The microphone queue is bounded to ten seconds and controller actions
to 32 entries. Busy profile/capture operations respond 409; missing mic responds 503 and leaves
manual phrase tiles available. Capture timeout errors are handled without dispatching requests.

The room UI uses server-side capture, stages one take in memory, reports quality, and saves only
after Keep. Saving recalibrates the draft. Test runs against the draft without adding a template
or invoking the controller. Default persistence contains no audio. Retention is explicit and local.
Profile finish loads it into the running recognizer and remembers the selection. Deleting a
profile removes its templates and retained audio. The existing caregiver token protects caregiver
writes; room/profile APIs retain the existing trusted-LAN room access model.
