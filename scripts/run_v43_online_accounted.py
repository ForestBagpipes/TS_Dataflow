#!/usr/bin/env python3
"""Measure complete online process wall time, including startup and teardown."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
import psutil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    root = args.run.resolve()
    out = root / 'online-accounted-v3'
    logdir = Path('logs/v43') / root.name
    report_path = logdir / 'online-accounted-v3-process.json'
    assert not out.exists() and not report_path.exists()
    report = dict(status='running', started_at=datetime.now(timezone.utc).isoformat(),
                  output=str(out), accounting='entire child process from spawn to reaped exit')
    started = time.perf_counter()
    with (logdir / 'online-accounted-v3.log').open('x') as log, (logdir / 'online-accounted-v3-resources.jsonl').open('x') as resources:
        process = subprocess.Popen([sys.executable, 'scripts/online_v43_agent.py', str(root), '--output-name', out.name], stdout=log, stderr=subprocess.STDOUT)
        report['pid'] = process.pid
        report_path.write_text(json.dumps(report, indent=2)+'\n')
        while process.poll() is None:
            entries=[]
            try:
                family=[psutil.Process(process.pid)]
                family+=family[0].children(recursive=True)
                for item in family:
                    try: entries.append(dict(pid=item.pid, rss=item.memory_info().rss, cpu_seconds=sum(item.cpu_times()[:2])))
                    except psutil.NoSuchProcess: pass
            except psutil.NoSuchProcess: pass
            resources.write(json.dumps(dict(at=datetime.now(timezone.utc).isoformat(), processes=entries,
                available_memory=psutil.virtual_memory().available))+'\n');resources.flush()
            try:process.wait(timeout=.25)
            except subprocess.TimeoutExpired:pass
    report.update(exit_code=process.returncode,wall_seconds=time.perf_counter()-started,
                  finished_at=datetime.now(timezone.utc).isoformat(),status='completed' if process.returncode==0 else 'failed')
    if process.returncode==0:
        rows=json.loads((out/'decisions.json').read_text())
        measured=sum(r['total_governance_seconds']+r['final_forecast_seconds'] for r in rows)
        residual=report['wall_seconds']-measured
        assert residual>=0, 'component charges exceed measured whole process'
        report.update(episodes=len(rows),component_seconds=measured,unallocated_process_seconds=residual,
            unallocated_scope='Python/imports, frozen policy/context initialization, serialization, service spawn/teardown and orchestration',
            complete_seconds_per_request=report['wall_seconds']/len(rows),
            interpretation='one serial 7-request process, initialization charged once; not a steady-state throughput estimate')
    report_path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)
    raise SystemExit(process.returncode)


if __name__=='__main__':main()
