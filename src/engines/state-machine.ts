// ============================================================
// 状态自动机 — 核心调度引擎
// ============================================================

import {
  Stage,
  Mode,
  RawRequirement,
  StructuredRequirement,
  ExecutionPlan,
  ExecutionContext,
  VerificationResult,
  Task,
  TaskStatus,
} from "../types/index.ts";

/** 状态转换表 */
const TRANSITIONS: Record<Stage, Partial<Record<Stage, TransitionCondition>>> = {
  [Stage.UNKNOWN]: {
    [Stage.PARSED]: { condition: (ctx) => ctx.rawRequirement !== null, action: "parseRequirement" },
    [Stage.FAILED]: { condition: (ctx) => ctx.error !== undefined, action: "reportError" },
  },
  [Stage.PARSED]: {
    [Stage.PLANNED]: { condition: (ctx) => ctx.structured !== null, action: "generatePlan" },
    [Stage.UNKNOWN]: { condition: (ctx) => true, action: "reset" },
    [Stage.FAILED]: { condition: (ctx) => ctx.error !== undefined, action: "reportError" },
  },
  [Stage.PLANNED]: {
    [Stage.EXECUTING]: { condition: (ctx) => ctx.plan !== null && ctx.planConfirmed, action: "executePlan" },
    [Stage.PARSED]: { condition: (ctx) => true, action: "reparse" },
    [Stage.FAILED]: { condition: (ctx) => ctx.error !== undefined, action: "reportError" },
  },
  [Stage.EXECUTING]: {
    [Stage.VERIFYING]: { condition: (ctx) => ctx.allTasksComplete(), action: "verifyResults" },
    [Stage.ROLLBACK]: { condition: (ctx) => ctx.shouldRollback(), action: "rollback" },
    [Stage.FAILED]: { condition: (ctx) => ctx.error !== undefined, action: "reportError" },
  },
  [Stage.VERIFYING]: {
    [Stage.DONE]: { condition: (ctx) => ctx.verification?.passed === true, action: "complete" },
    [Stage.EXECUTING]: { condition: (ctx) => ctx.verification?.passed === false, action: "reExecute" },
    [Stage.PLANNED]: { condition: (ctx) => ctx.needsReplan(), action: "replan" },
    [Stage.FAILED]: { condition: (ctx) => ctx.error !== undefined, action: "reportError" },
  },
  [Stage.DONE]: {
    // 终极状态，没有出边（除非reset）
  },
  [Stage.FAILED]: {
    [Stage.UNKNOWN]: { condition: (ctx) => true, action: "reset" },
  },
  [Stage.ROLLBACK]: {
    [Stage.PLANNED]: { condition: (ctx) => true, action: "replanAfterRollback" },
    [Stage.FAILED]: { condition: (ctx) => !ctx.canRecover(), action: "reportError" },
  },
};

interface TransitionCondition {
  condition: (ctx: AutomatonContext) => boolean;
  action: string;
}

/** 自动机内部上下文 */
export interface AutomatonContext {
  rawRequirement: RawRequirement | null;
  structured: StructuredRequirement | null;
  plan: ExecutionPlan | null;
  planConfirmed: boolean;
  context: ExecutionContext | null;
  verification: VerificationResult | null;
  error: string | undefined;
  history: StageTransition[];

  // 以下为方法（由外部注入）
  allTasksComplete: () => boolean;
  shouldRollback: () => boolean;
  canRecover: () => boolean;
  needsReplan: () => boolean;
}

export interface StageTransition {
  from: Stage;
  to: Stage;
  action: string;
  timestamp: string;
  durationMs?: number;
}

// ==================== 事件系统 ====================

export type AutomatonEvent =
  | { type: "INPUT_RECEIVED"; requirement: RawRequirement }
  | { type: "REQUIREMENT_PARSED"; structured: StructuredRequirement }
  | { type: "PLAN_GENERATED"; plan: ExecutionPlan }
  | { type: "PLAN_CONFIRMED" }
  | { type: "PLAN_REJECTED"; reason: string }
  | { type: "TASK_COMPLETED"; task: Task }
  | { type: "TASK_FAILED"; task: Task; error: string }
  | { type: "VERIFICATION_PASSED"; result: VerificationResult }
  | { type: "VERIFICATION_FAILED"; result: VerificationResult }
  | { type: "ERROR"; error: string }
  | { type: "RESET" }
  | { type: "ROLLBACK" };

// ==================== 自动机类 ====================

export class StateMachine {
  private currentStage: Stage = Stage.UNKNOWN;
  private ctx: AutomatonContext;
  private listeners: Array<(event: AutomatonEvent) => void> = [];

  constructor(initialCtx?: Partial<AutomatonContext>) {
    this.ctx = {
      rawRequirement: null,
      structured: null,
      plan: null,
      planConfirmed: false,
      context: null,
      verification: null,
      error: undefined,
      history: [],
      allTasksComplete: () => this.checkAllTasksDone(),
      shouldRollback: () => false,
      canRecover: () => false,
      needsReplan: () => false,
      ...initialCtx,
    };
  }

  get stage(): Stage {
    return this.currentStage;
  }

  get context(): AutomatonContext {
    return this.ctx;
  }

  /** 注册事件监听 */
  onEvent(handler: (event: AutomatonEvent) => void): void {
    this.listeners.push(handler);
  }

  /** 派发事件 → 自动转换 */
  dispatch(event: AutomatonEvent): Stage {
    const prev = this.currentStage;
    this.notifyListeners(event);

    // 处理事件（更新上下文 + 触发转换）
    this.applyEvent(event);

    // 尝试转换
    const next = this.tryTransition();
    if (next !== prev) {
      const transition: StageTransition = {
        from: prev,
        to: next,
        action: TRANSITIONS[prev]?.[next]?.action ?? "unknown",
        timestamp: new Date().toISOString(),
      };
      this.ctx.history.push(transition);
      this.currentStage = next;
      console.log(
        `[自动机] ${transition.from} → ${transition.to} (${transition.action})`
      );
    }
    return this.currentStage;
  }

  /** 查询可达的下一个阶段 */
  getAvailableTransitions(): { to: Stage; action: string }[] {
    const transitions = TRANSITIONS[this.currentStage] ?? {};
    return Object.entries(transitions)
      .filter(([_, t]) => t.condition(this.ctx))
      .map(([to, t]) => ({ to: to as Stage, action: t.action }));
  }

  /** 重置 */
  reset(): void {
    this.currentStage = Stage.UNKNOWN;
    this.ctx.history = [];
    this.ctx.error = undefined;
    this.notifyListeners({ type: "RESET" });
  }

  // ---- Private ----

  private applyEvent(event: AutomatonEvent): void {
    switch (event.type) {
      case "INPUT_RECEIVED":
        this.ctx.rawRequirement = event.requirement;
        break;
      case "REQUIREMENT_PARSED":
        this.ctx.structured = event.structured;
        break;
      case "PLAN_GENERATED":
        this.ctx.plan = event.plan;
        break;
      case "PLAN_CONFIRMED":
        this.ctx.planConfirmed = true;
        break;
      case "PLAN_REJECTED":
        this.ctx.planConfirmed = false;
        break;
      case "ERROR":
        this.ctx.error = event.error;
        break;
      case "RESET":
        this.ctx.rawRequirement = null;
        this.ctx.structured = null;
        this.ctx.plan = null;
        this.ctx.planConfirmed = false;
        this.ctx.verification = null;
        this.ctx.error = undefined;
        break;
      default:
        break;
    }
  }

  private tryTransition(): Stage {
    const transitions = TRANSITIONS[this.currentStage] ?? {};
    for (const [nextStage, transition] of Object.entries(transitions)) {
      if (transition.condition(this.ctx)) {
        return nextStage as Stage;
      }
    }
    return this.currentStage;
  }

  private checkAllTasksDone(): boolean {
    if (!this.ctx.plan) return false;
    return this.ctx.plan.tasks.every(
      (t) => t.status === TaskStatus.DONE || t.status === TaskStatus.SKIPPED
    );
  }

  private notifyListeners(event: AutomatonEvent): void {
    for (const handler of this.listeners) {
      try {
        handler(event);
      } catch {
        // 忽略监听器错误
      }
    }
  }
}
