# 贡献指南

感谢关注 AI Dev Flow。这是一个 Python 编排引擎，通过 YAML 定义阶段和任务，驱动 goose CLI 完成软件开发流程。

## 开发环境

| 依赖 | 版本 |
|------|------|
| Python | 3.9+ |
| goose CLI | >= 1.33 |
| PyYAML | >= 6.0 |

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt   # pytest + pytest-mock
```

AI 阶段需要 `CUSTOM_DEEPSEEK_API_KEY`。跑单元测试不需要 API Key。

## 运行测试

```bash
pytest tests/ -v
```

集成测试标记为 `integration`，CI 中单独运行。提交前请确保单元测试全绿：

```bash
pytest tests/ -v -m "not integration"
```

## 代码结构

- `pipeline/` — 编排引擎模块
- `pipeline.py` — CLI 入口
- `pipeline.yaml` — 阶段定义
- `recipes/steps/` — 各阶段的 goose recipe
- `tests/` — 单元与集成测试

架构说明见 `ARCHITECTURE.md`，编码约定见 `.claude/rules/`。

## 提交规范

提交信息格式：`<type>: <简述>`

| type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `refactor` | 重构（不改行为） |
| `docs` | 文档 |
| `test` | 测试 |
| `chore` | 构建、依赖、发布杂项 |

一个提交做一件事。修复 Bug 时附上能复现问题的测试。

## 提交 Pull Request

1. 从 `main` 切分支，命名 `fix/...`、`feat/...` 或 `docs/...`
2. 改动聚焦单一主题
3. 确保 `pytest tests/ -v -m "not integration"` 通过
4. 在 PR 描述里写明：改了什么、为什么、如何验证
5. 涉及行为变更时同步更新 `CHANGELOG.md` 的 `[Unreleased]` 段

## 报告问题

请使用 Issue 模板，附上：

- 复现步骤
- Python / goose 版本、操作系统
- 完整报错信息（注意移除 API Key）
- `.ai-dev/` 下相关的状态文件片段（同样移除敏感信息）

## 安全

日志、Issue、PR 中不要出现 API Key、token 或连接串凭据。
