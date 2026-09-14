"""Sequential resident services: explicit target-backbone routing, no silent substitution."""
import copy,json,os,subprocess,sys,time
from pathlib import Path
from online_v43_agent import Services
from introact_ts.v43.cli import atomic_json
from introact_ts.v43.data_io import file_hash

def with_timesfm(model):
    model=copy.deepcopy(model);root=Path('/home/vipuser/work/work2');r=json.loads((root/'logs/v431/baselines/timesfm-preparation.json').read_text());bolt=model['models']['bolt']
    model['models']['timesfm']=dict(status='ready',validation={'status':'passed','evidence':'results/v431/20260914-sprint/timesfm/independent_replay.json'},revision=r['revision'],repo_id=r['repo_id'],snapshot_path=r['snapshot_path'],environment_python=bolt['environment_python'],environment_lock=bolt['environment_lock'],environment_lock_sha256=bolt['environment_lock_sha256'],official_code_path=r['official_code_path'],official_code_commit=r['official_code_commit'],adapter_sha256=file_hash(root/'scripts/v431_baselines/worker.py'),files={'model.safetensors':{'path':str(Path(r['snapshot_path'])/'model.safetensors'),'sha256':r['verified_sha256']}})
    return model

class R2Services(Services):
    def __init__(self,out,model,code,status,collector,family='timesfm'):
        if family!='timesfm':raise ValueError('Use unchanged Services for Bolt')
        self.out,self.model,self.code,self.status,self.collector=out,with_timesfm(model),code,status,collector
        atomic_json(out/'model_manifest.json',self.model)
        self.processes={};self.logs={};self.startup=[];allowed=out/'allowed_services.json'
        for key in ('tsicl','timesfm'):
            log=(out/(key+'-service.log')).open('x');self.logs[key]=log
            cmd=[self.model['models'][key]['environment_python']]
            if key=='tsicl':cmd += [str(Path(__file__).with_name('serve_v43_model.py')),'--key','tsicl','--allowed',str(allowed)]
            else:cmd += [str(Path(__file__).with_name('serve_v431_r2_timesfm.py')),'--allowed',str(allowed),'--output',str(out/'timesfm-native')];(out/'timesfm-native').mkdir()
            self.processes[key]=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,text=True)
        atomic_json(allowed,[dict(model=k,pid=p.pid,start_ticks=Path(f'/proc/{p.pid}/stat').read_text().rsplit(')',1)[1].split()[19]) for k,p in self.processes.items()])
        atomic_json(out/'backbone_routing.json',dict(logical_collector_forecast_slot='bolt',actual_target_backbone='timesfm',request_model_key='timesfm',method_family='timesfm',model_revision=self.model['models']['timesfm']['revision'],explicit_routing=True))
    def call(self,key,task,mode,candidates,shard):
        if key=='bolt':
            if task!='forecast':raise ValueError('Only forecast role routes to target TimesFM')
            key='timesfm'
        return super().call(key,task,mode,candidates,shard)
    def load(self,e):
        for key in ('tsicl','timesfm'):
            task='impute' if key=='tsicl' else 'forecast';shard='load-'+key
            _,path=self.request(key,task,'none',[(e,'A0_NATIVE',e.target)],shard);tick=time.perf_counter()
            response=self.command(key,dict(action='load',request=str(path),response=str(self.out/(shard+'.response.json'))))
            self.startup.append(dict(model=key,wall_seconds=time.perf_counter()-tick,load_seconds=response['service_initial_load_seconds']))
        atomic_json(self.out/'service_startup.json',self.startup)
