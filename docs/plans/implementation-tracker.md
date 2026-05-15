# 实现追踪

> 最后更新: 2026-05-15 | 当前版本: v3.8.0

---

## ✅ 已实现

### v3.0.0 — 任务驱动架构 (2026-05-10)
- 任务图执行引擎（`pipeline/task_graph.py`）
- TaskStateManager：依赖拓扑 + 崩溃恢复
- ContextAssembler：上下文组装
- Git 自动提交（`pipeline/git_ops.py`）
- 12 阶段 pipeline.yaml + 10 个 Recipe YAML

### v3.1.0 — 增量上下文 (2026-05-12)
- SnapshotManager：文件树 hash 快照 + 增量变更检测
- SemanticSummarizer：8 语言代码语义提取（零 AI 成本）
- KnowledgeAccumulator：跨任务知识自动积累
- 原子写入 task_state.json（tempfile + rename）
- 159 个测试 + GitHub Actions CI

### v3.2.0 — 沙箱隔离 (2026-05-13)
- ProcessWatchdog：独立线程看门狗 + `taskkill /F /T` 杀进程树
- SandboxManager：Git worktree 沙箱（创建→执行→同步→销毁）
- executor 线程化 I/O + 心跳检测
- `commit_files()` 按文件列表提交
- 171 个测试（新增 18 个 watchdog + sandbox 测试）

### v3.3.0 — 并发上限控制 (2026-05-13)
- `_execute_single_task()`：从主循环提取单任务执行逻辑
- `ThreadPoolExecutor(max_workers)`：线程池控制 goose 并发数
- `parallel_group` 分组：同组内并行，组间串行，`None` = 独立组
- `TaskGraphConfig.max_workers`：可从 tasks.yaml 配置（默认 3）
- `threading.Lock`：保护 state_mgr/git/snapshot 共享状态
- 176 个测试

### v3.4.0 — 单任务验证闭环 (2026-05-13)
- `_get_verification_steps(profile)`：从 profile.commands 提取 compile → test 步骤
- `_run_verification_step(sandbox_path, ...)`：沙箱内 subprocess.run 执行编译/测试命令
- 验证流程：goose 成功 → 产出文件存在 → 编译 → 测试 → 全部通过才 sync
- 验证失败：保留沙箱、即时反馈、走 error_handler 决策（重试/跳过/终止）
- 向后兼容：profile 无 commands 段时跳过验证
- 189 个测试

### v3.5.0 — goose 输出静默 (2026-05-13)
- `executor._build_args(quiet=True)` → 追加 `-q` flag
- `run_stage(quiet=True)` / `run_task(quiet=True)` 默认静默
- `pipeline.py --verbose` 恢复全量输出

### v3.6.0 — 子管线执行器 (2026-05-13)
- `TaskConfig.sub_pipeline`：标记大模块任务走 mini-pipeline
- `_run_sub_pipeline()`：4 阶段 goose session（方案 25% / 编码 40% / 测试 20% / 审查 15% turns）
- 阶段间上下文累积，任一阶段失败立即停止保留沙箱
- 191 个测试

### v3.7.0 — Bug 修复 + JDK 自动检测 (2026-05-13)
- `detect_jdk(required_version)`：扫描系统 JDK 安装，匹配主版本返回 JAVA_HOME
- `_run_verification_step(env=...)`：注入 JAVA_HOME 到验证子进程
- **修复**：产出文件缺失时不再标记 completed → 走 error_handler 决策
- **修复**：`--new` 清理 task_state.json + tasks.yaml + 残留沙箱 worktree
- 197 个测试

---

## ✅ v3.8.0 可控性修复 (2026-05-15)

> 来源：2026-05-14 进销存 WMS 项目实战 — 任务图执行 2 个任务失败 + 编译与测试 Goose 卡死

| # | 改动 | 文件 | 优先级 | 状态 |
|---|------|------|--------|------|
| **D1** | JAVA_HOME pre-flight + PATH 注入加固 | `pipeline/task_graph.py` | P0 | ✅ |
| **D2** | TaskConfig.verification + 按 category 选择验证策略 | `pipeline/config.py` + `task_graph.py` | P0 | ✅ |
| **D3** | 三元任务状态：completed / code_produced / failed_no_output | `pipeline/task_state.py` + `task_graph.py` | P1 | ✅ |
| **D4** | Phase 5 前置守卫：prerequisite 字段 + 启动前检查 | `pipeline.yaml` + `pipeline.py` | P1 | ✅ |
| **D5** | Goose 循环检测：输出内容模式分析 | `pipeline/executor.py` | P2 | ✅ |
| **D6** | 任务错误信息结构化 | `pipeline/task_graph.py` | P2 | ✅ |

### 背景

2026-05-14 进销存 WMS 项目运行全流程时暴露 3 层系统缺陷：

1. **验证策略一刀切** — `_get_verification_steps()` 全局加载 `mvn compile`，前端 Vue 任务也被迫跑 Maven
2. **任务状态二值化** — 代码已成功写入但验证步骤失败，task_state.json 报告 `output_files_produced: []` 和 `failed`
3. **失败传播无阻断** — Phase 4 失败后 Phase 5 仍启动，Goose 同因卡死 4m36s

### 实施顺序

1. **P0 先修**（阻止失败传播）→ D1 + D2
2. **P1 再补**（让失败可诊断）→ D3 + D4
3. **P2 加固**（让异常可捕获）→ D5 + D6

---

---

## 📋 v3.9.0 管线瘦身（待实施 — 2026-05-15 分析结论）

> 来源：v3.8 修复后的深层问题 — Phase 5 AI 阶段不匹配 + CI 模式不可用于真实 CI
> 方案：`docs/plans/v3.9-pipeline-slim.md`

| # | 改动 | 文件 | 优先级 | 状态 |
|---|------|------|--------|------|
| **D7** | Phase 5 脚本化：goose session → 确定性编译+测试 | `pipeline.yaml` + `pipeline/runner.py` + `05-build.yaml` | P0 | [ ] |
| **D8** | CI 退出码：区分环境失败和业务失败，非零退出 | `pipeline/error_handler.py` + `pipeline/runner.py` | P1 | [ ] |
| **D9** | CI 摘要增强：x/y 阶段完成度 + 退出码解释 | `pipeline/runner.py` `_print_summary()` | P2 | [ ] |

### 背景

1. **Phase 5** 当前是 goose session（最多 60 turns），prompt 含"尝试修复编译错误"。实际上编译 30s + 测试 2min，其余时间 AI 在无任务上下文下猜测性改代码。Phase 5 应该是确定性验证，不是 AI 编码。
2. **CI 模式** 对所有失败统一 `SKIP`，pipeline 始终 exit 0。环境问题（JAVA_HOME）和业务问题（代码 bug）被等同对待，无法用于真实 CI/CD。

### 实施顺序

1. **D7 P0** — 去掉 goose，直接 subprocess 跑编译+测试，输出报告
2. **D8 P1** — 失败分类 + `sys.exit(1/2)`
3. **D9 P2** — 摘要加完成度和退出码

---

## 🚧 v4.0 Multica Native 改造

> 目标：从独立编排引擎 → Multica 标准执行层
> 状态：已启动。Multica 尚未完成时，先用本地 Mock 管理层跑通 Native 调用方式。
> 输入文档外部仍有：`D:\MyPrj\test\ai-dev-flow升级改造方案.md` + `D:\MyPrj\test\AI研发体系接入规范.md`

### Foundation：可嵌入执行内核

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| F1 | 稳定运行契约：RunRequest / RunEvent / RunResult | `pipeline/contracts.py` | ✅ |
| F2 | 事件流接口 + JSONL 本地事件 sink | `pipeline/events.py` | ✅ |
| F3 | run-scoped 本地存储 `.ai-dev/runs/<run_id>/` | `pipeline/stores.py` | ✅ |
| F4 | CLI 主流程抽入 `PipelineRunner` | `pipeline/runner.py` + `pipeline.py` | ✅ |
| F5 | 本地 Multica 模拟入口 | `multica_agent.py` | ✅ |

### 第 1 周：安全 + 多模型

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| T1 | 子进程环境变量过滤 | `pipeline/executor.py` | [ ] |
| T2 | output_files 路径穿越检测 | `pipeline/sandbox.py` | [ ] |
| T3 | 多 Provider 模型配置 | `pipeline/model_config.py` (新) | [ ] |

### 第 2 周：Multica 通信层

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| T4 | Multica HTTP 客户端 | `pipeline/multica_client.py` (新) | [ ] |
| T5 | Token 用量追踪 | `pipeline/token_tracker.py` (新) | [ ] |
| T6 | executor Token 集成 | `pipeline/executor.py` | [ ] |

### 第 3 周：任务图升级

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| T7 | 提取 execute_single_task + 回调 | `pipeline/task_graph.py` | [ ] |
| T8 | 交互式 → 策略驱动 | `pipeline/error_handler.py` | [ ] |
| T9 | 对接技能库 API | `pipeline/knowledge_accumulator.py` | [ ] |

### 第 4 周：新入口 + 清理

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| T10 | Multica 守护进程入口 | `multica_agent.py` (新) | [ ] |
| T11 | Standalone / Multica 双模式 | `pipeline.py` | [ ] |
| T12 | 废弃模块清理 | `checkpoint.py` + `state.py` 阶段函数 + `src/` | [ ] |

---

## 📋 计划实现（待排期）

### P2 — 质量体系
- [ ] **多代理审查**：独立 goose session + 对立视角 prompt
- [ ] **5 维质量评分**：正确性/测试/代码质量/安全/性能，替代二进制 pass/fail
- [ ] **规划偏离检测**：执行中检测实际产出与 03-plan.md 的偏差

### P3 — 增强
- [ ] **Web Dashboard**：可选的 Web 界面查看管线状态
