#!/usr/bin/env python3
"""Public metadata only: pin prospective backbones without installing or loading."""
import json,hashlib,urllib.request
from datetime import datetime,timezone
from pathlib import Path

OUT=Path('results/v431-r5/backbone-registry')
def fetch(url):
    with urllib.request.urlopen(url,timeout=60) as f:
        data=f.read(4_000_001)
    if len(data)>4_000_000:raise ValueError('Metadata size guard')
    return data
def main():
    OUT.mkdir(parents=True,exist_ok=True);rows=[]
    for repo in ['google/timesfm-3.0-pytorch','amazon/chronos-2']:
        name=repo.split('/')[-1];d=OUT/name;d.mkdir(exist_ok=True)
        row=dict(repo=repo,status='metadata_only_not_executed',checked_utc=datetime.now(timezone.utc).isoformat(),files={},failures=[])
        try:
            api=fetch('https://huggingface.co/api/models/'+repo+'?blobs=true');(d/'model_info.json').write_bytes(api);info=json.loads(api)
            row.update(revision=info['sha'],license=info.get('cardData',{}).get('license'),
              license_name=info.get('cardData',{}).get('license_name'),metadata_sha256=hashlib.sha256(api).hexdigest(),
              weights=[{k:v for k,v in x.items() if k in ('rfilename','size','lfs')} for x in info['siblings'] if x['rfilename'].endswith('.safetensors')])
            names={x['rfilename'] for x in info['siblings']}
            for file in ['README.md','LICENSE','config.json']:
                if file not in names:continue
                url=f'https://huggingface.co/{repo}/resolve/{info["sha"]}/{file}'
                b=fetch(url);(d/file).write_bytes(b);row['files'][file]=dict(url=url,sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
        except Exception as exc:row['failures'].append(type(exc).__name__+': '+str(exc));row['status']='metadata_partial'
        rows.append(row)
    result=dict(checked_utc=datetime.now(timezone.utc).isoformat(),rows=rows,
      weights_downloaded=False,environment_modified=False,inference_run=False,
      missingness='native NaN/as-of behavior requires separate real contract tests before execution',
      memory='weight byte sizes are not peak VRAM measurements; no model loaded',
      use='future protocol preparation only; cannot replace r5 failed development result')
    (OUT/'registry.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
