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
TITLE_SIZE, AXIS_SIZE, TICK_SIZE, VALUE_SIZE, LEGEND_SIZE = 11, 11, 10, 9.5, 10
plt.rcParams.update({
    'font.family': 'sans-serif', 'font.sans-serif': ['Arial', 'DejaVu Sans'],
    'font.size': 11, 'axes.labelsize': AXIS_SIZE, 'axes.titlesize': TITLE_SIZE,
    'xtick.labelsize': TICK_SIZE, 'ytick.labelsize': TICK_SIZE, 'legend.fontsize': LEGEND_SIZE,
    'xtick.major.size': 3, 'ytick.major.size': 3,
    'xtick.major.pad': 4, 'ytick.major.pad': 4,
    'axes.spines.top': False, 'axes.spines.right': False,
    'axes.grid': False, 'axes.linewidth': .8, 'legend.frameon': False,
    'pdf.fonttype': 42, 'ps.fonttype': 3, 'figure.facecolor': 'white',
    'savefig.facecolor': 'white', 'axes.unicode_minus': False,
})


def save(fig, name):
    # Identical canvas widths preserve actual printed font sizes across main figures.
    fig.align_xlabels()
    fig.align_ylabels()
    fig.savefig(FIG / (name + '.eps'), format='eps')
    eps = FIG / (name + '.eps')
    eps.write_bytes(eps.read_bytes().replace(b'\r\n', b'\n'))
    fig.savefig(PREVIEW / (name + '.png'), dpi=200)
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
    ax.set_xticks(x, labels, rotation=50, ha='right', fontsize=TICK_SIZE)
    ax.set_title(title, loc='left', weight='bold', fontsize=TITLE_SIZE, pad=8)
    low = min(0, min(vals)); high = max(vals)
    span = high-low or 1
    ax.set_ylim(low-span*.22 if low<0 else 0, high+span*(.42 if fmt in ['.3f','.4f'] and len(vals)>5 else .24))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=4,steps=[1,2,2.5,5,10]))
    for xi,v in zip(x,vals):
        ax.text(xi,v+span*.03 if v>=0 else v-span*.025,format(v,fmt),
                ha='center',va='bottom' if v>=0 else 'top',fontsize=VALUE_SIZE,rotation=90 if len(vals)>5 and fmt in ['.3f','.4f'] else 0)
    if low<0: ax.axhline(0,color='#5B6C7B',lw=.7)
    ax.grid(False)


def panels(count, legend=False, ratios=None):
    height=3.15 if legend else 2.8
    fig,axs=plt.subplots(1,count,figsize=(7.5,height),gridspec_kw={'width_ratios':ratios or [1]*count})
    fig.subplots_adjust(left=.08,right=.985,bottom=.72/height,top=2.37/height,wspace=.36)
    return fig,axs


def utility():
    r=read('utility.csv'); fig,axs=panels(3)
    labels=['KEEP','Ffill','Single','Multi','Ridge','SAITS']
    bars(axs[0],[float(x['best_share']) for x in r],labels,COLORS,'(a) Oracle-best (%)')
    bars(axs[1],[float(x['beneficial_share']) for x in r[1:]],labels[1:],COLORS[1:],'(b) Beneficial (%)')
    bars(axs[2],[float(x['mean_utility']) for x in r[1:]],labels[1:],COLORS[1:],'(c) Mean utility','.3f')
    save(fig,'fig3_action_utility')


def harm():
    hr=read('harm.csv')
    fig,axes=panels(2,legend=True)
    bars(axes[0],[float(v['harmful_loss']) for v in hr],SHORT,COLORS,'(a) Harmful loss','.4f')
    ax=axes[1];x=np.arange(6)
    ax.bar(x-.18,[float(v['intervention_rate']) for v in hr],width=.36,color=COLORS)
    ax.bar(x+.18,[np.nan]+[float(v['conditional_hir']) for v in hr[1:]],width=.36,color='white',edgecolor=COLORS,hatch='///',linewidth=1)
    ax.set_xticks(x,SHORT,rotation=50,ha='right',fontsize=TICK_SIZE)
    ax.set_ylim(0,115);ax.set_yticks([0,25,50,75,100]);ax.grid(False)
    ax.set_title('(b) Intervention rates (%)',loc='left',weight='bold',fontsize=TITLE_SIZE,pad=8)
    from matplotlib.patches import Patch
    fig.legend(handles=[Patch(facecolor='#526D94',label='Intervention frequency'),Patch(facecolor='white',edgecolor='#526D94',hatch='///',label='Harmful rate among interventions')],loc='upper center',bbox_to_anchor=(.53,.985),ncol=2,fontsize=LEGEND_SIZE,handlelength=1.4,columnspacing=1.5)
    save(fig,'fig4_intervention_harm')


def severity():
    rows = read('severity.csv')
    fig, axes = panels(2,legend=True,ratios=[1.6,1])
    ax=axes[0]
    styles = [('o','--'), ('s','--'), ('^','-'), ('D','-.'), ('v',':'), ('o','-')]
    for row, color, (marker, ls) in zip(rows, COLORS, styles):
        vals = [float(row[k]) for k in ['s10','s30','s50']]
        ax.plot([10,30,50], vals, color=color, marker=marker, ls=ls,
                markersize=6, linewidth=2.4 if row['method']=='IntroAct-TS' else 1.5,
                label=row['method'], zorder=5 if row['method']=='IntroAct-TS' else 2)
    ax.set(xlabel='Missingness (%)', xticks=[10,30,50], xlim=(7,53), ylim=(1.38,2.09))
    ax.set_title('(a) Source-macro MASE',loc='left',weight='bold',fontsize=TITLE_SIZE,pad=8)
    ax.set_yticks([1.4,1.6,1.8,2.0])
    ax.yaxis.set_major_formatter(FormatStrFormatter('%.1f'))
    fig.legend(*ax.get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.53,.995),ncol=3,columnspacing=1.5,handlelength=1.8,fontsize=LEGEND_SIZE)
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
    save(fig, 'fig6_rank_agreement')


if __name__ == '__main__':
    for name in ['fig1_example', 'fig2_Architecture']: bmp_eps(name)
    utility(); harm(); severity(); ranks()
    files = sorted(FIG.glob('*.eps')) + sorted((FIG/'data').glob('*.csv')) + sorted(FIG.glob('*.bmp'))
    manifest = {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (HERE/'build/figure_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print('Built 2 lossless raster EPS figures and 4 vector experimental EPS figures.')
