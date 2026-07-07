"""Unified time series window record for symmetric injection and detection.

Defines UnifiedTSWindow as a dataclass that serves as the single exchange
format between noise injection (synthetic experiments) and signal detection
(profiling, behavior extraction, calibration). Every pipeline stage receives
and returns this record type.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class UnifiedTSWindow:
    """A single time series window with metadata and quality annotations.

    Fields:
        window_id: unique integer identifier within the corpus.
        series: 1D numpy array of float, the raw time series values.
        freq: string frequency label (e.g. "H" for hourly, "D" for daily).
        dataset: string dataset name (e.g. "Electricity", "Traffic").
        split: string split name ("train", "val", "test").
        noise_label: optional string describing injected noise type, or None.
        true_quality: optional float in [-1, 1] for synthetic ground truth.
        true_difficulty: optional float in [-1, 1] for synthetic ground truth.
        profile: optional numpy array of shape (12,), filled by profiling.
        behavior: optional numpy array of shape (2L+4,), filled by behavior extraction.
        q_i: optional float quality score, filled by calibration.
        stratum: optional int, 0=bottom, 1=middle, 2=top, filled by stratification.
        seed: int random seed propagated through all stages.
    """
    window_id: int
    series: np.ndarray
    freq: str = ""
    dataset: str = ""
    split: str = "train"
    noise_label: Optional[str] = None
    true_quality: Optional[float] = None
    true_difficulty: Optional[float] = None
    profile: Optional[np.ndarray] = field(default=None, repr=False)
    behavior: Optional[np.ndarray] = field(default=None, repr=False)
    q_i: Optional[float] = None
    stratum: int = -1
    seed: int = 42

    def to_manifest_row(self) -> dict:
        """Convert to a flat dict suitable for manifest (JSON-serializable)."""
        row = {
            "window_id": self.window_id,
            "dataset": self.dataset,
            "split": self.split,
            "freq": self.freq,
            "noise_label": self.noise_label,
            "seed": self.seed,
        }
        if self.profile is not None:
            for d in range(len(self.profile)):
                row[f"profile_{d}"] = float(self.profile[d])
        if self.behavior is not None:
            for d in range(len(self.behavior)):
                row[f"behavior_{d}"] = float(self.behavior[d])
        if self.q_i is not None:
            row["q_i"] = float(self.q_i)
        if self.stratum >= 0:
            row["stratum"] = int(self.stratum)
        if self.true_quality is not None:
            row["true_quality"] = float(self.true_quality)
        if self.true_difficulty is not None:
            row["true_difficulty"] = float(self.true_difficulty)
        return row
