#!/usr/bin/env python3
"""Run the unchanged confirmatory forecaster against the single-fit replay."""

from pathlib import Path

import v54_confirmatory_forecast as stage

stage.OUT = Path(__file__).resolve().parent.parent / "results/v55/confirmatory/replay"

if __name__ == "__main__":
    stage.main()
