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
COLORS = ['#A1A9B3', '#6D9FC4', '#389B93', '#9B85B4', '#637DB3', '#163F69']
ACTION_COLORS = [COLORS[i] for i in [0, 1, 2, 4, 5, 3]]
BAR_WIDTH, BAR_EDGE, BAR_HATCH = .64, .8, '///'
METHODS = ['Native KEEP', 'Best Fixed', 'R2-CART', 'Fixed SAITS', 'TATO', 'IntroAct-TS']
SHORT = ['KEEP', 'Fixed', 'CART', 'SAITS', 'TATO', 'Ours']
TITLE_SIZE, AXIS_SIZE, TICK_SIZE, VALUE_SIZE, LEGEND_SIZE = 11, 11, 10, 9.5, 10
plt.rcParams.update({
    'font.family': 'sans-serif', 'font.sans-serif': ['Arial', 'DejaVu Sans'],
    'font.size': 11, 'axes.labelsize': AXIS_SIZE, 'axes.titlesize': TITLE_SIZE,
    'xtick.labelsize': TICK_SIZE, 'ytick.labelsize': TICK_SIZE, 'legend.fontsize': LEGEND_SIZE,
    'xtick.major.size': 3, 'ytick.major.size': 3,
    'xtick.major.pad': 4, 'ytick.major.pad': 4,
    'axes.spines.top': True, 'axes.spines.right': True,
    'xtick.direction': 'in', 'ytick.direction': 'in',
    'xtick.top': True, 'ytick.right': True,
    'axes.grid': False, 'axes.linewidth': .8, 'legend.frameon': False,
    'pdf.fonttype': 42, 'ps.fonttype': 3, 'figure.facecolor': 'white',
    'savefig.facecolor': 'white', 'axes.unicode_minus': False,
})


def save(fig, name):
    # Identical canvas widths preserve actual printed font sizes across main figures.
    fig.savefig(FIG / (name + '.eps'), format='eps')
    eps = FIG / (name + '.eps')
    eps.write_bytes(eps.read_bytes().replace(b'\r\n', b'\n'))
    fig.savefig(PREVIEW / (name + '.png'), dpi=450)
    fig.savefig(PREVIEW / (name + '.svg'), format='svg')
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


def bar_axis(ax, labels, title):
    ax.set_xticks(np.arange(len(labels)), labels, fontsize=TICK_SIZE)
    ax.set_xlim(-.6, len(labels)-.4)
    ax.tick_params(axis='x', length=0, pad=7)
    ax.set_title(title, loc='left', fontsize=TITLE_SIZE, pad=7)
    ax.grid(False)


def paired_bars(ax, first, second, labels, colors, title):
    x = np.arange(len(labels))
    for shift, vals, filled in [(-.17, first, True), (.17, second, False)]:
        ax.bar(x+shift, vals, width=.30, color=colors if filled else 'white',
               edgecolor=colors, linewidth=BAR_EDGE, hatch=None if filled else BAR_HATCH)
    bar_axis(ax, labels, title)


def bar_legend(fig, first, second):
    from matplotlib.patches import Patch
    color = '#64758A'
    handles = [Patch(facecolor=color, edgecolor=color, linewidth=BAR_EDGE, label=first),
               Patch(facecolor='white', edgecolor=color, linewidth=BAR_EDGE, hatch=BAR_HATCH, label=second)]
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.53,.985),
               ncol=2, fontsize=LEGEND_SIZE, handlelength=1.5, columnspacing=1.8)


def bars(ax, vals, labels, colors, title, fmt='.1f'):
    x = np.arange(len(vals))
    ax.bar(x, vals, color=colors, width=BAR_WIDTH, edgecolor=colors, linewidth=BAR_EDGE)
    bar_axis(ax, labels, title)
    low = min(0, min(vals)); high = max(vals)
    span = high-low or 1
    ax.set_ylim(low-span*.25 if low<0 else 0, high+span*.24)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=4,steps=[1,2,2.5,5,10]))
    for xi,v in zip(x,vals):
        ax.annotate(format(v,fmt), (xi,v), xytext=(0,3 if v>=0 else -3), textcoords='offset points',
                ha='center',va='bottom' if v>=0 else 'top',fontsize=VALUE_SIZE, color='#25384B')
    if low<0: ax.axhline(0,color='#5B6C7B',lw=.7)
    ax.grid(False)


def panels(count, legend=False, ratios=None):
    height=2.65 if legend else 2.4
    fig,axs=plt.subplots(1,count,figsize=(7.5,height),gridspec_kw={'width_ratios':ratios or [1]*count})
    fig.subplots_adjust(left=.055,right=.995,bottom=.40/height,top=1.98/height,wspace=.22)
    return fig,axs


def utility():
    r=read('utility.csv'); fig,axs=panels(2,legend=True)
    labels=['KEEP','Ffill','Single','Multi','Ridge','SAITS']
    ax=axs[0]
    paired_bars(ax, [float(v['best_share']) for v in r],
                [float(v['beneficial_share']) if v['beneficial_share'] else np.nan for v in r],
                labels, ACTION_COLORS, '(a) Action frequency (%)')
    ax.set_ylim(0,65);ax.set_yticks([0,20,40,60])
    ax.set_title('(a) Action frequency (%)',loc='left',weight='normal',pad=8)
    bars(axs[1],[100*float(v['mean_utility']) for v in r],labels,ACTION_COLORS,r'(b) Mean utility ($\times 10^{-2}$)','.1f')
    axs[1].set_ylim(-13,15);axs[1].set_yticks([-10,-5,0,5,10])
    bar_legend(fig, 'Oracle-best', 'Beneficial')
    save(fig,'fig3_action_utility')


def harm():
    hr=read('harm.csv')
    fig,axes=panels(2,legend=True)
    bars(axes[0],[100*float(v['harmful_loss']) for v in hr],SHORT,COLORS,r'(a) Harmful loss ($\times 10^{-2}$)','.2f')
    ax=axes[1]
    paired_bars(ax, [float(v['intervention_rate']) for v in hr],
                [np.nan]+[float(v['conditional_hir']) for v in hr[1:]],
                SHORT, COLORS, '(b) Intervention rates (%)')
    ax.set_ylim(0,115);ax.set_yticks([0,25,50,75,100]);ax.grid(False)
    ax.set_title('(b) Intervention rates (%)',loc='left',weight='normal',fontsize=TITLE_SIZE,pad=8)
    bar_legend(fig, 'Intervention frequency', 'Harmful rate among interventions')
    save(fig,'fig4_intervention_harm')


def severity():
    rows = read('severity.csv')
    fig, axes = panels(2,legend=True)
    ax=axes[0]
    styles = [('o',(0,(4,2))), ('s',(0,(3,2))), ('^','-'), ('D',(0,(4,2,1,2))), ('v',(0,(1,2))), ('o','-')]
    for row, color, (marker, ls) in zip(rows, COLORS, styles):
        vals = [float(row[k]) for k in ['s10','s30','s50']]
        ax.plot([10,30,50], vals, color=color, marker=marker, ls=ls,
                markersize=6.5, markerfacecolor=color if row['method']=='IntroAct-TS' else 'white', markeredgewidth=1.4,
                linewidth=2.4 if row['method']=='IntroAct-TS' else 1.7,
                label=row['method'], zorder=5 if row['method']=='IntroAct-TS' else 2)
    ax.set(xlabel='Missingness (%)', xticks=[10,30,50], xlim=(7,53), ylim=(1.38,2.09))
    ax.xaxis.labelpad=6
    ax.set_title('(a) Source-macro MASE',loc='left',weight='normal',fontsize=TITLE_SIZE,pad=8)
    ax.set_yticks([1.4,1.6,1.8,2.0])
    ax.yaxis.set_major_formatter(FormatStrFormatter('%.1f'))
    handles, labels = ax.get_legend_handles_labels()
    # Matplotlib fills legends by column. Reorder so reading order remains row-wise.
    order = [0, 3, 1, 4, 2, 5]
    fig.legend([handles[i] for i in order], [labels[i] for i in order],
               loc='lower left', bbox_to_anchor=(.055,.835,.94,.16), mode='expand',
               ncol=3, borderaxespad=0, handlelength=2.0, handletextpad=.55,
               labelspacing=.35, fontsize=LEGEND_SIZE)
    bars(axes[1],[100*float(r['worst_cell']) for r in rows],SHORT,COLORS,r'(b) Worst-cell increase ($\times 10^{-2}$)','.1f')
    ax.grid(False)
    save(fig, 'fig5_missingness_severity')


def gate_controls():
    from matplotlib.lines import Line2D
    evidence = json.loads((FIG/'data/v55_gate_evidence.json').read_text())
    backbones = ['bolt', 'timesfm', 'chronos2']
    methods = ['GATE_DISPERSION', 'GATE_MEAN_ONLY', 'GATE_LINEAR', 'GATE_RANDOM']
    labels = ['FULL', 'Mean', 'Linear', 'Random']
    colors = [COLORS[5], COLORS[1], COLORS[2], COLORS[3]]
    markers = ['*', 'o', 's', 'D']
    fig, axes = panels(3, legend=True)
    fig.subplots_adjust(left=.075, right=.985, wspace=.40)
    for j, bb in enumerate(backbones):
        result = evidence[bb]
        for i, method in enumerate(methods[1:], 1):
            rec = result['comparisons']['GATE_DISPERSION_vs_' + method]
            y = 100*rec['difference']
            axes[0].errorbar(j+(i-2)*.19, y, yerr=[[100*(rec['difference']-rec['ci_low'])], [100*(rec['ci_high']-rec['difference'])]],
                            fmt=markers[i], color=colors[i], markersize=5, capsize=2, linewidth=1.1)
        for i, method in enumerate(methods):
            for ax, metric, scale in [(axes[1], 'intervention_rate', 100), (axes[2], 'harmful_loss', 100)]:
                ax.bar(j+(i-1.5)*.19, scale*result['rows'][method][metric], width=.17,
                       facecolor=colors[i] if i != 3 else 'white', edgecolor=colors[i],
                       linewidth=BAR_EDGE, hatch=BAR_HATCH if i == 3 else None)
    titles = [r'(a) $\Delta$MASE ($\times 10^{-2}$)', '(b) Interventions (%)', r'(c) Harm ($\times 10^{-2}$)']
    for ax, title in zip(axes, titles):
        bar_axis(ax, ['Bolt', 'TF-2.5', 'C-2'], title)
    axes[0].axhline(0, color='#7D8791', lw=.9, ls='--')
    axes[0].set_ylim(-20, 18)
    axes[0].set_yticks([-20, -10, 0, 10])
    axes[1].set_ylim(0, 100)
    axes[1].set_yticks([0, 25, 50, 75, 100])
    axes[2].set_ylim(0, 8)
    axes[2].set_yticks([0, 2, 4, 6, 8])
    from matplotlib.patches import Patch
    handles = [Patch(facecolor=colors[0], edgecolor=colors[0])]
    handles += [Line2D([], [], color=c, marker=m, linestyle='none', markersize=7) for c, m in zip(colors[1:], markers[1:])]
    fig.legend(handles, labels,
               loc='upper center', bbox_to_anchor=(.53, .985), ncol=4, columnspacing=1.6, handletextpad=.35)
    save(fig, 'fig7_gate_controls')


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


def diagnostics():
    """Six complementary diagnostics, aligned on a two-by-three full-width grid."""
    from matplotlib.lines import Line2D
    fig, axes = plt.subplots(2, 3, figsize=(7.5, 4.95))
    fig.subplots_adjust(left=.065, right=.995, bottom=.09, top=.81,
                        wspace=.30, hspace=.66)
    a,b,c,d,e,f = axes.flat
    utility_rows=read('utility.csv'); harm_rows=read('harm.csv'); severity_rows=read('severity.csv')
    action_labels=['KEEP','Ffill','Single','Multi','Ridge','SAITS']
    paired_bars(a,[float(r['best_share']) for r in utility_rows],
                [float(r['beneficial_share']) if r['beneficial_share'] else np.nan for r in utility_rows],
                action_labels,ACTION_COLORS,'(a) Action frequency (%)')
    a.set(ylim=(0,65),yticks=[0,20,40,60])
    bars(b,[100*float(r['mean_utility']) for r in utility_rows],action_labels,ACTION_COLORS,
         r'(b) Utility ($\times 10^{-2}$)')
    b.set(ylim=(-13,16),yticks=[-10,0,10])
    bars(c,[100*float(r['harmful_loss']) for r in harm_rows],SHORT,COLORS,
         r'(c) Harm ($\times 10^{-2}$)')
    c.set(ylim=(0,31),yticks=[0,10,20,30])
    paired_bars(d,[float(r['intervention_rate']) for r in harm_rows],
                [np.nan]+[float(r['conditional_hir']) for r in harm_rows[1:]],SHORT,COLORS,
                '(d) Intervention rates (%)')
    d.set(ylim=(0,115),yticks=[0,25,50,75,100])
    styles=[('o','--'),('s','--'),('^','-'),('D','-.'),('v',':'),('*','-')]
    handles=[]
    for row,color,(marker,ls) in zip(severity_rows,COLORS,styles):
        line,=e.plot([10,30,50],[float(row[k]) for k in ['s10','s30','s50']],
                    color=color,marker=marker,ls=ls,markersize=6 if marker!='*' else 8,
                    markerfacecolor=color if marker=='*' else 'white',markeredgewidth=1.0,
                    lw=2.1 if marker=='*' else 1.25,zorder=5 if marker=='*' else 2)
        handles.append(line)
    e.set(xlim=(7,53),xticks=[10,30,50],ylim=(1.38,2.09),yticks=[1.4,1.6,1.8,2.0],xlabel='Missingness (%)')
    e.set_title('(e) Forecast MASE',loc='left',fontsize=TITLE_SIZE,pad=7)
    bars(f,[100*float(r['worst_cell']) for r in severity_rows],SHORT,COLORS,
         r'(f) Worst cell ($\times 10^{-2}$)')
    f.set(ylim=(0,91),yticks=[0,25,50,75])
    for ax in axes.flat:
        ax.tick_params(axis='both',labelsize=9)
        ax.tick_params(axis='x',pad=5)
        ax.grid(False)
    # Dense labels are abbreviated consistently instead of rotated or reduced further.
    for ax in [a,b]: ax.set_xticklabels(['K','F','S','M','R','A'])
    for ax in [c,d,f]: ax.set_xticklabels(['K','BF','C','A','T','IA'])
    order=[0,3,1,4,2,5]
    fig.legend([handles[i] for i in order],[METHODS[i] for i in order],
               loc='lower left',bbox_to_anchor=(.065,.89,.93,.09),mode='expand',
               ncol=3,borderaxespad=0,handlelength=2,labelspacing=.4,fontsize=10)
    save(fig,'fig8_diagnostics')


if __name__ == '__main__':
    for name in ['fig1_example', 'fig2_Architecture']:
        if (FIG / (name + '.bmp')).exists():
            bmp_eps(name)
        elif not (FIG / (name + '.eps')).exists():
            raise FileNotFoundError(f'missing source and EPS for {name}')
    utility(); harm(); severity(); ranks(); gate_controls(); diagnostics()
    files = sorted(FIG.glob('*.eps')) + sorted((FIG/'data').glob('*.csv')) + sorted(FIG.glob('*.bmp'))
    manifest = {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (HERE/'build/figure_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print('Built 2 lossless raster EPS figures and 5 vector experimental EPS figures.')
