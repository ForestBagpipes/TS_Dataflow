#!/usr/bin/env python3
"""Read completed TRAIN-only bank without reading CSV values or target labels."""
import hashlib,json,contextlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'results/v431-r5/main-train-bank'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ah(a):
 a=np.ascontiguousarray(a);return hashlib.sha256(a.dtype.str.encode()+str(a.shape).encode()+a.tobytes()).hexdigest()
def main():
 cp=ROOT/'configs/v431-r5/main_train_bank.json';c=json.loads(cp.read_text());queue=json.loads((BASE/'queue.json').read_text())
 for key,path in [('runner_sha256','scripts/v431_r5_main_train_bank.py'),('worker_sha256','scripts/v431_r5_main_train_smoke.py'),('native_backend_sha256','scripts/v431_baselines/worker.py')]:assert sha(ROOT/path)==c[key]
 smoke=json.loads((ROOT/'configs/v431-r5/main_train_smoke.json').read_text());assert c['worker_sha256']==smoke['worker_sha256'] and c['native_backend_sha256']==smoke['native_backend_sha256']
 assert sha(c['inputs'])==c['inputs_sha256'];pp=ROOT/'configs/v431-r5/main_protocol_v2.json';assert sha(pp)==c['protocol_sha256'];protocol=json.loads(pp.read_text());sources={x['source']:x for x in protocol['sources']}
 metadata={x['parent']:x for x in protocol['windows_metadata']};rows=c['rows'];assert len(rows)==920 and len(c['selected'])==230 and len({r['parent'] for r in rows})==230
 assert len(c['excluded_timestamp_parents'])==2
 with np.load(c['inputs'],allow_pickle=False) as z:inputs={k:z[k].copy() for k in z.files}
 assert set(inputs)=={r['uid'] for r in rows}
 for s in c['selected']:
  w=metadata[s['parent']];lo,hi=sources[s['source']]['split_bounds']['train'];assert w['role']=='train' and s['numeric_read']==[w['read_start'],w['origin']] and lo<=w['read_start'] and w['origin']+192<=hi
 for r in rows:
  x=inputs[r['uid']];info=sources[r['source']];assert r['data_sha256']==info['file_sha256'];assert x.shape==(512,) and ah(x)==r['input_hash'] and ah(np.isfinite(x))==r['target_mask_hash']
  raw=inputs[f"{r['source']}-o{r['origin']}-raw-h{r['H']}"];assert np.isfinite(raw).all() and ah(raw)==r['raw_target_hash'];assert np.array_equal(x[np.isfinite(x)],raw[np.isfinite(x)])
  assert np.isnan(x).sum()==(0 if r['condition']=='raw' else 51)
  if r['condition']!='raw':assert np.isnan(x[230:281]).all()
 for parent in {r['parent'] for r in rows}:assert {(r['H'],r['condition']) for r in rows if r['parent']==parent}=={(h,k) for h in (96,192) for k in ('raw','target_block_10')}
 families={};pending=[]
 for family in ('bolt','timesfm'):
  d=BASE/family;sp=d/'status.json';job=next((x for x in queue['jobs'] if x['family']==family),{})
  if not sp.exists() or job.get('status')=='running':pending.append(family);continue
  st=json.loads(sp.read_text());rec=json.loads((d/'records.json').read_text()) if (d/'records.json').exists() else [];calls=json.loads((d/'calls.json').read_text()) if (d/'calls.json').exists() else []
  completed=[r for r in rec if r['status']=='completed'];failed=[r for r in rec if r['status']=='failed'];unrun=[r for r in rec if r['status']=='not_run_deadline']
  assert st['status'] in ('completed','partial','not_run_deadline','not_run_deadline_after_lock')
  if (d/'model_identity.json').exists():
   identity=json.loads((d/'model_identity.json').read_text());original=json.loads((ROOT/'results/v431-r5/main-train-smoke'/family/'model_identity.json').read_text())
   assert identity['model']==original['model'] and identity['native_backend_sha256']==c['native_backend_sha256']
  assert all(not x['cache_hit'] for x in calls)
  checked=[]
  if not (d/'predictions.npz').exists():assert not completed
  with (np.load(d/'predictions.npz',allow_pickle=False) if (d/'predictions.npz').exists() else contextlib.nullcontext(None)) as final:
   assert (set(final.files) if final is not None else set())=={r['uid'] for r in completed}
   # Each completed request is paired by the raw input/horizon identity, not by
   # a potentially shifted record index after a failed call.
   indexed={}
   for call in calls:
    with np.load(d/call['raw_file'],allow_pickle=False) as raw:key=(ah(raw['input'][0,:,0]),call['horizon'])
    indexed.setdefault(key,[]).append(call)
   for r in completed:
    key=(ah(inputs[r['uid']]),r['H']);assert indexed.get(key)
    call=indexed[key].pop(0);assert sha(d/call['raw_file'])==call['raw_sha256']
    with np.load(d/call['raw_file'],allow_pickle=False) as raw:
     p=raw['point'][0,:,0] if family=='bolt' else raw['point'][0];saved=np.load(d/(r['uid']+'.npy'),allow_pickle=False)
     assert np.isfinite(p).all() and p.shape==(r['H'],);assert np.array_equal(p,saved) and np.array_equal(p,final[r['uid']]);assert p.dtype==saved.dtype==final[r['uid']].dtype and str(p.dtype)==r['prediction_dtype'] and ah(p)==r['prediction_hash']
    checked.append(r['uid'])
  times=np.array([r['hot_request_seconds'] for r in completed]);families[family]={'status':st['status'],'requests':len(rows),'completed':len(completed),'failures':failed,'not_run_deadline':len(unrun),'unrecorded':len(rows)-len(rec),'raw_actual_calls':len(calls),'cache_hits':0,'full_subprocess_seconds':job.get('complete_subprocess_seconds'),'cold_seconds':st.get('cold_seconds'),'worker_body_seconds':st.get('wall_seconds'),'hot_sum':float(times.sum()),'hot_mean':float(times.mean()) if len(times) else None,'hot_p95':float(np.quantile(times,.95)) if len(times) else None,'hot_max':float(times.max()) if len(times) else None,'over_low':int(sum(times>.8140623268639832)),'over_high':int(sum(times>3.5)),'failed_incurred_seconds':sum(r.get('incurred_seconds',0) for r in failed),'checked_uids':checked}
  if st['status']=='completed':assert len(completed)==len(calls)==920 and not failed and not unrun
 result={'status':'passed' if len(families)==2 else 'partial_audit_waiting','config_sha256':sha(cp),'runner_sha256':c['runner_sha256'],'worker_sha256':c['worker_sha256'],'backend_sha256':c['native_backend_sha256'],'inputs_sha256':c['inputs_sha256'],'parents':230,'input_count':920,'support':c['support'],'pending':pending,'labels_read':False,'new_r5_training_support':False,'families':families}
 (BASE/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
 lines=['# TRAIN-only Native KEEP账本独立审核','','读取冻结context NPZ、协议元数据和已有预测；未读取CSV数值或未来标签，未重新推理或拟合r5。登记232个TRAIN parent扣除2个Weather时间异常parent，共230 parent；每parent完整/51点受控删除×H96/H192，共每家族920请求。来源可能在物理时间上相关，不等同230统计独立市场或新增r5有效训练支持。','', '| 家族 | 完成/登记 | 真实调用 | 完整进程秒 | 加载秒 | 请求均值/P95/最大秒 | low/high超支 |', '|---|---:|---:|---:|---:|---|---|']
 def fmt(x):return '未测' if x is None else f'{x:.6f}'
 for f,r in families.items():lines.append(f"| {f} | {r['completed']}/920 | {r['raw_actual_calls']} | {fmt(r['full_subprocess_seconds'])} | {fmt(r['cold_seconds'])} | {fmt(r['hot_mean'])}/{fmt(r['hot_p95'])}/{fmt(r['hot_max'])} | {r['over_low']}/{r['over_high']} |")
 lines+=['',f"待审核家族：{pending}。失败及截止未运行项逐条保留于audit.json，不将未运行当作零成本成功。",'', 'bank runner、原smoke冻结worker、backend和输入文件hash均核验；data身份与已冻结协议hash一致（未重读CSV标签）。920个context键与登记完全一致，selected范围均在TRAIN，H192结束不越TRAIN边界；每parent两种mask及两个H齐全，所有有效点原值保留。逐条真实调用cache_hit=false，raw point与最终npy/npz数值、dtype及hash一致。','', '只审核已进入终态的家族；请求墙钟含输入检查、清缓存、模型推断和npy持久化，首次惰性开销不删除。模型加载和完整进程分别报告，不重复相加。该账本不是完整治理请求预算证明。','', '准备程序按source单次字符串流读取，仅将selected context范围数值解析；跨窗口间隔的CSV字符串可能被遍历，但未作为当前目标解析/评分。原smoke首次准备多fetch origin字符串的历史修复仍保留，新bank使用已修复的islice上界。不能将数值标签未读扩大为底层文件字节从未被读取。','', '没有MASE、没有r5重新训练或主矩阵效果结论。现有calibration/test封存；230parent不是r5新增监督支持，八来源也不自动成为独立确认集。']
 (ROOT/'docs/v431_r5_main_train_bank_verification.md').write_text('\n'.join(lines)+'\n');print(json.dumps({k:{a:b for a,b in v.items() if a not in ('checked_uids','failures')} for k,v in families.items()},indent=2))
if __name__=='__main__':main()
