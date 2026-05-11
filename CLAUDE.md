# CLAUDE.md — AI Dev Flow 项目说明

> 这是项目的"持续记忆"。新会话启动后，Claude Code 会自动加载此文件，确保开发不会因对话关闭而中断。

---

## 项目概述

**AI Dev Flow** 是 `ai-dev-platform` 的重构版本 —— 一个 AI 驱动的全流程软件开发管线。

- **定位**：AI 项目经理 — 从需求到交付的完整自动化流水线
- **入口**：`python pipeline.py --project D:/MyPrj/目标项目`
- **核心技术**：Python（编排）+ Goose CLI（AI 引擎）+ YAML Recipe（阶段定义）

---

## 开发状态追踪

### 已实现 (2026-05-11)

| 模块 | 状态 | 说明 |
|------|------|------|
| `pipeline/__init__.py` | ✅ 完成 | 包初始化，版本号 2.0.0 |
| `pipeline/logger.py` | ✅ 完成 | 结构化日志，终端+文件双输出，带颜色 |
| `pipeline/state.py` | ✅ 完成 | .pipeline_stage / .pipeline_note 读写 |
| `pipeline/config.py` | ✅ 完成 | pipeline.yaml + profile.yml 加载，dataclass 定义 |
| `pipeline/executor.py` | ✅ 完成 | goose CLI 调用封装，参数构建 |
| `pipeline/checkpoint.py` | ✅ 完成 | 人工确认交互 |
| `pipeline/error_handler.py` | ✅ 完成 | 4 选项错误处理 (retry/fix/note/skip) |
| `pipeline.yaml` | ✅ 完成 | 8 阶段 + 4 检查点定义，数据驱动 |
| `pipeline.py` | ✅ 完成 | CLI 入口，argparse，主循环 |
| Recipe 文件 (7个) | ✅ 完成 | 从原项目复制 |
| Profile 模板 | ✅ 完成 | java-spring.yml |
| `CLAUDE.md` | ✅ 完成 | 本文件 |
| `ARCHITECTURE.md` | ✅ 完成 | 架构设计文档 |
| Bug 修复 | ✅ 完成 | checkpoint 节点 recipe 字段 KeyError (2026-05-11) |
| Bug 修复 | ✅ 完成 | Phase 2-7 缺少 output_file 校验，导致 03-plan.md 缺失未被发现 (2026-05-11) |
| Bug 发现 | 🔴 已知 | AI 会额外生成非预期文件 (02-review-report.md, 03-change-list.md, 04-build-report.md) |
| Bug 发现 | 🔴 已知 | goose 进程退出后未清理，存在僵尸进程堆积 |
| `README.md` | ✅ 完成 | 用户手册 |
| `.gitignore` | ✅ 完成 | Git 忽略规则 |
| Git 初始化 | ✅ 完成 | 仓库初始化 |

### 待实现（按优先级）

| 优先级 | 任务 | 说明 |
|--------|------|------|
| **P0** | 依赖声明 | 创建 `requirements.txt` (PyYAML) |
| **P0** | 集成测试 | 用 testproj 做端到端测试 |
| **P1** | `--ci` 模式 | 跳过所有人工检查点，自动使用默认选择 |
| **P1** | 上下文共享 | 阶段间传递摘要，减少重复读取 |
| **P2** | 阶段耗时统计 | 记录每个阶段的执行时间，定位瓶颈 |
| **P2** | 并发安全 | 防止同一项目重复执行管线 |
| **P3** | Web Dashboard | 可选的 Web 界面查看管线状态 |
| **P3** | 多项目并行 | 同时管理多个项目的管线 |

---

## 架构决策记录

### ADR-001: 选择 Python 替代 Bat

**决策**：编排引擎从 Windows Batch 改为 Python 3.9+。

**原因**：
- 代码复用：Bat 中 7 个 phase 是 copy-paste，Python 用一个循环解决
- 数据结构化：状态机、阶段定义全部用 dataclass，加新阶段只改 YAML
- 可测试性：核心逻辑可单测，Bat 无法测试
- 中文编码：Python 天然 UTF-8，无 PowerShell/Bat 的编码问题

**权衡**：增加了 Python 依赖（原方案零依赖），但 Python 是开发者的标准工具。

### ADR-002: Recipe 文件保持不变

**决策**：YAML Recipe 格式和内容不修改，作为稳定接口层。

**原因**：Recipe 是 AI 的"操作手册"，格式已经过验证且与 goose CLI 深度绑定。重构的重点是编排层，不是 Recipe 层。

### ADR-003: 数据驱动阶段定义

**决策**：阶段定义从 Bat 中的 goto 标签迁移到 `pipeline.yaml`。

**原因**：添加新阶段只需改 YAML 配置，无需修改任何 Python 代码。

---

## 如何继续开发

### 新会话启动

1. Claude Code 自动加载此文件
2. 查看「开发状态追踪」了解进度
3. 查看「待实现」选择下一个任务
4. 完成后更新本文件的对应状态

### 开发约定

- **所有功能添加必须更新 CLAUDE.md** 的开发状态追踪表格
- 重大设计决策写入「架构决策记录」
- 代码风格：Python 标准，type hints，无过度抽象
- 测试：`pipeline/tests/` 目录下
- 不修改 `recipes/` 目录中的 YAML 文件（除非 goose 版本升级需要适配）

### 环境要求

- Python 3.9+
- goose CLI >= 1.33
- PyYAML (`pip install pyyaml`)
