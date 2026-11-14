"""Unit-tested SCI scenario calculations. No energy measurements are invented."""
from __future__ import annotations
import math
from statistics import mean


def nonnegative(value: float, name: str) -> float:
    if not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
        raise ValueError(f'{name} must be finite and nonnegative')
    return float(value)


def watts_hours_to_kwh(watts: float, hours: float) -> float:
    return nonnegative(watts,'watts')*nonnegative(hours,'hours')/1000


def allocated_embodied_g(kg: float, years: float, hours: float=24., share: float=1.) -> float:
    nonnegative(kg,'embodied kg');nonnegative(hours,'hours');nonnegative(share,'share')
    if not math.isfinite(years) or years<=0 or hours>24 or share>1:raise ValueError('Invalid allocation')
    return kg*1000*(hours/(years*365*24))*share


def weighted_statistics(records: list[dict], engine: str, weights: dict[str,float]) -> dict:
    selected=[r for r in records if r['engine']==engine]
    if not weights or abs(sum(weights.values())-1)>1e-9:raise ValueError('Workload weights must sum to one')
    cpu=capture=playback=correct=0.
    for kind,weight in weights.items():
        nonnegative(weight,'weight')
        group=[r for r in selected if r['kind']==kind]
        if not group:raise ValueError(f'Missing workload category {kind}')
        cpu+=weight*mean(r['cpu_s'] for r in group)
        capture+=weight*mean(r['virtual_capture_s'] for r in group)
        playback+=weight*mean((r['simulated_prompt_s'] or 0)+(r.get('simulated_confirmation_prompt_s') or 0) for r in group)
        # Repetitions are timing repeats, not independent accuracy observations.
        unique={r['case']:r for r in group}
        correct+=weight*sum(r['expected']!='UNKNOWN' and r['prediction']['intent']==r['expected'] for r in unique.values())/len(unique)
    return {'matching_cpu_s':cpu,'capture_s':capture,'playback_s':playback,'correct_request_fraction':correct}


def bed_day(config: dict, scenario: str, stats: dict, attempts: float, logical_cpus: int) -> dict:
    nonnegative(attempts,'attempts')
    if logical_cpus<=0:raise ValueError('Logical CPU count must be positive')
    intensity=nonnegative(config['grid_gco2e_per_kwh'],'grid intensity')
    p=config['scenarios'][scenario]
    idle=nonnegative(p['board_idle_w'],'idle power');full=nonnegative(p['board_full_w'],'full power')
    if full<idle:raise ValueError('Full-load power must not be below idle')
    components=p['components'];board=[c for c in components if c['id']=='board']
    if len(board)!=1 or board[0]['power_w']!=idle or board[0]['hours']!=24 or board[0]['resource_share']!=1:
        raise ValueError('Dedicated board baseline must match power model')
    if len({c['id'] for c in components})!=len(components):raise ValueError('Duplicate component')
    operational={};embodied={};energy={}
    for c in components:
        energy[c['id']]=watts_hours_to_kwh(c['power_w'],c['hours'])*c['resource_share']
        operational[c['id']]=energy[c['id']]*intensity
        embodied[c['id']]=allocated_embodied_g(c['embodied_kg'],p['lifespan_years'],c['hours'],c['resource_share'])
    cpu=nonnegative(stats['matching_cpu_s'],'matching CPU')
    common=(nonnegative(stats['capture_s'],'capture seconds')*nonnegative(config['capture_cpu_s_per_audio_s'],'capture model')+
            nonnegative(stats['playback_s'],'playback seconds')*nonnegative(config['playback_cpu_s_per_audio_s'],'playback model')+
            nonnegative(config['delivery_cpu_s_per_attempt'],'delivery model'))
    setup=nonnegative(config['setup_cpu_s'],'setup CPU')
    lifetime=config['profile_lifetime_days']
    if not math.isfinite(lifetime) or lifetime<=0:raise ValueError('Profile lifetime must be positive')
    slope=(full-idle)/logical_cpus
    # Baseline is charged for all 24 h. Add only incremental CPU energy, never active idle twice.
    matching_kwh=slope*cpu*attempts/3600000
    common_kwh=slope*(common*attempts+setup/lifetime)/3600000
    operational['recognition_increment']=matching_kwh*intensity
    operational['capture_playback_delivery_setup_increment']=common_kwh*intensity
    total=sum(operational.values())+sum(embodied.values())
    fraction=nonnegative(stats['correct_request_fraction'],'correct request fraction')
    if fraction>1:raise ValueError('Correct request fraction exceeds one')
    correct=attempts*fraction
    return {'scenario':scenario,'attempts_per_day':attempts,'estimated_energy_kwh':sum(energy.values())+matching_kwh+common_kwh,
            'operational_g':operational,'embodied_g':embodied,'sci_g_per_bed_day':total,
            'modelled_correct_requests':correct,'g_per_modelled_correct_request':total/correct if correct>0 else None,
            'matching_increment_g_per_attempt':slope*cpu/3600000*intensity,
            'kind':'MODELLED scenario; not measured watts/carbon. Correct requests assume confirmation and delivery.'}
