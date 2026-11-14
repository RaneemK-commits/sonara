"""Paired offline replay: no microphone, sound output, controller or request delivery."""
from __future__ import annotations
import argparse,hashlib,json,os,platform,sys,time,wave
from pathlib import Path
import numpy as np


def temperature():
    for p in Path('/sys/class/hwmon').glob('hwmon*'):
        try:
            if (p/'name').read_text().strip()=='cpuss0_thermal':return float((p/'temp1_input').read_text())/1000
        except (OSError,ValueError):pass
    return None


def clock():
    values=[]
    for p in Path('/sys/devices/system/cpu').glob('cpu[0-9]*/cpufreq/scaling_cur_freq'):
        try:values.append(float(p.read_text()))
        except (OSError,ValueError):pass
    return float(np.mean(values)) if values else None


def prompt_seconds(directory,key):
    try:
        with wave.open(str(directory/f'{key}.wav'),'rb') as f:return f.getnframes()/f.getframerate()
    except (OSError,wave.Error):return None


def checkpoint(path,report):
    temporary=path.with_suffix('.partial.json')
    temporary.write_text(json.dumps(report,indent=2))
    temporary.replace(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-root',type=Path,required=True)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--library',type=Path,required=True)
    parser.add_argument('--inputs',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--repetitions',type=int,default=5)
    args=parser.parse_args()
    if not 1<=args.repetitions<=20:parser.error('repetitions must be 1–20')
    sys.path.insert(0,str(args.app_root))
    from sonara.models.personal import PersonalWordCandidate
    from sonara.models.native_dtw import NativeDTW
    from sonara.audio.wavio import read_wav
    models={name:PersonalWordCandidate.load(args.candidate) for name in ('numpy','native')}
    models['numpy']._native=None;models['native']._native=NativeDTW(str(args.library))
    cases=json.loads((args.inputs/'manifest.json').read_text())['cases']
    audios={}
    for case in cases:
        if case['kind'].startswith('real') and case['source_sha256'] in models['native'].families:
            raise ValueError('Replay audio duplicates an enrollment source')
        p=(args.inputs/case['file']).resolve()
        if not p.is_relative_to(args.inputs.resolve()):raise ValueError('Invalid replay path')
        audio,sr=read_wav(p)
        if sr!=16000:raise ValueError('16 kHz required')
        audios[case['id']]=audio
    report={'complete':False,'machine':platform.machine(),'python':platform.python_version(),
            'logical_cpus':os.cpu_count(),
            'numpy_version':np.__version__,
            'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'native_library_sha256':hashlib.sha256(args.library.read_bytes()).hexdigest(),'profile_sha256':hashlib.sha256((args.candidate/'candidate.json').read_bytes()).hexdigest(),
            'policy':{'threshold':.75,'global_margin':0,'intent_margins':models['native'].intent_margins,
                      'speech_gate':models['native'].speech_gate,'min_rms':models['native'].min_rms},
            'scope':'Measured MFCC+DTW only. Capture/playback durations simulated; no live requests or audible output.',
            'repetitions':args.repetitions,'records':[]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    for model in models.values():model.predict(audios[cases[0]['id']],threshold=.75,required_margin=0)
    for repetition in range(args.repetitions):
        for index,case in enumerate(cases):
            order=('numpy','native') if (repetition+index)%2==0 else ('native','numpy')
            pair={}
            for engine in order:
                audio=audios[case['id']];cpu=time.process_time();start=time.perf_counter()
                result=models[engine].predict(audio,threshold=.75,required_margin=0)
                elapsed=time.perf_counter()-start;cpu_used=time.process_time()-cpu
                output=result.intent if result.accepted else 'didnt_understand'
                playback=prompt_seconds(args.app_root/'assets/tts',output)
                confirmation=prompt_seconds(args.app_root/'assets/tts','ask_send') if result.accepted else 0.
                if playback is None or confirmation is None:
                    raise ValueError('Missing Piper WAV metadata; do not model missing playback as zero')
                row={'case':case['id'],'kind':case['kind'],'expected':case['expected'],'repetition':repetition,
                     'engine':engine,'wall_s':elapsed,'cpu_s':cpu_used,'temperature_c':temperature(),
                     'frequency_khz':clock(),'virtual_capture_s':len(audio)/16000,
                     'simulated_prompt_s':playback,'simulated_confirmation_prompt_s':confirmation,'prediction':result.to_dict()}
                report['records'].append(row);pair[engine]=result
                print(f'{repetition+1}/{args.repetitions} {case["id"]} {engine}: {elapsed*1000:.1f} ms accepted={result.accepted}',flush=True)
            a,b=pair['numpy'],pair['native']
            if a.intent!=b.intent or a.best!=b.best or a.scores.keys()!=b.scores.keys():raise ValueError('Decision parity failure')
            if any(abs(a.scores[k]-b.scores[k])>1e-9 for k in a.scores):raise ValueError('Numerical parity failure')
            checkpoint(args.output,report)
            time.sleep(.1)
    report['complete']=True
    report['peak_rss_mib']=None
    try:
        if not sys.platform.startswith('linux'):raise ImportError
        import resource
        report['peak_rss_mib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    except ImportError:pass
    checkpoint(args.output,report)
    print('Replay complete; all paired decisions and raw scores match',flush=True)

if __name__=='__main__':main()
