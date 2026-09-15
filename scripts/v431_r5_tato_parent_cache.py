"""Explicit same-parent offline native-output cache, never deployment reuse."""
import hashlib,json,time
import numpy as np

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def array_hash(x):
 x=np.ascontiguousarray(x);return hashlib.sha256(x.dtype.str.encode()+str(x.shape).encode()+x.tobytes()).hexdigest()

class ParentScopedForecast:
 def __init__(self,backend,numeric_protocol):
  self.backend=backend;self.identity=dict(backend.identity);self.numeric_protocol=dict(numeric_protocol)
  self.model_hash=digest(self.identity);self.protocol_hash=digest(self.numeric_protocol)
  self.identity['cache_numeric_protocol']=self.numeric_protocol
  self.memo={};self.calls=[];self.parent=None;self.phase=None;self.uid=None
 def set_scope(self,parent,phase,uid):
  if phase not in ('train','dev'):raise ValueError('Only explicit TRAIN or deployment scope')
  self.parent=str(parent);self.phase=phase;self.uid=str(uid)
  if phase=='dev':self.memo.clear();self.backend.cache.clear()
 def forecast(self,x,horizon):
  if self.parent is None:raise RuntimeError('Missing parent scope')
  started=time.perf_counter();x=np.asarray(x)
  identity=dict(parent=self.parent,model_identity_hash=self.model_hash,numeric_protocol_hash=self.protocol_hash,
   input_hash=array_hash(x),dtype=x.dtype.str,shape=list(x.shape),H=int(horizon))
  key=digest(identity);row=dict(cache_key=key,cache_identity=identity,cache_scope='train_cross_trial' if self.phase=='train' else 'deployment_request',
   episode_uid=self.uid,horizon=int(horizon),cache_hit=key in self.memo)
  if key in self.memo:
   entry=self.memo[key];prediction=entry['prediction'].copy()
   row.update(first_raw_file=entry['raw_file'],first_raw_sha256=entry['raw_sha256'],first_call_index=entry['index'],
    first_charged_seconds=entry['charged_seconds'],point_hash=array_hash(prediction),native_compute_seconds=0.)
   row['lookup_seconds']=time.perf_counter()-started;row['seconds']=row['lookup_seconds'];self.calls.append(row);return prediction
  self.backend.cache.clear();lookup=time.perf_counter()-started
  try:prediction=self.backend.forecast(x,horizon)
  except Exception as exc:
   row.update(status='failed',error=repr(exc),seconds=time.perf_counter()-started,lookup_seconds=lookup,native_compute_seconds=None);self.calls.append(row);raise
  raw=self.backend.calls[-1]
  if raw.get('cache_hit'):raise AssertionError('Native cache unexpectedly bypassed physical miss')
  elapsed=time.perf_counter()-started
  row.update(status='completed',raw_file=raw['raw_file'],raw_sha256=raw['raw_sha256'],first_raw_file=raw['raw_file'],
   first_raw_sha256=raw['raw_sha256'],first_call_index=len(self.calls),first_charged_seconds=elapsed,
   point_hash=array_hash(prediction),native_compute_seconds=float(raw['seconds']),lookup_seconds=lookup,seconds=elapsed,
   peak_gpu_bytes=raw.get('peak_gpu_bytes'))
  self.memo[key]=dict(prediction=prediction.copy(),raw_file=raw['raw_file'],raw_sha256=raw['raw_sha256'],index=len(self.calls),charged_seconds=elapsed)
  self.calls.append(row);return prediction.copy()
