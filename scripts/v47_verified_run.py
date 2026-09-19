#!/usr/bin/env python3
"""Durable TRAIN-only experiment driver. Run after sourcing env_new_server.sh."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent


def save(path, payload):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, indent=2) + '\n')
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['pilot', 'train'], default='pilot')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    os.chdir(ROOT)
    run = 'results/v47_verified_pilot' if args.mode == 'pilot' else 'results/v47_verified'
    out = ROOT / run
    out.mkdir(parents=True, exist_ok=True)
    logs = ROOT / 'logs/v47_verified' / args.mode
    logs.mkdir(parents=True, exist_ok=True)
    status = dict(mode=args.mode, pid=os.getpid(), started=time.time(), status='running', stages=[], test_records_read=0)
    code = list((ROOT / 'src/introact_ts/v47_verified').glob('*.py')) + list((ROOT / 'scripts').glob('*verified*.py'))
    status['code_hashes'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in code}
    protocol = ROOT / 'configs/v47-verified/protocol.json'
    status['protocol_file'] = str(protocol.relative_to(ROOT))
    status['protocol_sha256'] = hashlib.sha256(protocol.read_bytes()).hexdigest()
    status_path = out / 'run_status.json'
    completed = set()
    if status_path.exists():
        if not args.resume:
            raise SystemExit('Existing run preserved; inspect it before starting another run')
        old = json.loads(status_path.read_text())
        if old['status'] == 'running':
            raise SystemExit('Refusing to resume an active run')
        for stage in old['stages']:
            if stage['status'] != 'completed':
                continue
            command = stage['command']
            if len(command) > 1 and command[1].startswith('scripts/'):
                source = command[1]
                if old['code_hashes'].get(source) != status['code_hashes'].get(source):
                    raise SystemExit(f'Completed stage source changed: {source}')
            if stage['name'].startswith('prepare_'):
                block = stage['name'].removeprefix('prepare_')
                manifest = json.loads((out / 'replay/inputs' / f'{block}.json').read_text())
                artifact = ROOT / manifest['inputs_npz']
                if hashlib.sha256(artifact.read_bytes()).hexdigest() != manifest['inputs_sha256']:
                    raise SystemExit('Prepared inputs corrupted')
            elif stage['name'].startswith('tsicl_'):
                block = stage['name'].removeprefix('tsicl_')
                manifest = json.loads((out / 'replay/tsicl' / f'{block}.json').read_text())
                artifact = ROOT / manifest['outputs_npz']
                if manifest['status'] != 'completed' or hashlib.sha256(artifact.read_bytes()).hexdigest() != manifest['outputs_sha256']:
                    raise SystemExit('TS-ICL cache corrupted or incomplete')
            elif stage['name'] != 'contracts':
                raise SystemExit('Resume for later stages requires an explicit dependency audit')
            completed.add(stage['name'])
        save(out / f'run_status.previous.{int(time.time())}.json', old)
        status['reused_stages'] = old['stages']
        completed.discard('contracts')
    save(status_path, status)
    core = os.environ['W2_CORE_PY']
    tsicl = os.environ['W2_TSICL_PY']
    chronos = os.environ['W2_CHRONOS_PY']
    baseline = '/home/vipuser/work2-envs/w2-baseline/bin/python'
    # Trust only the explicitly inspected TimesFM checkout, for child Git calls.
    os.environ.update(GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='safe.directory',
                      GIT_CONFIG_VALUE_0=str(ROOT / '.cache/v431-timesfm-source'))
    blocks = ['bankx'] if args.mode == 'pilot' else ['bankx', 'bankx2', 'train_eval']
    pilot = ['--pilot-parents', '32'] if args.mode == 'pilot' else []
    stages = [('contracts', [core, '-m', 'pytest', 'tests/v47_verified', '-q'])]
    for block in blocks:
        stages.append((f'prepare_{block}', [core, 'scripts/v47_prepare_verified.py', '--block', block, '--output-root', run] + pilot))
    for block in blocks:
        stages.append((f'tsicl_{block}', [tsicl, '-u', 'scripts/v47_tsicl_verified.py', '--block', block, '--output-root', run] + pilot))
    stages.append(('saits_crossfit', [baseline, '-u', 'scripts/v47_saits_verified.py', '--mode', 'crossfit', '--blocks', ','.join(b for b in blocks if b.startswith('bank')), '--output-root', run] + pilot + (['--epochs', '2'] if args.mode == 'pilot' else [])))
    if args.mode == 'train':
        stages.append(('saits_full', [baseline, '-u', 'scripts/v47_saits_verified.py', '--mode', 'full', '--blocks', 'train_eval', '--output-root', run]))
    for block in blocks:
        for backbone in ['bolt', 'timesfm', 'chronos2']:
            stages.append((f'forecast_{block}_{backbone}', [chronos, '-u', 'scripts/v47_forecast_verified.py', '--block', block, '--backbone', backbone, '--output-root', run]))
    if args.mode == 'train':
        for backbone in ['bolt', 'timesfm', 'chronos2']:
            stages.append((f'select_{backbone}', [core, '-u', 'scripts/v47_select_verified.py',
                           '--backbone', backbone, '--bank-blocks', 'bankx,bankx2',
                           '--output-root', run]))
            stages.append((f'evaluate_train_eval_{backbone}', [core, '-u',
                           'scripts/v47_evaluate_verified.py', '--backbone', backbone,
                           '--block', 'train_eval', '--bank-blocks', 'bankx,bankx2',
                           '--output-root', run]))
        stages.append(('development_gate', [core, '-u',
                       'scripts/v47_development_gate_verified.py', '--output-root', run]))
    try:
        for name, command in stages:
            if name in completed:
                continue
            entry = dict(name=name, command=command, started=time.time(), status='running')
            status['stages'].append(entry)
            status['phase'] = name
            save(status_path, status)
            with (logs / f'{name}.log').open('w') as handle:
                result = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT)
            entry.update(exit_code=result.returncode, elapsed_seconds=time.time()-entry['started'], status='completed' if result.returncode == 0 else 'failed')
            save(status_path, status)
            if result.returncode:
                raise RuntimeError(f'{name} failed; see {logs / (name + ".log")}')
        if args.mode == 'train':
            gate = json.loads((out / 'development_gate.json').read_text())
            status['development_gate'] = gate['status']
            status['status'] = ('completed' if gate['status'] == 'passed'
                                else 'completed_negative')
        else:
            status['status'] = 'completed'
    except BaseException as exc:
        status.update(status='failed', error=str(exc))
        raise
    finally:
        status['finished'] = time.time()
        save(status_path, status)


if __name__ == '__main__':
    main()
