import shutil
from pathlib import Path
import numpy as np
import pytest
from sonara.models.dtw import dtw_distance
from sonara.models.native_dtw import NativeDTW
from roles.speech.evaluation.build_native_dtw import build


@pytest.fixture(scope='module')
def native(tmp_path_factory):
    if shutil.which('cc') is None:pytest.skip('Optional native compiler is unavailable')
    path=tmp_path_factory.mktemp('native')/'dtw.so'
    build(path)
    return NativeDTW(str(path))


@pytest.mark.parametrize('band',[0.,.2,1.])
@pytest.mark.parametrize('n,m,dimensions',[(1,1,1),(1,9,13),(9,3,39),(31,51,39),(60,60,39),(100,65,13)])
def test_native_matches_reference(native,band,n,m,dimensions):
    rng=np.random.default_rng(451)
    query=rng.normal(size=(n,dimensions))
    templates=[rng.normal(size=(m,dimensions)),np.zeros((m,dimensions)),np.ones((m,dimensions))]
    assert native.distances(query,templates,band)==pytest.approx([dtw_distance(query,t,band=band) for t in templates],abs=1e-10)


def test_native_ties_repeats_and_invalid_sequences(native):
    a=np.array([[0.],[1.],[1.],[0.]])
    templates=[a,np.repeat(a,2,axis=0),np.zeros((8,1)),np.full((2,1),np.nan),np.zeros((601,1)),np.zeros((3,2))]
    assert native.distances(a,templates)==pytest.approx([dtw_distance(a,t,band=.2) for t in templates],abs=1e-10)
    assert all(np.isinf(native.distances(np.empty((0,1)),templates)))
    with pytest.raises(ValueError):native.distances(a,templates,band=-1)
