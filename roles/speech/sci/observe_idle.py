"""Read-only Linux idle/thermal observation; no energy measurement implied."""
from pathlib import Path
import argparse,json,os,platform,time


def cpu_counters():
    values=[int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
    return sum(values),sum(values)-values[3]-values[4]


def temperatures():
    result={}
    for sensor in Path('/sys/class/hwmon').glob('hwmon*'):
        try:
            name=(sensor/'name').read_text().strip()
            if name=='cpuss0_thermal':
                for value in sensor.glob('temp*_input'):
                    result[name+'/'+value.name]=float(value.read_text())/1000
        except (OSError,ValueError):pass
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seconds',type=int,default=300)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--thermal',action='store_true',help='optional CPU thermal reads; disabled for a low-overhead idle baseline')
    args=p.parse_args()
    if not 1<=args.seconds<=3600:p.error('seconds must be 1–3600')
    rows=[];previous=cpu_counters();start=time.monotonic()
    second=0
    deadline=start+args.seconds
    while time.monotonic()<deadline:
        time.sleep(min(1.,max(0.,deadline-time.monotonic())))
        current=cpu_counters();total=current[0]-previous[0]
        rows.append({'elapsed_s':time.monotonic()-start,'system_cpu_fraction':(current[1]-previous[1])/total if total else 0,
                     'temperatures_c':temperatures() if args.thermal and second%10==0 else {}})
        previous=current;second+=1
        if second%30==0:print(f'Idle observation {time.monotonic()-start:.1f}/{args.seconds} s',flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'kind':'measured CPU/temperature; NOT watts','machine':platform.machine(),
                                     'logical_cpus':os.cpu_count(),'requested_seconds':args.seconds,'actual_seconds':time.monotonic()-start,'samples':rows},indent=2))
    print('Idle observation complete',flush=True)
