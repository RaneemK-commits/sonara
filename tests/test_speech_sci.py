from copy import deepcopy
import json
from pathlib import Path
import pytest
from roles.speech.sci.calculate import watts_hours_to_kwh,allocated_embodied_g,bed_day,weighted_statistics


@pytest.fixture
def config():
    return json.loads((Path(__file__).resolve().parents[1]/'roles/speech/sci/assumptions.json').read_text())


@pytest.fixture
def stats():
    return {'matching_cpu_s':4.,'capture_s':3.,'playback_s':4.,'correct_request_fraction':.8}


def test_units():
    assert watts_hours_to_kwh(1,1)==.001
    assert watts_hours_to_kwh(1000,1)==1
    assert allocated_embodied_g(100,5)==pytest.approx(100000/(5*365))
    assert allocated_embodied_g(100,5,hours=.5,share=.1)==pytest.approx(100000/(5*365)*.5/24*.1)


def test_incremental_energy_and_embodied_unchanged_by_speed(config,stats):
    slow=bed_day(config,'central',stats,100,4)
    faster={**stats,'matching_cpu_s':.4}
    fast=bed_day(config,'central',faster,100,4)
    assert slow['embodied_g']==fast['embodied_g']
    expected=(12-5)/4*(4-.4)*100/3600000*406
    assert slow['sci_g_per_bed_day']-fast['sci_g_per_bed_day']==pytest.approx(expected)
    assert slow['operational_g']['board']==pytest.approx(.120*406)
    assert slow['embodied_g']['board']==pytest.approx(6500/(365*5))


def test_zero_grid_keeps_energy_and_embodied(config,stats):
    a=bed_day(config,'central',stats,100,4)
    config['grid_gco2e_per_kwh']=0
    b=bed_day(config,'central',stats,100,4)
    assert b['estimated_energy_kwh']==a['estimated_energy_kwh']
    assert b['sci_g_per_bed_day']==sum(b['embodied_g'].values())


def test_all_rejected_has_no_per_success_score(config,stats):
    stats['correct_request_fraction']=0
    result=bed_day(config,'central',stats,100,4)
    assert result['sci_g_per_bed_day']>0
    assert result['g_per_modelled_correct_request'] is None


@pytest.mark.parametrize('value',[-1,float('nan'),float('inf')])
def test_invalid_quantities_rejected(value):
    with pytest.raises(ValueError):watts_hours_to_kwh(value,1)
    with pytest.raises(ValueError):allocated_embodied_g(10,value)


def test_allocation_and_power_model_validation(config,stats):
    with pytest.raises(ValueError):allocated_embodied_g(10,5,hours=25)
    with pytest.raises(ValueError):allocated_embodied_g(10,5,share=1.1)
    with pytest.raises(ValueError):bed_day(config,'central',stats,100,0)
    config['scenarios']['central']['board_full_w']=1
    with pytest.raises(ValueError):bed_day(config,'central',stats,100,4)


def test_accuracy_repetitions_are_not_independent_and_unknown_is_not_productive():
    rows=[]
    for repetition in range(5):
        rows.extend([{'engine':'native','kind':'real_known','case':'WATER','expected':'WATER',
                      'cpu_s':1,'virtual_capture_s':2,'simulated_prompt_s':1,'prediction':{'intent':'WATER'}},
                     {'engine':'native','kind':'real_similar_word','case':'warmer','expected':'UNKNOWN',
                      'cpu_s':1,'virtual_capture_s':2,'simulated_prompt_s':1,'prediction':{'intent':'WATER'}}])
    stats=weighted_statistics(rows,'native',{'real_known':.8,'real_similar_word':.2})
    assert stats['correct_request_fraction']==.8
    assert stats['matching_cpu_s']==1
    with pytest.raises(ValueError):weighted_statistics(rows,'native',{'real_known':.5})


def test_incomplete_replay_cannot_generate_final_sci(config):
    from roles.speech.sci.analyze import analyze
    with pytest.raises(ValueError,match='incomplete'):
        analyze({'complete':False},config)


def test_analysis_uses_accepted_predictions_and_keeps_energy_for_false_accepts(config):
    from roles.speech.sci.analyze import analyze
    rows=[]
    for engine in ('numpy','native'):
        for kind,expected,intent in [('real_known','WATER',None),('real_similar_word','UNKNOWN','WATER'),('synthetic_noise','UNKNOWN',None)]:
            rows.append({'engine':engine,'kind':kind,'case':kind,'expected':expected,'cpu_s':1.,'wall_s':1.,
                         'virtual_capture_s':3.,'simulated_prompt_s':1.,
                         'prediction':{'best':'WATER','intent':intent,'accepted':intent is not None}})
    report=analyze({'complete':True,'records':rows,'repetitions':1,'logical_cpus':4},config)
    assert report['quality_unique_recordings']['native']['correct_accepted']==0
    assert report['quality_unique_recordings']['native']['real_negative_false_accepts']==1
    assert report['modelled_scenarios'][0]['g_per_modelled_correct_request'] is None
    assert report['modelled_scenarios'][0]['sci_g_per_bed_day']>0
