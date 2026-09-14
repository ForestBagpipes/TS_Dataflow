# IntroActTS 本地迁移资产只读盘点

盘点日期：2026-09-14。源目录：`F:/work/Time-research/work2`。
本报告只读取目录、Git 状态与已有文档/JSON；未运行实验、测试、模型推理、统计重算，未连接旧服务器，未读取 `tools/remote.py` 正文。

## 当前项目状态

- Git HEAD：`23c131a06c664fafdbff1a3284c1470a831d529c`。
- 最新研究记录：2026-09-05 的 **v4.2 PORTFOLIO-ACT**，在 Phase 0 红灯停止，未形成正式新版本；incumbent 仍为 **PICS_joint_relabel**。
- `docs/HANDOFF.md` 开头的 2026-09-01 至 2026-09-05 更新和 `docs/version_ledger.md` 是现状依据。HANDOFF 下半部是 2026-08-15 历史快照，其中旧节点地址、路径和排队状态不能视作当前机器事实。
- `docs/CHANGELOG.md` 最新日期节仅到 2026-08-27，不足以单独判定当前版本。
- `docs/data_provenance_contract.md` 要求跨运行按 `sample_uid` 关联，冻结 manifest 按哈希引用，不能为迁移方便重新生成标签或改用位置索引。
- 根目录及项目内未发现 `AGENTS.md`；上级 `F:/work/Time-research` 与 `F:/work` 也未发现该文件。本轮遵循用户要求始终使用简体中文。

## 目录体积

以下为文件元数据统计，包含部分可排除的 Python 缓存；1 MiB = 1,048,576 字节。

| 目录 | 文件数 | 字节 | MiB |
|---|---:|---:|---:|
| src | 45 | 615055 | 0.59 |
| experiments | 189 | 3429672 | 3.27 |
| tests | 49 | 1035711 | 0.99 |
| tools | 40 | 331182 | 0.32 |
| scripts | 4 | 8894 | 0.01 |
| docs | 63 | 763154 | 0.73 |
| docx | 28 | 18182891 | 17.34 |
| data | 11 | 39112263 | 37.30 |
| data/raw | 不存在 | — | — |
| results | 369 | 673412115 | 642.22 |
| third_party | 7 | 9751 | 0.01 |
| .git | 5876 | 290656822 | 277.19 |
| .tmp | 241 | 23725406 | 22.63 |
| figure-studio-runs | 9 | 1332575 | 1.27 |
| figures | 7 | 959582 | 0.92 |
| gpt_pack | 317 | 6160648 | 5.88 |
| logs | 3 | 34308 | 0.03 |

## v3.3 至 v4.2 结果资产

目录名以 `v33` 至 `v42` 为前缀，包含相应子目录文件。

| 前缀 | 文件数 | 字节 |
|---|---:|---:|
| v33 | 17 | 12881964 |
| v34 | 3 | 4338533 |
| v35 | 6 | 16057172 |
| v36 | 4 | 23930492 |
| v37 | 2 | 121522 |
| v38 | 6 | 6592128 |
| v39 | 32 | 14140260 |
| v40 | 82 | 471620364 |
| v41 | 6 | 2710033 |
| v42 | 2 | 6408 |

`results` 顶层名中包含 manifest/registry/freeze/integrity 的文件共 21 个、888132 字节。关键项包括：

- `p0_corpus_manifest_a.json`：冻结 seed-101 mixed corpus，文档记录 1599 个窗口。
- `v33_clean_rerun_manifest.json`、`v33_ood_manifest.json`、`v38_phase0_manifest.json`。
- `v39_phase0_manifest.json`、`v39_model_manifest.json`、`v39_longgap_candidates_freeze.json`、`v39_bridge_manifest.json`、`v39_bridge_freeze.json`。
- `v40_counterfactual_bank_manifest.json`、`v40_bank_freeze.json`、`v40_feature_manifest.json`、`v40_phase3_pool_manifest.json`、`v40_rescue_counterfactual_bank_manifest.json`、`v40_rescue_bank_freeze.json`、`v40_data_registry.json`。

## 数据与模型

`data` 中现有 11 个文件应全部原样保留：

| 文件 | 字节 |
|---|---:|
| ETT-small_ETTh1.csv | 2589657 |
| ETT-small_ETTh2.csv | 2417960 |
| ETT-small_ETTm1.csv | 10360719 |
| ETT-small_ETTm2.csv | 9677236 |
| exchange.txt.gz | 177142 |
| solar.txt.gz | 8748993 |
| time_Crypto.npz | 40814 |
| time_Oil_Price.npz | 160800 |
| time_US_Term_Structure.npz | 1376927 |
| time_export.json | 2669 |
| valuation_xl.npz | 3559346 |

ETT CSV 被 `.gitignore` 排除，但属于迁移必需数据，不能跟随 Git 忽略规则漏传。`time_export.json` 记录 TIME 数据的原始通道、频率、起始时间；其中绝对路径是旧节点历史元数据。

`results/v40_critic_ckpt` 有 **30 个非空 .pt 文件，共 61860486 字节**，应全部保留。项目根目录的 `TSFM_latent_only__Crypto.pt` 为 **0 字节**，是无效资产，应排除，勿替换同名的有效子目录 checkpoint。

项目目录内未发现 Chronos、TimesFM、MOMENT、OpenFIM、TS-ICL 基础模型权重。`third_party` 当前仅有 TimeInf；`third_party/openfim` 不存在。历史 `results/v39_model_manifest.json` 中的 available=true 仅证明旧环境当时可用，不代表本机或新服务器已有资产。

供服务器后续按历史 revision 补齐的记录：

- MOMENT：`AutonLab/MOMENT-1-large`，revision `ca58581bc7bea2ebed4e80dc0a3e4b8b609c6ecc`。
- OpenFIM：`FIM4Science/fim-imp-pointwise-base`，revision `e00537a9fc695c69e6f22bf8dce3903c3bff3af3`；代码仓库 `FIM4Science/OpenFIM` commit `cee2bb53be1e8e92b73f98dfdbe3605efc9119cc`。
- TS-ICL：`taharnbl/TS-ICL`，revision `19c94031439fb31f36ce395088ee50a6762d3774`；历史 Python 包 `tsicl==0.2.1`。

## 已确认缺失的大件

`results/v40_sync_note.json` 明确记录以下三个文件当时留在旧节点，本机确实没有：

1. `results/v40_feature_cache.npz`。
2. `results/v40_rescue_bank_candidates.jsonl`。
3. `results/v40_rescue_bank_records.jsonl`。

相关 manifest、单臂 rescue 候选文件、parents 数据仍在本地。后续可由服务器 Codex 按冻结输入和历史代码重建，并与 sync note 内的 SHA-256 核对；本轮不重建。`.tmp/rescue_bank.sh`（1026 字节）是历史执行脚本，若恢复 rescue 需要它，应单独审阅后选取，不能为此整包迁移 `.tmp`。

## 必须保留的未提交状态

当前至少有 14 个 tracked 修改与 1 个 tracked 删除。大量 v3.2 至 v4.2 方法文件、测试、文档、结果和 checkpoint 尚未跟踪。应迁移**当前工作区内容**，仅 clone / git archive 会漏掉主要进展。

Tracked 修改：

- `docs/HANDOFF.md`、`docs/claims.md`、`docs/diagnostic-playbook.md`、`docs/experiment-matrix.md`、`docs/v3_triage_design.md`、`docs/version_ledger.md`。
- `results/chain_check.json`、`results/ltsv_scores_xl.json`、`results/spo_learn.json`、`results/tsrating_consistency.json`、`results/valuation_scores_xl.json`。
- `src/introact_ts/__init__.py`、`src/introact_ts/probe.py`。
- `tools/remote.py`：旧服务器连接工具，本地保持原状；传输包应排除此文件或使用不含凭据的新服务器替代工具，不能直接传播历史连接凭据。

Tracked 删除：`docx/胡宏彬-进度文档-20260820.docx`。当前存在带 `【work2】` 前缀的 20260820 与 20260904 文档；应保留实际工作区命名，不从 HEAD 恢复已删旧文件。

重点 untracked：`experiments/metrics_common.py`、`experiments/v3*.py`、`experiments/v4*.py`、`src/introact_ts/contextual_shield.py`、`pics.py`、`mast_pics.py`、配套 `tests`、`docs/v3*`/`docs/v4*`、`results/v3*`/`results/v4*`、TIME 数据导出、最新 DOCX。

## 迁移优先级与排除建议

优先一次完整迁移：`src`、`experiments`、`tests`、`scripts`、去除历史连接凭据后的 `tools`、`requirements.txt`、`docs`、`data`、`results`、`third_party`、当前 DOCX。其余论文源文件与正式图可随包保留。

论文材料补充：`paper` 有 9 文件/81909 字节，是正在整理的中英文 Markdown 章节，建议全传。`en` 有 13 文件/342162 字节、`zh` 有 13 文件/426866 字节，建议传 `.tex`/`.bib`/`.sty`/`.bst` 源文件，排除 `.aux`/`.log`/`.out`/`.blg`/`.synctex.gz` 等编译副产物。`进度文档` 仅有 `进度文档-胡宏彬-20260608.docx`（39485 字节），可以随包保留为历史背景；当前方法依据优先使用 `docx` 的 20260904 版本和更新后的 `docs`，勿把六月旧稿当成现行方案。

默认排除：`.git`、`.tmp`、`.pytest_cache`、所有 `__pycache__`/`.pyc`、`.server-codex-setup` 中本机脚本/SSH辅助状态、`.codex-setup-known-hosts`、`.claude`/`.superpowers` 等本机代理状态、历史日志、重复 `gpt_pack`/项目 ZIP、论文参考仓库、图工作流临时输出、0 字节根目录 checkpoint。若需要 Git 历史可另行做受控迁移；本轮代码接续不依赖将 `.git` 整包传输。

本报告仅记录磁盘存在性与历史文档事实，不声称模型环境可复现、数据语义完整、实验已通过或新服务器已完成验证。迁移后的传输哈希、环境安装与验证由主执行任务记录。
