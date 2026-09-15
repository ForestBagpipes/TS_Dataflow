#!/usr/bin/env python3
"""Append audited final report to a new progress DOCX, preserving the old file."""
from pathlib import Path
import re,zipfile,xml.etree.ElementTree as E

NS='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
def tag(s):return '{'+NS+'}'+s
def paragraph(text):
    p=E.Element(tag('p'));run=E.SubElement(p,tag('r'));t=E.SubElement(run,tag('t'))
    t.set('{http://www.w3.org/XML/1998/namespace}space','preserve');t.text=text
    return p

def main():
    source=Path('docx/【work2】胡宏彬-进度文档-20260916-r5.docx')
    target=source.with_name('【work2】胡宏彬-进度文档-20260916-r5-final.docx')
    if target.exists():raise RuntimeError('Preserve existing final progress document')
    marker='2026-09-16 r5 截止前最终交付：研究未晋升'
    with zipfile.ZipFile(source) as archive:
        original=archive.read('word/document.xml')
        parsed=E.fromstring(original);old_body=parsed.find(tag('body'))
        prefix=re.search(rb'<([^ <>:]+):body(?:\s|>)',original).group(1)
        insertion=original.rfind(b'</'+prefix+b':body>')
        if old_body.find(tag('sectPr')) is not None:
            insertion=original.rfind(b'<'+prefix+b':sectPr',0,insertion)
        if insertion<0:raise ValueError('Cannot locate original body boundary')
        body=E.Element(tag('body'))
        body.append(paragraph(marker))
        for filename in ('docs/v431_r5_report.md','docs/v431_r5_final_snapshot.md'):
            content=Path(filename).read_text();table=None
            for line in content.splitlines():
                if line.startswith('|'):
                    fields=[x.strip() for x in line.strip().strip('|').split('|')]
                    if all(re.fullmatch(r'[-: ]+',x) for x in fields):continue
                    if table is None:
                        table=E.SubElement(body,tag('tbl'))
                        props=E.SubElement(table,tag('tblPr'));style=E.SubElement(props,tag('tblStyle'));style.set(tag('val'),'TableGrid')
                    row=E.SubElement(table,tag('tr'))
                    for field in fields:
                        cell=E.SubElement(row,tag('tc'));cell.append(paragraph(field.replace('**','').replace('`','')))
                else:
                    table=None
                    if line.strip():body.append(paragraph(line.lstrip('# ').replace('**','').replace('`','')))
        replacement=original[:insertion]+b''.join(E.tostring(child,encoding='utf-8') for child in body)+original[insertion:]
        # Earlier exports renamed XML prefixes but left mc:Ignorable values.
        # Restore missing namespace aliases from the project's original Word file.
        with zipfile.ZipFile('docx/【work2】胡宏彬-进度文档-20260821.docx') as baseline:
            bindings=dict(re.findall(rb'xmlns:([^= ]+)="([^"]+)"',baseline.read('word/document.xml')[:10000]))
        root_tag=re.search(rb'<[^?!][^>]+>',replacement)
        declaration=root_tag.group();present=dict(re.findall(rb'xmlns:([^= ]+)="([^"]+)"',declaration))
        ignorable=re.search(rb':Ignorable="([^"]*)"',declaration)
        needed=[] if ignorable is None else ignorable.group(1).split()
        extra=b''.join(b' xmlns:'+name+b'="'+bindings[name]+b'"' for name in needed if name not in present)
        replacement=replacement[:root_tag.end()-1]+extra+replacement[root_tag.end()-1:]
        E.fromstring(replacement)
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as result:
            for item in archive.infolist():
                data=replacement if item.filename=='word/document.xml' else archive.read(item.filename)
                result.writestr(item,data)
    with zipfile.ZipFile(target) as archive:
        text=''.join(E.fromstring(archive.read('word/document.xml')).itertext())
        if marker not in text:raise AssertionError('Final text missing')
    print(str(target))
if __name__=='__main__':main()
