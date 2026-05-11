// ============================================================
// Skill桥接层 — 连接系统与gstack已有技能
//
// 这是最关键的集成层，它定义了：
// 1. 自动机各阶段应该调用哪些skill
// 2. 每个skill的调用时机和参数
// 3. 如何从skill输出中提取决策信息
// ============================================================

import {
  Stage,
  ExecutionPlan,
  ExecutionContext,
  Task,
  ReviewRecord,
  Mode,
} from "./types/index.ts";

/**
 * Skill桥接层
 * 
 * 设计哲学：
 * - 不直接实现skill的功能（那是各skill自己的事）
 * - 只负责"路由"——在正确的时间调用正确的skill
 * - 提供统一的接口抽象
 * 
 * skill调用方式：
 * 实际运行时，使用 load_skill() 加载skill内容
 * 然后按skill的SKILL.md指令执行
 */
export class SkillBridge {
  private verbose: boolean;

  constructor(verbose = true) {
    this.verbose = verbose;
  }

  // ==================== 阶段路由表 ====================

  /**
   * 自动机各阶段 → skill路由
   * 
   * 每个阶段会调用对应的skill来辅助决策
   */
  getSkillRoute(stage: Stage, mode: Mode): SkillCall[] {
    switch (stage) {
      case Stage.PLANNED:
        return this.getPlanSkills(mode);
      case Stage.EXECUTING:
        return [this.getInvestigateSkill()];
      case Stage.VERIFYING:
        return this.getVerifySkills(mode);
      case Stage.DONE:
        return this.getCompleteSkills(mode);
      default:
        return [];
    }
  }

  /** 计划阶段调用的skill */
  private getPlanSkills(mode: Mode): SkillCall[] {
    const skills: SkillCall[] = [
      {
        skill: "plan-ceo-review",
        purpose: "评审目标是否足够大，是否有更好的方向",
        phase: "plan",
        required: mode === Mode.GREENFIELD,
        autoInvoke: true,
      },
      {
        skill: "plan-eng-review",
        purpose: "评审架构合理性、技术方案、风险",
        phase: "plan",
        required: true,
        autoInvoke: true,
      },
    ];

    // 半路接手时加安全审计
    if (mode === Mode.BROWNFIELD) {
      skills.push({
        skill: "cso",
        purpose: "安全审计——检查现有代码的安全风险",
        phase: "plan",
        required: false,
        autoInvoke: false,
      });
    }

    return skills;
  }

  /** 验证阶段调用的skill */
  private getVerifySkills(mode: Mode): SkillCall[] {
    const skills: SkillCall[] = [
      {
        skill: "review",
        purpose: "diff评审——检查变更的质量",
        phase: "verify",
        required: true,
        autoInvoke: true,
      },
    ];

    if (mode === Mode.GREENFIELD) {
      skills.push({
        skill: "qa",
        purpose: "端到端QA测试",
        phase: "verify",
        required: false,
        autoInvoke: false,
      });
    }

    return skills;
  }

  /** 完成阶段调用的skill */
  private getCompleteSkills(mode: Mode): SkillCall[] {
    return [
      {
        skill: "ship",
        purpose: "提交PR、推送代码",
        phase: "complete",
        required: false,
        autoInvoke: false,
      },
      {
        skill: "context-save",
        purpose: "保存工作状态和上下文",
        phase: "complete",
        required: true,
        autoInvoke: true,
      },
    ];
  }

  // ==================== Skill调用接口 ====================

  /**
   * 调用 plan-ceo-review skill
   * 由agent执行：load_skill("plan-ceo-review") 然后按指令操作
   */
  async callCEOReview(plan: ExecutionPlan, ctx: ExecutionContext | null): Promise<ReviewRecord> {
    if (this.verbose) console.log(`   [Skill] 调用 plan-ceo-review ...`);
    
    // 实际由agent执行：
    // 1. load_skill("plan-ceo-review")
    // 2. 按skill指令完成评审
    // 3. 输出ReviewRecord

    return {
      type: "ceo",
      skill: "plan-ceo-review",
      result: "pass",
      findings: ["目标清晰，方向合理"],
      timestamp: new Date().toISOString(),
    };
  }

  /**
   * 调用 plan-eng-review skill
   */
  async callEngReview(plan: ExecutionPlan, ctx: ExecutionContext | null): Promise<ReviewRecord> {
    if (this.verbose) console.log(`   [Skill] 调用 plan-eng-review ...`);
    
    return {
      type: "engineering",
      skill: "plan-eng-review",
      result: "pass",
      findings: ["架构合理，覆盖了主要场景"],
      timestamp: new Date().toISOString(),
    };
  }

  /**
   * 调用 plan-design-review skill
   */
  async callDesignReview(plan: ExecutionPlan, ctx: ExecutionContext | null): Promise<ReviewRecord> {
    if (this.verbose) console.log(`   [Skill] 调用 plan-design-review ...`);
    
    return {
      type: "design",
      skill: "plan-design-review",
      result: "pass",
      findings: [],
      timestamp: new Date().toISOString(),
    };
  }

  /**
   * 调用 investigate skill — 调试错误
   * 由agent执行：load_skill("investigate") 然后按4阶段流程操作
   */
  async callInvestigate(error: string, task: Task, ctx: ExecutionContext | null): Promise<string> {
    if (this.verbose) console.log(`   [Skill] 调用 investigate ...`);
    
    // 实际由agent执行：
    // 1. load_skill("investigate")
    // 2. Phase 1: 调查 - 收集错误信息
    // 3. Phase 2: 分析 - 根因分析
    // 4. Phase 3: 假设 - 提出修复方案
    // 5. Phase 4: 实施 - 修复代码
    
    return `investigate完成: 分析错误 "${error.slice(0, 50)}..."`;
  }

  /**
   * 调用 review skill — diff评审
   */
  async callReview(plan: ExecutionPlan, ctx: ExecutionContext | null): Promise<void> {
    if (this.verbose) console.log(`   [Skill] 调用 review (diff评审) ...`);
    // 实际由agent执行
  }

  /**
   * 调用 qa skill — 端到端测试
   */
  async callQA(ctx: ExecutionContext | null): Promise<void> {
    if (this.verbose) console.log(`   [Skill] 调用 qa ...`);
    // 实际由agent执行
  }

  /**
   * 调用 ship skill — 提交PR
   */
  async callShip(plan: ExecutionPlan, ctx: ExecutionContext | null): Promise<void> {
    if (this.verbose) console.log(`   [Skill] 调用 ship ...`);
    // 实际由agent执行
  }

  /**
   * 调用 context-save — 保存上下文
   */
  async callContextSave(plan: ExecutionPlan, ctx: ExecutionContext | null): Promise<void> {
    if (this.verbose) console.log(`   [Skill] 调用 context-save ...`);
    // 实际由agent执行
  }

  /**
   * 调用 health — 代码健康检查
   */
  async callHealthCheck(ctx: ExecutionContext | null): Promise<void> {
    if (this.verbose) console.log(`   [Skill] 调用 health ...`);
    // 实际由agent执行
  }
}

// ==================== Skill调用定义 ====================

export interface SkillCall {
  skill: string;
  purpose: string;
  phase: "plan" | "execute" | "verify" | "complete";
  required: boolean;
  autoInvoke: boolean;
}

/**
 * 完整的Skill路由表
 * 
 * 这是整个系统可用的所有skill及其调用规则
 */
export const SKILL_ROUTING_TABLE: SkillCall[] = [
  // === 计划阶段 ===
  { skill: "plan-ceo-review", purpose: "战略评审", phase: "plan", required: false, autoInvoke: true },
  { skill: "plan-eng-review", purpose: "技术架构评审", phase: "plan", required: true, autoInvoke: true },
  { skill: "plan-design-review", purpose: "设计评审", phase: "plan", required: false, autoInvoke: false },
  { skill: "cso", purpose: "安全审计", phase: "plan", required: false, autoInvoke: false },
  { skill: "plan-devex-review", purpose: "开发者体验评审", phase: "plan", required: false, autoInvoke: false },

  // === 执行阶段 ===
  { skill: "investigate", purpose: "调试错误", phase: "execute", required: false, autoInvoke: true },

  // === 验证阶段 ===
  { skill: "review", purpose: "diff评审", phase: "verify", required: true, autoInvoke: true },
  { skill: "qa", purpose: "端到端QA测试", phase: "verify", required: false, autoInvoke: false },
  { skill: "qa-only", purpose: "仅报告QA结果", phase: "verify", required: false, autoInvoke: false },
  { skill: "health", purpose: "代码健康检查", phase: "verify", required: false, autoInvoke: false },
  { skill: "design-review", purpose: "视觉设计审查", phase: "verify", required: false, autoInvoke: false },

  // === 完成阶段 ===
  { skill: "ship", purpose: "提交PR/部署", phase: "complete", required: false, autoInvoke: false },
  { skill: "context-save", purpose: "保存上下文", phase: "complete", required: true, autoInvoke: true },
  { skill: "document-release", purpose: "更新文档", phase: "complete", required: false, autoInvoke: false },
  { skill: "learn", purpose: "记录学习", phase: "complete", required: false, autoInvoke: true },
];
