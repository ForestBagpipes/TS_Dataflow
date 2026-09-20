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
COLORS = ['#7A7A7A', '#C39B58', '#619997', '#8B7BA8', '#AA756A', '#214F79']
METHODS = ['Native KEEP', 'Best Fixed', 'R2-CART', 'Fixed SAITS', 'TATO', 'IntroAct-TS']
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
    (FIG / (name + '.eps')).write_text(header + '\n'.join(textwrap.wrap(payload, 100, break_on_hyphens=False)) + '\n~>\ngrestore\nshowpage\n%%EOF\n', encoding='ascii')
    im.thumbnail((1800, 1100))
    im.save(PREVIEW / (name + '.png'))


def read(name):
    with (FIG / 'data' / name).open(encoding='utf8', newline='') as f:
        return list(csv.DictReader(f))


def harm():
    rows = read('harm.csv')
    fig, axes = plt.subplots(1, 2, figsize=(7.1, 2.55), sharey=True)
    fig.subplots_adjust(left=.17, right=.98, bottom=.21, top=.84, wspace=.34)
    y = np.arange(len(rows))
    for ax, field, title, xmax, fmt in zip(axes,
            ['intervention_rate', 'harmful_loss'],
            ['(a) Intervention rate (%)', '(b) Harmful loss'],
            [117, .30], ['.1f', '.4f']):
        vals = [float(r[field]) for r in rows]
        ax.barh(y, vals, color=COLORS, height=.63)
        ax.set_xlim(0, xmax)
        ax.set_title(title, loc='left', pad=9, weight='bold')
        ax.set_yticks(y, METHODS)
        ax.tick_params(axis='y', length=0)
        ax.xaxis.set_major_locator(MaxNLocator(3))
        for yi, v in zip(y, vals):
            ax.text(v + xmax * .022, yi, format(v, fmt), va='center', fontsize=10)
        ax.grid(False)
    axes[0].invert_yaxis()
    save(fig, 'fig3_intervention_harm')


def severity():
    rows = read('severity.csv')
    fig, ax = plt.subplots(figsize=(6.7, 3.15))
    fig.subplots_adjust(left=.13, right=.98, bottom=.22, top=.80)
    styles = [('o','--'), ('s','--'), ('^','-'), ('D','-.'), ('v',':'), ('o','-')]
    for row, color, (marker, ls) in zip(rows, COLORS, styles):
        vals = [float(row[k]) for k in ['s10','s30','s50']]
        ax.plot([10,30,50], vals, color=color, marker=marker, ls=ls,
                markersize=6, linewidth=2.4 if row['method']=='IntroAct-TS' else 1.5,
                label=row['method'], zorder=5 if row['method']=='IntroAct-TS' else 2)
    ax.set(xlabel='Missingness (%)', ylabel='Source-macro MASE', xticks=[10,30,50], xlim=(7,53), ylim=(1.38,2.09))
    ax.legend(loc='lower center', bbox_to_anchor=(.5,1.03), ncol=3,
              columnspacing=1.3, handlelength=2.1, borderaxespad=0)
    ax.grid(False)
    save(fig, 'fig4_missingness_severity')


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
    save(fig, 'fig5_rank_agreement')


if __name__ == '__main__':
    for name in ['fig1_example', 'fig2_Architecture']: bmp_eps(name)
    harm(); severity(); ranks()
    files = sorted(FIG.glob('*.eps')) + sorted((FIG/'data').glob('*.csv')) + sorted(FIG.glob('*.bmp'))
    manifest = {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (HERE/'build/figure_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print('Built 2 lossless raster EPS figures and 3 vector experimental EPS figures.')
