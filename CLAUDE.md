# 全流程自动化工程系统 — Agent行为指南

## 你的使命

你加载了全流程自动化工程系统。你的任务是：
**将任何原始工程需求，通过自动化的"需求→计划→代码→验证"闭环，转化为可交付的成果。**

## 核心原则

### 铁律一：状态驱动
严格遵循状态自动机（`src/engines/state-machine.ts`）定义的状态转换。不要跳过状态，不要混合阶段。

### 铁律二：接管优先于修改
面对已有工程，必须先执行**接管协议**（`src/engines/handover-protocol.ts`）——侦察→理解→建议——然后才能修改任何代码。

### 铁律三：读-改-验循环
每个任务遵循：先读取文件 → 再修改代码 → 最后验证结果。

### 铁律四：不可变需求
原始需求一旦解析，不因执行中的困难而修改。如果必须修改，回到计划阶段重新评审。

## 工作流程

### 第0步：模式检测（自动）

```
检测逻辑：
  空目录 → GREENFIELD（从0开始）
  有项目文件 → BROWNFIELD（半路接手）
  需求含"接手/迁移/重构" → BROWNFIELD
```

### 第1步：需求解析

```
动作：
  1. 读取用户输入
  2. 使用 src/engines/requirement-engine.ts 的 parse() 方法
  3. 提取：目标、范围、约束、验收标准、模糊点
  4. 如果存在模糊点 → 调用 AskUserQuestion 澄清
```

**调用skill：** 无（此阶段纯解析）

### 第2步：计划生成（关键步骤）

```
动作：
  1. 结构化需求 → 任务分解
  2. 依赖排序
  3. 风险评估
  4. 插入人类确认点
```

**调用skill：** 
- ✅ `plan-eng-review`（必须 — 架构评审）
- ⚡ `plan-ceo-review`（建议 — 战略评审）
- ⚡ `plan-design-review`（需要时 — 设计评审）

**每个skill调用方式：**
```markdown
1. load_skill("plan-ceo-review")   # 加载skill内容
2. 按skill的SKILL.md指令执行
3. 记录评审结果到 plan.reviews[]
```

### 第3步：计划确认

```
动作：
  1. 向用户展示计划（任务列表、风险、评审结果）
  2. 等待确认
  3. 确认后开始执行
```

**人类确认点（高风险操作前）：**
- 文件删除/重构
- 数据库变更
- API接口变更
- 生产环境配置变更

### 第4步：代码执行

```
动作：
  对每个任务（按依赖顺序）：
    1. 读取相关文件
    2. 使用 analyze 工具分析代码结构
    3. 执行变更（write/edit）
    4. 验证变更（编译/语法/格式化）
    5. 创建检查点（git commit）
```

**每个任务执行模式：**
```typescript
// 文件创建任务
write(path, content) → 验证 → git commit

// 文件修改任务
read(path) → 理解 → edit(path, before, after) → 验证 → git commit

// 多文件任务
read(file1) → read(file2) → analyze(dir) → edit(file1) → edit(file2) → 验证 → git commit
```

**执行中遇到错误：**
```typescript
// 自动调用 investigate skill
load_skill("investigate")
// 按 investigage 的4阶段流程：
// Phase 1: 调查 (收集错误信息)
// Phase 2: 分析 (根因分析)
// Phase 3: 假设 (提出修复)
// Phase 4: 实施 (修复+验证)
```

**检查点提交格式：**
```
WIP: <任务摘要>

[gstack-context]
Decisions: <本次变更的关键决策>
Remaining: <剩余工作>
Tried: <失败的方案> (可选)
[/gstack-context]
```

### 第5步：验证闭环

```
动作：
  对已完成的任务：
    1. 编译检查（tsc/build）
    2. 类型检查（tsc --noEmit）
    3. 代码质量（lint）
    4. 测试运行（test）
    5. 安全审计（高风险变更时）
    6. Diff评审 (review skill)
    7. 回归测试（BROWNFIELD模式）
```

**调用skill：**
- ✅ `review`（必须 — diff评审）
- ⚡ `qa`（建议 — 端到端测试）
- ⚡ `health`（建议 — 代码健康检查）

**验证失败处理：**
- 编译/类型失败 → 修复后重新验证
- 测试失败 → 调用 investigate
- 评审发现问题 → 修复后重新评审
- 连续3次失败 → 回滚到上一个检查点

### 第6步：完成与交付

```
动作：
  1. 生成执行总结
  2. 调用 context-save 保存状态
  3. 调用 ship（如配置）
  4. 输出交付报告
```

**调用skill：**
- ✅ `context-save`（必须 — 保存上下文）
- ⚡ `ship`（可选 — 提交PR）
- ⚡ `document-release`（可选 — 更新文档）
- ⚡ `learn`（可选 — 记录学习）

## 接管协议详细指南

当检测到BROWNFIELD模式时，必须执行以下流程：

### Phase 1：仓库侦察

```markdown
1. 使用 tree 工具分析目录结构（depth 3-5）
2. 读取关键配置文件：
   - package.json / Cargo.toml / go.mod
   - tsconfig.json / .gitignore
   - README.md / ARCHITECTURE.md / DESIGN.md
3. 运行 git 分析：
   - git log --oneline -30
   - git branch --show-current
   - git diff origin/main --stat (如适用)
4. 检测CI/CD配置：
   - .github/workflows/
   - .gitlab-ci.yml
   - ...
```

### Phase 2：心智模型重建

```markdown
1. 使用 analyze 工具提取实体：
   - 类/函数/组件
   - 接口/类型
   - 模块/路由
2. 构建数据流理解
3. 识别设计约束和模式
4. 评估技术债务
```

### Phase 3：介入点推荐

```markdown
1. 评估仓库状态（原型/活跃/稳定/遗留）
2. 推荐最小侵入策略
3. 给出首次行动建议
4. 标注高风险区域
```

## Skill调用速查表

| 我要... | 调用... | 加载方式 |
|---------|---------|---------|
| 评审目标战略 | `plan-ceo-review` | `load_skill("plan-ceo-review")` |
| 评审技术架构 | `plan-eng-review` | `load_skill("plan-eng-review")` |
| 评审UI/UX设计 | `plan-design-review` | `load_skill("plan-design-review")` |
| 调试错误 | `investigate` | `load_skill("investigate")` |
| diff评审 | `review` | `load_skill("review")` |
| QA测试 | `qa` | `load_skill("qa")` |
| 安全审计 | `cso` | `load_skill("cso")` |
| 代码健康 | `health` | `load_skill("health")` |
| 提交推送 | `ship` | `load_skill("ship")` |
| 保存状态 | `context-save` | `load_skill("context-save")` |
| 更新文档 | `document-release` | `load_skill("document-release")` |
| 学习记录 | `learn` | `load_skill("learn")` |

## 自适应行为规则

系统会根据执行历史动态调整行为。以下是你作为agent需要遵循的规则：

### 连续成功时（加速模式）
```
- 5+ 任务连续成功 → 减少人类确认点
- 降低验证严格度（跳过lint/类型检查）
- 增加并行度
```

### 连续失败时（保守模式）
```
- 3+ 任务连续失败 → 增加人类确认点
- 提高到最严格验证
- 回退到"每次一个文件"模式
- 调用 investigate 分析根因
```

### 高风险变更时（必须确认）
```
- 删除文件/目录
- 修改数据库schema
- 修改API接口
- 修改生产配置
- 涉及安全相关代码
```

## 错误处理

### 任务级别错误
```
1. 记录错误信息到 task.result
2. 调用 investigate skill 分析根因
3. 尝试修复（最多3次）
4. 如果修复失败 → 标记任务为 FAILED
5. 检查依赖该任务的其他任务 → 标记为 BLOCKED
```

### 关键路径错误
```
1. 高/关键风险任务失败
2. 有>3个下游任务的核心任务失败
3. → 终止整个流程
4. → 回滚到上一个稳定检查点
5. → 输出错误报告
```

## 上下文管理

系统使用 `context-injector.ts` 来管理上下文。作为agent，你需要注意：

1. **上下文不要超限** — 文件列表和分析结果占token。只在需要时读取。
2. **使用 analyze 工具代替读文件** — analyze 返回结构化信息，比读全文省token。
3. **善用 learn skill** — 每次session学到的项目特定知识存到 learnings 中。
4. **必要时调用 context-save** — 长时间任务中间可以保存状态。

## 检查清单

开始前确认：
- [ ] 你已了解工作目录是否有已有代码
- [ ] 如果是已有工程，你已执行接管协议
- [ ] 需求已解析为结构化格式
- [ ] 计划已生成并通过评审
- [ ] 计划已获确认

执行中确认：
- [ ] 每个任务按依赖顺序执行
- [ ] 每个变更前已读取文件
- [ ] 每个变更后已验证
- [ ] 连续创建检查点

完成前确认：
- [ ] 所有任务已完成
- [ ] 验证闭环全部通过
- [ ] 上下文已保存
- [ ] 学习记录已保存

---

*这个系统本身就是自举的产物。它用自己描述的自动化流程来构建自己。*
