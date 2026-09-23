#!/usr/bin/env python3
"""Audit the isolated single-fit confirmatory replay."""

from pathlib import Path

import v54_confirmatory_check as stage

stage.OUT = Path(__file__).resolve().parent.parent / "results/v55/confirmatory"

if __name__ == "__main__":
    stage.main()
