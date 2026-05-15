# 开发状态追踪

> 最后更新: 2026-05-15 | 当前版本: v3.8.0

## 模块状态

| 模块 | 状态 | 版本 | 说明 |
|------|------|------|------|
| `pipeline/__init__.py` | ✅ | v3.8 | 版本号 3.8.0 |
| `pipeline/logger.py` | ✅ | 完成 | 结构化日志 |
| `pipeline/state.py` | ✅ | v3.1 | 阶段/任务状态读写（原子写入） |
| `pipeline/config.py` | ✅ | v3.8 | StageConfig + TaskConfig（verification 字段） |
| `pipeline/executor.py` | ✅ | v3.8 | Popen + 看门狗 + 线程化 I/O + 循环检测 |
| `pipeline/checkpoint.py` | ⚠️ 待废弃 | v3.1 | 人工确认（v4.0 废弃） |
| `pipeline/error_handler.py` | ✅ | v3.1 | 双层级错误处理 + CI 自动决策 |
| `pipeline/task_state.py` | ✅ | v3.8 | TaskStateManager（三元状态） |
| `pipeline/task_context.py` | ✅ | v3.1 | ContextAssembler |
| `pipeline/task_graph.py` | ✅ | v3.8 | 任务图执行器（按类型验证/三元状态/JAVA_HOME 加固/结构化错误） |
| `pipeline/git_ops.py` | ✅ | v3.2 | Git 自动提交 + commit_files() |
| `pipeline/snapshot.py` | ✅ | 完成 | SnapshotManager |
| `pipeline/semantic_summarizer.py` | ✅ | 完成 | 8 语言语义提取 |
| `pipeline/knowledge_accumulator.py` | ✅ | 完成 | KnowledgeAccumulator |
| `pipeline/sandbox.py` | ✅ | v3.2 | Git worktree 沙箱管理器 |
| `pipeline/watchdog.py` | ✅ | v3.2 | 进程看门狗（taskkill /F /T） |
| `pipeline.py` | ✅ | v3.8 | CLI 入口（前置守卫） |
| `pipeline.yaml` | ✅ | v3.8 | 12 阶段定义（Phase 5 prerequisite） |
| Recipe 文件 (10) | ✅ | v3.1 | Phase 0-7 + task-template |
| `tests/` (15 文件) | ✅ | v3.7 | 197 测试覆盖全模块 |
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
| 沙箱子模块拷贝失败 | 2026-05-14 |

## 已知问题

| 问题 | 状态 | 说明 |
|------|------|------|
| goose 僵尸进程 | 🟡 v3.2 看门狗覆盖 | taskkill /F /T 杀进程树 |
| 单 agent 串行 | ✅ v3.3 已实现 | ThreadPoolExecutor + max_workers=3 + parallel_group |
| 质量评分缺失 | 🟡 P2 计划 | 仍为二进制 pass/fail |
| 规划偏离检测 | 🟡 P2 计划 | 无 StrayMark 式检测 |
| **验证步骤无任务类型区分** | ✅ v3.8 已修复 | 前端任务被 mvn compile 验证误判。加 `TaskConfig.verification` 字段，按 category 自动选策略 |
| **任务状态二值化** | ✅ v3.8 已修复 | 验证失败=任务失败，丢失"代码已产出"。扩展 completed/code_produced/failed_no_output 三元 |
| **JAVA_HOME 注入不稳定** | ✅ v3.8 已修复 | shell=True + env dict + set 三重注入仍可能失效。加 pre-flight check + PATH 注入 |
| **阶段间无前置守卫** | ✅ v3.8 已修复 | Phase 4 失败后 Phase 5 仍启动。pipeline.yaml 加 prerequisite 字段 |
| Goose 语义卡死 | ✅ v3.8 已修复 | 心跳仅检测频率不检测内容模式。加连续重复输出检测 |
