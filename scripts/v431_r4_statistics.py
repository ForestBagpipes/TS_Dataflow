#!/usr/bin/env python3
"""Independent descriptive r4 statistics and TRAIN-only oracle accounting.

Never fits a policy or generates predictions. Missing ledgers stay pending.
"""
import argparse, importlib.util, json, hashlib
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import numpy as np

ROOT=Path('results/v431-r4')
SPEC=importlib.util.spec_from_file_location('r3_verified_statistics',Path(__file__).with_name('v431_r3_statistics.py'))
R3=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(R3)
POOL=R3.POOL
SUITES=('dev','T_check','T_acq','T_fit','financial','generalization')
COMPARATORS=('FREE_ONLY','STAGED','JOINT_CLASSIFICATION','FIXED_H32','FIXED_H','FIXED_CONTROL','FIXED_REFERENCE',
             'TRAIN_BEST_FIXED_FLOW','R3_FROZEN','R3_RETRAINED','DIRECT_control','CART_H','R2_EXISTING_CART','TATO')

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False,default=lambda x:x.item() if isinstance(x,np.generic) else (_ for _ in ()).throw(TypeError(type(x).__name__)))+'\n')
def summarize(rows,field):return R3.macro(rows,field)
def finite(v):return v is not None and np.isfinite(v)
def overrun(row):
 budget=row.get('budget')
 if budget is None:
  suffix=row['policy'].rsplit('_',1)[-1]
  budget={'low':0.8140623268639832,'high':3.5}.get(suffix)
 if budget is None:raise ValueError('Missing budget identity, cannot infer compliance')
 return float(row['total_seconds'])>float(budget)+1e-12

def paired(left,right):
 l={r['episode_uid']:r for r in left};r={v['episode_uid']:v for v in right}
 if len(l)!=len(left) or len(r)!=len(right):raise ValueError('Duplicate policy episode')
 common=sorted(set(l)&set(r));out=[]
 for uid in common:
  a,b=l[uid],r[uid]
  for field in ('parent_group','source','horizon'):
   if a[field]!=b[field]:raise ValueError('Pair identity changed: '+field)
  z={k:a[k] for k in ('episode_uid','parent_group','source','raw_start','horizon','condition')}
  z.update({k:float(a[k])-float(b[k]) for k in ('mase','total_seconds','tool_count')})
  z.update(left_arm=a['arm'],right_arm=b['arm'],action_changed=a['arm']!=b['arm'],
           prediction_changed=a.get('forecast_hash')!=b.get('forecast_hash'),
           left_overrun=overrun(a),right_overrun=overrun(b))
  out.append(z)
 if not out:return {'status':'pending_no_common_rows'}
 harm=sorted(out,key=lambda z:z['mase'],reverse=True)
 parent=defaultdict(list)
 for z in out:parent[z['source'],z['parent_group']].append(z['mase'])
 return {'status':'computed_descriptive','left_episodes':len(l),'right_episodes':len(r),'common_episodes':len(out),
  'left_missing':sorted(set(r)-set(l)),'right_missing':sorted(set(l)-set(r)),
  'parents':len(parent),'mase_left_minus_right':R3.blocked_bootstrap(out,'mase'),
  'seconds_left_minus_right':R3.blocked_bootstrap(out,'total_seconds'),
  'tools_left_minus_right':R3.blocked_bootstrap(out,'tool_count'),
  'improved':sum(x['mase']<-1e-12 for x in out),'equal':sum(abs(x['mase'])<=1e-12 for x in out),
  'worsened':sum(x['mase']>1e-12 for x in out),'action_changes':sum(x['action_changed'] for x in out),
  'prediction_changes':sum(x['prediction_changed'] for x in out),
  'left_overruns':sum(x['left_overrun'] for x in out),'right_overruns':sum(x['right_overrun'] for x in out),
  'tail_harm':{'worst_10_windows':harm[:10],'worst_parent_mean':max(map(np.mean,parent.values())),
               'p95_parent_mean':float(np.quantile(list(map(np.mean,parent.values())),.95))},
  'by_source':[{ 'source':s,'difference':summarize([x for x in out if x['source']==s],'mase')} for s in sorted({x['source'] for x in out})],
  'paired_rows':out}

def coverage(rows):
 by=defaultdict(list)
 for r in rows:by[r['family'],r['policy']].append(r)
 output=[]
 for (family,policy),rr in sorted(by.items()):
  reasons=defaultdict(int);unsupported=failures=0
  for r in rr:
   t=r.get('trace',{});after=t.get('after',{});reason=after.get('reason',t.get('reason','unrecorded'));reasons[reason]+=1
   unsupported+=int(t.get('supported') is False or 'unsupported' in reason)
   failures+=int('failure' in reason or 'failed' in reason)
  output.append(dict(family=family,policy=policy,episodes=len(rr),parents=len({r['parent_group'] for r in rr}),
   mase=summarize(rr,'mase'),seconds=summarize(rr,'total_seconds'),tool_count=summarize(rr,'tool_count'),
   budget_overruns=sum(overrun(r) for r in rr),unsupported=unsupported,failures=failures,reasons=dict(reasons),
   p95_seconds=float(np.quantile([r['total_seconds'] for r in rr],.95)),max_seconds=max(r['total_seconds'] for r in rr)))
 return output

def evaluation_statistics(root):
 suites={}
 for suite in SUITES:
  paths=[root/'evaluation'/suite/'common_decisions.json',root/'evaluation'/suite/'decisions.json']
  path=next((p for p in paths if p.exists()),None)
  if path is None:suites[suite]={'status':'pending_inputs'};continue
  rows=read(path);groups=defaultdict(list)
  for row in rows:groups[row['family'],row['policy']].append(row)
  comparisons=[]
  for family in ('bolt','timesfm'):
   for budget in ('low','high'):
    left='JOINT_'+budget
    if (family,left) not in groups:continue
    names={c+'_'+budget for c in COMPARATORS}
    # Include actual merged legacy names, without assuming information equivalence.
    names|={p for f,p in groups if f==family and p.endswith('_'+budget) and any(k.lower() in p.lower() for k in ('cart','direct','r3','tato'))}
    for right in sorted(names):
     if (family,right) not in groups:continue
     comparisons.append(dict(family=family,left=left,right=right,budget=budget,**paired(groups[family,left],groups[family,right])))
  suites[suite]={'status':'completed','input':str(path),'sha256':sha(path),'coverage':coverage(rows),'comparisons':comparisons}
 return suites

def training_diagnostics(root):
 if not (root/'hot_costs.json').exists():return {'status':'pending_hot_cost_ledger'}
 spec=importlib.util.spec_from_file_location('r4_evaluation_reader',Path(__file__).with_name('v431_r4_run.py'));runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
 if root!=ROOT:raise ValueError('Canonical runner input root required')
 frozen=root/'fit/manifest.json';manifest=read(frozen) if frozen.exists() else None
 train_path=next((p for p in (root/'evaluation/T_fit/common_decisions.json',root/'evaluation/T_fit/decisions.json') if p.exists()),None)
 pathrows=read(train_path) if train_path else []
 result={'status':'completed' if train_path and manifest else 'partial_pending_frozen_library','diagnostic_only':True,
         'units':'origin-visible scaled MAE for learning; separately outer frozen TRAIN MASE','families':{},
         'warning':'Future labels choose oracle paths only in this TRAIN diagnostic; never deploy these oracle selections.',
         'hot_cost_sha256':sha(root/'hot_costs.json'),'frozen_manifest_sha256':sha(frozen) if manifest else None,
         'library_scope':'only actually evaluated frozen T_fit policies; unexecuted legacy paths excluded, not claimed beaten',
         'library_path':str(train_path) if train_path else None,'library_sha256':sha(train_path) if train_path else None}
 for family in ('bolt','timesfm'):
  b=runner.load_batch('main',family);b=b.subset(b.roles=='T_fit')
  ref=manifest['families'][family]['reference_action'] if manifest else int(np.argmin(np.dot(b.weights,b.losses)))
  groups=defaultdict(list)
  for r in pathrows:
   if r['family']==family:groups[r['episode_uid']].append(r)
  rows=[];ranking=[]
  for i,uid in enumerate(b.uids):
   meta=b.rows[i];row={'episode_uid':str(uid),'parent_group':str(b.parents[i]),'source':str(b.sources[i]),'raw_start':meta['meta']['raw_start'],
      'horizon':meta['meta']['horizon'],'condition':meta['meta']['condition'],'reference_arm':POOL[ref]}
   unique={}
   aliases=[]
   for a,arm in enumerate(POOL):
    d=meta['actions'][arm];key=(d['input_hash'],d['prediction_hash'])
    if key not in unique or b.action_costs[i,a]<b.action_costs[i,unique[key]]:unique[key]=a
    if d.get('native_alias'):aliases.append({'arm':arm,'reason':d.get('reason')})
   actions=[0] if b.fully_observed[i] else list(unique.values())
   best=min(actions,key=lambda a:(b.losses[i,a],b.action_costs[i,a],a!=ref))
   row.update(legal_unique_actions=len(actions),native_aliases=aliases,reference_loss=float(b.losses[i,ref]),
      action_oracle_loss=float(b.losses[i,best]),action_oracle_report_mase=float(b.report_losses[i,best]),action_oracle_arm=POOL[best])
   for budget_name,budget in runner.BUDGETS.items():
    feasible=[a for a in actions if b.action_costs[i,a]<=budget]
    br={'budget':budget,'feasible_actions':len(feasible),'status':'completed' if feasible else 'no_feasible_final_action'}
    if feasible:
     a=min(feasible,key=lambda a:(b.losses[i,a],b.action_costs[i,a],a!=ref));br.update(arm=POOL[a],loss=float(b.losses[i,a]),report_mase=float(b.report_losses[i,a]),cost=float(b.action_costs[i,a]))
    library=[r for r in groups[str(uid)] if r['policy'].endswith('_'+budget_name) and r['total_seconds']<=budget+1e-12]
    learned_library=[r for r in library if not r['policy'].startswith('FIXED_A') and not r['policy'].startswith('FIXED_REFERENCE')]
    if learned_library:
     chosen_learned=min(learned_library,key=lambda r:(r['learning_loss'],r['total_seconds'],r['policy']))
     br['learned_path_oracle']={k:chosen_learned[k] for k in ('policy','arm','learning_loss','mase','total_seconds','tool_count')}
    else:br['learned_path_oracle_status']='pending_T_fit_library' if train_path is None else 'no_feasible_learned_path'
    if library:
     chosen=min(library,key=lambda r:(r['learning_loss'],r['total_seconds'],r['policy']))
     br['path_oracle']={k:chosen[k] for k in ('policy','arm','learning_loss','mase','total_seconds','tool_count')}
     joint=next((r for r in groups[str(uid)] if r['policy']=='JOINT_'+budget_name),None)
     if joint and learned_library and feasible and not joint['budget_overrun']:
      br['learned_only_decomposition']={'budget_action_to_learned_path':chosen_learned['learning_loss']-br['loss'],
        'joint_to_learned_path':joint['learning_loss']-chosen_learned['learning_loss']}
     if joint and feasible and not joint['budget_overrun']:
      br['decomposition']={'reference_to_action_oracle':row['reference_loss']-row['action_oracle_loss'],
       'budget_exclusion_loss':br['loss']-row['action_oracle_loss'],
       'frozen_library_representation_and_evidence_loss':chosen['learning_loss']-br['loss'],
       'joint_path_selection_loss':joint['learning_loss']-chosen['learning_loss'],
       'joint_minus_reference':joint['learning_loss']-row['reference_loss']}
    else:br['path_oracle_status']='pending_T_fit_library' if train_path is None else 'no_feasible_frozen_path'
    row[budget_name]=br
   rows.append(row)
   # Simple historical ranking diagnostic: actual acquired historical MAE, not future proxy labels.
   for tool in b.evidence:
    if not b.supported[tool][i] or b.fully_observed[i]:continue
    atom='h32' if tool=='H32' else 'long';names=b.evidence_names[tool]
    vals=np.array([b.evidence[tool][i,names.index(atom+':mae_origin:'+a)] for a in POOL])
    pick=min(actions,key=lambda a:(vals[a],a!=ref,a));oracle=min(actions,key=lambda a:b.losses[i,a])
    ranking.append(dict(row_identity={k:row[k] for k in ('episode_uid','parent_group','source','raw_start')},tool=tool,
      historical_selected_arm=POOL[pick],actual_loss=float(b.losses[i,pick]),oracle_loss=float(b.losses[i,oracle]),
      ranking_regret=float(b.losses[i,pick]-b.losses[i,oracle]),
      evidence_gain=(vals[ref]-vals).tolist(),deployment_gain=(b.losses[i,ref]-b.losses[i]).tolist(),
      zero_evidence_gain=int(np.sum(np.abs(vals[ref]-vals)<=1e-12))))
  summary={'parents':len(set(b.parents)),'variants':len(b.uids),'reference_arm':POOL[ref],
           'reference_loss':summarize(rows,'reference_loss'),'legal_unique_action_oracle_loss':summarize(rows,'action_oracle_loss'),
           'unique_action_counts':{str(n):sum(r['legal_unique_actions']==n for r in rows) for n in range(1,6)},
           'alias_arm_records':sum(len(r['native_aliases']) for r in rows),
           'alias_limit':'Reasons retained per row. Alias is duplicate effective action, not a successful independent candidate.',
           'budgets':{}}
  for budget in runner.BUDGETS:
   feas=[dict(r,feasible_loss=r[budget]['loss']) for r in rows if 'loss' in r[budget]]
   dec=[dict(r,**r[budget]['decomposition']) for r in rows if 'decomposition' in r[budget]]
   ld=[dict(r,**r[budget]['learned_only_decomposition']) for r in rows if 'learned_only_decomposition' in r[budget]]
   summary['budgets'][budget]={'learned_library_common_variants':len(ld),
     'learned_library_representation_loss':summarize(ld,'budget_action_to_learned_path'),
     'joint_selection_gap_to_learned_library':summarize(ld,'joint_to_learned_path'),
     'feasible_variants':len(feas),'feasible_parents':len({r['parent_group'] for r in feas}),
     'excluded_variants':len(rows)-len(feas),'feasible_action_oracle_loss_conditional':summarize(feas,'feasible_loss'),
     'decomposition_common_variants':len(dec),'decomposition_common_parents':len({r['parent_group'] for r in dec}),
     'decomposition':{key:summarize(dec,key) for key in ('reference_to_action_oracle','budget_exclusion_loss','frozen_library_representation_and_evidence_loss','joint_path_selection_loss','joint_minus_reference')}}
  summary['historical_ranking']={}
  for tool in b.evidence:
   rr=[r for r in ranking if r['tool']==tool];sg=[]
   for r in rr:
    actual=np.array(r['deployment_gain']);measured=np.array(r['evidence_gain']);arms=[a for a in range(5) if a!=ref]
    nz=[a for a in arms if abs(actual[a])>1e-12 and abs(measured[a])>1e-12]
    sg.append(dict(r['row_identity'],regret=r['ranking_regret'],
     nonzero_sign_agreement=float(np.mean([np.sign(actual[a])==np.sign(measured[a]) for a in nz])) if nz else None,
     deployment_zero=sum(abs(actual[a])<=1e-12 for a in arms),evidence_zero=sum(abs(measured[a])<=1e-12 for a in arms)))
   valid=[r for r in sg if r['nonzero_sign_agreement'] is not None]
   summary['historical_ranking'][tool]={'variants':len(rr),'ranking_regret':summarize(sg,'regret'),
    'nonzero_sign_agreement':summarize(valid,'nonzero_sign_agreement'),'sign_supported_variants':len(valid),
    'deployment_zero_arm_records':sum(r['deployment_zero'] for r in sg),'evidence_zero_arm_records':sum(r['evidence_zero'] for r in sg)}
  result['families'][family]={'summary':summary,'rows':rows,'historical_ranking_rows':ranking}
 result['decomposition_limit']='Library representation/evidence and joint path selection gaps are diagnostic upper bounds, not separately identified causal evidence/acquisition effects. Conditional feasible subsets retain explicit excluded counts. Including all fixed five-arm policies makes the inclusive path oracle equal the action oracle when no overhead changes feasibility; learned-only library is therefore reported separately.'
 return result

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT);args=parser.parse_args();root=args.root
 suites=evaluation_statistics(root);diagnostics=training_diagnostics(root)
 result={'created_at':datetime.now(timezone.utc).isoformat(),'status':'completed' if all(s['status']=='completed' for s in suites.values()) and diagnostics['status']=='completed' else 'partial_pending_inputs',
  'bootstrap':'Inherited verified r3: source fixed, time-adjacent blocks of two parent, 2000 replicates, seed101; variants remain grouped',
  'limitation':'Old DEV repeatedly used; singleton USTS/financial sources cannot identify temporal uncertainty. No confirmation claim.',
  'suites':suites,'training_diagnostics':diagnostics}
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ');write(root/'statistics_runs'/stamp/'statistics.json',result);write(root/'statistics.json',result)
 lines=['# v4.3.1-r4 描述性统计与诊断','',f"状态：`{result['status']}`。输入缺失明确保留 pending，不伪造结果。",'',
 '同 source 内按原始时间相邻两个 parent 分块，2000 次 bootstrap，seed=101。变体和跨度不拆 parent；source 等权。单一 USTS parent 与金融两个单来源 parent 的时间不确定性不可识别。旧 DEV 多次查看，区间不构成独立确认。','',
 '差值为 JOINT − 对照，负数更好。尾部退步、预测改变、超预算和 unsupported 分开保留。费用使用完整路径实测值；缺预算标志不视为合规。','']
 for suite,s in suites.items():
  lines += [f'## {suite}', '', f"状态：{s['status']}。",'']
  if s['status']!='completed':continue
  lines+=['| 家族 | 对照 | 预算 | MASE 差 | 90% 描述区间 | JOINT 超支 / 对照超支 |','|---|---|---|---:|---|---:|']
  for c in s['comparisons']:
   if c['status']!='computed_descriptive':continue
   stat=c['mase_left_minus_right'];lines.append(f"| {c['family']} | {c['right']} | {c['budget']} | {stat['mean']:.6f} | [{stat['ci90'][0]:.6f}, {stat['ci90'][1]:.6f}] | {c['left_overruns']} / {c['right_overruns']} |")
  lines.append('')
 lines += ['## Oracle 解释','',f"TRAIN 诊断状态：`{diagnostics['status']}`。",'',
 '合法独特动作按真实输入与预测 hash 合并，Native alias 记录理由与费用。动作预算 oracle 只在实际最终费用可行的动作内选；完整路径 oracle 只在已经冻结并实际评估的整条策略路径内选，包含工具与最终费用。它们使用 TRAIN 未来监督，因此绝不能部署或记为方法成绩。',
 '', '分解在共同可行子集上进行，排除计数保留。策略库表示及证据误差、路径选择误差属于诊断上界，不能无额外对照直接归因成纯证据或纯主动获取因果贡献。完整覆盖表不删不可行窗口。','']
 write(root/'training_oracle_diagnostics.json',diagnostics)
 Path('docs/v431_r4_statistics.md').write_text('\n'.join(lines).rstrip()+'\n')
 print(json.dumps({'status':result['status'],'suites':{k:v['status'] for k,v in suites.items()},'diagnostics':diagnostics['status']}))
if __name__=='__main__':main()
