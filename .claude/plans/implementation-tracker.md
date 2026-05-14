# 实现追踪

> 最后更新: 2026-05-13 | 当前版本: v3.2.0

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
- `_execute_single_task()`：从主循环提取单任务执行逻辑（T7 前置）
- `ThreadPoolExecutor(max_workers)`：线程池控制 goose 并发数
- `parallel_group` 分组：同组内并行，组间串行，`None` = 独立组
- `TaskGraphConfig.max_workers`：可从 tasks.yaml 配置（默认 3）
- `threading.Lock`：保护 state_mgr/git/snapshot 共享状态
- 176 个测试（新增 5 个 _execute_single_task 测试 + 1 个 config 测试）

### v3.4.0 — 单任务验证闭环 (2026-05-13)
- `_get_verification_steps(profile)`：从 profile.commands 提取 compile → test 步骤
- `_run_verification_step(sandbox_path, ...)`：沙箱内 subprocess.run 执行编译/测试命令
- 验证流程：goose 成功 → 产出文件存在 → 编译 → 测试 → 全部通过才 sync
- 验证失败：保留沙箱、即时反馈、走 error_handler 决策（重试/跳过/终止）
- 向后兼容：profile 无 commands 段时跳过验证
- 189 个测试（新增 13 个：6 个验证步骤 + 5 个 subprocess 执行 + 2 个集成测试）

### v3.5.0 — goose 输出静默 (2026-05-13)
- `executor._build_args(quiet=True)` → 追加 `-q` flag
- `run_stage(quiet=True)` / `run_task(quiet=True)` 默认静默
- `pipeline.py --verbose` 恢复全量输出
- 全链路穿透：pipeline.py → execute_task_graph → _execute_single_task → run_task

### v3.6.0 — 子管线执行器 (2026-05-13)
- `TaskConfig.sub_pipeline`：标记大模块任务走 mini-pipeline
- `_run_sub_pipeline()`：4 阶段 goose session（方案 25% / 编码 40% / 测试 20% / 审查 15% turns）
- 阶段间上下文累积（前一阶段产出追加到下一阶段 context）
- 任一阶段失败立即停止，保留沙箱供排查
- 191 个测试（新增 2 个 sub_pipeline 测试 + 1 个 config 测试）

### v3.7.0 — Bug 修复 + JDK 自动检测 (2026-05-13)
- `detect_jdk(required_version)`：扫描系统 JDK 安装，匹配主版本返回 JAVA_HOME
- `_run_verification_step(env=...)`：注入 JAVA_HOME 到验证子进程，解决沙箱编译失败
- **修复**：产出文件缺失时不再标记 completed → 走 error_handler 决策（重试/跳过）
- **修复**：`--new` 清理 task_state.json + tasks.yaml + 残留沙箱 worktree
- 197 个测试（新增 5 个 detect_jdk 测试 + 1 个 _parse_javac_version 测试）

---

## ⏸️ 搁置 — v4.0 升级改造

> 目标：从独立编排引擎 → Multica 标准执行层
> 状态：已搁置，优先 P1 执行能力增强
> 输入文档外部仍有：`D:\MyPrj\test\ai-dev-flow升级改造方案.md` + `D:\MyPrj\test\AI研发体系接入规范.md`

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

### P1 — 执行能力增强
- [x] **并发上限控制**（v3.3.0）：线程池限制同时执行的 goose 任务数（max_workers=3），同一 parallel_group 内可并行，超过上限的任务排队等空闲；让拆分粒度可以更细（10-20 turn），靠背压避免单任务触达 goose max actions 上限
- [x] **单任务验证闭环**（v3.4.0）：沙箱内 goose 完成后 → 编译验证 → 测试验证 → 全部通过才 sync 回真实项目。编译/测试命令从 profile.yml commands 取，任一失败保留沙箱供排查，即时反馈不传染后续任务
- [x] **goose 输出静默**（v3.5.0）：executor 默认传 `-q` 给 goose，仅显示模型回复，隐藏文件扫描噪音；加 `--verbose` flag 恢复全量输出
- [x] **子管线执行器**（v3.6.0）：大模块内部走 mini-pipeline（方案→编码→测试→审查），`TaskConfig.sub_pipeline=True` 触发，4 阶段累计上下文，任一阶段失败保留沙箱
- [ ] **`--new` 白名单保留式清理**：当前是列 8 个文件名逐个删，遗漏了 `task_contexts/`（51 文件）、`summaries/`（14 文件）、`logs/`（堆积）、`snapshot.json`、`prompts/` 等。改为遍历 `.ai-dev/` 一级条目，仅保留 `logs/`，其余全部删除。避免白名单遗漏导致跨运行状态污染

### P2 — 质量体系
- [ ] **多代理审查**：独立 goose session + 对立视角 prompt
- [ ] **5 维质量评分**：正确性/测试/代码质量/安全/性能，替代二进制 pass/fail
- [ ] **规划偏离检测**：执行中检测实际产出与 03-plan.md 的偏差

### P3 — 增强
- [ ] **Web Dashboard**：可选的 Web 界面查看管线状态
