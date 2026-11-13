"""Generate reproducible NON-SPEECH WAV fixtures. Never use these as speech accuracy evidence."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sonara.audio.wavio import write_wav

FREQUENCIES = {'WATER': (300,600), 'HELP': (900,450), 'FOOD': (700,1200),
               'PAIN': (200,1200), 'BATHROOM': (1300,250)}


def generate(root: Path, duration: float = .6) -> None:
    for split, seeds in [('enrollment', range(5)), ('test', range(10,13))]:
        for label, freqs in FREQUENCIES.items():
            for seed in seeds:
                rng = np.random.default_rng(seed)
                t = np.arange(int(16000*duration)) / 16000
                frequencies = np.array(freqs)[np.minimum(np.arange(len(t))*2//len(t),1)]
                audio = .2*np.sin(2*np.pi*frequencies*t) + .005*rng.standard_normal(len(t))
                write_wav(root/split/label/f'{seed:02d}.wav',audio.astype(np.float32),16000)
    for seed in range(3):
        noise = np.random.default_rng(100+seed).normal(0,.08,int(16000*duration)).astype(np.float32)
        write_wav(root/'test'/'_UNKNOWN'/f'{seed:02d}.wav',noise,16000)
    (root/'SYNTHETIC.txt').write_text('Non-speech tones and noise: software validation only. No clinical or human recognition claims.\n')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('output',type=Path)
    ap.add_argument('--seconds',type=float,default=.6)
    args = ap.parse_args()
    if not .3 <= args.seconds <= 5:
        ap.error('seconds must be 0.3–5')
    generate(args.output,args.seconds)
    print(f'Synthetic non-speech WAV fixtures written to {args.output}')
