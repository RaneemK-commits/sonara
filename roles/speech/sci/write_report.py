"""Create a concise report with measured/modelled evidence kept separate."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import numpy as np


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--analysis',type=Path,required=True)
    p.add_argument('--idle',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();a=json.loads(args.analysis.read_text());idle=json.loads(args.idle.read_text())
    m=a['measured'];scenarios=a['modelled_scenarios']
    central={e:next(r for r in scenarios if r['engine']==e and r['scenario']=='central' and r['attempts_per_day']==100) for e in ('numpy','native')}
    baseline=central['numpy']['sci_g_per_bed_day'];optimized=central['native']['sci_g_per_bed_day']
    low=next(r['sci_g_per_bed_day'] for r in scenarios if r['engine']=='native' and r['scenario']=='low' and r['attempts_per_day']==100)
    high=next(r['sci_g_per_bed_day'] for r in scenarios if r['engine']=='native' and r['scenario']=='high' and r['attempts_per_day']==100)
    q=a['quality_unique_recordings']['native']
    elapsed=np.array([s['elapsed_s'] for s in idle['samples']])
    cpu_idle=np.average([s['system_cpu_fraction'] for s in idle['samples']],weights=np.diff(np.r_[0,elapsed]))*100
    if 'requested_seconds' in idle:
        idle_note=f"The CPU-only observation collected {len(idle['samples'])} samples over {elapsed[-1]:.1f} s; time-weighted CPU use was {cpu_idle:.2f}% of total capacity."
    else:
        idle_note=f"The sensor-heavy diagnostic collected {len(idle['samples'])} samples over {elapsed[-1]:.1f} s. It overran and was not accepted as a clean idle baseline. The short CPU-only follow-up did not yield a retrievable result; no clean idle CPU baseline is claimed."
    text=f'''# Sonara: less computation, transparent carbon accounting

**Measured on Arduino UNO Q · Germany · no power meter**

## What changed

Native C DTW performs the same personalized matching as the NumPy baseline. The reference
features, speech/noise checks, distance threshold and intent margins are identical. This study
replays recordings in an isolated process; it does not change the live app, use the microphone,
play audio or create caregiver requests.

## Measured results

| Metric, known-word replay | NumPy | Native |
|---|---:|---:|
| Median processing latency | {m['numpy']['wall_s']['median']*1000:.1f} ms | {m['native']['wall_s']['median']*1000:.1f} ms |
| 95th-percentile latency | {m['numpy']['wall_s']['p95']*1000:.1f} ms | {m['native']['wall_s']['p95']*1000:.1f} ms |
| Median process CPU time | {m['numpy']['cpu_s']['median']:.3f} s | {m['native']['cpu_s']['median']:.3f} s |

**{a['measured_median_latency_speedup']:.2f}× median speedup; {a['measured_median_cpu_reduction_fraction']*100:.1f}% less median CPU time.**
{a['timing_repetitions']} repetitions alternate engine order. The corpus contains {q['known_trials']} real known-word tests,
{q['real_negative_trials']} real similar-word negatives and {q['synthetic_noise_trials']} explicitly synthetic noise controls. Repetitions
are timing samples, not additional independent speech recordings. All paired decisions and raw
matching scores passed the replay's numerical-equivalence check (tolerance 1e-9).

{idle_note}
The initial sensor trace is retained as `idle_sensor_probe_rejected.json` for audit. It is not
used to calibrate power. The supplied collector now has an elapsed-time deadline and optional
thermals. Only temperature sensors were found in the checked standard interfaces; no exposed
board power/energy telemetry was used.
CPU activity is not electricity consumption.

## Modelled SCI results

Functional unit: **one occupied bed-day**, including 24-hour hardware reservation and standby.
SCI = (energy × grid intensity + allocated embodied emissions) / functional unit.

At an **assumed 100 Talk attempts/day**, the central scenario estimates:

| Scenario calculation | NumPy | Native |
|---|---:|---:|
| SCI, gCO₂e per occupied bed-day | {baseline:.3f} | {optimized:.3f} |
| Modelled energy, kWh per bed-day | {central['numpy']['estimated_energy_kwh']:.6f} | {central['native']['estimated_energy_kwh']:.6f} |
| Recognition-increment emissions per attempt | {central['numpy']['matching_increment_g_per_attempt']:.6f} g | {central['native']['matching_increment_g_per_attempt']:.6f} g |

The whole-day difference is **{baseline-optimized:.4f} gCO₂e/day ({(baseline-optimized)/baseline*100:.3f}%)**
under the central assumptions. The native low/high scenario range is **{low:.1f}–{high:.1f} gCO₂e/day**.
These are sensitivity scenarios, **not measured emissions or confidence intervals**.

The important result: reducing recognition CPU work does not remove the display, standby power
or manufacturing footprint. A large inference speedup can produce a much smaller estimated
whole-system carbon reduction. Do not present the speedup as an equal reduction in total carbon.

## Quality and limits

On unique real known-word tests: **{q['correct_accepted']}/{q['known_trials']} correct accepted**,
{q['wrong_known_accepts']} wrong accepted and {q['known_rejected']} rejected. Real soundalike false
accepts: **{q['real_negative_false_accepts']}/{q['real_negative_trials']}**. Synthetic noise rejected:
{q['synthetic_noise_rejected']}/{q['synthetic_noise_trials']}. Native and NumPy behavior match.
This small personal development set is not clinical validation or general recognition accuracy.
Physical confirmation remains necessary.

Electricity is estimated from a linear CPU-work power model, not measured. Capture, playback,
confirmation and delivery are simulated. Prompt durations use existing WAV metadata; their CPU
costs, daily workload, device lifespan, resource shares and embodied footprints are assumptions.
The secondary per-correct-request score assumes successful confirmation and delivery; wrong
accepted predictions do not count as productive requests, but their energy remains included.

Boundary: board, 7-inch MPI7010 display, mic/speaker/hub/buttons, allocated router and caregiver
phone, plus amortized local setup. Dedicated devices get full daily allocation; router share is
1/20, phone reservation 30 minutes/day. Research/development runs and remote initial-download
infrastructure are excluded, not claimed zero. Carbon accounting is provisional and model-based.
No offsets or avoided nurse journeys are credited.

## Plots

![Measured recognition latency](plots/01_latency.png)
![Measured CPU work](plots/02_cpu_work.png)
![Modelled daily footprint](plots/03_daily_footprint.png)
![Modelled SCI sensitivity](plots/04_sci_sensitivity.png)
![Recognition confusion](plots/05_confusion.png)

SVG versions are supplied alongside PNGs for slides and editing.

## Sources and reproducibility

- [SCI specification](https://sci.greensoftware.foundation/): boundary, functional unit and embodied allocation.
- [UBA 2026 report](https://www.umweltbundesamt.de/system/files/medien/11850/publikationen/2026-03/16_2026_CC.pdf): 406 gCO₂e/kWh, estimated German 2025 mix including upstream emissions.
- [Arduino published range](https://store.arduino.cc/collections/single-board-computers): power context only; assigning idle/full endpoints is an assumption.
- [MPI7010 manufacturer information](https://www.lcdwiki.com/7inch_HDMI_Display-D): display identity, not an LCA.
- [Raspberry Pi reports](https://investors.raspberrypi.com/reports) and [Apple product report](https://www.apple.com/environment/pdf/products/iphone/iPhone_15_and_iPhone_15_Plus_PER_Sept2023.pdf): explicitly labelled proxy context, not identification or footprints of Sonara's actual hardware.

See [assumptions](../assumptions.json), [study commands](../README.md), raw replay/idle JSON and
calculated scenario JSON in this directory. Private WAVs and voice templates are excluded from Git.
'''
    args.output.write_text(text)

if __name__=='__main__':main()
