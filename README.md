# AI Dev Flow

> 一条命令驱动「需求→分析→方案→编码→审查→交付」的完整开发管线。
> 中断可恢复，失败可介入，全过程可追溯。

---

## 一句话理解

这是一个 **AI 项目经理** — 你告诉它要做什么，它帮你走完整个软件开发流程，每一步产出文档，每一步你可以审核、修改、打断、恢复。

---

## 流程总览

```
python pipeline.py --project D:/MyPrj/你的项目

Phase 1 ─── 需求精炼 (AI 输出结构化需求文档)
  ⚠ 检查点 A ─ 确认需求
Phase 2 ─── 需求分析 (拆功能点、数据流、不确定项)
  ⚠ 检查点 B ─ 闭环不确定项
Phase 3 ─── 工程方案 (架构设计、接口定义、数据模型)
  ⚠ 检查点 C ─ 确认方案
Phase 4 ─── 编码实现 (AI 写代码，200 turns)
Phase 5 ─── 编译 + 测试
Phase 6 ─── 代码 + 安全审查
  ⚠ 检查点 D ─ 安全确认（仅高危暂停）
Phase 7 ─── 交付 (变更清单、构建验证、审查结论)
```

---

## 快速开始

### 前置条件

| 依赖 | 说明 |
|------|------|
| Python 3.9+ | 编排引擎 |
| goose CLI >= 1.33 | AI 执行引擎 |
| LLM API Key | DeepSeek 或其他 goose 兼容的 Provider |

### 安装

```bash
cd D:/MyPrj/ai-dev-flow

# 安装 Python 依赖
pip install pyyaml

# 配置 API Key
set CUSTOM_DEEPSEEK_API_KEY=你的key
# 或写入系统环境变量
```

### 使用

```bash
# 交互式启动
python pipeline.py

# 指定项目路径
python pipeline.py --project D:/MyPrj/my-project

# 从指定阶段开始
python pipeline.py --project D:/MyPrj/my-project --from-stage phase3

# 预览模式（不实际执行）
python pipeline.py --project D:/MyPrj/my-project --dry-run
```

---

## 核心机制

### 中断恢复

任何原因中断（Ctrl+C、关机、goose 崩溃），重新运行相同命令即可从断点继续。

**原理**：项目目录下的 `.ai-dev/.pipeline_stage` 记录了当前进度。

### 错误处理

每个 AI 阶段失败时提供 4 个选项：

| 选项 | 行为 | 适用场景 |
|------|------|---------|
| 1) retry | 原地重试 | 网络波动 |
| 2) fix | 手动修改后重试 | 编译错误 |
| 3) write note | 写说明笔记并退出 | 问题复杂，晚点处理 |
| 4) skip | 跳过该阶段 | 已手动完成 |

---

## 项目结构

```
ai-dev-flow/
├── pipeline.py              ← 入口
├── pipeline.yaml            ← 阶段定义
├── pipeline/                ← 编排引擎
├── recipes/steps/           ← AI 阶段定义 (7 个 YAML)
├── profiles/                ← 项目画像模板
├── ARCHITECTURE.md          ← 架构设计
└── CLAUDE.md                ← 开发进度
```

---

## 与原项目 (ai-dev-platform) 的区别

| 维度 | ai-dev-platform | ai-dev-flow |
|------|-----------------|-------------|
| 编排语言 | Windows Batch | Python 3.9+ |
| 阶段定义 | 硬编码在 bat 中 | 数据驱动 (pipeline.yaml) |
| 日志 | 屏幕输出 | 结构化日志到文件 |
| 加新阶段 | 改 bat 代码 | 改 YAML 配置 |
| 测试 | 不可测试 | 可单测 |
| Recipe 文件 | YAML | YAML (不变) |

---

## 许可证

MIT
