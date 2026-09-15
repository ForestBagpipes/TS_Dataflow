#!/usr/bin/env python3
"""Read-only audit of completed context-only native calls; no target reader."""
import hashlib,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'results/v431-r5/main-train-smoke'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ah(a):
 a=np.ascontiguousarray(a);return hashlib.sha256(a.dtype.str.encode()+str(a.shape).encode()+a.tobytes()).hexdigest()
def main():
 configpath=ROOT/'configs/v431-r5/main_train_smoke.json';c=json.loads(configpath.read_text());q=json.loads((BASE/'queue.json').read_text())
 assert q['status']=='finished'
 assert sha(ROOT/'scripts/v431_r5_main_train_smoke.py')==c['worker_sha256']
 assert sha(ROOT/'scripts/v431_baselines/worker.py')==c['native_backend_sha256']
 assert sha(c['inputs'])==c['inputs_sha256']
 rows=c['rows'];assert len(rows)==32 and len({r['parent'] for r in rows})==8 and len({r['source'] for r in rows})==8
 assert all(r['role']=='train' and r['L']==512 for r in rows)
 with np.load(c['inputs'],allow_pickle=False) as z:inputs={k:z[k].copy() for k in z.files}
 assert set(inputs)=={r['uid'] for r in rows}
 for r in rows:
  x=inputs[r['uid']];assert x.shape==(512,) and ah(x)==r['input_hash'] and ah(np.isfinite(x))==r['target_mask_hash']
  raw=inputs[f"{r['source']}-raw-h{r['H']}"];assert np.isfinite(raw).all() and ah(raw)==r['raw_target_hash']
  visible=np.isfinite(x);assert np.array_equal(x[visible],raw[visible]);assert np.isnan(x).sum()==(0 if r['condition']=='raw' else 51)
  if r['condition']!='raw':assert np.isnan(x[230:281]).all() and np.isfinite(x[:230]).all() and np.isfinite(x[281:]).all()
 for source in {r['source'] for r in rows}:
  rr=[r for r in rows if r['source']==source];assert {(r['H'],r['condition']) for r in rr}=={(h,d) for h in (96,192) for d in ('raw','target_block_10')}
 results={}
 for family in ('bolt','timesfm'):
  d=BASE/family;status=json.loads((d/'status.json').read_text());records=json.loads((d/'records.json').read_text());calls=json.loads((d/'calls.json').read_text());identity=json.loads((d/'model_identity.json').read_text())
  assert status['status']=='completed' and status['failures']==0 and status['forecast_target_labels_read']==0 and status['heldout_labels_read']==0 and not status['loss_computed']
  assert len(records)==len(calls)==32 and all(not x['cache_hit'] for x in calls)
  assert identity['native_backend_sha256']==c['native_backend_sha256']
  checked=[]
  with np.load(d/'predictions.npz',allow_pickle=False) as combined:
   assert set(combined.files)==set(inputs)
   for r,call in zip(records,calls):
    assert r['status']=='completed' and call['horizon']==r['H'] and sha(d/call['raw_file'])==call['raw_sha256']
    with np.load(d/call['raw_file'],allow_pickle=False) as raw:
     assert np.array_equal(raw['input'][0,:,0],inputs[r['uid']],equal_nan=True)
     p=raw['point'][0,:,0] if family=='bolt' else raw['point'][0]
     saved=np.load(d/(r['uid']+'.npy'),allow_pickle=False);assert p.shape==(r['H'],) and np.isfinite(p).all()
     assert np.array_equal(saved,p) and np.array_equal(combined[r['uid']],p)
     assert saved.dtype==p.dtype==combined[r['uid']].dtype and str(p.dtype)==r['prediction_dtype'] and ah(p)==r['prediction_hash']
     checked.append({'uid':r['uid'],'dtype':str(p.dtype),'prediction_hash':ah(p),'raw_sha256':call['raw_sha256']})
  times=np.array([r['hot_request_seconds'] for r in records]);job=next(j for j in q['jobs'] if j['family']==family);assert job['status']=='process_completed'
  results[family]={'requests':32,'parents':8,'sources':8,'actual_model_calls':32,'cache_hits':0,'failures':0,'worker_body_seconds':status['wall_seconds'],'full_subprocess_seconds':job['complete_subprocess_seconds'],'cold_model_load_seconds':status['cold_seconds'],'hot_request_sum':float(times.sum()),'hot_request_mean':float(times.mean()),'hot_request_p95':float(np.quantile(times,.95)),'hot_request_max':float(times.max()),'over_low':int(sum(times>.8140623268639832)),'over_high':int(sum(times>3.5)),'first_request_seconds':float(times[0]),'raw_native_seconds':sum(x['seconds'] for x in calls),'peak_gpu_bytes':max(x['peak_gpu_bytes'] for x in calls),'checks':checked}
 result={'status':'passed','scope':'TRAIN-only native interface; no predictive losses, no governance success','config_sha256':sha(configpath),'worker_sha256':c['worker_sha256'],'backend_sha256':c['native_backend_sha256'],'context_only_keys':list(inputs),'future_labels_read_by_audit':False,'historical_boundary_amendment':c['boundary_amendment'],'families':results}
 (BASE/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
 lines=['# 新主矩阵 TRAIN 原生接口独立核验','','只读现成输入与预测；未重跑模型，未读取CSV未来或目标标签。八来源各1个TRAIN parent，两个跨度×完整/受控删除，共每家族32请求；这是接口覆盖，不是64个独立parent或主实验成绩。','',f"配置SHA `{sha(configpath)}`；worker SHA `{c['worker_sha256']}`，backend SHA `{c['native_backend_sha256']}`。当前文件均与配置相符。",'', '| 家族 | 完整子进程秒 | 模型加载秒 | 请求均值秒 | P95秒 | 最大秒 | low超支 | high超支 |', '|---|---:|---:|---:|---:|---:|---:|---:|']
 for f,r in results.items():lines.append(f"| {f} | {r['full_subprocess_seconds']:.6f} | {r['cold_model_load_seconds']:.6f} | {r['hot_request_mean']:.6f} | {r['hot_request_p95']:.6f} | {r['hot_request_max']:.6f} | {r['over_low']} | {r['over_high']} |")
 lines+=['','32个NPZ键全部对应context-only输入；8parent×2H×2条件完整。每请求清空模型缓存，调用账本各32条且cache_hit均false。原始worker保存的input与冻结context逐值一致；有效观测未改；51点删除位置保持不变。原始point与独立npy及合并npz数值、dtype、hash一致，无失败或静默填零。','', '请求墙钟覆盖hash/输入检查、清缓存、模型调用及npy保存，首次惰性计算也在内；外层子进程另含启动/import等开销，加载单列，不重复相加。它不是完整r5治理请求的时延保证，不能替代真实策略预算验收。','', '旧准备器曾额外获取origin行字符串再break，但未将该行数值解析、保存、评分或用于选择。运行前已改islice，使迭代在origin前停止；原准备状态及修订信息保留，32输入值未变。本审计不抹除该物理I/O历史事实，也不把“未读取数值标签”等同“从未接触未来行字符串”。','', '当前run入口只加载冻结context NPZ与配置，调用原生模型后保存结果，不调用评估标签读取器；这是代码路径检查，不是通用信息流形式证明。Electricity/Exchange/Traffic缺原始时钟，不能宣称严格point-in-time。TimesFM原生内部缺失处理与Bolt原生NaN行为不同，不能称输入缺失处理机制完全相同。','', '未计算任何MASE或当前任务损失，不构成r5晋升、金融自然缺口验证或独立确认。完整逐请求hash和费用见 results/v431-r5/main-train-smoke/audit.json。']
 (ROOT/'docs/v431_r5_main_train_smoke_verification.md').write_text('\n'.join(lines)+'\n')
 print(json.dumps({k:{a:b for a,b in v.items() if a!='checks'} for k,v in results.items()},indent=2))
if __name__=='__main__':main()
