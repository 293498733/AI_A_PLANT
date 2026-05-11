// ============================================================
// 全流程自动化工程系统 — 核心类型定义
// ============================================================

// -------------------- 状态自动机 --------------------

/** 系统阶段 */
export enum Stage {
  UNKNOWN = "UNKNOWN",
  PARSED = "PARSED",
  PLANNED = "PLANNED",
  EXECUTING = "EXECUTING",
  VERIFYING = "VERIFYING",
  DONE = "DONE",
  FAILED = "FAILED",
  ROLLBACK = "ROLLBACK",
}

/** 模式 */
export enum Mode {
  GREENFIELD = "GREENFIELD",   // 从0开始
  BROWNFIELD = "BROWNFIELD",   // 半路接手
}

/** 风险等级 */
export enum RiskLevel {
  LOW = "LOW",
  MEDIUM = "MEDIUM",
  HIGH = "HIGH",
  CRITICAL = "CRITICAL",
}

/** 变更类型 */
export enum ChangeType {
  CREATE = "CREATE",
  MODIFY = "MODIFY",
  DELETE = "DELETE",
  REFACTOR = "REFACTOR",
  MIGRATE = "MIGRATE",
}

// -------------------- 需求层 --------------------

/** 原始需求输入 */
export interface RawRequirement {
  /** 自然语言描述 / PRD / Issue文本 */
  text: string;
  /** 需求来源 */
  source: "user_prompt" | "prd" | "issue" | "handover" | "file";
  /** 来源路径（如果是文件） */
  sourcePath?: string;
  /** 附加上下文 */
  context?: Record<string, unknown>;
}

/** 结构化需求 */
export interface StructuredRequirement {
  /** 唯一标识 */
  id: string;
  /** 一句话描述 */
  summary: string;
  /** 详细描述 */
  description: string;
  /** 目标 */
  goals: string[];
  /** 范围 */
  scope: { inScope: string[]; outOfScope: string[] };
  /** 约束 */
  constraints: string[];
  /** 验收标准 */
  acceptanceCriteria: string[];
  /** 优先级: P0=必须 P1=重要 P2=nice-to-have */
  priority: "P0" | "P1" | "P2";
  /** 检测到的模糊点 */
  ambiguities: Ambiguity[];
  /** 原始需求引用 */
  rawRef: string;
  /** 创建时间 */
  createdAt: string;
}

/** 模糊点 */
export interface Ambiguity {
  field: string;
  description: string;
  suggestedClarification: string;
  resolved: boolean;
}

// -------------------- 计划层 --------------------

/** 可执行任务 */
export interface Task {
  id: string;
  summary: string;
  description: string;
  /** 涉及文件 */
  files: string[];
  /** 依赖（前置任务ID） */
  dependencies: string[];
  /** 变更类型 */
  changeType: ChangeType;
  /** 风险等级 */
  riskLevel: RiskLevel;
  /** 预估工作量 S/M/L/XL */
  effort: "S" | "M" | "L" | "XL";
  /** 状态 */
  status: TaskStatus;
  /** 执行结果 */
  result?: TaskResult;
  /** 子任务 */
  subTasks: Task[];
}

export enum TaskStatus {
  PENDING = "PENDING",
  BLOCKED = "BLOCKED",
  READY = "READY",
  EXECUTING = "EXECUTING",
  VERIFYING = "VERIFYING",
  DONE = "DONE",
  FAILED = "FAILED",
  SKIPPED = "SKIPPED",
}

export interface TaskResult {
  success: boolean;
  stdout?: string;
  stderr?: string;
  error?: string;
  /** 创建/修改的文件列表 */
  changedFiles: string[];
  /** 验证结果 */
  verification?: VerificationResult;
}

/** 执行计划 */
export interface ExecutionPlan {
  id: string;
  requirementId: string;
  summary: string;
  tasks: Task[];
  /** 整体风险评估 */
  riskAssessment: RiskAssessment;
  /** 人类确认点 */
  checkpoints: Checkpoint[];
  /** 评审记录 */
  reviews: ReviewRecord[];
  createdAt: string;
}

export interface RiskAssessment {
  level: RiskLevel;
  factors: string[];
  mitigation: string[];
}

export interface Checkpoint {
  id: string;
  description: string;
  /** 在哪些任务之后触发 */
  afterTasks: string[];
  status: "pending" | "approved" | "rejected";
  humanResponse?: string;
}

export interface ReviewRecord {
  type: "ceo" | "engineering" | "design" | "security" | "dx";
  skill: string;
  result: "pass" | "fail" | "concern";
  findings: string[];
  timestamp: string;
}

// -------------------- 执行层 --------------------

/** 执行上下文 */
export interface ExecutionContext {
  mode: Mode;
  workDir: string;
  /** 仓库根路径 */
  repoRoot: string;
  /** 已有的文件索引 */
  fileIndex?: FileEntry[];
  /** 当前分支 */
  branch?: string;
  /** 已保存的学习记录 */
  learnings?: string[];
  /** 最近执行记录 */
  recentActions?: string[];
}

export interface FileEntry {
  path: string;
  language: string;
  sizeBytes: number;
  lastModified: string;
}

/** 执行命令 */
export interface ExecutionCommand {
  type: "read" | "write" | "edit" | "shell" | "analyze" | "review" | "delegate";
  params: Record<string, unknown>;
  description: string;
}

// -------------------- 验证层 --------------------

export interface VerificationResult {
  passed: boolean;
  checks: Check[];
  summary: string;
  artifacts?: string[];
}

export interface Check {
  name: string;
  type: "compile" | "test" | "lint" | "typecheck" | "security" | "diff_review" | "qa" | "custom";
  passed: boolean;
  detail: string;
  durationMs: number;
}

// -------------------- 接管协议 --------------------

/** 仓库侦察报告 */
export interface ReconReport {
  repoRoot: string;
  languages: string[];
  buildSystem: string | null;
  testFramework: string | null;
  hasCI: boolean;
  fileCount: number;
  dirStructure: DirNode[];
  recentActivity: string;
  activeBranch: string;
  dependencies: Record<string, string>;
  documentation: string[];
  state: RepoState;
}

export interface DirNode {
  name: string;
  type: "file" | "dir";
  children?: DirNode[];
  size?: number;
}

export enum RepoState {
  PROTOTYPE = "PROTOTYPE",
  ACTIVE_DEV = "ACTIVE_DEV",
  STABLE = "STABLE",
  LEGACY = "LEGACY",
  ABANDONED = "ABANDONED",
}

/** 心智模型 */
export interface MentalModel {
  domainEntities: EntityDef[];
  dataFlows: DataFlow[];
  designConstraints: string[];
  techDebt: string[];
}

export interface EntityDef {
  name: string;
  type: "class" | "function" | "component" | "route" | "module";
  file: string;
  responsibilities: string[];
  dependencies: string[];
}

export interface DataFlow {
  from: string;
  to: string;
  data: string;
}

/** 接管推荐 */
export interface HandoverRecommendation {
  mode: Mode;
  entryPoints: string[];
  riskLevel: RiskLevel;
  suggestedFirstAction: string;
  reasoning: string;
}
