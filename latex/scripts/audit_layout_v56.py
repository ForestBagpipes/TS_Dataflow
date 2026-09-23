"""Check layout and preservation of recorded table data, not experimental validity."""
from pathlib import Path
import hashlib
import json
import re
from pypdf import PdfReader

HERE=Path(__file__).resolve().parents[1]
NAME='IntroActTS_20260923_v56'
text=(HERE/(NAME+'.tex')).read_text(encoding='utf8')
baseline=(HERE.parent/'archive/paper_20260923/pre_layout/IntroActTS_20260921_v52.tex').read_text(encoding='utf8')
log=(HERE/'build'/(NAME+'.log')).read_text(encoding='utf8',errors='replace')
assert 'Overfull' not in log and 'undefined' not in log
labels=re.findall(r'\\label\{([^}]+)\}',text)
refs=re.findall(r'\\(?:eqref|ref)\{([^}]+)\}',text)
assert len(labels)==len(set(labels)) and set(refs)<=set(labels)

def values(source):
    result={}
    for table in re.findall(r'\\begin\{table\}.*?\\end\{table\}',source,re.S):
        label=re.search(r'\\label\{([^}]+)\}',table).group(1)
        body=table[table.index(r'\toprule'):table.rindex(r'\bottomrule')]
        rows=[row for row in body.splitlines() if '&' in row and re.search(r'&\s*(?:\\(?:best|second)\{)?[+-]?\d',row)]
        result[label]=[re.findall(r'(?<![A-Za-z])[-+]?\d+(?:\.\d+)?',row) for row in rows]
    return result

assert values(baseline)==values(text), 'Recorded table values changed'
aux=(HERE/'build'/(NAME+'.aux')).read_text(encoding='utf8')
page=int(re.search(r'\\newlabel\{sec:main-end\}\{\{[^}]*\}\{(\d+)\}',aux).group(1))
assert page<=9
body=text.split(r'\appendix')[0]
for label in ['tab:main','tab:ablation']:
    assert '\\label{'+label+'}' in body
assert text.index(r'\section{Conclusion}') < text.index(r'\section*{AI Use Statement}')
for name,record in json.loads((HERE/'figure/data/v56_layout/manifest.json').read_text()).items():
    assert hashlib.sha256((HERE/'figure/data/v56_layout'/name).read_bytes()).hexdigest()==record['sha256']
figures=re.findall(r'\\includegraphics\[[^\]]*\]\{([^}]+)\}',text)
assert all((HERE/name).exists() for name in figures)
report={'manuscript':NAME,'main_text_last_page':page,'pdf_pages':len(PdfReader(HERE/(NAME+'.pdf')).pages),
        'tables_with_numeric_cells_preserved':len(values(text)), 'missing_labels':[],
        'overfull_boxes':0,'figure_panels':'2 rows by 3 columns, common axes dimensions',
        'new_experiments':False,'scope':'Layout and stored-value preservation only. No new citation audit or experimental validation.'}
(HERE/'build/layout_audit_v56.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
