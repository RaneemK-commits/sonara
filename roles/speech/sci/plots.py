"""Export presentation-ready PNG/SVG. Carbon panels are explicitly MODELLED."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BG='#0B1326';PANEL='#142039';TEXT='#EDF4FF';MUTED='#A4B6D1'
COLORS={'numpy':'#FF9CAC','native':'#46DDCB'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--replay',type=Path,required=True)
    p.add_argument('--analysis',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    replay=json.loads(args.replay.read_text());analysis=json.loads(args.analysis.read_text())
    if not replay.get('complete'):raise ValueError('Incomplete replay')
    rows=replay['records'];scenarios=analysis['modelled_scenarios']
    quality=analysis['quality_unique_recordings']['native']
    plt.rcParams.update({'figure.facecolor':BG,'axes.facecolor':PANEL,'axes.edgecolor':'#334564',
                         'axes.labelcolor':TEXT,'text.color':TEXT,'xtick.color':MUTED,'ytick.color':MUTED,
                         'font.family':'DejaVu Sans','font.size':11,'axes.titleweight':'bold',
                         'savefig.facecolor':BG,'svg.fonttype':'none'})
    def finish(fig,name,caption):
        fig.text(.05,.025,caption,color=MUTED,fontsize=9)
        fig.subplots_adjust(bottom=.18,top=.85,left=.12,right=.95)
        for ax in fig.axes:
            ax.spines['top'].set_visible(False);ax.spines['right'].set_visible(False)
        for extension in ('png','svg'):fig.savefig(args.output/f'{name}.{extension}',dpi=180)
        plt.close(fig)
    names=['NumPy baseline','Native DTW']
    # Individual timing samples retain the observed distribution; no invented confidence interval.
    fig,ax=plt.subplots(figsize=(10,6))
    rng=np.random.default_rng(8)
    for i,engine in enumerate(('numpy','native')):
        values=np.array([r['wall_s']*1000 for r in rows if r['engine']==engine and r['kind']=='real_known'])
        ax.scatter(i+rng.uniform(-.12,.12,len(values)),values,s=28,alpha=.6,color=COLORS[engine])
        med=float(np.median(values));p95=float(np.percentile(values,95))
        ax.plot([i-.22,i+.22],[med,med],color=TEXT,lw=3)
        ax.annotate(f'median {med:,.0f} ms\np95 {p95:,.0f} ms',(i+.22,med),color=TEXT,fontsize=10)
    ax.set_xticks([0,1],names);ax.set_ylabel('Processing time (ms)');ax.set_xlim(-.5,1.7);ax.set_ylim(bottom=0)
    ax.set_title('Same voice. Same decisions. Less waiting.\nMEASURED on Arduino UNO Q',pad=20)
    finish(fig,'01_latency',f"{quality['known_trials']} independent known-word recordings × {replay['repetitions']} timing repetitions. Capture/playback excluded.")
    fig,ax=plt.subplots(figsize=(10,6))
    cases=sorted({r['case'] for r in rows if r['kind']=='real_known'})
    for case in cases:
        medians=[np.median([r['cpu_s'] for r in rows if r['engine']==e and r['case']==case]) for e in ('numpy','native')]
        ax.plot([0,1],medians,'o-',lw=2,alpha=.85,label=case.split('_')[0])
    ax.set_xticks([0,1],names);ax.set_ylabel('CPU seconds per recognition');ax.set_ylim(bottom=0)
    ax.legend(frameon=False,labelcolor=TEXT);ax.set_title('A smaller computational workload\nMEASURED process CPU time',pad=20)
    finish(fig,'02_cpu_work','Paired per-word medians. CPU time is measured; it is not a wattmeter.')
    fig,ax=plt.subplots(figsize=(10,6))
    categories=['Board standby','Display','Other operational','Recognition','Other activity/setup','Embodied hardware']
    shades=['#5978BD','#9B8FE8','#4DADB8','#46DDCB','#F3BD62','#C57FAB']
    for i,e in enumerate(('numpy','native')):
        r=next(s for s in scenarios if s['engine']==e and s['scenario']=='central' and s['attempts_per_day']==100)
        o=r['operational_g'];m=r['embodied_g']
        values=[o['board'],o['display'],sum(o[k] for k in ('mic_speaker_hub_buttons','router','caregiver_phone')),
                o['recognition_increment'],o['capture_playback_delivery_setup_increment'],sum(m.values())]
        bottom=0
        for j,(label,value) in enumerate(zip(categories,values)):
            ax.bar(i,value,bottom=bottom,color=shades[j],label=label if i==0 else None,width=.55);bottom+=value
        ax.text(i,bottom+2,f'~{bottom:.0f} g',ha='center',color=TEXT)
    ax.set_xticks([0,1],names);ax.set_ylabel('Estimated gCO₂e per occupied bed-day');ax.set_ylim(bottom=0)
    ax.legend(frameon=False,labelcolor=TEXT,fontsize=8,loc='upper left',bbox_to_anchor=(1,1))
    ax.set_title('Standby and hardware matter too\nMODELLED central scenario · 100 Talk attempts/day',pad=20)
    fig.subplots_adjust(right=.74)
    # finish's layout would reclaim right; reserve legend within plot instead.
    ax.get_legend().remove();ax.legend(frameon=False,labelcolor=TEXT,fontsize=8,loc='upper left',ncol=2)
    ax.set_ylim(0,ax.get_ylim()[1]*1.35)
    finish(fig,'03_daily_footprint','Illustrative energy/lifecycle assumptions. Dedicated hardware charged for all 24 hours. No power meter.')
    fig,ax=plt.subplots(figsize=(10,6))
    for e in ('numpy','native'):
        x=sorted({r['attempts_per_day'] for r in scenarios});bands=[]
        for scenario in ('low','central','high'):
            values=[next(r['g_per_modelled_correct_request'] for r in scenarios if r['engine']==e and r['scenario']==scenario and r['attempts_per_day']==n) for n in x]
            bands.append([np.nan if value is None else value for value in values])
        ax.fill_between(x,bands[0],bands[2],color=COLORS[e],alpha=.12)
        ax.plot(x,bands[1],'o-',color=COLORS[e],label=e)
    ax.set_xlabel('Assumed Talk attempts per bed-day');ax.set_ylabel('Estimated gCO₂e per correct request')
    ax.set_ylim(bottom=0);ax.legend(frameon=False,labelcolor=TEXT)
    ax.set_title('Show the assumptions, not false precision\nMODELLED sensitivity scenarios',pad=20)
    finish(fig,'04_sci_sensitivity','Shading = low/high assumptions, NOT confidence intervals. Correct requests assume confirmation/delivery.')
    labels=['WATER','HELP','FOOD','PAIN','BATHROOM','UNKNOWN']
    fig,axes=plt.subplots(1,2,figsize=(13,6))
    for ax,e in zip(axes,('numpy','native')):
        unique={r['case']:r for r in rows if r['engine']==e and r['kind']!='synthetic_noise'}
        matrix=np.zeros((6,6),int)
        for r in unique.values():
            actual=r['expected'];pred=r['prediction']['intent'] or 'UNKNOWN'
            matrix[labels.index(actual),labels.index(pred)]+=1
        ax.imshow(matrix,cmap='Blues',vmin=0,vmax=max(1,matrix.max()))
        for i in range(6):
            for j in range(6):ax.text(j,i,str(matrix[i,j]),ha='center',va='center',color='#FFFFFF' if matrix[i,j]>matrix.max()/2 else '#17243B',fontsize=11)
        ax.set_xticks(range(6),labels,rotation=50,ha='right');ax.set_yticks(range(6),labels)
        ax.set_title(e.upper());ax.set_xlabel('Accepted intent or rejection');ax.set_ylabel('Actual label')
    fig.suptitle('Efficiency must preserve behavior · measured replay',fontsize=17,fontweight='bold',y=.97)
    finish(fig,'05_confusion',f"{quality['known_trials']} real known tests + {quality['real_negative_trials']} real soundalikes, counted once each. Not clinical validation. Synthetic noise excluded.")
    (args.output/'plot_versions.json').write_text(json.dumps({'matplotlib':matplotlib.__version__,'numpy':np.__version__},indent=2))

if __name__=='__main__':main()
