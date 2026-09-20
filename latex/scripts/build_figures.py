"""Build manuscript EPS directly from BMP artwork and recorded CSV tables.

No experiment is rerun. Table values are used at their recorded precision.
The first two EPS files embed the original pixels losslessly and remain raster
images. Experimental EPS files contain vector marks and embedded vector glyphs.
"""
from pathlib import Path
import base64
import csv
import hashlib
import json
import math
import textwrap
import zlib

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator, FormatStrFormatter
from PIL import Image
import numpy as np

HERE = Path(__file__).resolve().parents[1]
FIG = HERE / 'figure'
PREVIEW = HERE / 'build' / 'preview'
PREVIEW.mkdir(parents=True, exist_ok=True)
COLORS = ['#9AAFC0', '#739BBF', '#368E9D', '#817BAA', '#526D94', '#173F68']
METHODS = ['Native KEEP', 'Best Fixed', 'R2-CART', 'Fixed SAITS', 'TATO', 'IntroAct-TS']
SHORT = ['KEEP', 'Fixed', 'CART', 'SAITS', 'TATO', 'Ours']
plt.rcParams.update({
    'font.family': 'sans-serif', 'font.sans-serif': ['Arial', 'DejaVu Sans'],
    'font.size': 11, 'axes.labelsize': 12, 'axes.titlesize': 12,
    'xtick.labelsize': 10.5, 'ytick.labelsize': 10.5, 'legend.fontsize': 10.5,
    'axes.spines.top': False, 'axes.spines.right': False,
    'axes.grid': False, 'axes.linewidth': .8, 'legend.frameon': False,
    'pdf.fonttype': 42, 'ps.fonttype': 3, 'figure.facecolor': 'white',
    'savefig.facecolor': 'white', 'axes.unicode_minus': False,
})


def save(fig, name):
    fig.savefig(FIG / (name + '.eps'), format='eps', bbox_inches='tight', pad_inches=.06)
    eps = FIG / (name + '.eps')
    eps.write_bytes(eps.read_bytes().replace(b'\r\n', b'\n'))
    fig.savefig(PREVIEW / (name + '.png'), dpi=200, bbox_inches='tight', pad_inches=.06)
    plt.close(fig)


def bmp_eps(name):
    im = Image.open(FIG / (name + '.bmp')).convert('RGB')
    w, h = im.size
    width, height = 432., 432. * h / w
    payload = base64.a85encode(zlib.compress(im.tobytes(), 9)).decode('ascii')
    header = f'''%!PS-Adobe-3.0 EPSF-3.0
%%BoundingBox: 0 0 {math.ceil(width)} {math.ceil(height)}
%%HiResBoundingBox: 0 0 {width:.6f} {height:.6f}
%%LanguageLevel: 3
%%Title: {name}
%%Creator: IntroActTS BMP lossless export
%%EndComments
gsave
{width:.6f} {height:.6f} scale
/DeviceRGB setcolorspace
<< /ImageType 1 /Width {w} /Height {h} /BitsPerComponent 8
/Decode [0 1 0 1 0 1] /ImageMatrix [{w} 0 0 -{h} 0 {h}]
/DataSource currentfile /ASCII85Decode filter /FlateDecode filter >> image
'''
    (FIG / (name + '.eps')).write_text(header + '\n'.join(textwrap.wrap(payload, 100, break_on_hyphens=False)) + '\n~>\ngrestore\nshowpage\n%%EOF\n', encoding='ascii', newline='\n')
    im.thumbnail((1800, 1100))
    im.save(PREVIEW / (name + '.png'))


def read(name):
    with (FIG / 'data' / name).open(encoding='utf8', newline='') as f:
        return list(csv.DictReader(f))


def bars(ax, vals, labels, colors, title, fmt='.1f'):
    x = np.arange(len(vals))
    ax.bar(x, vals, color=colors, width=.72)
    ax.set_xticks(x, labels, rotation=52, ha='right', fontsize=10)
    ax.set_title(title, loc='left', weight='bold', fontsize=11, pad=8)
    low = min(0, min(vals)); high = max(vals)
    span = high-low or 1
    ax.set_ylim(low-span*.22 if low<0 else 0, high+span*(.42 if fmt in ['.3f','.4f'] and len(vals)>5 else .24))
    ax.yaxis.set_major_locator(MaxNLocator(4))
    for xi,v in zip(x,vals):
        ax.text(xi,v+span*.03 if v>=0 else v-span*.025,format(v,fmt),
                ha='center',va='bottom' if v>=0 else 'top',fontsize=8.5,rotation=90 if len(vals)>5 and fmt in ['.3f','.4f'] else 0)
    if low<0: ax.axhline(0,color='#5B6C7B',lw=.7)
    ax.grid(False)


def triple():
    fig,axs=plt.subplots(1,3,figsize=(7.5,2.55))
    fig.subplots_adjust(left=.065,right=.99,bottom=.29,top=.85,wspace=.36)
    return fig,axs


def utility():
    r=read('utility.csv'); fig,axs=triple()
    labels=['KEEP','Ffill','Single','Multi','Ridge','SAITS']
    bars(axs[0],[float(x['best_share']) for x in r],labels,COLORS,'(a) Oracle-best (%)')
    bars(axs[1],[float(x['beneficial_share']) for x in r[1:]],labels[1:],COLORS[1:],'(b) Beneficial (%)')
    bars(axs[2],[float(x['mean_utility']) for x in r[1:]],labels[1:],COLORS[1:],'(c) Mean utility','.3f')
    save(fig,'fig3_action_utility')


def main_comparison():
    r=read('main.csv')[:6]
    hr=read('harm.csv')
    fig,grid=plt.subplots(2,2,figsize=(7.5,4.2),gridspec_kw={'width_ratios':[1.25,1]})
    fig.subplots_adjust(left=.14,right=.99,bottom=.14,top=.91,wspace=.29,hspace=.59)
    axs=[grid[0,0],grid[1,0]]
    a=np.array([[float(x[k]) for k in ['bolt','timesfm','chronos2','overall']] for x in r])
    ax=axs[0]; ax.pcolormesh(np.arange(5)-.5,np.arange(7)-.5,a,cmap='Blues',vmin=1.30,vmax=1.75,edgecolors='none')
    ax.set_ylim(5.5,-.5);ax.set_xticks(range(4),['Bolt','TimesFM','Chronos-2','Overall'],fontsize=9)
    ax.set_yticks(range(6),METHODS,fontsize=9);ax.tick_params(length=0)
    ax.set_title('(a) Source-macro MASE',loc='left',weight='bold',fontsize=11,pad=8)
    for i in range(6):
        for j in range(4):ax.text(j,i,f'{a[i,j]:.3f}',ha='center',va='center',fontsize=10,color='white' if a[i,j]>1.57 else '#132D49',weight='bold' if a[i,j]==min(a[:,j]) else 'normal')
    for spine in ax.spines.values():spine.set_visible(False)
    bars(axs[1],[float(x['rank']) for x in r],SHORT,COLORS,'(c) Average rank','.2f')
    bars(grid[0,1],[float(x['harmful_loss']) for x in hr],SHORT,COLORS,'(b) Harmful loss','.4f')
    ax=grid[1,1]; x=np.arange(6)
    ax.bar(x-.18,[float(v['intervention_rate']) for v in hr],width=.36,color=COLORS)
    ax.bar(x+.18,[np.nan]+[float(v['conditional_hir']) for v in hr[1:]],width=.36,color='white',edgecolor=COLORS,hatch='///',linewidth=1)
    ax.set_xticks(x,SHORT,rotation=52,ha='right',fontsize=10)
    ax.set_ylim(0,125);ax.set_yticks([0,50,100]);ax.grid(False)
    ax.set_title('(d) Intervention / harmful rate (%)',loc='left',weight='bold',fontsize=10)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(facecolor='#526D94',label='Intervention'),Patch(facecolor='white',edgecolor='#526D94',hatch='///',label='Harmful | acted')],loc='upper left',ncol=2,fontsize=7.5,handlelength=1.2,columnspacing=.8)
    save(fig,'fig4_main_harm')


def ablation():
    r=read('ablation.csv');fig,axs=triple();labels=[x['variant'] for x in r]
    cols=[COLORS[-1],*COLORS[:-1]]
    for ax,field,title,fmt in zip(axs,['mase','harmful_loss','calls'],['(a) MASE','(b) Harmful loss','(c) Backbone calls'],['.3f','.4f','.2f']):
        bars(ax,[float(x[field]) for x in r],labels,cols,title,fmt)
        ax.tick_params(axis='x',rotation=0)
    save(fig,'fig6_ablation_cost')


def severity():
    rows = read('severity.csv')
    fig, axes = plt.subplots(1,2,figsize=(7.5,2.9),gridspec_kw={'width_ratios':[1.6,1]})
    fig.subplots_adjust(left=.08, right=.99, bottom=.27, top=.75,wspace=.32)
    ax=axes[0]
    styles = [('o','--'), ('s','--'), ('^','-'), ('D','-.'), ('v',':'), ('o','-')]
    for row, color, (marker, ls) in zip(rows, COLORS, styles):
        vals = [float(row[k]) for k in ['s10','s30','s50']]
        ax.plot([10,30,50], vals, color=color, marker=marker, ls=ls,
                markersize=6, linewidth=2.4 if row['method']=='IntroAct-TS' else 1.5,
                label=row['method'], zorder=5 if row['method']=='IntroAct-TS' else 2)
    ax.set(xlabel='Missingness (%)', xticks=[10,30,50], xlim=(7,53), ylim=(1.38,2.09))
    ax.set_title('(a) Source-macro MASE',loc='left',weight='bold',fontsize=11)
    fig.legend(*ax.get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.54,1.04),ncol=3,columnspacing=1.5,handlelength=1.8,fontsize=10)
    bars(axes[1],[float(r['worst_cell']) for r in rows],SHORT,COLORS,'(b) Worst-cell increase','.3f')
    ax.grid(False)
    save(fig, 'fig5_missingness_severity')


def ranks():
    rows = read('rank_agreement.csv')
    a = np.array([[float(r[f'utility_{i}']) for i in range(1,6)] for r in rows])
    fig, ax = plt.subplots(figsize=(4.7, 3.75), layout='constrained')
    ax.pcolormesh(np.arange(6)-.5, np.arange(6)-.5, a, cmap='Blues', vmin=0, vmax=45,
                  edgecolors='none', rasterized=False)
    ax.set_ylim(4.5,-.5)
    ax.set_aspect('equal')
    for i in range(5):
        for j in range(5):
            ax.text(j, i, f'{a[i,j]:.1f}%', ha='center', va='center',
                    color='white' if a[i,j]>=28 else '#102E4A', fontsize=11)
    ax.set(xticks=range(5), xticklabels=range(1,6), yticks=range(5), yticklabels=range(1,6),
           xlabel='Forecasting-utility rank (1 = best)', ylabel='Reconstruction rank (1 = best)')
    ax.tick_params(length=0)
    for spine in ax.spines.values(): spine.set_visible(False)
    save(fig, 'fig7_rank_agreement')


if __name__ == '__main__':
    for name in ['fig1_example', 'fig2_Architecture']: bmp_eps(name)
    utility(); main_comparison(); severity(); ablation(); ranks()
    files = sorted(FIG.glob('*.eps')) + sorted((FIG/'data').glob('*.csv')) + sorted(FIG.glob('*.bmp'))
    manifest = {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (HERE/'build/figure_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print('Built 2 lossless raster EPS figures and 5 vector experimental EPS figures.')
