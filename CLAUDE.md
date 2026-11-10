# CLAUDE.md — AI Dev Flow

> 项目的"持续记忆"。Claude Code 新会话启动时自动加载。
> 所有回复使用**简体中文**。
> 本文件仅含项目定位、入口和文档索引。详细规则、计划、状态见 `.claude/` 目录。

---

## 项目定位

**AI Dev Flow** — AI 驱动的全流程软件开发管线，当前版本 **v3.10.0**。

- **入口**: `ai-dev-flow --project <目标项目路径>`（源码树内 `python pipeline.py` 等价）
- **技术栈**: Python 3.9+（编排）+ Goose CLI（AI 引擎）+ YAML Recipe（阶段/任务定义）
- **测试**: `pytest tests/ -v`（212 个用例）
- **环境**: Python 3.9+, goose CLI >= 1.33, PyYAML

---

## 关键目录

| 目录/文件 | 用途 |
|-----------|------|
| `ai_dev_flow/` | 编排引擎包（17 个 Python 文件，含 cli/`__main__`） |
| `ai_dev_flow/cli.py` | CLI 主入口（根 `pipeline.py` 为等价启动器） |
| `ai_dev_flow/data/pipeline.yaml` | 12 阶段定义 |
| `ai_dev_flow/data/recipes/steps/` | AI 阶段 Recipe（9 个 YAML） |
| `tests/` | 单元 + 集成测试（15 个文件） |
| `.claude/rules/` | 开发规则（Git 工作流、编码规范、环境要求） |
| `.claude/memory/` | 跨会话持久记忆 |
| `docs/adrs/` | 架构决策记录 |
| `docs/plans/implementation-tracker.md` | **已实现 / 实施中 / 计划实现** 三段式进度追踪 |
| `docs/status.md` | 模块状态、Bug 追踪、已知问题 |

---

## 文档索引

- `ARCHITECTURE.md` — 架构设计文档
- `README.md` — 用户手册（中文，主入口）
- `README.en.md` — 英文README
- `LICENSE` — MIT 许可证
- `CONTRIBUTING.md` — 贡献指南（环境、测试、提交规范、PR 流程）
- `CHANGELOG.md` — 版本变更记录
- `docs/FAQ.md` — 常见问题
- `pyproject.toml` — 打包配置（发行名 `ai-dev-flow`）
- `docs/plans/implementation-tracker.md` — **← 新会话首先看这个**：已实现/实施中/计划实现
- `docs/status.md` — 模块状态 + Bug 追踪
