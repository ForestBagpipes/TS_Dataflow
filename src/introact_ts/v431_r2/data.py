"""Audited task/evidence assembly. This offline evaluator is never an online reader."""
from collections import defaultdict
import hashlib,json,time
from pathlib import Path
import numpy as np
from introact_ts.v43.agent_fit import AgentDataset
from introact_ts.v43.agent_inputs import POOL,context_scale
from introact_ts.v43.schemas import array_hash
from introact_ts.v431.data import dirty_features,PERIODS,source_parent_weights
from introact_ts.v431.acquisition import Charge,CostInvoice

OLD=Path('results/v43/20260914T141030.324186Z-agent')
SPRINT=Path('results/v431/20260914-sprint')
ROOT=Path('results/v431-r2')
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

class R2Data:
    def __init__(self,require_timesfm=True):
        t=time.perf_counter();self.old=AgentDataset(OLD);self.meta=read(SPRINT/'partition.json');self.uids=list(self.meta)
        self.episodes=self.old.episodes;self.parents=np.array([self.meta[u]['parent_group'] for u in self.uids]);self.roles=np.array([self.meta[u]['v431_role'] for u in self.uids])
        features=[];diagnostic=[]
        for u in self.uids:
            tick=time.perf_counter();features.append(dirty_features(self.episodes[u],PERIODS[self.meta[u]['source']]));diagnostic.append(time.perf_counter()-tick)
        self.X=np.array(features);self.diagnostic_costs=np.array(diagnostic);self.complete=np.array([np.isfinite(self.episodes[u].target).all() for u in self.uids])
        self.scales=read(OLD/'mase_scales.json');self.mask=np.array([[np.nan if x is None else x for a in POOL for x in self.old.evidence[u]['strict_mask'][a]] for u in self.uids])
        h=read(SPRINT/'history/evidence.json')['target_horizon'];self.history={'bolt':np.array([[np.nan if x is None else x for a in POOL for x in h[u][a]] for u in self.uids])}
        hc=read(SPRINT/'history/tool_costs.json')['target_horizon']
        self.tool_costs={'bolt':{u:dict(mask=self.old.tool_costs[u]['strict_mask'],history=hc[u]) for u in self.uids}}
        self.L={'bolt':np.array([[self.old.labels[u,a]['mase'] for a in POOL] for u in self.uids])}
        self.MAE={'bolt':np.array([[self.old.labels[u,a]['mae'] for a in POOL] for u in self.uids])}
        with np.load(OLD/'forecasts.npz',allow_pickle=False) as f:self.predictions={'bolt':{u:{a:f[u+'_'+a] for a in POOL} for u in self.uids}}
        self.forecast_costs={'bolt':self.old.forecast_costs.copy()}
        if require_timesfm:self.load_timesfm()
        self.initialization_seconds=time.perf_counter()-t

    def ids(self,role):
        if role=='fit':return np.flatnonzero(np.isin(self.roles,['T_fit','T_gate']))
        return np.flatnonzero(self.roles==role)
    def weights(self,indices):return source_parent_weights([self.uids[i] for i in indices],self.meta)
    def state_evidence(self,family,indices=None):
        if indices is None:indices=np.arange(len(self.uids))
        return {'mask':self.mask[indices],'history':self.history[family][indices]}
    def final_invoice(self,family,i,a,diagnostic=False):
        u=self.uids[i];arm=POOL[int(a)]
        inv=CostInvoice((Charge('candidate:'+u+':'+arm,self.old.direct_costs[u][arm]),Charge('forecast:'+family+':'+u+':'+arm,self.forecast_costs[family][u+'_'+arm])))
        if diagnostic:inv=inv.merge(CostInvoice((Charge('diagnostic:'+u,float(self.diagnostic_costs[i])),)))
        return inv
    def tool_invoice(self,family,i,state):
        tools=('mask','history') if state=='both' else (state,)
        return CostInvoice(tuple(Charge('tool:'+family+':'+self.uids[i]+':'+t,self.tool_costs[family][self.uids[i]][t]) for t in tools))

    def load_timesfm(self):
        cache=ROOT/'timesfm-cache';status=read(cache/'status.json');assert status['status']=='completed'
        assert sha(cache/'predictions.npz')==status['prediction_sha256']
        records=read(cache/'records.json');indexed={}
        with np.load(cache/'predictions.npz',allow_pickle=False) as f:
            for r in records:
                pred=f[r['key']];assert array_hash(pred)==r['prediction_hash']
                key=(r['phase'],r['base_uid'],r['input_hash'])
                assert key not in indexed
                indexed[key]=(pred,r['charged_seconds'])
        tf=SPRINT/'timesfm';assert read(tf/'independent_replay.json')['status']=='passed'
        assert sha(tf/'predictions.npz')==read(tf/'status.json')['prediction_file_sha256']
        self.predictions['timesfm']={};self.forecast_costs['timesfm']={}
        tfrows=read(tf/'scored_rows.json');devcost={(r['episode_uid'],r['arm']):r for r in tfrows}
        # The baseline scorer reprices inference caches and includes governance;
        # remove exactly the same stored direct candidate cost to isolate forecast.
        with np.load(tf/'predictions.npz',allow_pickle=False) as f:
            for u in self.uids:
                self.predictions['timesfm'][u]={}
                for a in POOL:
                    if self.meta[u]['split']=='dev':
                        pred=f[u+'_'+a];r=devcost[u,a]
                        seconds=r['total_seconds']-self.old.direct_costs[u][a]
                    else:pred,seconds=indexed['current',u,array_hash(self.old.pools[u][a])]
                    assert seconds>=0
                    self.predictions['timesfm'][u][a]=pred;self.forecast_costs['timesfm'][u+'_'+a]=seconds
        losses=[];maes=[]
        with np.load(OLD/'targets.npz',allow_pickle=False) as f:
            for u in self.uids:
                y,m=f[u+'_values'],f[u+'_mask'];assert m.any()
                mae=[float(abs(self.predictions['timesfm'][u][a][m]-y[m]).mean()) for a in POOL]
                maes.append(mae);losses.append(np.array(mae)/self.scales[self.meta[u]['source']])
        self.L['timesfm']=np.array(losses);self.MAE['timesfm']=np.array(maes)
        candhash=read(SPRINT/'history/candidate_hashes.json');views=read(SPRINT/'history/view_manifest.json')
        oldinvoice=read(SPRINT/'history/model_invoices.json');oldfc=defaultdict(float)
        for r in oldinvoice:
            if r['shard'].startswith('targeth-'):oldfc[r['episode_uid'].split(':asof:',1)[0]]+=r['charged_seconds']
        hist=[];self.tool_costs['timesfm']={}
        for u in self.uids:
            e=self.episodes[u];r=512-e.horizon;y=e.target[r:r+e.horizon];mask=np.isfinite(y);v=views[u]['full'];pred={};fees={}
            for a in POOL:
                digest=candhash[v][a];pred[a],fees[digest]=indexed['history',u,digest]
            base=float(abs(pred['A0_NATIVE'][mask]-y[mask]).mean()) if mask.any() else None
            hist.append([x for a in POOL for x in ((base-float(abs(pred[a][mask]-y[mask]).mean()))/context_scale(e),0.,float(mask.mean()))] if mask.any() else [x for a in POOL for x in (np.nan,np.nan,0.)])
            nonforecast=self.tool_costs['bolt'][u]['history']-oldfc[u];assert nonforecast>=0
            self.tool_costs['timesfm'][u]=dict(mask=self.old.tool_costs[u]['strict_mask'],history=nonforecast+sum(fees.values()))
        self.history['timesfm']=np.array(hist)
