# AI Dev Flow — 架构设计文档

## 一、设计目标

将 `ai-dev-platform` 从约 300 行重复的 Windows Batch 脚本重构为 **数据驱动、可测试、可扩展** 的 Python 编排引擎，同时保持 Recipe 文件不变。

## 二、三层架构

```
CLI 入口 (pipeline.py)     ← argparse，用户交互
        ↓
编排引擎 (pipeline/)        ← 状态机、错误处理、检查点
        ↓
AI 引擎 (goose CLI)         ← LLM 通信，执行具体任务
```

### 各层职责

| 层 | 文件 | 职责 |
|----|------|------|
| CLI | `pipeline.py` | 参数解析、项目初始化、主循环 |
| 配置 | `pipeline/config.py` | 加载 pipeline.yaml 和 profile.yml |
| 状态 | `pipeline/state.py` | .pipeline_stage / .pipeline_note 读写 |
| 执行 | `pipeline/executor.py` | goose CLI 调用封装 |
| 检查点 | `pipeline/checkpoint.py` | 人工确认交互 |
| 错误 | `pipeline/error_handler.py` | 4 选项错误处理菜单 |
| 日志 | `pipeline/logger.py` | 结构化日志，终端+文件双输出 |
| 阶段定义 | `pipeline.yaml` | 阶段列表、参数、状态值 |

## 三、状态机

```
input_done → phase1(refine) → checkpoint_a → phase2(analysis) → checkpoint_b
→ phase3(design) → checkpoint_c → phase4(implement) → phase5(build)
→ phase6(review) → checkpoint_d → phase7(delivery) → done
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
├── pipeline.yaml               ← 阶段定义（数据驱动）
├── pipeline/                   ← 编排引擎包
│   ├── __init__.py
│   ├── config.py
│   ├── state.py
│   ├── executor.py
│   ├── checkpoint.py
│   ├── error_handler.py
│   └── logger.py
├── recipes/steps/              ← 7 个 Goose Recipe (不变)
├── profiles/                   ← 项目画像模板
├── CLAUDE.md                   ← 项目说明 + 开发进度
├── ARCHITECTURE.md             ← 本文件
├── README.md                   ← 用户手册
└── requirements.txt            ← Python 依赖
```

## 六、目标项目的 .ai-dev 结构

```
目标项目/
└── .ai-dev/
    ├── profile.yml                ← 项目画像
    ├── requirement-raw.md         ← 原始需求
    ├── requirement.md             ← 精炼后需求
    ├── .pipeline_stage            ← 当前阶段
    ├── .pipeline_note             ← 人工笔记
    ├── logs/                      ← 执行日志
    │   └── pipeline_20260511_100000.log
    └── outputs/                   ← 各阶段产出
        ├── 02-analysis.md
        ├── 03-plan.md
        ├── 04-change-list.md
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
