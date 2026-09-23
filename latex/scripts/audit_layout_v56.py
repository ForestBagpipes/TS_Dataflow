"""Check layout and preservation of recorded table data, not experimental validity."""
from pathlib import Path
import hashlib
import json
import re
from pypdf import PdfReader

HERE=Path(__file__).resolve().parents[1]
NAME='IntroActTS_20260923_v56'
text=(HERE/(NAME+'.tex')).read_text(encoding='utf8')
baseline=(HERE.parent/'archive/paper_20260923/pre_reference_format'/ (NAME+'.tex')).read_text(encoding='utf8')
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

old,new=values(baseline),values(text)
assert set(old)-set(new)=={'tab:app-map'} and not set(new)-set(old)
old.pop('tab:app-map')
for label in old:
        assert sorted(old[label])==sorted(new[label]), f'Recorded numeric cells changed: {label}'
holm_table=re.search(r'\\begin\{table\}(?:(?!\\end\{table\}).)*?\\label\{tab:app-holm\}.*?\\end\{table\}',text,re.S).group(0)
for bb in ['bolt','timesfm','chronos2']:
    data=json.loads((HERE.parent/f'results/v55/evaluation/test_{bb}.json').read_text())
    for row in ['NATIVE_KEEP','BEST_FIXED','SOURCE_FIXED','R2_CART','FIXED_SAITS','TATO','TIMESNET','PSW_I','T1']:
        comp=data['comparisons']['FULL_INTROACT_vs_'+row]
        for key in ['difference','ci_low','ci_high','p_value','p_holm']:
            assert f'{comp[key]:.4f}' in holm_table, (bb,row,key)
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
        'tables_with_numeric_cells_preserved':len(new),
        'holm_rows_checked_against_saved_results':27, 'missing_labels':[],
        'overfull_boxes':0,'figures':'Unchanged in this text-only revision',
        'new_experiments':False,'scope':'Text layout and preservation of existing table values. No figures changed, no new citation audit or experimental rerun.'}
translation=(HERE/(NAME+'_中文逐段对照.md')).read_text(encoding='utf8')
assert hashlib.sha256((HERE/(NAME+'.tex')).read_bytes()).hexdigest() in translation
assert len(re.findall(r'^## 对照 \d+',translation,re.M))==301
assert len(re.findall(r'^### 共用数值表 \d+',translation,re.M))==49
report['bilingual_text_blocks']=301
(HERE/'build/layout_audit_v56.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
