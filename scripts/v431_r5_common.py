#!/usr/bin/env python3
"""Frozen legacy common baselines, free-coverage repair, TRAIN-only space audit."""
import argparse,copy,itertools,json,time
from pathlib import Path
import joblib
import numpy as np
from introact_ts.v43.agent_inputs import POOL
from introact_ts.v431_r4.trajectory_dataset import group_weights
from v431_r4_run import row_record,summarize
from v431_r5_run import load,frozen,write,sha,BUDGETS

ROOT=Path('results/v431-r5');R4=Path('results/v431-r4')
BASES=('FIXED_A0_NATIVE','FIXED_A0_FFILL','FIXED_A2_SINGLE','FIXED_A3_COV',
       'FIXED_A4_RIDGE_CONTEXT','TRAIN_BEST_FIXED_FLOW','LEGACY_DIRECT_control',
       'LEGACY_CART_H','R2_EXISTING_CART','JOINT','TATO_NATIVE_8')


def fixed_simple_freeze():
    target=ROOT/'strong_simple_freeze.json'
    if target.exists():return json.loads(target.read_text())
    old=json.loads((R4/'common_fixed_freeze.json').read_text())
    result=dict(status='frozen',source_path=str(R4/'common_fixed_freeze.json'),
      source_sha256=sha(R4/'common_fixed_freeze.json'),selection_role='inherited original T_fit only',
      dev_consulted=False,rule='Use previously TRAIN-selected strongest feasible fixed flow; no DEV family routing',
      families=old['families'],main_admission_comparison='TRAIN_BEST_FIXED_FLOW_high',
      low_support_warning='Old low budget had no uniformly feasible fixed flow; retain fallback, not a feasible champion')
    write(target,result);return result


def repaired_coverage(d,family):
    models=joblib.load(R4/'fit/models.joblib');p=models[family]['JOINT_high'];tree=p.tree
    assert tree['kind']=='acquire' and tree['tool']=='H'
    term=tree['terminal'];assert term['kind']=='split' and term['feature']=='long:covariate_coverage'
    b=d['batch'];rows=[]
    for bn,budget in BUDGETS.items():
        for i,x in enumerate(b.visible):
            tick=time.perf_counter();features=dict(zip(p.free_names,x[:len(p.free_names)]))
            available=max(0.,budget-float(d['feature_seconds'][i]));fallback=p._fallback(features,available)
            coverage=x[b.free_names.index('known_history_covariate_coverage')]
            if b.fully_observed[i]:a=0;reason='complete_target_KEEP'
            elif not np.isfinite(coverage):a=fallback;reason='unsupported_free_metadata_fallback'
            else:
                a=term['left' if coverage<=term['threshold'] else 'right']['arm'];reason='frozen_r4_threshold_free_metadata'
                if p.cost.action_estimate(a,features)>available:a=fallback;reason='budget_fallback'
            elapsed=time.perf_counter()-tick
            total=float(d['feature_seconds'][i]+d['governance_costs'][i,a]+d['forecast_costs'][i,a]+elapsed)
            trace=dict(action=int(a),tool=None,tool_count=0,total_seconds=total,reason=reason,
                       coverage=None if not np.isfinite(coverage) else float(coverage),
                       frozen_threshold=term['threshold'],decision_seconds=elapsed,
                       estimated_final_seconds=p.cost.action_estimate(a,features),
                       historical_model_calls=0,total_budget_unmet=p.cost.action_estimate(a,features)>available)
            rows.append(row_record(b,i,'R4_FREE_COVERAGE_'+bn,trace,p.reference_arm,budget,
                origin='r4-free-metadata-repair',information='same frozen r4 split; coverage computed without historical model'))
    return rows


def space():
    out=ROOT/'space'
    if (out/'status.json').exists():raise RuntimeError('Preserve first space audit')
    fixed_simple_freeze();models,_=frozen();summaries=[];paths=[];windows=[]
    for family in ('bolt','timesfm'):
        d=load('main',family,'T_fit');b=d['batch'];refmodel=models['families'][family]['reference']
        for bn,budget in BUDGETS.items():
            rows=[]
            for i,uid in enumerate(b.uids):
                ref=refmodel.predict(b.visible[i],bool(b.fully_observed[i]));pred=d['predictions'][i]
                unique=[]
                for a in range(5):
                    if not any(np.array_equal(pred[a],pred[j]) for j in unique):unique.append(a)
                seqs=[(ref,)]
                if not b.fully_observed[i]:
                    other=[a for a in range(5) if a!=ref]
                    seqs += [(ref,)+q for k in (1,2) for q in itertools.permutations(other,k)]
                window=[]
                for seq in seqs:
                    seen=set();cost=float(d['feature_seconds'][i]);charges=[]
                    for a in seq:
                        key=d['cache_metadata'][i][a]['input_version_hash'];reused=key in seen
                        cg=float(d['governance_costs'][i,a]);cf=0. if reused else float(d['forecast_costs'][i,a]);seen.add(key)
                        cost+=cg+cf;charges.append(dict(action=a,governance_seconds=cg,forecast_seconds=cf,forecast_reused=reused))
                    # Conservative, declared solver/output reservations are kept
                    # separate from measured historical component costs.
                    reserve=.001+.05*(len(seq)-1)
                    feasible=cost+reserve<=budget
                    a=min(seq,key=lambda a:(b.losses[i,a],a!=ref,a))
                    item=dict(family=family,budget_name=bn,uid=str(uid),parent=str(b.parents[i]),
                        query_actions=list(seq),measured_component_seconds=cost,
                        solver_output_reservation_seconds=reserve,admission_seconds=cost+reserve,
                        feasible=feasible,oracle_final_action=int(a),oracle_loss=float(b.losses[i,a]),charges=charges)
                    window.append(item);paths.append(item)
                feasible=[r for r in window if r['feasible']]
                best=min(feasible,key=lambda r:(r['oracle_loss'],r['admission_seconds'])) if feasible else None
                feasible_actions=set(a for r in feasible for a in r['query_actions'])
                gain=0. if best is None else float(b.losses[i,ref]-best['oracle_loss'])
                rr=dict(family=family,budget_name=bn,uid=str(uid),parent=str(b.parents[i]),source=str(b.sources[i]),
                    reference_action=int(ref),unique_predictions=len(unique),at_least_three=len(unique)>=3,
                    aliases=sum(bool(m.get('alias')) for m in d['cache_metadata'][i]),
                    declared_legal_actions=1 if b.fully_observed[i] else 5,
                    feasible_actions=len(feasible_actions),feasible_paths=len(feasible),
                    reference_infeasible=not window[0]['feasible'],reference_loss=float(b.losses[i,ref]),
                    feasible_oracle_gain=gain,best_path=None if best is None else best['query_actions'],
                    best_path_cost=None if best is None else best['admission_seconds'])
                rows.append(rr);windows.append(rr)
            w=group_weights(b.parents,b.sources)
            summaries.append(dict(family=family,budget_name=bn,role='T_fit',parents=len(set(b.parents)),variants=len(b.uids),
                paths=sum(len(r['query_actions'])>0 for r in paths if r['family']==family and r['budget_name']==bn),
                at_least_three_count=sum(r['at_least_three'] for r in rows),
                reference_infeasible_count=sum(r['reference_infeasible'] for r in rows),
                **{k:float(np.dot(w,[r[k] for r in rows])) for k in
                  ('unique_predictions','at_least_three','aliases','declared_legal_actions','feasible_actions','reference_loss','feasible_oracle_gain')}))
    write(out/'paths.json',paths);write(out/'windows.json',windows);write(out/'summary.json',summaries)
    write(out/'status.json',dict(status='completed',role='TRAIN fit only',model_sha256=sha(ROOT/'fit/models.joblib'),
        oracle_is_diagnostic_only=True,no_future_free_tool_choice=True,cost_scope='measured trial components plus separately declared solver/output reservation',
        paths_sha256=sha(out/'paths.json'),summary_sha256=sha(out/'summary.json')))
    print(json.dumps(summaries,ensure_ascii=False),flush=True)


def merge(suite):
    name='dev' if suite=='main' else suite;out=ROOT/'evaluation'/name
    if (out/'common_status.json').exists():raise RuntimeError('Preserve first common result')
    fixed_simple_freeze()
    status=json.loads((out/'status.json').read_text());assert status['status']=='completed'
    rows=json.loads((out/'decisions.json').read_text());oldpath=R4/'evaluation'/name/'common_decisions.json'
    old=json.loads(oldpath.read_text());oldsha=sha(oldpath);selected={a+'_'+bn for a in BASES for bn in BUDGETS}
    for r in old:
        if r['policy'] not in selected:continue
        r=copy.deepcopy(r);r['inherited_policy']=r['policy']
        if r['policy'].startswith('JOINT_'):r['policy']='R4_'+r['policy']
        r['legacy_cost_scope']=r.get('cost_scope','inherited r4 audited full component invoice; not newly measured wall latency')
        r['baseline_provenance']=dict(path=str(oldpath),sha256=oldsha)
        rows.append(r)
    for family in ('bolt','timesfm'):
        d=load(suite,family,'dev' if suite=='main' else None);b=d['batch'];uid_index={str(u):i for i,u in enumerate(b.uids)}
        rr=[r for r in rows if r['family']==family]
        for r in rr:
            assert r['episode_uid'] in uid_index
            i=uid_index[r['episode_uid']]
            assert r['parent_group']==str(b.parents[i]) and r['source']==str(b.sources[i])
            if not r['policy'].startswith('TATO'):
                a=POOL.index(r['arm'])
                assert r['candidate_hash']==b.rows[i]['actions'][r['arm']]['input_hash']
                assert abs(r['mase']-b.report_losses[i,a])<1e-9
        for policy in set(r['policy'] for r in rr):
            assert {r['episode_uid'] for r in rr if r['policy']==policy}==set(uid_index)
        rows.extend(repaired_coverage(d,family))
    table,sources=summarize(rows);write(out/'common_decisions.json',rows);write(out/'common_table.json',table);write(out/'common_sources.json',sources)
    write(out/'common_status.json',dict(status='completed',rows=len(rows),policies=len(table),
      inherited_baseline_sha256=sha(oldpath),r5_decision_sha256=sha(out/'decisions.json'),
      strong_simple_freeze_sha256=sha(ROOT/'strong_simple_freeze.json'),
      common_uid_parent_source_candidate_loss_checks=True,heldout_labels_read=False))
    print(json.dumps(dict(suite=suite,rows=len(rows),policies=len(table))))


def render_docs():
    title=['# v4.3.1-r5 完整共同开发主表','',
      '结论：本轮候选未满足开发准入。Bolt高预算与免费参考预测相同；TimesFM r5弱于免费参考及CART_H。额外当前试运行和联合投影尚未形成跨家族治理优势。calibration/test不解封。','',
      'MASE越低越好；秒为原实际模型组件账本加本轮CPU处理，非自然单请求墙钟。费用保留冷/热原审计范围，不能因缓存复用归零。超支按该表预算判定。—为原协议缺项，不是误差零。','',
      '旧DEV为26 parent、156相关变体；金融为2 parent、12变体，部分重叠，均非独立确认。source/parent/variant宏平均，不按变体数冒充独立支持。']
    for suite,label in [('dev','旧DEV'),('financial','金融附表')]:
        table=json.loads((ROOT/'evaluation'/suite/'common_extended_table.json').read_text());lookup={(r['family'],r['policy']):r for r in table}
        for bn,budget in BUDGETS.items():
            title += ['',f'## {label}：{bn}预算 {budget:.9f} 秒','',
                      '| 方法 | Bolt MASE | 秒/窗 | 超支 | TimesFM MASE | 秒/窗 | 超支 |',
                      '|---|---:|---:|---:|---:|---:|---:|']
            names=sorted({r['policy'][:-len(bn)-1] for r in table if r['policy'].endswith('_'+bn)})
            for name in names:
                cells=[name]
                for f in ('bolt','timesfm'):
                    r=lookup.get((f,name+'_'+bn));cells+=['—']*3 if r is None else [f"{r['mase']:.6f}",f"{r['total_seconds']:.6f}",str(r['budget_overruns'])]
                title.append('| '+' | '.join(cells)+' |')
        title += ['',f'### {label}：真正全部五臂，高成本对照','',
                  '| 家族 | MASE | 秒/窗 | 超过3.5秒 |','|---|---:|---:|---:|']
        for f in ('bolt','timesfm'):
            r=lookup[f,'ALL_FIVE_EXECUTED_UNCAPPED'];title.append(f"| {f} | {r['mase']:.6f} | {r['total_seconds']:.6f} | {r['budget_overruns']} |")
    title += ['', '## 对照身份和限制','',
      '- FIXED_A0_NATIVE/FFILL/A2_SINGLE/A3_COV/A4_RIDGE_CONTEXT为五臂固定方法；完整有效target仍直接KEEP。',
      '- TRAIN_BEST_FIXED_FLOW继承原T_fit冻结规则；不存在的低预算冠军保持缺项。',
      '- LEGACY_DIRECT_control、LEGACY_CART_H是r4尺度修复后的强简单对照。R2_EXISTING_CART使用不同历史/遮挡信息，不当同信息消融。',
      '- R4_JOINT为原结果；R4_FREE_COVERAGE沿原阈值/动作，通过当前mask计算覆盖，无历史模型费。',
      '- R5、R5_RAW、R5_SINGLE是自适应轨迹，不能将它们的差异全部归因于终态投影；固定轨迹归因另见机制表。',
      '- FIXED_ORDER_3与FIXED_COUNT_2仍受预算限制；ALL_FIVE同样受准入和失败停止限制，其名称不保证每窗实际执行5个版本。',
      '- ALL_FIVE_EXECUTED_UNCAPPED对每个不完整输入实际执行全部5臂后才终态投影，完整输入遵守KEEP。它不强制3.5秒上限，超支flag仅供比较，不算同预算方法。原bounded ALL_FIVE未覆盖。',
      '- TATO_NATIVE_8为现有8类算子、缩放长度单位的8-trial适配，非官方500-trial完整复现，长度失败与原费用范围保留。',
      '- 金融Bolt KEEP 2.820959优于本轮候选；TimesFM金融微小点差仅2parent，不能声称自然缺口或金融泛化已成立。',
      '- 当前无可验证自然缺口新增实验；策略自然查询不是自然缺口验证。自然在线总请求墙钟、冷启动及超时见本轮最终报告。','',
      '生成：`scripts/v431_r5_common.py --docs`；原始来源为各suite的common_extended_table.json。所有原始共同表及历史负结果保留。']
    Path('docs/v431_r5_main_table.md').write_text('\n'.join(title)+'\n')
    stats=json.loads((ROOT/'statistics/report.json').read_text())
    text=['# v4.3.1-r5 同信息机制表','',
      '结论：固定查询轨迹下，FULL相对RAW在Bolt稍有改善，在TimesFM退步；收益向量平方误差改善不等价于排序或最终预测改善。联合约束的跨家族开发条件未满足。','',
      'CURRENT四臂严格共用同一窗口查询动作与raw scorer；FREE/HISTORY沿相同当前查询集合，但其ridge分别拟合，只有架构、监督和alpha搜索预算一致，并非同一冻结系数。HISTORY额外取得并支付历史H证据，不能称同成本比较。当前完整L512任务响应与历史416/320输入任务分开。 表中激活与排名改变比例按source→parent→variant宏平均，不等于简单窗数比例；平方误差为每窗收益向量坐标平方和再宏平均，未除以动作数。失败/unsupported不从主MASE分母删除，评分指标只在有效配对记录上计算。']
    for suite,label in [('dev','旧DEV'),('financial','金融附表')]:
        mechanism=stats['suites'][suite]['mechanism']
        text+=['',f'## {label}：固定轨迹，全部窗口','',
          '| 家族 | scorer/约束 | MASE | 秒/窗 | 向量平方误差 | 约束违反 | 投影激活比例 | 排名改变比例 | 切换收益 | 错切损失 |',
          '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
        for r in mechanism['summary']:
            m=r.get('score_metrics',{});text.append('| '+' | '.join([r['family'],r['policy'],f"{r['mase']:.6f}",f"{r['seconds']:.6f}"]+
              [f"{m.get(k,float('nan')):.6g}" for k in ('projected_squared_error','projected_violation','projection_active','rank_changed')]+
              [f"{r['switch_gain']:.6f}",f"{r['wrong_switch_loss']:.6f}"])+' |')
        text+=['','### FULL配对差，负数更好','',
               '| 家族 | 相对方法 | 子集 | parent/窗 | MASE差 | 描述性90%区间 |','|---|---|---|---:|---:|---|']
        for r in mechanism['comparisons']:
            if r.get('status')!='computed_descriptive' or r['left']!='MECH_CURRENT_FULL':continue
            z=r['differences']['mase'];text.append(f"| {r['family']} | {r['right']} | {r['subset']} | {r['parents']}/{r['common_episodes']} | {z['mean']:.9f} | [{z['ci90'][0]:.9f}, {z['ci90'][1]:.9f}] |")
        text+=['','### 求解状态','', '| 家族 | 约束 | 调用 | 状态 | 最大gap | 求解总秒 | 失败窗 |','|---|---|---:|---|---:|---:|---:|']
        for r in mechanism['summary']:
            s=r.get('solver',{});text.append(f"| {r['family']} | {r['policy']} | {s.get('calls',0)} | {s.get('statuses',{})} | {s.get('max_gap',0):.6g} | {s.get('seconds',0):.6f} | {r['failure_count']} |")
        cert=mechanism['projection_certificate'];text+=['',f"实际真实gain投影余项核验：{cert['checked']}窗，超过1e-8的违规{cert['violations_over_1e8']}；这仅为数值几何核验，不是预测安全证书。"]
    text+=['','## 归因范围','',
      '- source固定、parent按相邻时间块处理，2000次bootstrap、seed101；所有区间仅描述反复使用的开发数据。',
      '- 至少3个数值不同预测的子集单列；完整分母包含KEEP、预算STOP、unsupported及失败回退。两个不同预测的退化区间不作为高阶结构证据。',
      '- iteration_limit不是精确投影；以实际gap和带2gap余项性质报告，不将未收敛改称完成。',
      '- 机制费用含同一基础固定轨迹执行及额外离线终态评分/求解；它是共同机制账本，不能冒充真实在线请求延迟。',
      '- 选择性、固定数量、固定顺序、预算约束全部调用和真正五臂执行的完整MASE/费用见共同主表。真正全部五臂为更高成本对照，不能归入最多三个版本方法。','',
      '生成依据：statistics/report.json和各suite机制原始记录；脚本v431_r5_common.py --docs。']
    Path('docs/v431_r5_mechanism_table.md').write_text('\n'.join(text)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--space',action='store_true');p.add_argument('--merge',choices=['main','financial']);p.add_argument('--docs',action='store_true');a=p.parse_args()
    if a.space:space()
    if a.merge:merge(a.merge)
    if a.docs:render_docs()
