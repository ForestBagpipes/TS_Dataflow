"""Read-only checks of manuscript assets, references and table provenance."""
from pathlib import Path
import base64
import csv
import hashlib
import json
import re
import zlib

from PIL import Image
from pypdf import PdfReader

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parent
NAME = 'IntroActTS_20260920_v49'
tex = (HERE/(NAME+'.tex')).read_text(encoding='utf8')
log = (HERE/'build'/(NAME+'.log')).read_text(encoding='utf8',errors='replace')
labels = re.findall(r'\\label\{([^}]+)\}',tex)
refs = re.findall(r'\\(?:eqref|ref)\{([^}]+)\}',tex)
missing = sorted(set(refs)-set(labels))
assert not missing, missing
assert len(labels)==len(set(labels)), 'Duplicate labels'
assert 'undefined' not in log and 'Overfull' not in log
assert r'\figph' not in tex and r'\ph{' not in tex
assert not re.search(r'(?<!\\);',tex), 'Prose semicolon'
assert '—' not in tex and '``' not in tex

provenance=json.loads((HERE/'figure/data/provenance.json').read_text())
source=ROOT/provenance['source_manuscript']
assert hashlib.sha256(source.read_bytes()).hexdigest()==provenance['sha256']
original=source.read_text(encoding='utf8')
sources={name:dict(source_manuscript=provenance['source_manuscript'],sha256=provenance['sha256'],table=label) for name,label in provenance['tables'].items()}
sources.update(provenance.get('additional_sources',{}))
for name,record in sources.items():
    source_path=ROOT/record['source_manuscript']
    assert hashlib.sha256(source_path.read_bytes()).hexdigest()==record['sha256']
    source_text=source_path.read_text(encoding='utf8')
    table=next(m.group() for m in re.finditer(r'\\begin\{table\}.*?\\end\{table\}',source_text,re.S) if '\\label{'+record['table']+'}' in m.group())
    with (HERE/'figure/data'/name).open(encoding='utf8',newline='') as f:
        for row in csv.DictReader(f):
            for key,value in row.items():
                if key not in ['method','action','variant'] and value:
                    assert value in table, (name,key,value)

for name in ['fig1_example','fig2_Architecture']:
    eps=(HERE/'figure'/(name+'.eps')).read_text(encoding='ascii')
    data=eps.split('>> image\n',1)[1].split('~>',1)[0]
    pixels=zlib.decompress(base64.a85decode(data.encode('ascii')))
    bmp=Image.open(HERE/'figure'/(name+'.bmp')).convert('RGB')
    assert pixels==bmp.tobytes(), name+' pixel mismatch'

graphic_refs=re.findall(r'\\includegraphics\[[^\]]*\]\{([^}]+)\}',tex)
assert len(graphic_refs)==7 and all((HERE/p).exists() for p in graphic_refs)
assert {Path(p).name for p in graphic_refs}=={p.name for p in (HERE/'figure').glob('*.eps')}
pdf=PdfReader(HERE/(NAME+'.pdf'))
report={
    'manuscript':NAME, 'pdf_pages':len(pdf.pages),
    'missing_references':missing, 'overfull_boxes':0,
    'figures':graphic_refs, 'bmp_eps_pixels':'exact match for both figures',
    'experimental_csv':'matches source table values at displayed precision',
    'new_experiments_run':False,
    'scope':'Document and asset consistency only. No acceptance of v47_verified or independent replication.',
    'pdf_sha256':hashlib.sha256((HERE/(NAME+'.pdf')).read_bytes()).hexdigest(),
}
(HERE/'build/audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
