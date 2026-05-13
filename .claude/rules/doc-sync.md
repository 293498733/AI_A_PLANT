# 文档同步规则

任何代码/文件变更后，以下索引文件必须同步更新：

## 必须同步的文件

| 当发生... | 必须更新... |
|-----------|-------------|
| 新增/删除/重命名 recipe 文件 | `CLAUDE.md`（数量、索引）、`.claude/status.md`（Recipe 行） |
| 新增/删除/重命名 pipeline 模块 | `CLAUDE.md`（数量）、`.claude/status.md`（模块状态表） |
| 删除任何被 memory 引用的文件 | `.claude/memory/` 相关文件（立即清理过时引用） |
| 删除任何被 CLAUDE.md 引用的文件 | `CLAUDE.md`（文档索引） |
| 计划状态变更（实施中→搁置→完成） | `.claude/plans/implementation-tracker.md`、`.claude/status.md`（已知问题） |
| 版本号变更 | `CLAUDE.md`、`pipeline/__init__.py`、`.claude/status.md` |
| 测试文件新增/删除 | `CLAUDE.md`（测试数量）、`.claude/status.md` |
| 新增/删除规则文件 | `CLAUDE.md` 或 `.claude/status.md` 无需更新（规则目录自说明） |

## 为什么

memory 和 CLAUDE.md 是静态快照，不会自动感知文件删除/重命名。过时引用会误导新会话，导致：
- 引用不存在的文件
- 数量统计错误
- 计划状态与事实不符

## 怎么做

变更完成后，立刻检查上述索引文件，直接 Edit 修正，与功能改动同 commit。
