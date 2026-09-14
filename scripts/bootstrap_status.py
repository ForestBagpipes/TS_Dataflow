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
):
    print('\n' + label + ': ' + str(path))
    if not path.exists():
        print('PENDING: no report yet')
        continue
    obj = json.loads(path.read_text())
    for key in ('status', 'phase', 'updated_at', 'pid', 'environment_phase', 'error', 'model_exit_code'):
        if key in obj:
            print(f'  {key}: {obj[key]}')
    if obj.get('pid'):
        print('  pid_exists:', Path(f'/proc/{obj["pid"]}').exists())
    for key, info in obj.get('models', {}).items():
        print(f'  {key}: {info.get("status", "pending")} revision={info.get("revision", "pending")}')
print('\nRecent installation log:')
path = stage / 'logs/bootstrap.log'
if path.exists():
    subprocess.run(['tail', '-n', '8', str(path)], check=False)
