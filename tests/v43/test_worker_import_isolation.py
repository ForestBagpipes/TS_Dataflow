"""Regress the actual pilot failure before any model or GPU can load."""
import subprocess
import sys


def test_worker_entrypoints_without_historical_core_dependencies():
    code = '''
import importlib.abc
import sys
class RejectCore(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('statsmodels', 'ruptures'):
            raise ImportError('core dependency forbidden in isolated worker')
sys.meta_path.insert(0, RejectCore())
import introact_ts.v43.workers.tsicl_worker
import introact_ts.v43.workers.chronos_worker
assert 'introact_ts.agent' not in sys.modules
assert 'introact_ts.profiling' not in sys.modules
'''
    subprocess.run([sys.executable, '-c', code], check=True, capture_output=True, text=True)


def test_legacy_exports_preserve_verify_function_after_agent_import():
    from introact_ts import AgentConfig, IntroActAgent, verify
    from introact_ts.agent import AgentConfig as OriginalConfig, IntroActAgent as OriginalAgent
    from introact_ts.verify import verify as original_verify
    assert AgentConfig is OriginalConfig and IntroActAgent is OriginalAgent
    assert verify is original_verify and callable(verify)


def test_worker_hash_includes_parent_entrypoint_dependencies(monkeypatch):
    from introact_ts.v43 import cli
    before = cli.code_manifest()
    original = cli.file_hash
    for filename in ('__init__.py', 'types.py', 'verify.py'):
        parent = cli.ROOT / 'src/introact_ts' / filename
        with monkeypatch.context() as patch:
            patch.setattr(cli, 'file_hash', lambda p: '0' * 64 if p == parent else original(p))
            assert cli.code_manifest()['hash'] != before['hash']
