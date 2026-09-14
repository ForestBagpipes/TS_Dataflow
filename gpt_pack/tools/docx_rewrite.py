"""Rewrite paragraph text in a docx, keeping formatting, with real Word formulas.

The progress document holds every formula as plain text, so a symbol like tau or
an expression like Q(j,a) is just characters in a run. The target is Word's own
equation objects, the same OMML the reference paper uses throughout.

Approach. Write each paragraph as markdown with LaTeX between dollar signs, run
it through pandoc, and lift the resulting run and oMath elements out of pandoc's
docx. Then replace the original paragraph's children while keeping its
paragraph properties, so indentation, spacing and style are untouched, and copy
the original run properties onto every new text run so the font and size match
the surrounding document.

Only the content of a paragraph changes. Nothing touches styles, section
properties, tables or numbering.
"""

import copy
import hashlib
import re
import subprocess
import tempfile
from pathlib import Path

import docx
from docx.oxml.ns import qn

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"

_CACHE = {}


def md_to_children(md_text, cache_dir=None):
    """Convert one markdown paragraph into a list of w:r and m:oMath elements.

    pandoc is invoked once per distinct string. Results are cached in memory,
    and optionally on disk, because a full document pass converts several
    hundred paragraphs and most of them repeat symbols.
    """
    key = hashlib.md5(md_text.encode("utf-8")).hexdigest()
    if key in _CACHE:
        return [copy.deepcopy(el) for el in _CACHE[key]]

    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "in.md"
        dst = Path(td) / "out.docx"
        src.write_text(md_text, encoding="utf-8")
        r = subprocess.run(["pandoc", str(src), "-o", str(dst)],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"pandoc failed: {r.stderr[:400]}")
        d = docx.Document(str(dst))
        kids = []
        for p in d.paragraphs:
            for el in p._p.iterchildren():
                tag = el.tag
                if tag in (f"{W}r", f"{M}oMath", f"{M}oMathPara"):
                    kids.append(copy.deepcopy(el))
    _CACHE[key] = kids
    return [copy.deepcopy(el) for el in kids]


def _first_rpr(paragraph):
    """The run properties of the paragraph's first run, if it has one."""
    for r in paragraph._p.findall(qn("w:r")):
        rpr = r.find(qn("w:rPr"))
        if rpr is not None:
            return copy.deepcopy(rpr)
    return None


def set_paragraph_md(paragraph, md_text):
    """Replace a paragraph's content with rendered markdown, keep its format.

    Paragraph properties survive untouched. Every produced text run inherits the
    original paragraph's run properties so the font matches. Equation objects
    keep pandoc's own formatting, which is what Word expects for OMML.
    """
    rpr = _first_rpr(paragraph)
    p = paragraph._p
    # Remove existing content but not w:pPr, which carries indentation and
    # spacing that must not change.
    for el in list(p.iterchildren()):
        if el.tag != f"{W}pPr":
            p.remove(el)

    for el in md_to_children(md_text):
        if el.tag == f"{W}r" and rpr is not None:
            old = el.find(qn("w:rPr"))
            if old is not None:
                el.remove(old)
            el.insert(0, copy.deepcopy(rpr))
        p.append(el)
    return paragraph


def find_paragraph(doc, prefix, start=0, contains=None):
    """Index of the first paragraph starting with prefix, or containing text."""
    for i, p in enumerate(doc.paragraphs):
        if i < start:
            continue
        t = p.text.strip()
        if contains is not None:
            if contains in t:
                return i
        elif t.startswith(prefix):
            return i
    raise LookupError(f"paragraph not found: {prefix or contains!r}")


def replace_many(doc, edits, verbose=True):
    """Apply a list of (locator, markdown) edits.

    A locator is either an integer index or a string that the target paragraph
    starts with. Each locator must match exactly one paragraph at apply time,
    and a miss raises rather than silently skipping, because a silent skip would
    leave the old wording in place while the report claims it was rewritten.
    """
    applied = 0
    for loc, md in edits:
        if isinstance(loc, int):
            idx = loc
        else:
            idx = find_paragraph(doc, loc)
        set_paragraph_md(doc.paragraphs[idx], md)
        applied += 1
        if verbose:
            head = md[:52].replace("\n", " ")
            print(f"  [{idx:4d}] {head}")
    return applied


def insert_after(doc, anchor_idx, md_list, template_idx=None):
    """Insert new paragraphs after an anchor, copying its paragraph format."""
    tmpl = doc.paragraphs[template_idx if template_idx is not None else anchor_idx]
    prev = doc.paragraphs[anchor_idx]._p
    made = []
    for md in md_list:
        new = copy.deepcopy(tmpl._p)
        for el in list(new.iterchildren()):
            if el.tag != f"{W}pPr":
                new.remove(el)
        prev.addnext(new)
        prev = new
        para = docx.text.paragraph.Paragraph(new, tmpl._parent)
        # Seed a run so _first_rpr on the template can be reused.
        rpr = _first_rpr(tmpl)
        for el in md_to_children(md):
            if el.tag == f"{W}r" and rpr is not None:
                old = el.find(qn("w:rPr"))
                if old is not None:
                    el.remove(old)
                el.insert(0, copy.deepcopy(rpr))
            new.append(el)
        made.append(para)
    return made


def delete_paragraph(paragraph):
    """Remove a paragraph from its parent."""
    el = paragraph._p
    el.getparent().remove(el)


def count_math(doc):
    xml = doc.element.body.xml
    return xml.count("</m:oMath>")
