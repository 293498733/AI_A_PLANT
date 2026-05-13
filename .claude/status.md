# 开发状态追踪

> 最后更新: 2026-05-13 | 当前版本: v3.5.0

## 模块状态

| 模块 | 状态 | 版本 | 说明 |
|------|------|------|------|
| `pipeline/__init__.py` | ✅ | v3.5 | 版本号 3.5.0 |
| `pipeline/logger.py` | ✅ | 完成 | 结构化日志 |
| `pipeline/state.py` | ✅ | v3.1 | 阶段/任务状态读写（原子写入） |
| `pipeline/config.py` | ✅ | v3.3 | StageConfig + TaskConfig + TaskGraphConfig（max_workers） |
| `pipeline/executor.py` | ✅ | v3.5 | Popen + 看门狗 + 线程化 I/O + 心跳 + quiet 输出 |
| `pipeline/checkpoint.py` | ⚠️ 待废弃 | v3.1 | 人工确认（v4.0 废弃） |
| `pipeline/error_handler.py` | ✅ | v3.1 | 双层级错误处理 + CI 自动决策 |
| `pipeline/task_state.py` | ✅ | v3.1 | TaskStateManager |
| `pipeline/task_context.py` | ✅ | v3.1 | ContextAssembler |
| `pipeline/task_graph.py` | ✅ | v3.5 | 任务图执行器 + 并发控制 + 验证闭环 + 静默输出 |
| `pipeline/git_ops.py` | ✅ | v3.2 | Git 自动提交 + commit_files() |
| `pipeline/snapshot.py` | ✅ | 完成 | SnapshotManager |
| `pipeline/semantic_summarizer.py` | ✅ | 完成 | 8 语言语义提取 |
| `pipeline/knowledge_accumulator.py` | ✅ | 完成 | KnowledgeAccumulator |
| `pipeline/sandbox.py` | ✅ | v3.2 | Git worktree 沙箱管理器 |
| `pipeline/watchdog.py` | ✅ | v3.2 | 进程看门狗（taskkill /F /T） |
| `pipeline.py` | ✅ | v3.2 | CLI 入口 |
| `pipeline.yaml` | ✅ | v3.1 | 12 阶段定义 |
| Recipe 文件 (10) | ✅ | v3.1 | Phase 0-7 + task-template |
| `tests/` (15 文件) | ✅ | v3.4 | 189 测试覆盖全模块 |
| `.github/workflows/test.yml` | ✅ | 完成 | GitHub Actions CI |

## 已修复 Bug

| Bug | 修复日期 |
|-----|---------|
| checkpoint KeyError | 2026-05-11 |
| output_file 校验缺失 | 2026-05-11 |
| 旧产出残留 | 2026-05-11 |
| 进度不可见 | 2026-05-11 |
| 检查点盲确认 | 2026-05-11 |
| 无运行摘要 | 2026-05-11 |
| AI 额外产出文件 | 2026-05-11 |
| Phase 3 不产出 03-plan.md | 2026-05-11 |
| 崩溃残留文件 | 2026-05-12 |
| 状态文件非原子写入 | 2026-05-12 |
| NOTE_EXIT 后无法继续 | 2026-05-12 |
| Goose 卡死 14 小时 | 2026-05-13（沙箱+看门狗修复） |

## 已知问题

| 问题 | 状态 | 说明 |
|------|------|------|
| goose 僵尸进程 | 🟡 v3.2 看门狗覆盖 | taskkill /F /T 杀进程树 |
| 单 agent 串行 | ✅ v3.3 已实现 | ThreadPoolExecutor + max_workers=3 + parallel_group |
| 质量评分缺失 | 🟡 P2 计划 | 仍为二进制 pass/fail |
| 规划偏离检测 | 🟡 P2 计划 | 无 StrayMark 式检测 |
