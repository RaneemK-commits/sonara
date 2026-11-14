"""Make a private, explicitly labelled replay bundle; never add its WAVs to Git."""
from pathlib import Path
import argparse,hashlib,json,shutil,sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from sonara.audio.wavio import read_wav,write_wav


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--known',type=Path,required=True)
    parser.add_argument('--negative-manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    cases=[];seen=set()
    def add(audio,label,kind,identifier):
        digest=hashlib.sha256(audio.tobytes()).hexdigest()
        if digest in seen:raise ValueError('Duplicate replay source')
        seen.add(digest);name=f'{len(cases):03d}.wav'
        write_wav(args.output/name,audio,16000)
        cases.append({'id':identifier,'file':name,'expected':label,'kind':kind,'source_sha256':digest})
    for label in ('WATER','HELP','FOOD','PAIN','BATHROOM'):
        paths=sorted((args.known/label).glob('*.wav'))
        if not paths:raise ValueError(f'No independent test audio for {label}')
        for index,path in enumerate(paths):
            audio,sr=read_wav(path)
            if sr!=16000:raise ValueError('16 kHz required')
            add(audio,label,'real_known',f'{label}_{index+1}')
    for index,entry in enumerate(json.loads(args.negative_manifest.read_text())):
        if entry.get('expected')!='UNKNOWN':continue
        path=(args.negative_manifest.parent/entry['file']).resolve()
        if not path.is_relative_to(args.negative_manifest.parent.resolve()):raise ValueError('Invalid source path')
        audio,sr=read_wav(path)
        if sr!=16000:raise ValueError('16 kHz required')
        add(audio,'UNKNOWN','real_similar_word',f'negative_{index+1}')
    rng=np.random.default_rng(20261114)
    add(np.zeros(48000,np.float32),'UNKNOWN','synthetic_noise','synthetic_silence')
    add(rng.normal(0,.001,48000).astype(np.float32),'UNKNOWN','synthetic_noise','synthetic_stationary_noise')
    click=np.zeros(48000,np.float32);click[16000:16160]=rng.normal(0,.02,160)
    add(click,'UNKNOWN','synthetic_noise','synthetic_click')
    (args.output/'manifest.json').write_text(json.dumps({'cases':cases,'warning':'Real personal recordings plus explicitly synthetic noise; no simulated impaired speech.'},indent=2))
    print(f'Private replay bundle: {len(cases)} cases')

if __name__=='__main__':main()
