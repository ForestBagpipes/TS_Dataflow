#!/usr/bin/env python3
"""Cost/information diagnostics from the unchanged first r5 prediction ledgers."""
from pathlib import Path
from collections import defaultdict
import json,hashlib
import numpy as np
from v431_r3_statistics import macro,blocked_bootstrap

ROOT=Path('results/v431-r5')
BUDGETS={'low':.8140623268639832,'high':3.5}
METHODS=('MECH_FREE_RAW','MECH_HISTORY_RAW','MECH_CURRENT_RAW')
COMPARATORS=('TRAIN_BEST_FIXED_FLOW','REFERENCE_FREE','R4_FREE_COVERAGE','LEGACY_DIRECT_control','LEGACY_CART_H')

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def group(rows):
    out=defaultdict(dict)
    for r in rows:
        key=r['family'],r['policy'];uid=r['episode_uid']
        assert uid not in out[key]
        out[key][uid]=r
    return out

def paired(left,right):
    common=sorted(set(left)&set(right));rows=[]
    for uid in common:
        a,b=left[uid],right[uid]
        assert all(a[k]==b[k] for k in ('source','parent_group','horizon','raw_start'))
        r={k:a[k] for k in ('episode_uid','source','parent_group','horizon','raw_start','condition')}
        r.update({k:float(a[k])-float(b[k]) for k in ('mase','total_seconds','switch_gain','wrong_switch_loss')})
        r.update(left_action=a['arm'],right_action=b['arm'])
        rows.append(r)
    if not rows:return {'status':'empty_support','episodes':0}
    parent=defaultdict(list)
    for r in rows:parent[r['source'],r['parent_group']].append(r['mase'])
    parent_rows=[{'source':s,'parent_group':p,'mean_mase_difference':float(np.mean(v)),'variants':len(v)} for (s,p),v in parent.items()]
    return {'status':'descriptive_only','episodes':len(rows),'parents':len(parent),
       'mase_difference':blocked_bootstrap(rows,'mase'),'cost_difference':blocked_bootstrap(rows,'total_seconds'),
       'switch_gain_difference':macro(rows,'switch_gain'),'wrong_switch_loss_difference':macro(rows,'wrong_switch_loss'),
       'improved_windows':sum(r['mase'] < -1e-12 for r in rows),'worse_windows':sum(r['mase'] > 1e-12 for r in rows),
       'worst_parent_delta':max(r['mean_mase_difference'] for r in parent_rows),
       'p95_parent_delta':float(np.quantile([r['mean_mase_difference'] for r in parent_rows],.95)),
       'worst_10_parents':sorted(parent_rows,key=lambda x:x['mean_mase_difference'],reverse=True)[:10],
       'worst_10_windows':sorted(rows,key=lambda x:x['mase'],reverse=True)[:10],
       'by_source':{s:macro([r for r in rows if r['source']==s],'mase') for s in sorted({r['source'] for r in rows})},
       'uid_list':common}

def summary(rows,budget):
    if not rows:return {'status':'empty_support','episodes':0,'parents':0}
    failure=[r for r in rows if r['trace'].get('failure')]
    return {'status':'completed','episodes':len(rows),'parents':len({r['parent_group'] for r in rows}),
      'sources':sorted({r['source'] for r in rows}),'mase':macro(rows,'mase'),'seconds':macro(rows,'total_seconds'),
      'switch_gain':macro(rows,'switch_gain'),'wrong_switch_loss':macro(rows,'wrong_switch_loss'),
      'budget_overruns':sum(r['total_seconds']>budget for r in rows),
      'queried_more_than_reference':sum(len(r['trace']['queried_actions'])>1 for r in rows),
      'at_least_three_numerical_predictions':sum(r.get('unique_predictions',0)>=3 for r in rows),
      'failure_fallbacks':len(failure),'failure_uid_list':[r['episode_uid'] for r in failure],
      'cost_p95':float(np.quantile([r['total_seconds'] for r in rows],.95)),
      'cost_max':max(r['total_seconds'] for r in rows),
      'horizons':{str(h):{'episodes':sum(r['horizon']==h for r in rows),'mase':macro([r for r in rows if r['horizon']==h],'mase')} for h in sorted({r['horizon'] for r in rows})}}


def process(suite):
    mech_path=ROOT/'evaluation'/suite/'mechanism_rows.json';common_path=ROOT/'evaluation'/suite/'common_decisions.json'
    rows=read(mech_path);g=group(rows);main=group(read(common_path));out={'input_sha256':{str(p):sha(p) for p in (mech_path,common_path)},'information_tables':[],'reference_comparisons':[],'missing_reference_comparisons':[]}
    for family in ('bolt','timesfm'):
        rr={method:g[family,method] for method in METHODS}
        uidsets=[set(x) for x in rr.values()];assert all(s==uidsets[0] for s in uidsets)
        uids=sorted(uidsets[0])
        for uid in uids:
            base=rr['MECH_CURRENT_RAW'][uid]
            for method in METHODS:
                r=rr[method][uid]
                assert r['trace']['queried_actions']==base['trace']['queried_actions']
                assert all(r[k]==base[k] for k in ('source','parent_group','horizon','raw_start'))
                if r['trace'].get('failure'):
                    assert r['arm']==r['reference_arm'],'Existing failed evidence must retain reference'
        for bn,budget in BUDGETS.items():
            valid=[u for u in uids if all(rr[m][u]['total_seconds']<=budget and not rr[m][u]['trace'].get('failure') for m in METHODS)]
            exclusion={}
            for u in uids:
                reasons=[]
                for m in METHODS:
                    if rr[m][u]['total_seconds']>budget:reasons.append(m+':over_budget')
                    if rr[m][u]['trace'].get('failure'):reasons.append(m+':'+rr[m][u]['trace']['failure'])
                if reasons:exclusion[u]=reasons
            for scope,selected in [('full_denominator_existing_fallbacks',uids),('common_success_and_actual_cost_feasible',valid)]:
                scope_rows={'family':family,'budget_name':bn,'budget_seconds':budget,'scope':scope,
                  'uid_list':selected,'exclusions':exclusion if scope!='full_denominator_existing_fallbacks' else {},
                  'methods':{m:summary([rr[m][u] for u in selected],budget) for m in METHODS},'comparisons':{}}
                for alternative in ('MECH_FREE_RAW','MECH_HISTORY_RAW'):
                    scope_rows['comparisons']['MECH_CURRENT_RAW-minus-'+alternative]=paired({u:rr['MECH_CURRENT_RAW'][u] for u in selected},{u:rr[alternative][u] for u in selected})
                out['information_tables'].append(scope_rows)
            left=main[family,'R5_'+bn]
            for comp in COMPARATORS:
                key=(family,comp+'_'+bn)
                if key in main:out['reference_comparisons'].append({'family':family,'budget_name':bn,'left':'R5_'+bn,'right':key[1],**paired(left,main[key])})
                else:out['missing_reference_comparisons'].append({'family':family,'budget_name':bn,'right':key[1],'status':'absent_from_frozen_common_ledger'})
    return out


def markdown(result):
    lines=['# r5 信息与费用诊断','',
      '使用首次冻结评分器与首次固定查询轨迹，不重训练、不执行模型、不改动 DEV UID。后验费用可行子集用于诊断，不能称为重新执行的低预算策略；超支路径保留原预测和全部费用，不允许事后免费回退。三个方法使用相同当前版本试运行集合；history另付完整H费用。因此是共享当前试运行的不同信息比较，不是精确等秒比较或完全同信息消融。','',
      '训练监督支持亦不同：current/free各54个fit parent、1296动作对，history51个parent、1224动作对。架构、正则候选相同，但不能称训练支持完全相同。','',
      '|集合|家族|预算|范围|窗口/parent|免费分数 MASE|历史分数 MASE|当前响应 MASE|三法费用秒（免费/历史/当前）|',
      '|---|---|---|---|---|---:|---:|---:|---|']
    for suite,v in result['suites'].items():
        for t in v['information_tables']:
            ms=t['methods'];free,hist,current=[ms[m] for m in METHODS]
            scope='全分母' if t['scope'].startswith('full_') else '共同可行'
            if current['episodes']==0:
                lines.append(f"|{suite}|{t['family']}|{t['budget_name']}|{scope}|0/0|—|—|—|—|");continue
            lines.append(f"|{suite}|{t['family']}|{t['budget_name']}|{scope}|{current['episodes']}/{current['parents']}|{free['mase']:.6f}|{hist['mase']:.6f}|{current['mase']:.6f}|{free['seconds']:.6f}/{hist['seconds']:.6f}/{current['seconds']:.6f}|")
    lines += ['', '完整分母中的历史不支持请求按原始机制账本回退参考，仍计此前已发生当前试运行费用。共同子集同时要求三法成功且各自全部真实组件费用在同一预算内，不按结果优劣挑选；子集来源/parent权重重新在该子集内宏平均，不能直接拿其绝对MASE与全分母比较。完整JSON保留排除UID与原因。', '',
              '低预算三法共同可行子集中，TimesFM DEV的50窗以及金融两家族各4窗全部只执行参考版本，没有当前响应或额外历史查询；其三法同效不能作为信息等价证据。Bolt DEV低预算共同129窗中78窗查询参考以外版本。完整JSON记录各组实际查询支持。', '', '## R5 对冻结强参照和免费策略的配对结果','',
              '|集合|家族|预算|对照|R5−对照 MASE|90%描述区间|最坏parent差|', '|---|---|---|---|---:|---|---:|']
    for suite,v in result['suites'].items():
        for r in v['reference_comparisons']:
            if r['right'].startswith(('TRAIN_BEST_FIXED_FLOW','REFERENCE_FREE','R4_FREE_COVERAGE')):
                ci=r['mase_difference']['ci90'];lines.append(f"|{suite}|{r['family']}|{r['budget_name']}|{r['right']}|{r['mase_difference']['mean']:.6f}|[{ci[0]:.6f}, {ci[1]:.6f}]|{r['worst_parent_delta']:.6f}|")
    lines += ['', '统计固定source、source内相邻双parent时间块、2000次、seed101，相关变体不拆组；单parent来源和已反复使用DEV限制保留。金融仅两个parent时区间可能退化为点，绝非确定性或确认结果。DIRECT_control/CART_H完整结果、逐来源差、尾部10个窗口/parent及原始UID见JSON。', '',
              '共同原账本没有Bolt低预算TRAIN_BEST_FIXED_FLOW行，因此该比较未运行，不自行推算或挪用高预算结果；缺项在JSON明确列出。', '', '这些诊断不改变r5开发门槛失败结论，不新增搜索或解封确认集。']
    return '\n'.join(lines)+'\n'


def main():
    manifest=read(ROOT/'fit/manifest.json')
    result={'status':'completed_descriptive','code_sha256':sha(Path(__file__)),
       'scope':'shared fixed current query traces; realized-cost feasibility, not a counterfactual low-budget online replay',
       'budgets':BUDGETS,'no_retraining_or_new_inference':True,'no_hidden_split_read':True,
       'training_support':{f:{m:{k:v[k] for k in ('parents','rows','alpha')} for m,v in t['scorers'].items() if m in ('free','history','current')} for f,t in manifest['families'].items()},
       'suites':{s:process(s) for s in ('dev','financial')}}
    out=ROOT/'statistics/cost_information.json';out.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    Path('docs/v431_r5_cost_information.md').write_text(markdown(result))
    print(json.dumps({s:len(v['information_tables']) for s,v in result['suites'].items()}))

if __name__=='__main__':main()
