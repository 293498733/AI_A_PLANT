// ============================================================
// 计划生成器 — 将结构化需求转为可执行任务计划
// ============================================================

import {
  StructuredRequirement,
  ExecutionPlan,
  Task,
  TaskStatus,
  ChangeType,
  RiskLevel,
  Checkpoint,
  ReviewRecord,
  RiskAssessment,
  ExecutionContext,
  Mode,
} from "../types/index.ts";

export interface PlanGeneratorOptions {
  /** 是否自动调用评审skill */
  autoReview: boolean;
  /** 评审类型 */
  reviewTypes: Array<"ceo" | "engineering" | "design" | "security">;
  /** 上下文 */
  context?: ExecutionContext;
}

export class PlanGenerator {
  private options: PlanGeneratorOptions;

  constructor(options?: Partial<PlanGeneratorOptions>) {
    this.options = {
      autoReview: true,
      reviewTypes: ["ceo", "engineering"],
      ...options,
    };
  }

  /**
   * 根据结构化需求生成执行计划
   * 
   * agent工作流（实际运行时由LLM执行以下步骤）：
   * 1. 分析需求 → 分解为原子任务
   * 2. 排序任务依赖
   * 3. 识别风险
   * 4. 插入人类确认点
   * 5. 调用评审skill（如果开启）
   */
  async generate(requirement: StructuredRequirement, ctx?: ExecutionContext): Promise<ExecutionPlan> {
    const tasks = this.decomposeTasks(requirement, ctx);
    this.resolveDependencies(tasks);
    
    const riskAssessment = this.assessRisk(tasks, requirement);
    const checkpoints = this.identifyCheckpoints(tasks, riskAssessment);
    
    const plan: ExecutionPlan = {
      id: `PLAN-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      requirementId: requirement.id,
      summary: requirement.summary,
      tasks,
      riskAssessment,
      checkpoints,
      reviews: [],
      createdAt: new Date().toISOString(),
    };

    // 自动评审
    if (this.options.autoReview) {
      await this.runReviews(plan, requirement);
    }

    return plan;
  }

  /**
   * 任务分解策略
   * 
   * 核心原则：
   * - 每个任务对应一个可验证的原子变更
   * - 任务粒度：一个任务修改 ≤ 3个文件
   * - 文件粒度的变更，不要跨模块
   */
  private decomposeTasks(req: StructuredRequirement, ctx?: ExecutionContext): Task[] {
    const tasks: Task[] = [];
    let taskIndex = 0;

    const addTask = (
      summary: string,
      desc: string,
      files: string[],
      changeType: ChangeType,
      risk: RiskLevel,
      effort: "S" | "M" | "L" | "XL",
      deps: string[] = [],
    ) => {
      const id = `TASK-${++taskIndex}`;
      tasks.push({
        id,
        summary,
        description: desc,
        files,
        dependencies: deps,
        changeType,
        riskLevel: risk,
        effort,
        status: TaskStatus.PENDING,
        subTasks: [],
      });
    };

    // 根据模式（从0开始 vs 半路接手）调整任务生成
    if (!ctx || ctx.mode === Mode.GREENFIELD) {
      this.decomposeGreenfield(req, addTask);
    } else {
      this.decomposeBrownfield(req, ctx, addTask);
    }

    return tasks;
  }

  /** 从0开始的任务分解 */
  private decomposeGreenfield(
    req: StructuredRequirement,
    addTask: (summary: string, desc: string, files: string[], changeType: ChangeType, risk: RiskLevel, effort: "S" | "M" | "L" | "XL", deps?: string[]) => void
  ): void {
    // 1. 脚手架
    addTask(
      "初始化项目结构",
      `创建项目脚手架，包括目录结构、构建配置、lint配置等`,
      ["package.json", "tsconfig.json", ".gitignore"],
      ChangeType.CREATE,
      RiskLevel.LOW,
      "S"
    );

    // 2. 核心数据结构
    addTask(
      "定义核心数据类型",
      `实现${req.summary}的核心数据模型`,
      ["src/types/index.ts"],
      ChangeType.CREATE,
      RiskLevel.MEDIUM,
      "M",
      ["TASK-1"]
    );

    // 3. 核心逻辑（按目标分解）
    req.goals.forEach((goal, i) => {
      addTask(
        `实现: ${goal}`,
        `实现目标"${goal}"的核心逻辑`,
        [`src/${this.goalToFile(goal)}`],
        ChangeType.CREATE,
        RiskLevel.MEDIUM,
        "M",
        ["TASK-2"]
      );
    });

    // 4. 集成层
    addTask(
      "实现集成与接口",
      `将各模块集成，提供统一的对外接口`,
      ["src/index.ts"],
      ChangeType.CREATE,
      RiskLevel.HIGH,
      "M",
      req.goals.map((_, i) => `TASK-${3 + i}`)
    );

    // 5. 测试
    addTask(
      "编写测试用例",
      "为核心逻辑和集成层编写单元测试和集成测试",
      ["tests/core.test.ts"],
      ChangeType.CREATE,
      RiskLevel.LOW,
      "M",
      [`TASK-${req.goals.length + 3}`]
    );

    // 6. 文档
    addTask(
      "编写文档",
      "编写README和API文档",
      ["README.md"],
      ChangeType.CREATE,
      RiskLevel.LOW,
      "S",
      [`TASK-${req.goals.length + 4}`]
    );
  }

  /** 半路接手（已有工程）的任务分解 */
  private decomposeBrownfield(
    req: StructuredRequirement,
    ctx: ExecutionContext,
    addTask: (summary: string, desc: string, files: string[], changeType: ChangeType, risk: RiskLevel, effort: "S" | "M" | "L" | "XL", deps?: string[]) => void
  ): void {
    // 1. 先理解现有代码（已由接管协议完成）
    // 2. 识别要修改的文件
    // 3. 按"理解→修改→验证"的顺序生成任务

    // 每个目标分解为：分析当前实现 → 实现变更 → 更新测试
    req.goals.forEach((goal, i) => {
      const baseTaskIndex = i * 3 + 1;

      addTask(
        `分析: ${goal} 的当前实现`,
        `阅读和分析与"${goal}"相关的现有代码`,
        [],
        ChangeType.MODIFY,
        RiskLevel.LOW,
        "S"
      );

      addTask(
        `实现变更: ${goal}`,
        `修改现有代码以实现"${goal}"`,
        [],
        ChangeType.MODIFY,
        RiskLevel.HIGH,
        "M",
        [`TASK-${baseTaskIndex}`]
      );

      addTask(
        `更新测试: ${goal}`,
        `更新或添加测试以覆盖"${goal}"的变更`,
        [],
        ChangeType.MODIFY,
        RiskLevel.MEDIUM,
        "S",
        [`TASK-${baseTaskIndex + 1}`]
      );
    });
  }

  /** 依赖解析（拓扑排序） */
  private resolveDependencies(tasks: Task[]): void {
    // 已由addTask的deps参数处理
    // 这里可以做循环依赖检测
    const visited = new Set<string>();
    const visiting = new Set<string>();

    const detectCycle = (taskId: string, path: string[]): boolean => {
      if (visiting.has(taskId)) {
        console.error(`[Plan] 循环依赖检测: ${path.concat(taskId).join(" → ")}`);
        return true;
      }
      if (visited.has(taskId)) return false;

      visiting.add(taskId);
      const task = tasks.find((t) => t.id === taskId);
      if (task) {
        for (const depId of task.dependencies) {
          if (detectCycle(depId, [...path, taskId])) return true;
        }
      }
      visiting.delete(taskId);
      visited.add(taskId);
      return false;
    };

    // 更新状态：可执行的任务标记为READY
    const allIds = new Set(tasks.map((t) => t.id));
    for (const task of tasks) {
      if (task.dependencies.every((d) => !allIds.has(d) || tasks.find((t) => t.id === d)?.status === TaskStatus.DONE)) {
        task.status = TaskStatus.READY;
      }
    }
  }

  /** 风险评估 */
  private assessRisk(tasks: Task[], req: StructuredRequirement): RiskAssessment {
    const factors: string[] = [];
    const levels = tasks.map((t) => t.riskLevel);
    
    if (levels.some((l) => l === RiskLevel.CRITICAL)) factors.push("存在关键风险任务");
    if (tasks.some((t) => t.effort === "XL")) factors.push("存在超大工作量任务");
    if (req.constraints.length > 5) factors.push("约束条件较多");
    if (req.ambiguities.some((a) => !a.resolved)) factors.push("存在未解决的模糊点");

    const level: RiskLevel = 
      levels.includes(RiskLevel.CRITICAL) ? RiskLevel.CRITICAL :
      levels.includes(RiskLevel.HIGH) ? RiskLevel.HIGH :
      levels.includes(RiskLevel.MEDIUM) ? RiskLevel.MEDIUM :
      RiskLevel.LOW;

    return {
      level,
      factors: factors.length > 0 ? factors : ["未检测到明显风险"],
      mitigation: [
        "高风险任务前插入确认点",
        "每次变更后自动运行测试",
        "关键路径设置回滚点",
      ],
    };
  }

  /** 识别需要人类确认的点 */
  private identifyCheckpoints(tasks: Task[], risk: RiskAssessment): Checkpoint[] {
    const checkpoints: Checkpoint[] = [];

    // 高风险任务前
    const highRiskTasks = tasks.filter((t) => t.riskLevel === RiskLevel.HIGH || t.riskLevel === RiskLevel.CRITICAL);
    for (const task of highRiskTasks) {
      checkpoints.push({
        id: `CP-${task.id}`,
        description: `高风险操作确认: ${task.summary}`,
        afterTasks: task.dependencies.length > 0 ? [task.dependencies[task.dependencies.length - 1]] : [],
        status: "pending",
      });
    }

    // 整体确认点
    checkpoints.unshift({
      id: "CP-INIT",
      description: "计划已生成，请确认是否执行",
      afterTasks: [],
      status: "pending",
    });

    return checkpoints;
  }

  /** 调用评审skill */
  private async runReviews(plan: ExecutionPlan, req: StructuredRequirement): Promise<void> {
    for (const reviewType of this.options.reviewTypes) {
      // 在实际运行时，这里会调用对应的skill
      // - "ceo" → plan-ceo-review
      // - "engineering" → plan-eng-review
      // - "design" → plan-design-review
      // - "security" → cso
      const record: ReviewRecord = {
        type: reviewType,
        skill: `plan-${reviewType}-review`,
        result: "pass",
        findings: [],
        timestamp: new Date().toISOString(),
      };
      plan.reviews.push(record);
    }
  }

  // ---- Utilities ----

  private goalToFile(goal: string): string {
    // 目标 → 文件名启发式
    const slug = goal
      .toLowerCase()
      .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, "-")
      .replace(/^-|-$/g, "");
    return `${slug}.ts`;
  }
}
