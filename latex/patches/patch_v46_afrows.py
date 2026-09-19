"""Rebuild the full-ablation rows with the two scaled metrics."""
import io
import re

PATH = "latex/IntroActTS_20260919_v46.tex"
PATTERN = re.compile(r"\\ph\{AF_([A-Z0-9]+)_MASE\}.*\\ph\{AF_[A-Z0-9]+_CALLS\}")


def main() -> None:
    lines = io.open(PATH, encoding="utf-8").read().split("\n")
    rebuilt = 0
    for i, line in enumerate(lines):
        match = PATTERN.search(line)
        if not match or "_MAE}" not in line:
            continue
        tag = match.group(1)
        label = line[:line.index("&")].rstrip()
        lines[i] = (f"{label} & \\ph{{AF_{tag}_MASE}} & \\ph{{AF_{tag}_RMSSE}} & "
                    f"\\ph{{AF_{tag}_IR}} & \\ph{{AF_{tag}_CHIR}} & \\ph{{AF_{tag}_HL}} & "
                    f"\\ph{{AF_{tag}_CALLS}} " + "\\" * 2)
        rebuilt += 1
    io.open(PATH, "w", encoding="utf-8").write("\n".join(lines))
    print(f"ablation rows rebuilt: {rebuilt}")


if __name__ == "__main__":
    main()
