#!/usr/bin/env python3
"""Render audited completion and missing work without opening data or fitting."""
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import json

ROOT = Path('results/v431-r5')


def read(path):
    return json.loads(Path(path).read_text())


def number(value):
    return '未取得' if value is None else f'{value:.6f}'


def table(headers, rows):
    return ('| ' + ' | '.join(headers) + ' |\n| ' + ' | '.join(['---'] * len(headers))
            + ' |\n' + '\n'.join('| ' + ' | '.join(map(str, row)) + ' |' for row in rows) + '\n')


def main():
    audit = read(ROOT / 'tato-scene/audit.json')
    now = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
    sections = [f'# r5 关机前交付快照\n\n生成时间：{now}。仅汇总已落盘并独立审核的记录，未完成项保留。\n',
                'r5开发准入失败，模型与配置保持冻结，不增加搜索、不解封calibration/test。PICS_joint_relabel保留历史身份。\n']
    compact = []
    for key, title in [('scenes', 'TATO 缩放长度单位的场景适配'),
                       ('official96_scenes', 'TATO 官方96单位、当前L512约束的场景适配')]:
        rows = []
        for scene in audit[key]:
            status = scene.get('worker_status', {})
            cost = scene.get('cost', {})
            scored = next((row for row in scene.get('table', [])
                           if row['policy'] in ('TATO_SCENE_high', 'TATO_OFFICIAL96_high')), {})
            # Each protocol may use the same policy name; identity stays in its own section.
            if not scored:
                scored = next((row for row in scene.get('table', [])
                               if row['policy'].startswith('TATO_') and row['policy'].endswith('_high')), {})
            record = dict(protocol=key, scene=scene['scene'], status=scene['status'],
                          train_parents=scene['train_parents'], dev_parents=scene['dev_parents'],
                          actual_trials=status.get('trials'), completed_trials=status.get('completed_trials'),
                          failed_trials=status.get('failed_trials'),
                          mase=scored.get('mase_full_denominator'),
                          search_seconds=cost.get('offline_search_seconds'),
                          cold_seconds=cost.get('cold_seconds'),
                          physical_calls=cost.get('actual_model_calls'), cache_hits=cost.get('cache_hits'),
                          hot_seconds=scored.get('seconds_macro_available_records'),
                          high_overruns=scored.get('budget_overruns'),
                          full_child_seconds=cost.get('complete_subprocess_wall_seconds'))
            compact.append(record)
            rows.append([record['scene'], f"{record['train_parents']}/{record['dev_parents']}",
                         record['status'], f"{record['actual_trials']}/{record['completed_trials']}/{record['failed_trials']}",
                         number(record['mase']), number(record['search_seconds']), number(record['hot_seconds'])])
        sections += [f'\n## {title}\n\n', table(
            ['场景', 'TRAIN/DEV parent', '审计状态', '试验/成功/失败', 'MASE', '搜索秒', '热部署秒/窗'], rows)]
    sections += ['\n缩放单位为Bolt16/TimesFM32；官方单位为96。两者均为当前L512和有限TRAIN支持的适配，'
                 '不是官方L1440、500个训练实例、top16/Pareto/OT完整复现。500 trial不等于500个独立parent。'
                 '超时搜索可冻结已完成训练最优方案，但不能称完整500trial。原始失败保留。\n',
                 '\n## 三来源共同子集\n\n每家族26 parent、52个target_block_10变体；与旧156变体主表不同，'
                 '不得直接比较绝对MASE。未完成场景使全分母MASE保持空缺。\n']
    combined = [row for row in audit['combined']['table'] if row['policy'].endswith('_high')]
    sections.append(table(['家族', '方法', '完成/登记窗', 'MASE完整分母', '秒/窗（已取得记录）', '超高预算'], [
        [r['family'], r['policy'], f"{r['successful_episodes']}/{r['episodes']}",
         number(r['mase_full_denominator']), number(r['seconds_macro_available_records']), r['budget_overruns']]
        for r in combined]))
    sections.append('\n缺少场景：' + (', '.join(audit['combined']['missing_scene_results']) or '无') + '。\n')
    sections += ['\n## TATO费用分账\n\n下表仅累计已独立审核场景；在途部分不写成零。搜索包含其中模型调用，'
                 '不能再把原生模型时间重复加到搜索时间。完整子进程包含搜索、加载等阶段，不与阶段时间相加。\n']
    costs = []
    for key in ('scenes', 'official96_scenes'):
        done = [r for r in compact if r['protocol'] == key and r['search_seconds'] is not None]
        measured = [r for r in done if r['full_child_seconds'] is not None]
        costs.append(dict(protocol=key, audited_scenes=len(done),
                          search_seconds=sum(r['search_seconds'] for r in done),
                          cold_seconds=sum(r['cold_seconds'] for r in done),
                          physical_calls=sum(r['physical_calls'] for r in done),
                          cache_hits=sum(r['cache_hits'] for r in done),
                          full_child_measured_scenes=len(measured),
                          full_child_seconds=sum(r['full_child_seconds'] for r in measured)))
    sections.append(table(['协议', '已审场景', '搜索秒', '冷加载秒', '物理调用/命中', '外层计时覆盖/秒'], [
        [r['protocol'], r['audited_scenes'], number(r['search_seconds']), number(r['cold_seconds']),
         f"{r['physical_calls']}/{r['cache_hits']}",
         f"{r['full_child_measured_scenes']}/{number(r['full_child_seconds'])}" if r['full_child_measured_scenes'] else '未测量']
        for r in costs]))
    native = read(ROOT / 'chronos2-native-check/audit/table.json')
    sections += ['\n## Chronos-2原生KEEP敏感性\n\n同旧DEV26 parent/156变体，先保存全部预测后独立评分。'
                 '仅更换骨干原生KEEP，未训练或执行Chronos-2治理策略，不归因r5、不当第三独立家族。\n',
                 table(['骨干', '方法', 'MASE'], [[r['model'], r['policy'], number(r['mase'])] for r in native]),
                 '\n下载477930472字节/917.244秒；TRAIN成功完整子进程6.369213秒、DEV7.965819秒；'
                 '首次记录层失败6.313467秒另计且保留。DEV104次物理调用、52次合法复用。'
                 '原生GPU调用均值不能替代完整请求延迟或同预算优势。实际许可/模型revision与原始预测审核另有账本。\n',
                 '\nChronos-2并非逐来源普遍更强：ETTm1为1.142987，弱于Native Bolt的0.997525及两个r5；'
                 'Solar和单parent USTS的点估计较低。逐来源同UID表见v431_r5_final_consistency。\n',
                 '\n## 主实验准备与缺项\n\n8来源登记286 parent（232train/54dev）、1716输入与mask契约。'
                 '只读合法context与元数据，未解析封存未来标签。重叠/时间审核后104 parent未发现已知旧读取重叠或时间异常'
                 '（84train/20dev），不等于已确认独立样本。Weather两个TRAIN parent时间异常保留unsupported。'
                 '当前286个context无原生NaN，自然缺口轨道仍缺少验证；金融仅两个已用parent，不能支持金融泛化。\n',
                 '\nTimesFM-3只核版本与许可，未下载运行。官方完整TATO、8来源r5主矩阵及独立确认均未运行。'
                 'r5未优于强简单对照，保持停止扩展。\n',
                 '\n费用说明：TRAIN搜索、下载、冷启动、请求和排队分别记账；primary TATO旧worker计时不含进程初始import，'
                 '未测外层时间记未知。extra/official队列另记锁后完整子进程墙钟。TRAIN缓存保存历史首次实际计算，'
                 'DEV请求缓存逐窗清空，未将离线预计算当免费在线信息。\n']
    queues = {}
    for name in ['tato-scene-extra/queue.execution.json', 'official96-queue-status.json', 'chronos2-queue-status.json']:
        queues[name] = read(ROOT / name)
    sections += ['\n## 队列与交接\n\n', table(['队列', '状态', '截止'], [
        [name, q['status'], q.get('deadline', '已完成')] for name, q in queues.items()]),
        '\n服务器预定关机2026-09-16 05:04:31 Asia/Shanghai；本程序不执行关机。'
        '新重任务截至04:45，随后保存提交与审阅包。重启后不得原样复用已过期deadline覆盖旧状态。\n']
    Path('docs/v431_r5_final_snapshot.md').write_text(''.join(sections))
    (ROOT / 'final_snapshot.json').write_text(json.dumps(dict(
        generated_at=now, scenes=compact, common_table=combined, tato_costs=costs,
        chronos2=native, queue_status={k: v['status'] for k, v in queues.items()},
        development_gate='failed', calibration_test='sealed'), ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(status='rendered', at=now, scenes=len(compact))))


if __name__ == '__main__':
    main()
