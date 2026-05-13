# ADR-006: 勤提交、智能推送 (2026-05-11)

**决策**: 代码修改随时 `git commit` 留痕，但 `git push` 由 Claude 自动判断时机——阶段性完成才推送，快速迭代中仅本地提交。

**原因**:
- 高频 commit 保证代码可回溯到任意中间状态
- 不盲目 push 避免远程历史碎片化
- 阶段性完成的完整提交才值得同步到 GitHub

详见 `.claude/rules/git-workflow.md`
