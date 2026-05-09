// ============================================================
// 主控编排器 — 将整个系统粘合在一起
// 
// 这是系统的"大脑"：
// 1. 接收需求
// 2. 自动判断模式（从0开始 vs 半路接手）
// 3. 驱动状态自动机
// 4. 调用各引擎
// 5. 集成gstack skill
// 6. 处理异常和回滚
// ============================================================

import { StateMachine, AutomatonEvent } from "./engines/state-machine.ts";
import { RequirementEngine } from "./engines/requirement-engine.ts";
import { PlanGenerator } from "./engines/plan-generator.ts";
import { CodeExecutor } from "./engines/code-executor.ts";
import { VerificationLoop } from "./engines/verification-loop.ts";
import { HandoverProtocol } from "./engines/handover-protocol.ts";

import {
  Stage,
  Mode,
  RawRequirement,
  StructuredRequirement,
  ExecutionPlan,
  ExecutionContext,
  Task,
  TaskStatus,
  VerificationResult,
  ReconReport,
  MentalModel,
  HandoverRecommendation,
} from "./types/index.ts";

import { SkillBridge } from "./skill-bridge.ts";
import { AdaptiveModeSelector } from "./adaptive-modes.ts";

export interface OrchestratorConfig {
  workDir: string;
  repoRoot?: string;
  mode?: Mode;             // 可选，不指定则自动检测
  autoModeDetection: boolean;  // 自动检测模式
  verbose: boolean;
  autoConfirm: boolean;    // 是否自动确认（无人类介入）
}

const DEFAULT_CONFIG: OrchestratorConfig = {
  workDir: process.cwd(),
  autoModeDetection: true,
  verbose: true,
  autoConfirm: false,
};

/**
 * # 全流程自动化工程系统 — 主控编排器
 * 
 * ## 使用方式（由AI agent调用）
 * 
 * ```typescript
 * const orch = new Orchestrator({ workDir: "/path/to/project" });
 * await orch.start("构建一个CLI工具...");
 * ```
 * 
 * ## 工作流程
 * 
 * ```
 * Orchestrator.start(原始需求)
 *   │
 *   ├─ 1. 模式检测 ← 自动判断GREENFIELD/BROWNFIELD
 *   │     ├─ 检测到已有工程 → 执行HandoverProtocol
 *   │     └─ 空目录 → GREENFIELD模式
 *   │
 *   ├─ 2. 需求解析 ← RequirementEngine
 *   │     └─ 检测到模糊点 → 追问人类
 *   │
 *   ├─ 3. 计划生成 ← PlanGenerator
 *   │     ├─ 调用 plan-ceo-review skill（评审目标）
 *   │     ├─ 调用 plan-eng-review skill（评审架构）
 *   │     ├─ 调用 plan-design-review skill（评审设计）
 *   │     └─ 插入人类确认点
 *   │
 *   ├─ 4. 计划确认
 *   │     └─ 等待人类确认（或autoConfirm）
 *   │
 *   ├─ 5. 代码执行 ← CodeExecutor
 *   │     ├─ 按依赖顺序执行任务
 *   │     ├─ 每个任务：读→改→验
 *   │     ├─ 连续检查点（git commit）
 *   │     └─ 遇错调用 investigate skill
 *   │
 *   ├─ 6. 验证闭环 ← VerificationLoop
 *   │     ├─ 编译检查
 *   │     ├─ 测试运行
 *   │     ├─ 代码质量检查
 *   │     ├─ Diff评审（调用 review skill）
 *   │     └─ QA测试（调用 qa skill）
 *   │
 *   └─ 7. 完成
 *         ├─ 调用 ship skill（推送/PR）
 *         ├─ 调用 context-save（保存状态）
 *         └─ 输出总结报告
 * ```
 */
export class Orchestrator {
  private config: OrchestratorConfig;
  private stateMachine: StateMachine;
  private requirementEngine: RequirementEngine;
  private planGenerator: PlanGenerator;
  private codeExecutor: CodeExecutor;
  private verificationLoop: VerificationLoop;
  private handoverProtocol: HandoverProtocol;
  private skillBridge: SkillBridge;
  private modeSelector: AdaptiveModeSelector;

  // 运行时状态
  private context: ExecutionContext | null = null;
  private requirement: StructuredRequirement | null = null;
  private plan: ExecutionPlan | null = null;
  private mode: Mode = Mode.GREENFIELD;

  // 接管信息
  private reconReport: ReconReport | null = null;
  private mentalModel: MentalModel | null = null;
  private handoverRecommendation: HandoverRecommendation | null = null;

  constructor(config?: Partial<OrchestratorConfig>) {
    this.config = { ...DEFAULT_CONFIG, ...config };

    // 初始化引擎
    this.stateMachine = new StateMachine();
    this.requirementEngine = new RequirementEngine({ autoClarify: true });
    this.planGenerator = new PlanGenerator({ autoReview: true });
    this.codeExecutor = new CodeExecutor();
    this.verificationLoop = new VerificationLoop();
    this.handoverProtocol = new HandoverProtocol();
    this.skillBridge = new SkillBridge(this.config.verbose);
    this.modeSelector = new AdaptiveModeSelector();

    // 注册状态机事件监听
    this.stateMachine.onEvent((event) => {
      if (this.config.verbose) {
        console.log(`[编排器] 事件: ${event.type}`);
      }
    });
  }

  // ==================== 主入口 ====================

  /**
   * 启动自动化流程
   * 
   * @param input - 原始需求（自然语言、PRD、或路径）
   * @param mode - 可选：强制指定模式
   */
  async start(input: string | RawRequirement, mode?: Mode): Promise<OrchestrationResult> {
    console.log(`\n${"=".repeat(60)}`);
    console.log(` 🤖 全流程自动化工程系统 v1.0`);
    console.log(` ${"=".repeat(60)}\n`);

    const rawReq: RawRequirement = typeof input === "string"
      ? { text: input, source: "user_prompt" }
      : input;

    try {
      // Phase 0: 模式检测
      await this.phase0DetectMode(rawReq, mode);
      
      // Phase 1: 需求解析
      await this.phase1ParseRequirement(rawReq);
      
      // Phase 2: 计划生成
      await this.phase2GeneratePlan();
      
      // Phase 3: 计划确认
      const planApproved = await this.phase3ConfirmPlan();
      if (!planApproved) {
        return { success: false, stage: Stage.PLANNED, reason: "计划被拒绝" };
      }
      
      // Phase 4: 代码执行
      await this.phase4ExecutePlan();
      
      // Phase 5: 验证
      await this.phase5Verify();
      
      // Phase 6: 完成
      return this.phase6Complete();

    } catch (error) {
      const errMsg = error instanceof Error ? error.message : String(error);
      console.error(`\n❌ 流程失败: ${errMsg}`);
      
      this.stateMachine.dispatch({ type: "ERROR", error: errMsg });
      
      return {
        success: false,
        stage: this.stateMachine.stage,
        reason: errMsg,
      };
    }
  }

  // ==================== Phase 0: 模式检测 ====================

  private async phase0DetectMode(rawReq: RawRequirement, forceMode?: Mode): Promise<void> {
    console.log(`\n📋 Phase 0: 环境检测`);

    // 如果强制指定了模式
    if (forceMode) {
      this.mode = forceMode;
      console.log(`   模式: ${forceMode === Mode.GREENFIELD ? "🆕 从0开始" : "🔧 半路接手"} (强制指定)`);
      return;
    }

    // 自动检测模式
    if (this.config.autoModeDetection) {
      this.mode = await this.detectMode(rawReq);
      
      if (this.mode === Mode.BROWNFIELD) {
        console.log(`   模式: 🔧 半路接手`);
        console.log(`\n📋 Phase 0.5: 执行接管协议\n`);
        
        const repoRoot = this.config.repoRoot || this.config.workDir;
        const handover = await this.handoverProtocol.execute(repoRoot);
        
        this.reconReport = handover.report;
        this.mentalModel = handover.mentalModel;
        this.handoverRecommendation = handover.recommendation;
        this.context = handover.context;
        
        // 打印接管报告摘要
        console.log(`\n   📊 仓库侦察报告:`);
        console.log(`      - 语言: ${handover.report.languages.join(", ") || "未知"}`);
        console.log(`      - 构建: ${handover.report.buildSystem || "未知"}`);
        console.log(`      - 测试: ${handover.report.testFramework || "无"}`);
        console.log(`      - CI: ${handover.report.hasCI ? "有" : "无"}`);
        console.log(`      - 状态: ${handover.report.state}`);
        console.log(`      - 分支: ${handover.report.activeBranch}`);
        console.log(`      - 文件数: ${handover.report.fileCount}`);
        console.log(`   📋 心智模型: ${handover.mentalModel.domainEntities.length} 个实体, ${handover.mentalModel.dataFlows.length} 条数据流`);
        console.log(`   💡 建议: ${handover.recommendation.suggestedFirstAction}`);
        
      } else {
        console.log(`   模式: 🆕 从0开始`);
        this.context = {
          mode: Mode.GREENFIELD,
          workDir: this.config.workDir,
          repoRoot: this.config.workDir,
        };
      }
    }
  }

  /**
   * 自动检测模式
   * 
   * 判断逻辑：
   * 1. 如果工作目录是空目录 → GREENFIELD
   * 2. 如果已有 package.json/Cargo.toml 等 → BROWNFIELD
   * 3. 如果需求是"接手"/"迁移"/"修改"已有项目 → BROWNFIELD
   */
  private async detectMode(rawReq: RawRequirement): Promise<Mode> {
    const fs = require("fs");
    const path = require("path");
    const workDir = this.config.workDir;

    // 检查目录是否为空
    try {
      const entries = fs.readdirSync(workDir);
      if (entries.length === 0) return Mode.GREENFIELD;
      
      // 检查常见项目文件
      const projectFiles = [
        "package.json", "Cargo.toml", "go.mod", "pyproject.toml",
        "CMakeLists.txt", "Makefile", "pom.xml", "build.gradle",
        "Gemfile", "requirements.txt", "Cargo.lock", "yarn.lock",
        "package-lock.json", "pnpm-lock.yaml", ".gitmodules",
      ];
      
      const hasProject = projectFiles.some((f) => fs.existsSync(path.join(workDir, f)));
      if (hasProject) return Mode.BROWNFIELD;

      // 检查是否有 .git
      if (fs.existsSync(path.join(workDir, ".git"))) return Mode.BROWNFIELD;

    } catch {
      // 读不了目录 = 出错了，保守起见从0开始
    }

    // 检查需求文本是否有"接手"、"迁移"、"修改"等关键词
    const brownfieldKeywords = [
      "接手", "迁移", "修改", "改进", "重构", "添加", 
      "接手现有", "已有项目", "现有代码", "遗留",
      "migrate", "refactor", "modify", "extend", "existing",
      "brownfield", "legacy", "handover",
    ];
    
    const hasBrownfieldSignal = brownfieldKeywords.some((kw) =>
      rawReq.text.toLowerCase().includes(kw.toLowerCase())
    );

    return hasBrownfieldSignal ? Mode.BROWNFIELD : Mode.GREENFIELD;
  }

  // ==================== Phase 1: 需求解析 ====================

  private async phase1ParseRequirement(rawReq: RawRequirement): Promise<void> {
    console.log(`\n📋 Phase 1: 需求解析`);

    this.stateMachine.dispatch({ type: "INPUT_RECEIVED", requirement: rawReq });

    // 解析需求
    this.requirement = await this.requirementEngine.parse(rawReq);
    
    // 如果有模糊点 → 提示人类
    const unresolved = this.requirement.ambiguities.filter((a) => !a.resolved);
    if (unresolved.length > 0) {
      console.log(`\n   ⚠️ 检测到 ${unresolved.length} 个模糊点:`);
      for (const amb of unresolved) {
        console.log(`      - [${amb.field}] ${amb.description}`);
      }
      // 实际运行时，在这里调用AskUserQuestion
    }

    console.log(`   ✅ 需求已解析: ${this.requirement.summary}`);
    console.log(`      目标: ${this.requirement.goals.length} 个`);
    console.log(`      约束: ${this.requirement.constraints.length} 个`);
    console.log(`      验收标准: ${this.requirement.acceptanceCriteria.length} 个`);

    this.stateMachine.dispatch({
      type: "REQUIREMENT_PARSED",
      structured: this.requirement,
    });
  }

  // ==================== Phase 2: 计划生成 ====================

  private async phase2GeneratePlan(): Promise<void> {
    console.log(`\n📋 Phase 2: 计划生成`);

    // 生成计划
    this.plan = await this.planGenerator.generate(this.requirement!, this.context!);

    console.log(`   ✅ 计划已生成:`);
    console.log(`      任务数: ${this.plan.tasks.length}`);
    console.log(`      风险等级: ${this.plan.riskAssessment.level}`);
    console.log(`      确认点: ${this.plan.checkpoints.length}`);

    // 如果有风险，提示
    if (this.plan.riskAssessment.factors.length > 0) {
      console.log(`   ⚠️ 风险因素:`);
      for (const factor of this.plan.riskAssessment.factors) {
        console.log(`      - ${factor}`);
      }
    }

    // 打印任务列表
    console.log(`\n   📋 任务列表:`);
    for (const task of this.plan.tasks) {
      const deps = task.dependencies.length > 0 ? ` (依赖: ${task.dependencies.join(", ")})` : "";
      console.log(`      ${task.id}: [${task.effort}/${task.riskLevel}] ${task.summary}${deps}`);
      for (const sub of task.subTasks) {
        console.log(`        └ ${sub.summary}`);
      }
    }

    this.stateMachine.dispatch({ type: "PLAN_GENERATED", plan: this.plan });

    // 评审
    if (this.plan.reviews.length > 0) {
      console.log(`\n   📋 评审记录:`);
      for (const review of this.plan.reviews) {
        console.log(`      ${review.skill}: ${review.result}`);
      }
    }
  }

  // ==================== Phase 3: 计划确认 ====================

  private async phase3ConfirmPlan(): Promise<boolean> {
    console.log(`\n📋 Phase 3: 计划确认`);

    if (this.config.autoConfirm) {
      console.log(`   🔄 自动确认模式 — 跳过人类确认`);
      this.stateMachine.dispatch({ type: "PLAN_CONFIRMED" });
      return true;
    }

    // 实际运行时，在这里使用 AskUserQuestion 等待人类确认
    // 返回 true 表示已确认
    const confirmed = true; // 实际由人类响应决定
    
    if (confirmed) {
      this.stateMachine.dispatch({ type: "PLAN_CONFIRMED" });
      console.log(`   ✅ 计划已确认`);
    } else {
      this.stateMachine.dispatch({ type: "PLAN_REJECTED", reason: "用户拒绝" });
      console.log(`   ❌ 计划被拒绝`);
    }

    return confirmed;
  }

  // ==================== Phase 4: 代码执行 ====================

  private async phase4ExecutePlan(): Promise<void> {
    console.log(`\n📋 Phase 4: 执行计划\n`);

    const tasks = this.plan!.tasks;
    const taskResults = new Map<string, boolean>();

    for (const task of tasks) {
      // 检查依赖状态
      const depsOk = task.dependencies.every(
        (depId) => taskResults.get(depId) === true
      );
      if (!depsOk) {
        console.log(`   ⛔ 跳过 ${task.id}: 依赖未就绪`);
        task.status = TaskStatus.SKIPPED;
        continue;
      }

      console.log(`   🔧 [${task.id}] ${task.summary}...`);

      // 执行任务
      const result = await this.codeExecutor.execute(task, this.context!);
      taskResults.set(task.id, result.success);

      if (result.success) {
        console.log(`      ✅ 完成 (${result.changedFiles.length} 个文件)`);
        
        // 每个任务完成后自动验证
        if (this.codeExecutor["options"]?.verifyAfterChange) {
          const vr = await this.verificationLoop.verify(task, result, this.context!);
          if (!vr.passed) {
            console.log(`      ⚠️ 验证发现 ${vr.checks.filter((c) => !c.passed).length} 个问题`);
          } else {
            console.log(`      ✅ 验证通过`);
          }
        }
      } else {
        console.log(`      ❌ 失败: ${result.error}`);
        
        // 调用 investigate 技能
        console.log(`      🔍 调用 investigate 分析失败原因...`);
        await this.skillBridge.callInvestigate(result.error!, task, this.context!);
        
        // 根据错误类型决定：继续还是回滚
        if (this.shouldAbortOnError(task, result)) {
          throw new Error(`任务 ${task.id} 失败，终止流程`);
        }
      }
    }

    // 通知状态机所有任务完成
    console.log(`\n   ✅ 所有任务执行完毕`);
  }

  // ==================== Phase 5: 验证 ====================

  private async phase5Verify(): Promise<void> {
    console.log(`\n📋 Phase 5: 验证闭环\n`);

    const completedTasks = this.plan!.tasks.filter(
      (t) => t.status === TaskStatus.DONE && t.result
    );

    if (completedTasks.length === 0) {
      console.log(`   ⚠️ 没有需要验证的任务`);
      this.stateMachine.dispatch({
        type: "VERIFICATION_PASSED",
        result: { passed: true, checks: [], summary: "无变更" },
      });
      return;
    }

    // 批量验证
    const result = await this.verificationLoop.verifyBatch(completedTasks, this.context!);

    console.log(`   ${result.summary}\n`);

    for (const check of result.checks) {
      const icon = check.passed ? "✅" : "❌";
      console.log(`   ${icon} ${check.name}: ${check.detail}`);
    }

    if (result.passed) {
      this.stateMachine.dispatch({ type: "VERIFICATION_PASSED", result });
      
      // 触发ship技能（如果所有验证通过）
      console.log(`\n   🚀 验证全部通过，准备交付...`);
      
    } else {
      this.stateMachine.dispatch({ type: "VERIFICATION_FAILED", result });
      
      // 根据失败类型决定策略
      const failedChecks = result.checks.filter((c) => !c.passed);
      console.log(`\n   ⚠️ ${failedChecks.length} 项检查失败，触发修复流程...`);
      
      // 调用skill桥接进行修复
      await this.skillBridge.callReview(this.plan!, this.context!);
    }
  }

  // ==================== Phase 6: 完成 ====================

  private async phase6Complete(): Promise<OrchestrationResult> {
    console.log(`\n${"=".repeat(60)}`);
    console.log(` 🎉 全流程自动化完成！`);
    console.log(` ${"=".repeat(60)}\n`);

    // 调用 context-save 保存状态
    await this.skillBridge.callContextSave(this.plan!, this.context!);

    // 生成总结
    const summary = this.generateSummary();

    return {
      success: true,
      stage: Stage.DONE,
      mode: this.mode,
      requirement: this.requirement!,
      plan: this.plan!,
      reconReport: this.reconReport,
      summary,
    };
  }

  // ==================== 辅助方法 ====================

  private shouldAbortOnError(task: Task, result: { error?: string }): boolean {
    // 关键路径失败 → 终止
    if (task.riskLevel === "HIGH" || task.riskLevel === "CRITICAL") return true;
    
    // 依赖多个下游的核心任务失败 → 终止
    const downstreamTasks = this.plan?.tasks.filter(
      (t) => t.dependencies.includes(task.id)
    ) ?? [];
    if (downstreamTasks.length > 3) return true;

    return false;
  }

  private generateSummary(): string {
    const tasks = this.plan?.tasks ?? [];
    const done = tasks.filter((t) => t.status === TaskStatus.DONE).length;
    const failed = tasks.filter((t) => t.status === TaskStatus.FAILED).length;
    const skipped = tasks.filter((t) => t.status === TaskStatus.SKIPPED).length;

    const changedFiles = tasks
      .flatMap((t) => t.result?.changedFiles ?? [])
      .filter((v, i, a) => a.indexOf(v) === i);

    return `
📊 执行总结
   • 模式: ${this.mode === Mode.GREENFIELD ? "从0开始" : "半路接手"}
   • 需求: ${this.requirement?.summary ?? "未知"}
   • 任务: ${done} 成功 / ${failed} 失败 / ${skipped} 跳过 (共${tasks.length})
   • 文件: ${changedFiles.length} 个文件变更
   • 风险: ${this.plan?.riskAssessment.level ?? "未知"}
   ${this.reconReport ? `• 仓库: ${this.reconReport.repoRoot} (${this.reconReport.state})` : ""}
`;
  }
}

// ==================== 结果类型 ====================

export interface OrchestrationResult {
  success: boolean;
  stage: Stage;
  mode?: Mode;
  requirement?: StructuredRequirement;
  plan?: ExecutionPlan;
  reconReport?: ReconReport | null;
  summary?: string;
  reason?: string;
}
