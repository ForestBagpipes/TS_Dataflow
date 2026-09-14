#!/usr/bin/env python3
"""Read current preparation status; never start or change jobs."""
import json
from pathlib import Path
import subprocess

root = Path('/home/vipuser/work/work2')
stage = Path('/home/vipuser/work2-staging/bootstrap-20260914')
for label, path in (
    ('Environment installation', stage / 'status.json'),
    ('Model preparation queue', stage / 'continuation-status.json'),
    ('Model manifest', root / 'configs/v43/model_manifest.bootstrap.json'),
    ('v43 pilot queue', root / 'results/v43/pilot_queue_status.json'),
    ('v43 live monitor', root / 'results/v43/monitor_status.json'),
):
    print('\n' + label + ': ' + str(path), flush=True)
    if not path.exists():
        print('PENDING: no report yet')
        continue
    obj = json.loads(path.read_text())
    for key in ('status', 'phase', 'updated_at', 'at', 'pid', 'monitor_pid', 'environment_phase',
                'pilot_status', 'pilot_directory', 'error', 'model_exit_code', 'alerts'):
        if key in obj:
            print(f'  {key}: {obj[key]}')
    pid = obj.get('pid', obj.get('monitor_pid'))
    if pid:
        print('  pid_visible_in_current_namespace:', Path(f'/proc/{pid}').exists())
        if not Path(f'/proc/{pid}').exists():
            print('  Check host process visibility before treating this as a dead process.')
    for key, info in obj.get('models', {}).items():
        if isinstance(info, dict):
            print(f'  {key}: {info.get("status", "pending")} revision={info.get("revision", "pending")}')
        else:
            print(f'  {key}: {info}')
print('\nRecent installation log:', flush=True)
path = stage / 'logs/bootstrap.log'
transition_path = root / 'logs/v43/direct-switch-20260914/transition.json'
if transition_path.exists() and (stage / 'status.json').exists():
    transition = json.loads(transition_path.read_text())
    environment = json.loads((stage / 'status.json').read_text())
    if transition.get('resumed_pid') == environment.get('pid'):
        path = stage / 'logs/bootstrap-direct-resume.log'
        print('  task-scoped direct download; shared proxy unchanged', flush=True)
if path.exists():
    print('  ' + str(path), flush=True)
    subprocess.run(['tail', '-n', '8', str(path)], check=False)
