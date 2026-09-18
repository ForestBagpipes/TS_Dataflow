"""Report how many words each body section spends, to decide where to trim."""
import io
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "latex/IntroActTS_20260919_v46_filled.tex"
text = io.open(path, encoding="utf-8").read()
body = text[:text.find("\\bibliography{references}")]
marks = [(m.start(), m.group(0)) for m in re.finditer(r"\\\\?sub?section\{[^}]*\}", body)]
marks = [(m.start(), m.group(0)) for m in re.finditer(r"\\(?:subsection|section)\{[^}]*\}", body)]
for i, (pos, name) in enumerate(marks):
    end = marks[i + 1][0] if i + 1 < len(marks) else len(body)
    chunk = body[pos:end]
    prose = re.sub(r"\\begin\{table\}.*?\\end\{table\}", "", chunk, flags=re.S)
    prose = re.sub(r"\\begin\{figure\}.*?\\end\{figure\}", "", prose, flags=re.S)
    floats = chunk.count("\\begin{table}") + chunk.count("\\begin{figure}")
    print(f"{name[:58]:<60} words={len(prose.split()):5d} floats={floats}")
