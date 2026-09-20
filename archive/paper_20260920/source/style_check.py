"""Count the constructions the manuscript is supposed to avoid, in the body only."""
import io
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "latex/IntroActTS_20260919_v46_filled.tex"
text = io.open(path, encoding="utf-8").read()
body = text[:text.find("\\bibliography{references}")]
body = re.sub(r"\\begin\{equation\}.*?\\end\{equation\}", " ", body, flags=re.S)
body = re.sub(r"\\begin\{table\}.*?\\end\{table\}", " ", body, flags=re.S)
body = re.sub(r"%.*", "", body)

semis = [m.start() for m in re.finditer(r";", body) if body[m.start() - 1] != "\\"]
print("prose semicolons:", len(semis))
for pos in semis:
    print("  ;", " ".join(body[max(0, pos - 100):pos + 30].split())[-120:])
print("em dashes:", len(re.findall(r"---", body)))
print("rather than:", len(re.findall(r"rather than", body)))
for m in re.finditer(r"[^.]*rather than[^.]*\.", body):
    print("  RT:", " ".join(m.group(0).split())[:130])
