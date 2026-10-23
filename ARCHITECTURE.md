# AI Dev Flow — 架构设计文档

## 一、设计目标

将 `ai-dev-platform` 从约 300 行重复的 Windows Batch 脚本重构为 **数据驱动、可测试、可扩展** 的 Python 编排引擎，同时保持 Recipe 文件不变。

## 二、三层架构

```
CLI 入口 (pipeline.py)     ← argparse，用户交互，--ci 模式
        ↓
编排引擎 (pipeline/)        ← 状态机、错误处理、检查点、任务图、快照
        ↓
AI 引擎 (goose CLI)         ← LLM 通信，执行具体任务
```

### 各层职责

| 层 | 文件 | 职责 |
|----|------|------|
| CLI | `pipeline.py` | 参数解析、项目初始化、主循环、--ci 模式 |
| 配置 | `pipeline/config.py` | 加载 pipeline.yaml 和 profile.yml |
| 状态 | `pipeline/state.py` | .pipeline_stage / .pipeline_note 读写（原子写入） |
| 执行 | `pipeline/executor.py` | goose CLI 调用封装，Popen 实时输出 |
| 检查点 | `pipeline/checkpoint.py` | 人工确认交互 + CI 自动跳过 |
| 错误 | `pipeline/error_handler.py` | 阶段级 + 任务级双层错误处理 + CI 自动决策 |
| 日志 | `pipeline/logger.py` | 结构化日志，终端+文件双输出 |
| 阶段定义 | `pipeline.yaml` | 12 阶段列表、参数、状态值 |
| 任务状态 | `pipeline/task_state.py` | TaskStateManager，依赖拓扑 + 崩溃恢复 + 模块进度 |
| 上下文 | `pipeline/task_context.py` | ContextAssembler，增量扫描 + 语义摘要 + 文件组装 |
| 任务图 | `pipeline/task_graph.py` | 任务图执行器，fresh session per task + 知识注入 |
| Git | `pipeline/git_ops.py` | 自动 commit per task |
| 快照 | `pipeline/snapshot.py` | SnapshotManager，文件树 hash + 增量变更检测 |
| 语义摘要 | `pipeline/semantic_summarizer.py` | SemanticSummarizer，8 种语言规则提取，零 AI 成本 |
| 知识积累 | `pipeline/knowledge_accumulator.py` | KnowledgeAccumulator，Key Decisions 自动提取注入 |

## 三、状态机

### 全局管线状态机
```
phase0(init) → phase1(refine) → checkpoint_a → phase2(analysis) → checkpoint_b
→ phase3(design) → checkpoint_c → phase3.5(decompose) → checkpoint_c2
→ task_graph(tasks) → phase5(build) → phase6(review) → checkpoint_d → phase7(delivery) → done
```

### 任务图内部状态机（task_graph 阶段）
```
                    ┌──────────┐
                    │ pending   │  depends_on 未满足
                    └────┬─────┘
                         │ depends_on 全部 done
                         ▼
                    ┌──────────┐
                    │ ready     │  等待调度
                    └────┬─────┘
                         │ 调度执行
                         ▼
                    ┌──────────┐
              ┌─────│in_progress│─────┐
              │     └──────────┘     │
              │ exit 0 + outputs ok  │ exit !=0 或 timeout
              ▼                      ▼
         ┌──────────┐          ┌──────────┐
         │ completed │          │  failed   │
         │ +git commit          └────┬─────┘
         └──────────┘               │ retries<limit → ready
                                    │ retries>=limit → 人工: skip/abort
                                    ▼
                               ┌──────────┐
                               │  skipped  │
                               └──────────┘
```

- 每个阶段完成后写入 `.pipeline_stage`
- 启动时读取该文件，跳过已完成阶段
- 全部完成后删除 `.pipeline_stage`
- 中断恢复：重跑相同命令，自动从断点继续

## 四、数据流

```
pipeline.yaml  ──→ config.py (StageConfig) ──→ pipeline.py (主循环)
                                                   │
                              ┌──────────────────────┤
                              ▼                      ▼
                         executor.py           checkpoint.py
                              │                      │
                              ▼                      ▼
                         goose CLI              人工确认
                              │
                              ▼
                         .pipeline_stage (写入状态)
```

## 五、目录结构

```
ai-dev-flow/
├── pipeline.py                 ← 入口
├── pipeline.yaml               ← 阶段定义（数据驱动，12 阶段）
├── pipeline/                   ← 编排引擎包（15 个模块）
│   ├── __init__.py
│   ├── config.py
│   ├── state.py
│   ├── executor.py
│   ├── checkpoint.py
│   ├── error_handler.py
│   ├── logger.py
│   ├── task_state.py          ← v3.0: 任务状态管理 + 依赖拓扑
│   ├── task_context.py        ← v3.1: 上下文组装 + 增量扫描 + 语义摘要
│   ├── task_graph.py          ← v3.1: 任务图执行 + 残留清理 + 知识注入
│   ├── git_ops.py             ← v3.0: Git 自动提交
│   ├── snapshot.py            ← v3.1: 文件树快照 + 增量变更检测
│   ├── semantic_summarizer.py ← v3.1: 代码语义结构提取（8 语言）
│   └── knowledge_accumulator.py ← v3.1: 跨任务知识自动积累
├── recipes/steps/              ← 10 个 Goose Recipe（+00-init-project.yaml）
├── profiles/                   ← 项目画像模板
├── CLAUDE.md                   ← 项目说明 + 开发计划 + 进度追踪
├── ARCHITECTURE.md             ← 本文件
├── README.md                   ← 用户手册
└── requirements.txt            ← Python 依赖
```

## 六、目标项目的 .ai-dev 结构

```
目标项目/
└── .ai-dev/
    ├── profile.yml                ← 项目画像（Phase 0 生成）
    ├── project-map.md             ← 项目架构地图（Phase 0 生成）
    ├── requirement-raw.md         ← 原始需求
    ├── requirement.md             ← 精炼后需求
    ├── .pipeline_stage            ← 当前阶段
    ├── .pipeline_note             ← 人工笔记
    ├── tasks.yaml                 ← 任务拆分定义
    ├── task_state.json            ← 任务执行状态（原子写入）
    ├── snapshot.json              ← v3.1: 文件树快照（增量扫描基准）
    ├── knowledge-base.md          ← v3.1: 自动积累的跨任务知识
    ├── task_contexts/             ← 每个任务的上下文文件
    │   └── {task_id}.md
    ├── summaries/                 ← v3.1: 语义摘要缓存
    │   └── {hash}.md
    ├── logs/                      ← 执行日志
    │   └── pipeline_20260511_100000.log
    └── outputs/                   ← 各阶段产出
        ├── 02-analysis.md
        ├── 03-plan.md
        ├── 05-build.md
        ├── 06-review.md
        └── 07-delivery.md
```

## 七、关键设计决策

### 为什么 Python 而不是继续用 Bat

| 维度 | Bat | Python |
|------|-----|--------|
| 代码复用 | 7 个 phase = 7 份 copy-paste | 1 个循环 |
| 加新阶段 | 改 bat + 加标签 | 改 pipeline.yaml |
| 可测试性 | 无法测试 | dataclass + mock |
| 中文编码 | 依赖终端配置 | 原生 UTF-8 |
| 错误处理 | goto + errorlevel | try/except + enum |
| 日志 | echo 到屏幕 | 结构化日志到文件 |

### 为什么 Recipe 文件不修改

Recipe 是 goose CLI 的"操作手册"，格式由 goose 定义。它已经是结构化的 YAML，包含参数定义、提示模板、扩展配置。这个格式足够好，重构的重点是编排层。

### 为什么用 YAML 而不是 JSON 做阶段定义

YAML 支持注释、多行字符串、更少语法噪音。`pipeline.yaml` 的读者是开发者，可读性比机器性能更重要。

## 八、扩展点

1. **加新阶段**：在 `pipeline.yaml` 的 `stages` 列表中添加条目即可
2. **加新 Profile**：在 `profiles/` 目录下添加新的 `.yml` 文件
3. **加新 Recipe**：在 `recipes/steps/` 目录下添加新的 `.yaml` 文件
4. **自定义错误处理**：修改 `error_handler.py` 中的 `Action` 枚举
5. **CI 模式**：设置 `--ci` 标志，跳过所有 `is_checkpoint` 阶段

## 九、任务驱动架构（v3.1.0）

### 核心原则

**上下文外化 + 语义积累**：每个任务在全新 goose 会话中执行，不依赖对话记忆。任务间通过文件、git、快照和知识库传递状态。

**关键设计**：
- `tasks.yaml` 定义任务图（id / depends_on / input_files / output_files / context_notes）
- 每个任务执行前，ContextAssembler 从 SnapshotManager 获取增量变更，SemanticSummarizer 对中大型文件做语义提取，KnowledgeAccumulator 注入相关历史决策
- 每个任务完成后自动 git commit，更新文件快照，提取 Key Decisions 到知识库
- 崩溃恢复：task_state.json 原子写入，残留文件自动清理，恢复时重置 in_progress → pending

### v3.0.0 → v3.1.0 演进

| 维度 | v3.0.0 | v3.1.0 |
|------|--------|--------|
| 项目扫描 | 每次全量扫描 | 文件树快照，mtime/size 增量检测 |
| 文件读取 | 按大小截断（前 300 行） | 语义摘要（类/函数签名、关键注释） |
| 知识传递 | 人工 .pipeline_note | 自动提取 Key Decisions，按 category 注入 |
| 错误恢复 | 重置 in_progress → pending | + 残留文件清理 + 笔记保留选项 |
| 人工交互 | 必须人工确认 | --ci 模式自动跳过所有检查点 |
| 模块管理 | 无模块概念 | 模块级进度聚合 + 进度条 |

### 为什么拆成任务而不是继续用大阶段

| 维度 | 单体 Phase 4 | 任务图 |
|------|-------------|--------|
| 上下文 | 200 turns 单会话，退化不可逆 | 每任务 20-60 turns，始终保持新鲜 |
| 可恢复 | 阶段中断从头重跑 | 从失败任务继续 |
| 可审计 | 一个 commit 或零 commit | 每个任务一个 commit |
| 可并行 | 不可 | 独立任务可并行（P1 待实现） |
| AI 盲区 | 自写自审 | 独立会话减少盲区 |
| 知识复用 | 无 | 跨任务决策自动积累注入 |

## 十、中断恢复机制

恢复分两层，各自独立落盘。

### 阶段级

- 每个阶段完成后把 `state_value` 写入 `.ai-dev/.pipeline_stage`
- 重跑同一命令时，`PipelineConfig.find_resume_index()` 找到该值对应的阶段，从下一阶段继续
- 状态值未知时记录警告并从头开始，避免静默跳过
- 全部阶段完成后删除该文件

### 任务级

任务状态保存在 `.ai-dev/task_state.json`，由 `TaskStateManager` 管理。

**写入是原子的**：先写同目录临时文件，再 `Path.replace()` 覆盖，避免进程中断留下半截 JSON。

**状态取值与恢复语义**：

| 状态 | 含义 | 重跑时 |
|------|------|--------|
| `pending` | 未开始 | 依赖满足后进入 ready |
| `in_progress` | 执行中 | 启动时重置为 `pending`（视为崩溃残留） |
| `completed` | 代码产出且验证通过 | 跳过 |
| `code_produced` | 代码已写入，验证未通过 | 计入已完成，下游不被阻塞；保留产出供人工判断 |
| `failed_no_output` | goose 失败或产出文件缺失 | 按重试次数走 ready 或人工决策 |
| `failed` | 已判定失败 | 同上 |
| `skipped` | 人工跳过 | 计入已完成 |

`code_produced` 是 v3.8.0 引入的三元状态之一：区分"没写出来"和"写出来了但验证没过"，后者不应阻断下游任务。

### 现场保留

- 验证失败时沙箱目录保留，供排查；任务错误信息记录在 `task_state.json`
- 看门狗超时后执行器返回 `returncode=-1`，任务按失败处理，沙箱同样保留
- 下一次运行先重置 `in_progress`，再按依赖拓扑继续

### 恢复的边界

- 任务图内部恢复到任务粒度，不恢复到任务内的对话轮次
- 阶段级恢复依赖 `.pipeline_stage` 与实际产出一致；手工删改该文件会改变恢复起点
- `tasks.yaml` 被重写后，`task_state.json` 中不再存在的任务条目会被清理并告警

