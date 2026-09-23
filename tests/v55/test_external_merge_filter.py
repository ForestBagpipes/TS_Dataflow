"""Hardware verification shards must never duplicate the main baseline rows."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from v54_external_merge import main_shard


def test_excludes_verification_and_smoke_shards():
    assert main_shard(Path("test__t1-etth1-full.npz"))
    assert not main_shard(Path("test__t1-etth1-verify.npz"))
    assert not main_shard(Path("test__smoke.npz"))
    assert not main_shard(Path("test.npz"))
