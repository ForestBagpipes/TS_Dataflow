"""The appendix map has to list the section that was added to it."""
import io

PATH = "latex/IntroActTS_20260919_v46.tex"

OLD = (r"    E. Ablations and stability & the full ablation vector, the $k$ and $\beta$ gate "
       r"grid, and mask-realisation stability & which component carries the gain, and is the "
       r"result an artefact of one mask? \\")

NEW = (r"    E. Ablations and stability & the full ablation vector, the $k$ and $\beta$ grid, "
       r"selection stability under bank subsampling, and mask-realisation stability & which "
       r"component carries the gain, and does the result rest on one configuration or one "
       r"mask? \\")


def main() -> None:
    text = io.open(PATH, encoding="utf-8").read()
    assert OLD in text, "appendix map row"
    io.open(PATH, "w", encoding="utf-8").write(text.replace(OLD, NEW, 1))
    print("appendix map updated")


if __name__ == "__main__":
    main()
