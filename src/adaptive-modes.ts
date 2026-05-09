// ============================================================
// 自适应模式选择器 — 动态调整执行策略
// 
// 核心能力：
// 1. 根据仓库状态自动选择模式
// 2. 根据执行历史动态调整策略
// 3. 根据错误模式切换修复策略
// 4. 保存和恢复上下文
// ============================================================

import {
  Mode,
  Stage,
  ExecutionContext,
  Task,
  TaskStatus,
  RiskLevel,
  RepoState,
} from "./types/index.ts";

export interface AdaptationState {
  mode: Mode;
  currentStage: Stage;
  /** 当前使用的策略集 */
  strategy: StrategyProfile;
  /** 上下文压缩级别 */
  contextLevel: "minimal" | "normal" | "detailed";
  /** 自动确认级别 */
  autoConfirmLevel: "none" | "low_risk" | "all";
  /** 验证严格度 */
  verificationStrictness: "quick" | "standard" | "exhaustive";
  /** 错误恢复策略 */
  errorRecovery: "retry" | "rollback_task" | "rollback_plan" | "abort";
}

export interface StrategyProfile {
  name: string;
  description: string;
  /** 适合的场景 */
  suitableFor: string[];
  /** 主要策略参数 */
  params: Record<string, unknown>;
}

/**
 * 自适应模式选择器
 * 
 * 核心逻辑：
 * - GREENFIELD: 探索优先，全面构建，测试驱动
 * - BROWNFIELD: 安全优先，最小侵入，回归验证
 * 
 * 动态调整规则：
 * - 连续成功 → 降低确认频率
 * - 连续失败 → 增加确认频率+切换保守策略
 * - 新领域 → 增加分析和探索
 * - 熟悉领域 → 加速执行
 */
export class AdaptiveModeSelector {
  private state: AdaptationState;
  private successStreak: number = 0;
  private failureStreak: number = 0;
  private adaptationHistory: AdaptationRecord[] = [];

  constructor() {
    this.state = this.getDefaultState();
  }

  /**
   * 根据仓库侦察报告选择初始模式
   */
  selectInitialMode(repoState?: RepoState): AdaptationState {
    switch (repoState) {
      case RepoState.PROTOTYPE:
        return {
          ...this.getDefaultState(),
          mode: Mode.GREENFIELD,
          strategy: this.getStrategy("rapid_prototype"),
          autoConfirmLevel: "low_risk",
          verificationStrictness: "quick",
        };
      case RepoState.ACTIVE_DEV:
        return {
          ...this.getDefaultState(),
          mode: Mode.BROWNFIELD,
          strategy: this.getStrategy("safe_integration"),
          autoConfirmLevel: "none",
          verificationStrictness: "standard",
        };
      case RepoState.STABLE:
        return {
          ...this.getDefaultState(),
          mode: Mode.BROWNFIELD,
          strategy: this.getStrategy("careful_extension"),
          autoConfirmLevel: "none",
          verificationStrictness: "exhaustive",
        };
      case RepoState.LEGACY:
        return {
          ...this.getDefaultState(),
          mode: Mode.BROWNFIELD,
          strategy: this.getStrategy("legacy_migration"),
          autoConfirmLevel: "none",
          verificationStrictness: "exhaustive",
        };
      default:
        return this.getDefaultState();
    }
  }

  /**
   * 根据执行反馈动态调整策略
   */
  adapt(result: TaskAdaptationFeedback): AdaptationState {
    const prevState = { ...this.state };

    // 更新连续成功/失败计数
    if (result.success) {
      this.successStreak++;
      this.failureStreak = 0;
    } else {
      this.failureStreak++;
      this.successStreak = 0;
    }

    // 动态调整策略
    if (this.failureStreak >= 3) {
      // 连续失败 → 切换保守模式
      this.state.strategy = this.getStrategy("conservative_recovery");
      this.state.autoConfirmLevel = "none";
      this.state.verificationStrictness = "exhaustive";
      this.state.errorRecovery = "rollback_task";
    } else if (this.successStreak >= 5) {
      // 连续成功 → 加速
      if (this.state.autoConfirmLevel === "none") {
        this.state.autoConfirmLevel = "low_risk";
      }
      this.state.errorRecovery = "retry";
    }

    // 根据错误类型调整
    if (result.errorType === "compilation" && this.failureStreak > 1) {
      this.state.verificationStrictness = "exhaustive";
      this.state.contextLevel = "detailed";
    }

    // 记录适应历史
    this.adaptationHistory.push({
      timestamp: new Date().toISOString(),
      from: prevState.strategy.name,
      to: this.state.strategy.name,
      reason: result.feedback || "自动适应",
      taskId: result.taskId,
    });

    return this.state;
  }

  /**
   * 获取当前适应状态
   */
  getState(): AdaptationState {
    return this.state;
  }

  /**
   * 获取适应历史
   */
  getAdaptationHistory(): AdaptationRecord[] {
    return this.adaptationHistory;
  }

  /**
   * 为任务选择合适的执行策略
   */
  getTaskExecutionPlan(task: Task): TaskExecutionPlan {
    const plan: TaskExecutionPlan = {
      taskId: task.id,
      summary: task.summary,
    };

    // 根据风险等级和当前模式设置验证级别
    switch (this.state.verificationStrictness) {
      case "exhaustive":
        plan.verifyBeforeCommit = true;
        plan.runFullTestSuite = true;
        plan.checkTypes = true;
        plan.checkLint = true;
        plan.checkSecurity = task.riskLevel === RiskLevel.HIGH || task.riskLevel === RiskLevel.CRITICAL;
        plan.diffReview = true;
        break;
      case "standard":
        plan.verifyBeforeCommit = true;
        plan.runFullTestSuite = false;
        plan.checkTypes = true;
        plan.checkLint = true;
        plan.checkSecurity = false;
        plan.diffReview = true;
        break;
      case "quick":
        plan.verifyBeforeCommit = task.riskLevel === RiskLevel.HIGH || task.riskLevel === RiskLevel.CRITICAL;
        plan.runFullTestSuite = false;
        plan.checkTypes = false;
        plan.checkLint = false;
        plan.checkSecurity = false;
        plan.diffReview = false;
        break;
    }

    // 根据自适应状态设置
    if (this.failureStreak > 0) {
      plan.verifyBeforeCommit = true;
      plan.runFullTestSuite = true;
    }

    return plan;
  }

  /**
   * 是否需要人类确认
   */
  needsHumanConfirmation(task: Task): boolean {
    switch (this.state.autoConfirmLevel) {
      case "all":
        return false;
      case "low_risk":
        return task.riskLevel === RiskLevel.HIGH || task.riskLevel === RiskLevel.CRITICAL;
      case "none":
        return true;
    }
  }

  // ---- Private ----

  private getDefaultState(): AdaptationState {
    return {
      mode: Mode.GREENFIELD,
      currentStage: Stage.UNKNOWN,
      strategy: this.getStrategy("default"),
      contextLevel: "normal",
      autoConfirmLevel: "low_risk",
      verificationStrictness: "standard",
      errorRecovery: "retry",
    };
  }

  private getStrategy(name: string): StrategyProfile {
    const strategies: Record<string, StrategyProfile> = {
      default: {
        name: "默认策略",
        description: "平衡的开发策略，适用于大多数场景",
        suitableFor: ["greenfield", "simple changes"],
        params: { preRead: true, postVerify: true, autoCommit: true },
      },
      rapid_prototype: {
        name: "快速原型",
        description: "最小化验证，快速产出可工作的原型",
        suitableFor: ["greenfield", "prototype", "hackathon"],
        params: { preRead: false, postVerify: false, autoCommit: true },
      },
      safe_integration: {
        name: "安全集成",
        description: "为活跃开发的项目添加功能，注重回归安全",
        suitableFor: ["active_dev", "feature_addition"],
        params: { preRead: true, postVerify: true, autoCommit: true, runRegression: true },
      },
      careful_extension: {
        name: "谨慎扩展",
        description: "为稳定项目添加功能，每个步骤都需要验证",
        suitableFor: ["stable_project", "production"],
        params: { preRead: true, postVerify: true, autoCommit: true, runRegression: true, requireReview: true },
      },
      legacy_migration: {
        name: "遗留系统迁移",
        description: "处理遗留代码，先写测试安全网再改代码",
        suitableFor: ["legacy", "debt_reduction"],
        params: { preRead: true, postVerify: true, autoCommit: true, writeTestsFirst: true, smallBatches: true },
      },
      conservative_recovery: {
        name: "保守恢复",
        description: "连续失败后的保守模式，每个操作都需要确认",
        suitableFor: ["error_recovery", "debugging"],
        params: { preRead: true, postVerify: true, autoCommit: false, requireReview: true, maxFilesPerTask: 1 },
      },
    };

    return strategies[name] || strategies.default;
  }
}

// ==================== 辅助类型 ====================

export interface TaskAdaptationFeedback {
  taskId: string;
  success: boolean;
  errorType?: "compilation" | "test" | "runtime" | "lint" | "unknown";
  feedback?: string;
  durationMs?: number;
}

export interface TaskExecutionPlan {
  taskId: string;
  summary: string;
  verifyBeforeCommit?: boolean;
  runFullTestSuite?: boolean;
  checkTypes?: boolean;
  checkLint?: boolean;
  checkSecurity?: boolean;
  diffReview?: boolean;
}

export interface AdaptationRecord {
  timestamp: string;
  from: string;
  to: string;
  reason: string;
  taskId?: string;
}
