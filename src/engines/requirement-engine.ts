// ============================================================
// 需求解析引擎 — 将原始输入转为结构化需求
// ============================================================

import {
  RawRequirement,
  StructuredRequirement,
  Ambiguity,
  ExecutionContext,
} from "../types/index.ts";

export interface RequirementEngineOptions {
  /** 是否自动追问模糊点 */
  autoClarify: boolean;
  /** 上下文（已有代码库、历史等） */
  context?: ExecutionContext;
}

export class RequirementEngine {
  private options: RequirementEngineOptions;

  constructor(options?: Partial<RequirementEngineOptions>) {
    this.options = {
      autoClarify: true,
      ...options,
    };
  }

  /**
   * 解析原始需求
   * 
   * agent工作流：
   * 1. 如果是"从0开始" → 从需求描述中提取目标/范围/约束
   * 2. 如果是"半路接手" → 先执行接管协议，再解析需求
   * 
   * 实际执行时，这个引擎会：
   * - 调用LLM进行结构化提取
   * - 或调用 plan-ceo-review skill 进行评审
   */
  async parse(raw: RawRequirement): Promise<StructuredRequirement> {
    const summary = this.extractSummary(raw.text);
    const goals = this.extractGoals(raw.text);
    const scope = this.extractScope(raw.text);
    const constraints = this.extractConstraints(raw.text);
    const criteria = this.extractAcceptanceCriteria(raw.text);
    const ambiguities = this.detectAmbiguities(raw.text);

    return {
      id: this.generateId(),
      summary,
      description: raw.text,
      goals,
      scope,
      constraints,
      acceptanceCriteria: criteria,
      priority: this.determinePriority(raw.text),
      ambiguities,
      rawRef: raw.source === "file" && raw.sourcePath ? raw.sourcePath : raw.text.slice(0, 100),
      createdAt: new Date().toISOString(),
    };
  }

  /** 批量解析多个需求 */
  async parseBatch(raws: RawRequirement[]): Promise<StructuredRequirement[]> {
    const results: StructuredRequirement[] = [];
    for (const raw of raws) {
      results.push(await this.parse(raw));
    }
    return results;
  }

  /**
   * 追问模糊点
   * 返回需要向人类确认的问题列表
   */
  getClarificationQuestions(ambiguities: Ambiguity[]): string[] {
    return ambiguities
      .filter((a) => !a.resolved)
      .map((a) => `[${a.field}] ${a.description}\n  建议确认: ${a.suggestedClarification}`);
  }

  // ---- Private helpers (这些在生产中会被LLM调用替代) ----

  private extractSummary(text: string): string {
    // 从文本中提取一句话总结
    const lines = text.split("\n").filter((l) => l.trim().length > 0);
    if (lines.length <= 3) return lines[0]?.trim() ?? text;
    // 取第一段有意义的内容
    return lines.slice(0, 3).join(" ").slice(0, 200);
  }

  private extractGoals(text: string): string[] {
    const goals: string[] = [];
    // 匹配 "目标"、"目的"、"Goal" 等关键词后的内容
    const goalPatterns = [
      /目标[：:]\s*(.+)/,
      /目的[：:]\s*(.+)/,
      /Goal[s]?[：:]\s*(.+)/i,
      /实现\s*(.+)/,
    ];
    for (const pattern of goalPatterns) {
      const match = text.match(pattern);
      if (match) goals.push(match[1].trim());
    }
    if (goals.length === 0) {
      // fallback: 用第一句话作为目标
      const firstLine = text.split("\n")[0]?.trim();
      if (firstLine) goals.push(firstLine);
    }
    return goals;
  }

  private extractScope(text: string): { inScope: string[]; outOfScope: string[] } {
    const inScope: string[] = [];
    const outOfScope: string[] = [];

    const inMatch = text.match(/范围[：:]\s*(.+?)(?=\n\n|$)/s);
    if (inMatch) {
      inScope.push(...inMatch[1].split(/[,，、]/).map((s) => s.trim()).filter(Boolean));
    }

    const outMatch = text.match(/不[在包含考虑][范围]*[：:]\s*(.+?)(?=\n\n|$)/s);
    if (outMatch) {
      outOfScope.push(...outMatch[1].split(/[,，、]/).map((s) => s.trim()).filter(Boolean));
    }

    return { inScope, outOfScope };
  }

  private extractConstraints(text: string): string[] {
    const constraints: string[] = [];
    const constraintPatterns = [
      /约束[：:]\s*(.+)/,
      /限制[：:]\s*(.+)/,
      /Constraint[s]?[：:]\s*(.+)/i,
      /必须\s*(.+?)[。，,.]/,
    ];
    for (const pattern of constraintPatterns) {
      const matches = text.matchAll(new RegExp(pattern, "g"));
      for (const match of matches) {
        constraints.push(match[1].trim());
      }
    }
    return constraints;
  }

  private extractAcceptanceCriteria(text: string): string[] {
    const criteria: string[] = [];
    const patterns = [
      /验收标准[：:]\s*(.+?)(?=\n\n|$)/s,
      /Acceptance Criteria[：:]\s*(.+?)(?=\n\n|$)/is,
      /done when[：:]\s*(.+?)(?=\n\n|$)/is,
    ];
    for (const pattern of patterns) {
      const match = text.match(pattern);
      if (match) {
        criteria.push(
          ...match[1].split("\n").map((l) => l.replace(/^[-*\d.]+\s*/, "").trim()).filter(Boolean)
        );
      }
    }
    return criteria;
  }

  private detectAmbiguities(text: string): Ambiguity[] {
    const ambiguities: Ambiguity[] = [];

    // 检测常见的模糊模式
    if (/尽快|尽快完成/.test(text)) {
      ambiguities.push({
        field: "timeline",
        description: '使用了"尽快"——需要明确的截止时间',
        suggestedClarification: "请指明具体的时间线或里程碑日期",
        resolved: false,
      });
    }

    if (/优化|改进|提升/.test(text) && !/\d+%/.test(text) && !/到\s*\d+/.test(text)) {
      ambiguities.push({
        field: "metrics",
        description: '使用了"优化/改进"但没有量化指标',
        suggestedClarification: "请定义具体的可量化目标（如：性能提升50%）",
        resolved: false,
      });
    }

    if (/用户|people/.test(text) && !/\d+[万kK]?/.test(text)) {
      ambiguities.push({
        field: "scale",
        description: "提到用户但没有说明规模",
        suggestedClarification: "请说明目标用户量级和并发要求",
        resolved: false,
      });
    }

    if (/简单|容易|方便/.test(text)) {
      ambiguities.push({
        field: "usability",
        description: '使用了"简单/容易"——这是主观描述',
        suggestedClarification: "请定义具体的可用性标准（如：3步内完成操作）",
        resolved: false,
      });
    }

    return ambiguities;
  }

  private determinePriority(text: string): "P0" | "P1" | "P2" {
    if (/P0|critical|紧急|必须|blocker/i.test(text)) return "P0";
    if (/P1|important|重要/i.test(text)) return "P1";
    return "P2";
  }

  private generateId(): string {
    return `REQ-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
  }
}
