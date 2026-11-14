"""Generate modelled SCI scenarios from measured replay records and explicit assumptions."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from roles.speech.sci.calculate import weighted_statistics,bed_day


def analyze(replay,config):
    if not replay.get('complete'):raise ValueError('Replay is incomplete; no final SCI report allowed')
    rows=replay['records'];engines=('numpy','native')
    case_sets={e:{r['case'] for r in rows if r['engine']==e} for e in engines}
    if not case_sets['numpy'] or case_sets['numpy']!=case_sets['native']:raise ValueError('Unpaired dataset')
    n=len(case_sets['numpy'])
    if len(rows)!=n*2*replay['repetitions']:raise ValueError('Incomplete repetitions')
    measured={};quality={};scenarios=[]
    for engine in engines:
        selected=[r for r in rows if r['engine']==engine]
        voiced=[r for r in selected if r['kind']=='real_known']
        measured[engine]={field:{'median':float(np.median([r[field] for r in voiced])),
                                 'mean':float(np.mean([r[field] for r in voiced])),
                                 'p95':float(np.percentile([r[field] for r in voiced],95))}
                          for field in ('wall_s','cpu_s')}
        unique={r['case']:r for r in selected}
        known=[r for r in unique.values() if r['kind']=='real_known']
        negative=[r for r in unique.values() if r['kind']=='real_similar_word']
        noise=[r for r in unique.values() if r['kind']=='synthetic_noise']
        quality[engine]={'known_trials':len(known),'correct_accepted':sum(r['prediction']['intent']==r['expected'] for r in known),
                         'wrong_known_accepts':sum(r['prediction']['accepted'] and r['prediction']['intent']!=r['expected'] for r in known),
                         'known_rejected':sum(not r['prediction']['accepted'] for r in known),
                         'real_negative_trials':len(negative),'real_negative_false_accepts':sum(r['prediction']['accepted'] for r in negative),
                         'synthetic_noise_trials':len(noise),'synthetic_noise_rejected':sum(not r['prediction']['accepted'] for r in noise)}
        stats=weighted_statistics(rows,engine,config['workload_weights'])
        for scenario in config['scenarios']:
            for attempts in config['attempts_per_day']:
                scenarios.append({'engine':engine,**bed_day(config,scenario,stats,attempts,replay['logical_cpus'])})
    return {'unique_cases':n,'timing_repetitions':replay['repetitions'],'evidence_grade':config['evidence_grade'],'functional_unit':config['functional_unit'],
            'measured':measured,'quality_unique_recordings':quality,'modelled_scenarios':scenarios,
            'measured_median_latency_speedup':measured['numpy']['wall_s']['median']/measured['native']['wall_s']['median'],
            'measured_median_cpu_reduction_fraction':1-measured['native']['cpu_s']['median']/measured['numpy']['cpu_s']['median'],
            'warning':'Timing repeats are not independent recognition samples. Electricity, carbon, lifecycle, daily usage and common-stage costs are modelled. No power meter.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--replay',type=Path,required=True)
    p.add_argument('--assumptions',type=Path,default=Path(__file__).with_name('assumptions.json'))
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    result=analyze(json.loads(args.replay.read_text()),json.loads(args.assumptions.read_text()))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps({'speedup':result['measured_median_latency_speedup'],'quality':result['quality_unique_recordings']},indent=2))

if __name__=='__main__':main()
