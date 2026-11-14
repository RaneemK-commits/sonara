"""Build the optional exact DTW library locally; no downloads or runtime compilation."""
from pathlib import Path
import argparse
import os
import shutil
import subprocess
import tempfile


def build(output: Path) -> None:
    compiler=shutil.which('cc')
    if compiler is None:raise RuntimeError('A local C compiler is required; NumPy fallback needs none')
    source=Path(__file__).resolve().parents[3]/'sonara/models/dtw_native.c'
    output=output.resolve();output.parent.mkdir(parents=True,exist_ok=True)
    descriptor,temporary=tempfile.mkstemp(prefix='dtw-',suffix='.so',dir=output.parent)
    os.close(descriptor)
    try:
        subprocess.run([compiler,'-O3','-std=c99','-shared','-fPIC',str(source),'-o',temporary,'-lm'],check=True)
        os.replace(temporary,output)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    build(parser.parse_args().output)
