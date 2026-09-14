# P0 实验溯源修复 — 接管报告

日期：2026-09-01  
执行范围：`/root/autodl-tmp/work2` 服务器；本地仅编辑与读取  
API 调用：0  

---

## 1. 服务器资源检查

- 主机：`autodl-container-319a479245-8f109bd5`（通过 `tools/remote.py` / paramiko）
- GPU：NVIDIA GeForce RTX 5090，利用率 0%，显存占用 2 MiB / 32607 MiB
- 内存：754 GiB 总计，可用约 560 GiB
- 数据盘 `/root/autodl-tmp`：150 GiB，使用 55 GiB（37%）
- 其他任务：work1 有低 CPU `pip install` 进程，未抢占；未启动任何与他人冲突的 GPU/CPU 任务
- 本轮回话产生的后台任务 `p0_operator_path_audit.py` 已正常结束，无残留进程

## 2. 执行命令

```bash
# P0-A: corpus 确定性审计（两个独立进程构建并比较）
cd /root/autodl-tmp/work2
/root/autodl-tmp/envs/w2/bin/python experiments/p0_corpus_determinism.py \
  --mode compare --n 1600 --seed 101 --source mixed \
  --out results/p0_corpus_determinism_report.json \
  --manifest-a results/p0_corpus_manifest_a.json \
  --manifest-b results/p0_corpus_manifest_b.json

# P0-B: 两条 operator 评估路径逐样本对比
/root/autodl-tmp/envs/w2/bin/python -u experiments/p0_operator_path_audit.py \
  --n 1600 --seed 101 --source mixed --device cuda \
  --out results/p0_operator_path_audit.json

# P0-C: 现有结果文件 manifest 审计
/root/autodl-tmp/envs/w2/bin/python experiments/p0_result_manifest_audit.py \
  --manifest results/p0_corpus_manifest_a.json \
  --out results/p0_result_manifest_audit.json
```

## 3. 代码位置

- `experiments/p0_corpus_determinism.py`：构建语料、生成 `sample_uid`、跨进程比较
- `experiments/p0_operator_path_audit.py`：在 67 个 level-shift 窗口上同时调用 `level_shift_operator_probe.evaluate_on_window` 与 `route_conditioned_shift.evaluate_variant`
- `experiments/p0_result_manifest_audit.py`：用冻结 manifest 审计已有结果文件
- 被审计的算子/评估函数：
  - `experiments/level_shift_operator_probe.py`（导入 `audit._nmse`）
  - `experiments/route_conditioned_shift.py`（本地 `_nmse`）
  - `experiments/audit.py:_nmse`

## 4. 根因证据

### P0-A：corpus 可确定性构建，但存在全局可变状态

- 两次独立进程构建均得到 1599 个窗口，1599 个唯一 `sample_uid`，完全重叠，无内容差异
- `build_calibration.py` 在构建过程中会修改 `SCALES[scale].seed`（可变全局 dict）
- 由于每个进程重新导入模块，该 mutation 不影响跨进程确定性；但同一进程内连续调用会累积状态，必须重置或使用副本

### P0-B：两条 operator 路径输出一致，但 NMSE/loss 口径不一致

在 `route_conditioned_shift.json` 中 `true_kind == "level_shift"` 的 67 个窗口上：

| 对比项 | keep | robust_offset_local |
|---|---|---|
| 输出序列 hash 一致 | 67/67 | 67/67 |
| offset 一致 | — | 67/67 |
| repair_rmsd 一致 | 67/67 | 67/67 |
| before_nmse 不一致 | 67/67 | 67/67 |
| after_nmse 不一致 | 67/67 | 66/67 |
| loss 不一致 | 0/67 | 36/67 |

根因：`level_shift_operator_probe` 使用 `audit._nmse`（对两条序列都做 median-centering 并用 median 填充 NaN），而 `route_conditioned_shift` 使用本地 `_nmse`（不居中，仅 mask finite 差值）。

后果：
- 全窗口探针 `level_shift_probe.json` 报告的 `mean_loss = 0.011`、`98.9% loss ≤ 0.03` 是 centered-NMSE 的 artefacts，不能代表部署 shield 实际看到的 uncentered 距离。
- `route_conditioned_shift.json` 的 loss 才是与当前 shield 同口径的数值，但旧结论“robust_offset_local coverage 9.0%”因此需要重新解释。

### P0-C：window-level 结果均可 metadata 验证，但 pre-P0 文件缺少 hash

| 文件 | 状态 | 说明 |
|---|---|---|
| `family_scores.jsonl` | 1599/1599 metadata_verifiable | — |
| `level_shift_probe.json` | 11193/11193 metadata_verifiable | hash 未存 |
| `route_conditioned_shift.json` | 4638/4638 metadata_verifiable | hash 未存 |
| `misroute_evidence.json` | 316/316 metadata_verifiable | — |
| `counterfactual_routing.json` | aggregate_only, n_windows 匹配 | 无 window-level 记录 |
| `conformal_family.json` | aggregate_only, n_windows 匹配 | 无 window-level 记录 |
| `resegment_noop.json` | aggregate_only, **n_windows 不匹配** | 该文件基于 350 窗口 smoke slice（slice_seed=202），与当前 1599 窗口 manifest 不可比 |

## 5. 受影响结果清单

- `results/level_shift_probe.json`：loss 列口径为 centered NMSE，与部署 shield 不一致；不能直接用于评估 operator 是否达到 `loss ≤ 0.03` 门控
- `results/route_conditioned_shift.json`：与 probe 的 loss 不可直接比较；需明确使用同一 `_nmse` 后重算
- `results/resegment_noop.json`：基于 350 窗口 smoke slice，不在当前冻结的 1599 窗口 calibration corpus 上，若用于 quantitative claim 必须重建
- 所有 pre-P0 结果文件：缺少 `sample_uid`、clean/corrupted hash、corpus manifest hash，按 `docs/data_provenance_contract.md` 属于 hash-unverifiable，仅能 metadata 验证

## 6. 文档更新

- `docs/version_ledger.md`
  - 新增 P0-A / P0-B / P0-C 诊断记录
  - 新增“P0 findings that change how prior diagnostics are read”章节
  - 明确 Phase B 为 integrity-blocked，Phase C 为 inconclusive（非 TSFM 失败）
  - 标注 `level_shift_probe.json` 的 loss 为 centered-NMSE artefact
- `docs/diagnostic-playbook.md`
  - 新增 Tree sixteen（corpus 不能靠 window_id 重载）
  - 新增 Tree seventeen（两脚本用不同函数算同一列）
  - 新增 Tree eighteen（旧结果文件 metadata-verifiable 但 hash-unverifiable）
- `docs/HANDOFF.md`
  - 在历史快照中追加 2026-09-01 P0 审计结果摘要
- `docs/v2_1_counterfactual_design.md`
  - 新增 0.1 节“P0 integrity findings”
  - 明确 frozen corpus、不一致 `_nmse`、Phase C 样本失衡三件事
- `docs/data_provenance_contract.md`（新建）
  - 规定今后结果 schema 必须包含 `sample_uid`、clean/corrupted hash、corpus manifest hash、code commit、config hash
  - 规定跨运行关联必须使用 `sample_uid`，禁止仅用 `window_id`

## 7. 输出路径

服务器：
- `results/p0_corpus_manifest_a.json`
- `results/p0_corpus_manifest_b.json`
- `results/p0_corpus_determinism_report.json`
- `results/p0_operator_path_audit.json`
- `results/p0_result_manifest_audit.json`

本地（已与服务器同步）：
- 同上，位于 `F:/work/Time-research/work2/results/`
- 新增/修改文档位于 `F:/work/Time-research/work2/docs/`

## 8. 是否达到预注册门槛

P0 完成门要求：

- [x] 两次独立 corpus 构造逐样本指纹一致（1599/1599）
- [x] 1599 个样本一一对应
- [x] 两条 operator 评估路径零差异？—— **否**：operator 输出/offset/RMSD 零差异，但 NMSE/loss 存在系统性差异；已定位根因为 `_nmse` 定义不同
- [x] 原始记录与独立汇总一致
- [x] 文档中明确 Phase B 为 integrity-blocked，Phase C 为 inconclusive

结论：P0 完成门已满足，但 Phase B 因口径不一致被 integrity-blocked，不能直接进入 v2.1 集成。

## 9. 下一步最小重建成本

为解除 Phase B integrity-block，必须：

1. **统一 `_nmse` 定义**
   - 选项 A：所有评估脚本统一使用 `audit._nmse`（centered）
   - 选项 B：所有评估脚本统一使用 uncentered finite-mask `_nmse`（与部署 shield 一致）
   - 建议选项 B，因为部署 shield 实际使用 uncentered 距离；但需确认 `audit._nmse` 在其它上下文（如 ablation/aggregate）是否也需同步
   - 成本：纯代码修改，无需 GPU；修改后重跑 `level_shift_operator_probe.py` 和 `route_conditioned_shift.py`

2. **重跑 Phase B（route-conditioned shift replay）**
   - 在统一 `_nmse` 后，用同一冻结 corpus 重跑
   - 预估：约 5–15 分钟（TSFM perceive 1599 窗口 + 67 窗口评估）
   - 资源：RTX 5090，约 2–4 GiB 显存
   - API：0

3. **重建 `resegment_noop.json`**
   - 若后续需要引用该文件，必须在当前 1599 窗口 corpus 上重跑，或明确标注其基于 350 窗口 slice
   - 成本：取决于是否急于使用；当前不阻塞 Phase B

4. **为所有新结果文件写入 provenance schema**
   - 按 `docs/data_provenance_contract.md` 在生成脚本中加入 `sample_uid`、hash、manifest hash 字段
   - 成本：中等，需在多个实验脚本中插入；可随下一次重跑时一并完成

在 Phase B integrity 修复前，不得：
- 将 `level_shift_probe.json` 的 `loss ≤ 0.03` 作为 operator 绿灯证据
- 将 route-conditioned 与 full-window 的 loss 直接比较
- 基于 `resegment_noop.json` 对 1599 窗口 corpus 做 quantitative claim
