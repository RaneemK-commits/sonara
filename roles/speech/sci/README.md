# Sonara SCI study

Separate `sci/measurement-and-plots` experiment. No production settings are changed.
The latest completed results and five PNG/SVG plots are in [results/REPORT.md](results/REPORT.md).

**Measured:** ARM64 recognition wall/CPU time, CPU temperature, frequency where available,
process peak RSS and idle CPU observation. **Modelled:** electricity, operational/embodied
carbon, daily use, setup costs and non-recognition stages. No power meter or energy sensors
were available. Numbers are provisional sensitivity scenarios, not a verified product footprint.

## Design

- Same full personal profile, input audio and acceptance policy in NumPy/native comparisons.
- Five timing repetitions, alternating execution order; warm-up excluded.
- Five real test words, fourteen real soundalikes and three labelled synthetic noise controls.
- Numerical score/decision parity enforced. Corpus recordings cannot duplicate enrollment hashes.
- Recognition quality counts unique recordings, never timing repetitions as extra test samples.
- No microphone capture, audible speech, SQLite mutations, caregiver messages or service restarts.
- Capture/playback/confirmation/delivery are simulated. Existing prompt WAV duration is metadata,
  not live output. Research runner overhead is outside timed recognition; retained as a limitation.
- A sensor-heavy idle probe was rejected as intrusive and is retained for audit. The short CPU-only follow-up did not produce a retrievable result, so no clean idle baseline is claimed. Idle energy remains an explicit model assumption. The collector uses an elapsed-time deadline and has optional thermal reads. Shared-board background activity,
  DVFS and thermal state are logged rather than claiming a controlled laboratory.

SCI uses one occupied bed-day, with all-day standby and reserved hardware. Three assumed daily
volumes (20/100/300 Talk attempts) and low/central/high parameter scenarios show sensitivity.
The secondary score divides by correctly recognized requests assuming successful confirmation
and delivery; energy of rejected/wrong attempts remains included. No embodied-carbon savings
are attributed to finishing inference sooner on dedicated always-reserved hardware.

## Reproduce

From repo root, with Python/NumPy and the optional native DTW library already available:

```bash
python roles/speech/sci/prepare_inputs.py \
  --known /private/session/recordings/test \
  --negative-manifest /private/recording_session/manifest.json \
  --output /private/sci_inputs
python roles/speech/sci/observe_idle.py --seconds 300 --output /private/idle.json
python roles/speech/sci/run_replay.py \
  --app-root /path/to/sonara --candidate /private/candidate \
  --library /private/libsonara_dtw.so --inputs /private/sci_inputs \
  --repetitions 5 --output /private/replay.json
python roles/speech/sci/analyze.py \
  --replay /private/replay.json --output roles/speech/sci/results/analysis.json
```

Build the native library using `roles/speech/evaluation/build_native_dtw.py` if needed.
No new package is installed on the board. Plots are generated separately on a laptop:

```bash
python -m venv /tmp/sonara-sci-plots
/tmp/sonara-sci-plots/bin/pip install -r roles/speech/sci/requirements-plot.txt
/tmp/sonara-sci-plots/bin/python roles/speech/sci/plots.py \
  --replay roles/speech/sci/results/replay.json \
  --analysis roles/speech/sci/results/analysis.json --output roles/speech/sci/results/plots
/tmp/sonara-sci-plots/bin/python roles/speech/sci/write_report.py \
  --analysis roles/speech/sci/results/analysis.json --idle roles/speech/sci/results/idle_sensor_probe_rejected.json \
  --output roles/speech/sci/results/REPORT.md
```

Inspect [assumptions.json](assumptions.json) before interpreting absolute SCI values. Values
without hardware-specific measurements/LCA are deliberately labelled scenario assumptions.
Low/high bands are not statistical confidence intervals. Full hardware days and allocated
embodied emissions remain in the baseline and optimized variants alike.

The old root `docs/SCI.md` is a historical draft containing obsolete neural comparisons; it
was not edited because this branch is scoped to speech-owned study files.
