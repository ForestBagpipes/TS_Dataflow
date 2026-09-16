# TATO Deterministic Restart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留旧 partial 证据的前提下，从 trial 0 确定性重跑并补完 5 个 TATO 场景级 500-trial 搜索。

**Architecture:** 新增一个只负责准备和串行调度的 restart queue；模型执行继续复用现有缓存 worker。独立审核器识别 restart 血缘、核对旧前缀，并在共同表中用新完整目录替换同名 partial 目录。

**执行修订:** 首次正式启动目录因 core 解释器缺少 `tqdm` 在模型加载前失败并保留。r2 目录预登记并强制使用历史成功队列相同的 `W2_CHRONOS_PY`；这只修复运行环境，不更改方法或数据契约。

**Tech Stack:** Python 3.11、pytest、Optuna、NumPy、现有 Bolt/TimesFM worker、JSON/NPZ 原子账本。

---

### Task 1: 冻结 restart 请求契约

**Files:**
- Create: `scripts/v431_r5_tato_restart_queue.py`
- Create: `tests/v431_r5/test_tato_restart_queue.py`

- [x] **Step 1: 写失败测试**

测试构造 completed 与 partial 两个假场景，要求准备器只登记 partial；新请求保留研究身份、指向新输出目录、写入 source request/status/frozen 的哈希，并明确 `fresh_deterministic_from_trial_zero`。

- [x] **Step 2: 在服务器验证 RED**

Run: `$W2_CORE_PY -m pytest tests/v431_r5/test_tato_restart_queue.py -q`

Expected: FAIL，因为 `scripts/v431_r5_tato_restart_queue.py` 尚不存在。

- [x] **Step 3: 实现最小准备器**

实现 `prepare_restart_queue(source_root, output_root, max_seconds, worker, cache_module)`；拒绝复用现有输出目录，拒绝非 partial 或 trial 已完整的场景，使用原子 JSON 写入。

- [x] **Step 4: 在服务器验证 GREEN**

Run: `$W2_CORE_PY -m pytest tests/v431_r5/test_tato_restart_queue.py -q`

Expected: PASS。

### Task 2: 加入 restart 血缘与前缀审核

**Files:**
- Modify: `scripts/v431_r5_tato_scene_audit.py`
- Modify: `tests/v431_r5/test_tato_restart_queue.py`

- [x] **Step 1: 写失败测试**

新增审核测试：合法 restart 通过；篡改 `rows` 或超过登记墙钟上限必须失败。

- [x] **Step 2: 在服务器验证 RED**

Run: `$W2_CORE_PY -m pytest tests/v431_r5/test_tato_restart_queue.py -q`

Expected: FAIL，因为审核器尚无 `verify_restart_amendment`。

- [x] **Step 3: 实现最小审核**

验证固定身份字段、source 三个账本哈希、旧 partial 终态、墙钟上限和新输出隔离；主审核用 restart 目录替换同名 partial 目录。对真实 run 再核对旧参数前缀、completed TRAIN 分数，并对预测记录字节一致或严格浮点数值复现。

- [x] **Step 4: 运行针对性与 r5 全组测试**

Run: `$W2_CORE_PY -m pytest tests/v431_r5 -q`

Expected: 全部 PASS。

### Task 3: 运行服务器队列并独立审核

**Files:**
- Create by program: `results/v431-r5/tato-scene-restart-20260916/`
- Modify by report generator: `docs/v431_r5_tato_scene_results.md`
- Modify by report generator: `docs/v431_r5_final_snapshot.md`

- [x] **Step 1: 准备新请求**

Run: `$W2_CORE_PY scripts/v431_r5_tato_restart_queue.py prepare --max-seconds 1200`

Expected: 只登记 5 个旧 partial 场景，`heldout_labels_read=0`。

- [x] **Step 2: 在独立 tmux 启动单 GPU 串行队列**

运行前再次检查 GPU、锁和其他进程；tmux 内显式 source `scripts/env_new_server.sh`，执行 queue 的 `run` 子命令。

- [x] **Step 3: 读取终态并独立审核**

Run: `$W2_CORE_PY scripts/v431_r5_tato_scene_audit.py`

Expected: 5 个 restart 场景均为 `audited_completed`，旧 partial 血缘和新费用保留；若任一失败则保留真实失败，不改结果分母。

- [x] **Step 4: 更新交接、台账和快照**

只登记实际完成范围，不改变 r5 负结果、开发门槛或封存状态。

- [x] **Step 5: 提交与同步**

检查凭据/数据/权重/大文件和 `git status`，运行 `codex-save-local "补齐TATO截止中断场景并保留确定性审计"`，核对本地与远端 SHA。
