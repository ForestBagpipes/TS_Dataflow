import numpy as np
import pytest
from introact_ts.v43.schemas import Episode


@pytest.fixture
def episode():
    n = 160
    t = np.arange(n, dtype=np.int64)
    x = np.sin(t/12).astype(np.float64)
    x[72:88] = np.nan
    x[130] = 1e6  # observed real extreme must survive imputation
    z = np.column_stack((np.sin(t/12), np.cos(t/12)))
    availability = np.broadcast_to(t[:, None], (n, 3)).copy()
    return Episode("e1", "synthetic", "p1", "parent1", "train", 0, 0, n,
                   8, t, x, z, availability)
