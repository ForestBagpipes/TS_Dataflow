#!/usr/bin/env python3
"""Render saved paired development statistics; no model or label access."""
import hashlib,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path('results/v431-r5')
def main():
    source=ROOT/'statistics/report.json';data=json.loads(source.read_text())['suites']['dev']
    out=Path('docs/figures/v431-r5');out.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.size':9,'svg.fonttype':'none','pdf.fonttype':42})
    fig,axes=plt.subplots(1,2,figsize=(11,4.9))
    panels=[('Complete method: r5 minus comparator',data['adaptive_comparisons'],
        [('R5_high','REFERENCE_FREE_high','free reference'),('R5_high','TRAIN_BEST_FIXED_FLOW_high','TRAIN fixed flow')]),
        ('Same queries: FULL minus comparator',data['mechanism']['comparisons'],
        [('MECH_CURRENT_FULL','MECH_CURRENT_RAW','RAW'),('MECH_CURRENT_FULL','MECH_CURRENT_SINGLE','single clipping')])]
    saved=[]
    for ax,(title,rows,comparisons) in zip(axes,panels):
        selected=[]
        for family in ('bolt','timesfm'):
            for left,right,label in comparisons:
                matches=[r for r in rows if r['family']==family and r['left']==left and r['right']==right and r.get('subset','all')=='all']
                if len(matches)!=1:raise ValueError((family,left,right,len(matches)))
                r=matches[0];v=r['differences']['mase'];lo,hi=v['ci90'];mean=v['mean']
                selected.append((family,label,mean,lo,hi))
                saved.append(dict(panel=title,family=family,left=left,right=right,mean=mean,ci90=[lo,hi],parents=r['parents'],windows=r['common_episodes']))
        for y,(family,label,mean,lo,hi) in enumerate(selected):
            color='#30689b' if family=='bolt' else '#c2652d'
            ax.errorbar(mean,y,xerr=[[max(0,mean-lo)],[max(0,hi-mean)]],fmt='o',color=color,capsize=4,markersize=6)
        ax.axvline(0,color='#777777',linewidth=.8,linestyle='--');ax.invert_yaxis()
        ax.set_yticks(range(len(selected)),[f'{family} vs {label}' for family,label,*_ in selected])
        ax.set_title(title,fontsize=11,pad=14);ax.set_xlabel('Paired MASE difference (negative is better)')
        ax.grid(axis='x',alpha=.18);ax.spines[['top','right']].set_visible(False)
    fig.suptitle('r5: development criteria not met across both TSFM families',fontsize=13)
    fig.text(.5,.015,'Old DEV: 26 parents / 156 related variants. Descriptive 90% source/parent-block intervals.\nRepeated development use; one USTS parent. Not independent confirmation.',ha='center',fontsize=8,color='#555555')
    fig.tight_layout(rect=(0,.12,1,.92))
    for ext in ('svg','pdf','png'):fig.savefig(out/f'development_differences.{ext}',dpi=160)
    svg=out/'development_differences.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    plt.close(fig)
    payload=dict(statistics_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),records=saved,
                 scope='Existing saved descriptive block statistics; no new training, targets, or inference')
    (out/'development_differences.json').write_text(json.dumps(payload,indent=2)+'\n')
    print(json.dumps({'status':'rendered','output':str(out),'points':len(saved)}))
if __name__=='__main__':main()
