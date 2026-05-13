---
name: v4.0 升级改造
description: 将 ai-dev-flow 从独立编排引擎改造为 Multica 标准执行层 — 已搁置
type: project
---

# v4.0 升级改造 — ⏸️ 已搁置

**Why**: 原基于 `D:\MyPrj\test\ai-dev-flow升级改造方案.md` 和 `D:\MyPrj\test\AI研发体系接入规范.md`，计划将 v3.2.0 改造为 Multica 标准执行层。

**搁置原因**: 输入文档外部仍有保留，但项目内分析报告和改造方案（temp/ 目录）已清理。当前优先 P1 执行能力增强（并发控制、验证闭环等），Multica 接入等实际需要时再做。

**How to apply**: 若恢复此计划，从外部输入文档重新生成分析报告，然后按 12 任务推进。

## 12 任务 4 周计划（备忘）

| 周 | 任务 | 文件 | 状态 |
|-----|------|------|------|
| W1 | T1: 子进程 env 过滤 | executor.py | [ ] |
| W1 | T2: 路径穿越检测 | sandbox.py | [ ] |
| W1 | T3: 多模型配置 | model_config.py (新) | [ ] |
| W2 | T4: HTTP 客户端 | multica_client.py (新) | [ ] |
| W2 | T5: Token 追踪 | token_tracker.py (新) | [ ] |
| W2 | T6: executor Token 集成 | executor.py | [ ] |
| W3 | T7: 任务图重构 | task_graph.py | [ ] |
| W3 | T8: 错误策略化 | error_handler.py | [ ] |
| W3 | T9: 知识库扩展 | knowledge_accumulator.py | [ ] |
| W4 | T10: 守护进程 | multica_agent.py (新) | [ ] |
| W4 | T11: 双模式 | pipeline.py | [ ] |
| W4 | T12: 废弃清理 | 5 文件 | [ ] |
