# CLAUDE.md — AI Dev Flow 项目说明

> 这是项目的"持续记忆"。新会话启动后，Claude Code 会自动加载此文件，确保开发不会因对话关闭而中断。

---

## 项目概述

**AI Dev Flow** 是 `ai-dev-platform` 的重构版本 —— 一个 AI 驱动的全流程软件开发管线。

- **定位**：AI 项目经理 — 从需求到交付的完整自动化流水线
- **入口**：`python pipeline.py --project D:/MyPrj/目标项目`
- **核心技术**：Python（编排）+ Goose CLI（AI 引擎）+ YAML Recipe（阶段定义）

---

## 当前开发计划

> **最后更新**: 2026-05-12 | **当前版本**: v3.1.0
> 
> 上次会话产物：snapshot.py（增量扫描）、semantic_summarizer.py（语义摘要）、knowledge_accumulator.py（知识积累）、CI mode、Phase 0（项目初始化）。
> 
> 对比 `temp/gap-analysis.md` 的 10 个差距维度，已闭合 7 个，剩余 3 个为架构升级项（P2）。

### 立即可做 — P0

- [x] **测试基础设施**：pytest + 159 个测试（153 单元 + 6 集成），覆盖全部 15 个模块。运行：`pytest tests/ -v`
- [ ] **端到端集成测试**：用真实 testproj 跑 `python pipeline.py --project testproj --ci` 验证全流程

### 下一批 — P1

- [ ] **多任务并行**：independent tasks 在 parallel_group 内并行执行（目前全串行）。改动点：`pipeline/task_graph.py` 调度循环
- [ ] **子管线执行器**：大模块内部走 mini-pipeline（方案→编码→测试→审查），而非单次 goose 调用。改动点：新增 `pipeline/sub_pipeline.py`

### 架构升级 — P2

- [ ] **多代理审查**：Phase 6 使用独立 goose session + 对立视角 prompt，替代自写自审
- [ ] **质量评分**：5 维加权评分（正确性/测试/质量/安全/性能），不达标自动返回 task_graph
- [ ] **规划偏离检测**：执行中检测实际产出与 03-plan.md 的偏差，自动告警

### 新会话启动指引

1. Claude Code 自动加载本文件 → 直接看本节了解"上次做到哪、接下来做什么"
2. 从 P0 开始，逐项完成
3. 每完成一项，勾选对应 checkbox 并更新「最后更新」日期
4. 不要在无计划的情况下开始大规模重构

---

## 开发状态追踪

### 已实现 (v3.1.0 — 增量扫描 + 语义摘要 + 知识积累 + 中断恢复加固)

| 模块 | 状态 | 说明 |
|------|------|------|
| `pipeline/__init__.py` | ✅ v3.1 | 包初始化，版本号 3.1.0 |
| `pipeline/logger.py` | ✅ 完成 | 结构化日志，终端+文件双输出，带颜色 |
| `pipeline/state.py` | ✅ v3.1 | .pipeline_stage / .pipeline_note / task_state.json 读写（原子写入） |
| `pipeline/config.py` | ✅ v3 | StageConfig + TaskConfig + TaskGraphConfig dataclass |
| `pipeline/executor.py` | ✅ v3 | Popen 实时输出 + run_task() 任务级执行 |
| `pipeline/checkpoint.py` | ✅ v3.1 | 人工确认 + CI 自动跳过 + 产出文件前 25 行摘要预览 |
| `pipeline/error_handler.py` | ✅ v3.1 | Action + TaskAction 双层级错误处理 + CI 自动决策 |
| `pipeline/task_state.py` | ✅ v3.1 | TaskStateManager：依赖拓扑、状态追踪、崩溃恢复、模块级进度 |
| `pipeline/task_context.py` | ✅ v3.1 | ContextAssembler：增量扫描 + 语义摘要 + 上下文组装 |
| `pipeline/task_graph.py` | ✅ v3.1 | 任务图执行器：拓扑排序 + fresh session + 残留清理 + 知识注入 |
| `pipeline/git_ops.py` | ✅ 完成 | Git 自动提交、pre-task stash、commit hash |
| `pipeline/snapshot.py` | ✅ 新增 | SnapshotManager：文件树 hash 快照 + 增量变更检测 |
| `pipeline/semantic_summarizer.py` | ✅ 新增 | SemanticSummarizer：代码/文档语义结构提取，零 AI 成本 |
| `pipeline/knowledge_accumulator.py` | ✅ 新增 | KnowledgeAccumulator：自动提取关键决策，下游任务注入 |
| `pipeline.py` | ✅ v3.1 | CLI、任务图路由、阶段计时、运行摘要、--ci 模式 |
| `pipeline.yaml` | ✅ v3.1 | 12 阶段：+Phase 0(项目初始化) + Phase 3.5(拆分) + task_graph |
| Recipe 文件 (10个) | ✅ v3.1 | 新增 00-init-project.yaml + 03.5-decompose.yaml + task-template.yaml |
| Profile 模板 | ✅ 完成 | java-spring.yml |
| `CLAUDE.md` | ✅ 完成 | 本文件 |
| `ARCHITECTURE.md` | ✅ 完成 | 架构设计文档 |
| `README.md` | ✅ 完成 | 用户手册 |
| `requirements.txt` | ✅ 完成 | pyyaml>=6.0 |
| `requirements-dev.txt` | ✅ 新增 | pytest + pytest-mock |
| `tests/` (13 文件) | ✅ 新增 | 159 个测试覆盖 15 个模块 |
| `.github/workflows/test.yml` | ✅ 新增 | GitHub Actions CI，Python 3.9-3.12 matrix |
| `.gitignore` | ✅ 完成 | Git 忽略规则 |
| Git 初始化 | ✅ 完成 | 仓库初始化 + GitHub push |

### 已修复 Bug

| Bug | 状态 | 说明 |
|-----|------|------|
| checkpoint KeyError | ✅ 已修复 | recipe 字段改为可选 (2026-05-11) |
| output_file 校验缺失 | ✅ 已修复 | Phase 2-7 补全 (2026-05-11) |
| 旧产出残留 | ✅ 已修复 | 自动检测 + 提示清理 + --new 参数 (2026-05-11) |
| 进度不可见 | ✅ 已修复 | executor 实时透传 goose 输出 (2026-05-11) |
| 检查点盲确认 | ✅ 已修复 | 展示产出文件前 25 行摘要 (2026-05-11) |
| 无运行摘要 | ✅ 已修复 | 完成后打印阶段耗时 + 产出物清单 (2026-05-11) |
| AI 额外产出文件 | ✅ 已检测 | 阶段后对比 snapshot，警告非预期文件 (2026-05-11) |
| Phase 3 不产出 03-plan.md | ✅ 已修复 | Recipe 指令冲突：明确文件类型 + 强制写入段落 (2026-05-11) |
| 崩溃残留文件 | ✅ 已修复 | 重跑前自动检测并清理上次半成品文件 (2026-05-12) |
| 状态文件非原子写入 | ✅ 已修复 | task_state.json 改为临时文件+重命名 (2026-05-12) |
| NOTE_EXIT 后无法继续 | ✅ 已修复 | 增加"保留笔记继续"选项 (2026-05-12) |

### 已知问题

| 问题 | 状态 | 说明 |
|------|------|------|
| goose 僵尸进程 | 🔴 暂缓 | 用户同时运行多个 goose，暂不确定是否管线导致 |
| 单 agent 串行执行 | 🟡 架构限制 | 无多代理协作、无交叉审查（自写自审） |
| 质量评分缺失 | 🟡 待实现 | 仍为二进制 pass/fail（exit code），无 5 维评分 |
| 规划-执行偏离检测 | 🟡 待实现 | 无 StrayMark 式偏离检测，方案变更后下游任务不知情 |
| 未沙箱隔离 | 🟢 设计选择 | goose 直接在真实项目目录操作，无沙箱回滚 |

### 待实现（按优先级）

| 优先级 | 任务 | 说明 |
|--------|------|------|
| **P0** | 集成测试 | 用 testproj 做端到端测试，验证任务图执行 |
| **P1** | 多任务并行 | independent tasks 在 parallel_group 内并行执行 |
| **P1** | 子管线执行器 | 大模块内部走 mini-pipeline（方案→编码→测试→审查） |
| **P2** | 多代理审查 | Phase 6 使用独立 AI 视角进行审查（非自审） |
| **P2** | 质量评分 | 5 维加权评分 (正确性/测试/质量/安全/性能) |
| **P2** | 规划偏离检测 | 执行中检测实际产出与方案规划的偏差，自动告警 |
| **P3** | Web Dashboard | 可选的 Web 界面查看管线状态 |

---

## 架构决策记录

### ADR-001: 选择 Python 替代 Bat

**决策**：编排引擎从 Windows Batch 改为 Python 3.9+。

### ADR-002: Recipe 文件保持不变

**决策**：YAML Recipe 格式和内容不修改，作为稳定接口层。

### ADR-003: 数据驱动阶段定义

**决策**：阶段定义从 Bat 中的 goto 标签迁移到 `pipeline.yaml`。

### ADR-004: Popen 替代 subprocess.run

**决策**：executor 使用 `subprocess.Popen` + 逐行读取 stdout。

### ADR-005: 任务驱动 + 上下文外化 (v3.0.0)

**决策**：将单体 Phase 4（200 turns）替换为任务图执行引擎。每个任务在全新 goose 会话中执行，上下文仅通过文件传递。

**原因**：
- 上下文退化：单会话在 turn 60-80 后开始退化，无法支撑中大型项目的 8+ 子系统
- 可恢复性：任务级状态追踪允许从任意任务恢复，而非整阶段重跑
- 可审计性：每个任务产出一个 git commit，变更可追溯
- 可并行性：独立任务可在 parallel_group 内并行执行（P1）

**权衡**：AI 无法利用之前的对话上下文，所有信息必须外化到 context_notes 和文件中。这要求任务拆分阶段（Phase 3.5）产出高质量的 context_notes。

### ADR-006: 勤提交、智能推送 (2026-05-11)

**决策**：代码修改随时 `git commit` 留痕，但 `git push` 由 Claude 自动判断时机——阶段性完成才推送，快速迭代中仅本地提交。

**原因**：
- 高频 commit 保证代码可回溯到任意中间状态
- 不盲目 push 避免远程历史碎片化（一堆"改了一半"的提交）
- 阶段性完成的完整提交才值得同步到 GitHub

### ADR-007: 增量扫描 + 语义摘要 + 知识积累 (v3.1.0, 2026-05-12)

**决策**：上下文管理从"文件截断"升级为"语义外化"三件套——项目快照增量扫描、代码语义结构提取、跨任务知识自动积累。

**原因**：
- 用户反馈每次扫描全项目费时费 token——SnapshotManager 存文件树 hash，后续只读变更文件
- ContextAssembler 原本对 10-50KB 文件只做前 300 行截断，丢失关键信息——SemanticSummarizer 按语言规则提取类/函数签名、关键注释，零 AI 成本
- 人工 .pipeline_note 无法规模化——KnowledgeAccumulator 自动从每个任务产出中提取 Key Decisions 段落，下游任务注入相关历史决策

**新增模块**：
- `pipeline/snapshot.py` — 文件树 hash + mtime/size 变更检测 + 内容缓存
- `pipeline/semantic_summarizer.py` — 支持 Python/Java/TS/Vue/YAML/Markdown/SQL/XML 8 种语言的结构提取
- `pipeline/knowledge_accumulator.py` — 扫描产出文件的 Key Decisions 段落，按 category 查询注入

**权衡**：摘要器是规则驱动而非 AI 驱动，复杂语义（如"这段代码做了什么业务判断"）无法提取。未来可升级为 AI 驱动的摘要（P2）。

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
- 不修改 `recipes/` 目录中的 YAML 文件（除非 goose 版本升级需要适配）

### Git 工作流规则

**核心理念：本地提交要勤（方便回溯），推送看时机（完整才推）。**

| 场景 | 行为 |
|------|------|
| **任何代码修改完成** | 立即 `git commit`，保持提交粒度细、回溯方便 |
| **阶段性完成**（如一个 bug 修完、一个功能做完） | commit → 自动 `git push origin main` |
| **快速迭代中**（多个小提交在短时间内） | 仅 commit 不 push，等阶段性完成再一起推 |
| **会话结束时仍有未推送提交** | 提醒用户，询问是否推送 |
| **用户明确说"提交"/"推送"** | commit + push |
| **推送失败（网络/权限）** | 告知用户，提交保留本地，不阻塞，不重试 |

**自动判断 push 的时机**：
1. 一个完整的功能/修复完成时 → push
2. 用户说"提交"/"推送"/"上传"时 → push
3. 连续修改多个相关文件，最后一个改动完成时 → push
4. 仅改一个错字或小调整，后续还有更多改动 → 只 commit 不 push
5. 推送失败 → 不重试，后续 commit 继续累积

### 环境要求

- Python 3.9+
- goose CLI >= 1.33
- PyYAML (`pip install pyyaml`)
