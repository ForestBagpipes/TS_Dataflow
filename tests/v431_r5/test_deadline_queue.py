"""A queue wait must not leave an expired admission budget usable."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/v431_r5_deadline_queue.py"
spec = importlib.util.spec_from_file_location("r5_deadline_queue", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class DeadlineQueueTest(unittest.TestCase):
    def test_expired_after_lock_never_opens_request_or_starts_worker(self):
        stamp = "2030-01-01T04:25:00+08:00"
        end = datetime.fromisoformat(stamp).timestamp()
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                Path("locks").mkdir()
                for scene in ("bolt-h96", "bolt-h192", "timesfm-h96", "timesfm-h192"):
                    p = Path("results/v431-r5/tato-scene") / scene / "run/status.json"
                    p.parent.mkdir(parents=True)
                    p.write_text(json.dumps({"status": "completed"}))
                q = Path("queue.json")
                q.write_text(json.dumps({"queue": [{"status": "not_run_preregistered", "request": "MUST_NOT_BE_OPENED"}]}))
                with patch("sys.argv", [str(SCRIPT), "--deadline", stamp, "--queue", str(q)]), patch.dict(os.environ, {"W2_CHRONOS_PY": "MUST_NOT_RUN"}), patch.object(module.time, "time", side_effect=[end-100, end+1]), patch.object(module.subprocess, "Popen") as spawn:
                    module.main()
                spawn.assert_not_called()
                status = json.loads(Path("queue.execution.json").read_text())
                self.assertEqual(status["jobs"][0]["status"], "not_run_deadline")
                self.assertFalse(status["server_shutdown_invoked"])
            finally:
                os.chdir(previous)

if __name__ == "__main__":
    unittest.main()
