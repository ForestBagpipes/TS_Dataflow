"""Actual context-only probe and final-action requests for r3 deployment."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import time
import numpy as np
import yaml
from introact_ts.v43.agent_collect import Collector
from introact_ts.v43.agent_inputs import POOL
from introact_ts.v43.candidates import prepare_model_input
from introact_ts.v43.cli import atomic_json, code_manifest
from introact_ts.v43.p2_candidates import ridge_candidate
from introact_ts.v43.schemas import Candidate, array_hash, json_hash, require, verify_impute
from introact_ts.v431.acquisition import Charge, CostInvoice
from .probe import prepare_probe, registered_specs, score_probe, proxy_mismatch

ROOT = Path(__file__).resolve().parents[3]
OLD = ROOT / 'results/v43/20260914T141030.324186Z-agent'


class LiveRuntime:
    def __init__(self, out, family, first_episode):
        self.out = Path(out).resolve()
        self.out.mkdir(exist_ok=False, parents=True)
        self.family = family
        self.counter = 0
        sys.path.insert(0, str(ROOT / 'scripts'))
        from online_v43_agent import Services
        from v431_r2_services import R2Services
        code = code_manifest()
        require(code['hash'] == json.loads((OLD / 'code_manifest.json').read_text())['hash'], 'Legacy worker changed')
        model = json.loads((OLD / 'model_manifest.json').read_text())
        config = yaml.safe_load((OLD / 'resolved_config.yaml').read_text())
        self.status = dict(status='running', pid=os.getpid(), family=family, future_labels_read=0, heldout_labels_read=0)
        atomic_json(self.out / 'code_manifest.json', code)
        atomic_json(self.out / 'model_manifest.json', model)
        self.collector = Collector(config, self.out, code, self.status, model)
        cls = Services if family == 'bolt' else R2Services
        self.services = cls(self.out, model, code, self.status, self.collector)
        try:
            self.services.load(first_episode)
            self.collector.call = self.services.call
        except BaseException:
            self.services.close()
            raise
        self.identity = json_hash(self.services.model['models'][family])

    def prefix(self, purpose):
        self.counter += 1
        return f'r3-{self.counter:04d}-{purpose}'

    def probe(self, episode, atom, scale, reference_arm):
        started = time.perf_counter()
        prepared = prepare_probe(episode, registered_specs(episode.horizon)[atom], scale)
        require(prepared.status == 'prepared', 'Probe unavailable: ' + str(prepared.reason))
        prefix = self.prefix(atom)
        pools, _, _ = self.collector.pools([prepared.view], prefix)
        predictions, _ = self.collector.forecasts([prepared.view], pools, prefix)
        values = {a: predictions[prepared.view.uid, a] for a in POOL}
        # Total wall covers independent preparation, governance, real forecast,
        # scoring and feature construction; callers must not add this again.
        provisional = CostInvoice((Charge(prefix, time.perf_counter() - started),))
        result = score_probe(prepared, self.family, values, self.identity, provisional.as_dict(), reference_arm=reference_arm).to_dict()
        result['checkpoint_record_hash'] = self.identity
        result['live_runtime_source_sha256'] = __import__('hashlib').sha256(Path(__file__).read_bytes()).hexdigest()
        result['identity_scope'] = 'actual checkpoint record; offline cache producer identity is a separate hash'
        result['psi'] = proxy_mismatch(episode, prepared.view, scale)
        result['candidate_hashes'] = {a: array_hash(pools[prepared.view.uid][a]) for a in POOL}
        result['invoice'] = CostInvoice((Charge(prefix, time.perf_counter() - started),)).as_dict()
        result['prepared'] = prepared.metadata()
        atomic_json(self.out / (prefix + '.probe.json'), result)
        return result

    def final(self, episode, arm):
        prefix = self.prefix('final')
        start = time.perf_counter()
        detail = dict(status='completed')
        if arm == 'A0_NATIVE':
            candidate = episode.target
        elif arm == 'A0_FFILL':
            candidate = prepare_model_input(episode.target, native_nan=False)
        elif arm in ('A2_SINGLE', 'A3_COV'):
            if np.isnan(episode.target).any():
                values, _ = self.collector.model_call('tsicl', 'impute', 'none' if arm == 'A2_SINGLE' else 'past_only',
                    [(episode, arm, episode.target)], prefix + '-impute')
                candidate = values[episode.uid, arm]
            else:
                candidate = episode.target
                detail['status'] = 'not_needed'
        elif arm == 'A4_RIDGE_CONTEXT':
            result, detail = ridge_candidate(episode)
            candidate = result.target
        else:
            raise ValueError('Unknown frozen governance action')
        verify_impute(episode, Candidate(episode.uid, arm, candidate))
        governance = time.perf_counter() - start
        start = time.perf_counter()
        values, _ = self.collector.model_call('bolt', 'forecast', 'none', [(episode, arm, candidate)], prefix + '-forecast')
        forecast = time.perf_counter() - start
        invoice = CostInvoice((Charge(prefix + '-governance', governance), Charge(prefix + '-forecast', forecast)))
        return candidate, values[episode.uid, arm], invoice, detail

    def close(self):
        self.services.close()
        self.status['status'] = 'services_closed'
        atomic_json(self.out / 'status.json', self.status)
