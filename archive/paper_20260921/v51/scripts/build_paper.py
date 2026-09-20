"""Build the sole active manuscript with fail-fast LaTeX and bibliography passes."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parents[1]
NAME = 'IntroActTS_20260920_v51'
BUILD = HERE / 'build'
BUILD.mkdir(exist_ok=True)
env = dict(os.environ)
if Path('D:/texlive/2025/bin/windows').exists():
    env['PATH'] = 'D:/texlive/2025/bin/windows' + os.pathsep + env.get('PATH','')


def run(cmd, log):
    with (BUILD/log).open('w', encoding='utf8') as out:
        subprocess.run(cmd, cwd=HERE, env=env, stdout=out, stderr=subprocess.STDOUT, check=True)


run([sys.executable, str(HERE/'scripts/build_figures.py')], 'figures.log')
gs = shutil.which('gswin64c') or shutil.which('gs')
if not gs and Path('D:/texlive/2025/tlpkg/tlgs/bin/gswin64c.exe').exists():
    gs = 'D:/texlive/2025/tlpkg/tlgs/bin/gswin64c.exe'
    gsroot = Path('D:/texlive/2025/tlpkg/tlgs')
    env['GS_LIB'] = os.pathsep.join(str(gsroot/p) for p in
        ['Resource/Init','lib','kanji','Resource/Font','Resource/CMap',
         'Resource/Encoding','Resource/ColorSpace','Resource/Decoding',
         'Resource/SubstCID','Resource/CIDFont','Resource/CIDFSubst','Resource/IdiomSet'])
if not gs:
    raise SystemExit('Ghostscript is required for EPS compilation.')
for name in ['fig1_example','fig2_Architecture','fig3_action_utility','fig4_intervention_harm',
             'fig5_missingness_severity','fig6_rank_agreement']:
    run([gs, '-q', '-dBATCH', '-dNOPAUSE', '-dSAFER', '-dEPSCrop',
         '-sDEVICE=pdfwrite', '-dAutoRotatePages=/None',
         '-dDownsampleColorImages=false', '-dDownsampleGrayImages=false',
         '-dAutoFilterColorImages=false', '-dColorImageFilter=/FlateEncode',
         '-sOutputFile=build/'+name+'-eps-converted-to.pdf',
         'figure/'+name+'.eps'], name+'.log')
latex = shutil.which('pdflatex', path=env['PATH'])
bibtex = shutil.which('bibtex', path=env['PATH'])
if not latex or not bibtex:
    raise SystemExit('pdflatex and bibtex are required.')
cmd = [latex, '-interaction=nonstopmode', '-halt-on-error', '-file-line-error',
       '-output-directory=build', NAME+'.tex']
run(cmd,'pass1.log')
run([bibtex,'build/'+NAME], 'bibtex.log')
run(cmd,'pass2.log')
run(cmd,'pass3.log')
shutil.copy2(BUILD/(NAME+'.pdf'), HERE/(NAME+'.pdf'))
print(HERE/(NAME+'.pdf'))
