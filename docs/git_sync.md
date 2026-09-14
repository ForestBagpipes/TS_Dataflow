# work2 Git 同步

用户于2026-09-14确认原仓库为 `https://github.com/ForestBagpipes/TS_Dataflow.git`。本机将其登记为 `origin`，默认分支为 `master`；工作分支为 `codex/introactts-v43-bootstrap`。

接入时远端master为 `2354b8572374bc148e3e15264eb53ad5606abc12`，只有初始论文/文献材料提交。迁移源标记 `23c131a06c664fafdbff1a3284c1470a831d529c` 不在该远端历史里；它仍保留为旧本地快照来源，不能伪称已恢复这段缺失历史。

本机此前独立初始化的迁移历史已与origin/master连接：在当前codex分支用保留当前树的merge接入远端初始提交，核验merge前后tree SHA完全相同，远端23个路径均保留。没有checkout旧HEAD覆盖工作区，没有修改master，没有force push。由此后续该分支可与原master正常比较。

每个阶段完成代码、配置、必要验证与文档后执行：

```bash
source scripts/env_new_server.sh
git status --short
git diff --check
# 只暂存明确属于本阶段的代码、配置、测试与文档，然后正常commit。
git push -u origin HEAD:refs/heads/codex/introactts-v43-bootstrap
git ls-remote origin refs/heads/codex/introactts-v43-bootstrap
```

必须核对远端SHA与本地HEAD一致后才报告上传成功。认证、网络或remote变化导致失败时保留本地提交和错误记录，研究任务继续；认证恢复后补推。数据、权重、原始大结果、缓存和凭据仍留在服务器对应资产目录，不进入Git。

本文件不存任何令牌或私钥。本次推送的实际结果由后续post-hoc记录说明；配置了origin不等于上传成功。
