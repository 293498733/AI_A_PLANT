// ============================================================
// 上下文感知层 — 构建和维护系统对工作环境的理解
//
// 功能：
// 1. 构建工作目录的上下文快照
// 2. 维护"学习记录"（从learn skill获取）
// 3. 提供压缩/解压上下文的能力
// 4. 检测上下文变化并更新
// ============================================================

import {
  ExecutionContext,
  FileEntry,
  Mode,
} from "./types/index.ts";

export interface ContextSnapshot {
  timestamp: string;
  workDir: string;
  mode: Mode;
  files: FileEntry[];
  branches?: string[];
  recentChanges: string[];
  dependencies: Record<string, string>;
  configFiles: Record<string, string>;
  projectMetrics: ProjectMetrics;
}

export interface ProjectMetrics {
  totalFiles: number;
  totalLines: number;
  languageBreakdown: Record<string, number>;
  testFiles: number;
  documentationFiles: number;
}

/**
 * 上下文感知层
 * 
 * 这层的关键价值：
 * 1. 保持上下文精简——只保留相关部分
 * 2. 自动检测上下文变化
 * 3. 跨会话持久化
 * 
 * 实际运行时由agent的文件读取和分析工具驱动
 */
export class ContextInjector {
  private snapshots: ContextSnapshot[] = [];
  private maxSnapshots: number = 10;

  constructor(maxSnapshots?: number) {
    if (maxSnapshots) this.maxSnapshots = maxSnapshots;
  }

  /**
   * 构建当前上下文的快照
   * 
   * 这是系统理解当前工作环境的基础。
   * 实际执行时由agent调用 tree / analyze 等工具。
   */
  async buildSnapshot(ctx: ExecutionContext): Promise<ContextSnapshot> {
    const fs = require("fs");
    const path = require("path");

    const files = await this.scanFiles(ctx.workDir);
    const recentChanges = await this.getRecentChanges(ctx.workDir);
    const dependencies = await this.getDependencies(ctx.workDir);
    const configFiles = await this.getConfigFiles(ctx.workDir);
    const metrics = await this.calculateMetrics(ctx.workDir);

    const snapshot: ContextSnapshot = {
      timestamp: new Date().toISOString(),
      workDir: ctx.workDir,
      mode: ctx.mode,
      files,
      recentChanges,
      dependencies,
      configFiles,
      projectMetrics: metrics,
    };

    this.snapshots.push(snapshot);
    if (this.snapshots.length > this.maxSnapshots) {
      this.snapshots.shift();
    }

    return snapshot;
  }

  /**
   * 对比两个快照，找出变化
   */
  diffSnapshots(before: ContextSnapshot, after: ContextSnapshot): ContextDiff {
    const added: string[] = [];
    const removed: string[] = [];
    const modified: string[] = [];

    const beforeFiles = new Map(before.files.map((f) => [f.path, f]));
    const afterFiles = new Map(after.files.map((f) => [f.path, f]));

    for (const [path, file] of beforeFiles) {
      if (!afterFiles.has(path)) {
        removed.push(path);
      } else {
        const afterFile = afterFiles.get(path)!;
        if (file.lastModified !== afterFile.lastModified) {
          modified.push(path);
        }
      }
    }

    for (const path of afterFiles.keys()) {
      if (!beforeFiles.has(path)) {
        added.push(path);
      }
    }

    return { added, removed, modified, timestamp: after.timestamp };
  }

  /**
   * 压缩上下文到字符串（用于跨会话传递）
   */
  compressToPrompt(snapshot: ContextSnapshot): string {
    const parts: string[] = [
      `## 当前工作上下文`,
      `工作目录: ${snapshot.workDir}`,
      `模式: ${snapshot.mode === Mode.GREENFIELD ? "从0开始" : "半路接手"}`,
      `文件数: ${snapshot.projectMetrics.totalFiles}`,
      `代码行数: ${snapshot.projectMetrics.totalLines}`,
      `语言分布: ${Object.entries(snapshot.projectMetrics.languageBreakdown)
        .map(([lang, count]) => `${lang}: ${count}文件`)
        .join(", ")}`,
    ];

    if (snapshot.configFiles) {
      parts.push(`\n配置文件:`);
      for (const [name, content] of Object.entries(snapshot.configFiles)) {
        parts.push(`  ${name}: ${content.slice(0, 100)}`);
      }
    }

    if (snapshot.recentChanges.length > 0) {
      parts.push(`\n最近变更:`);
      for (const change of snapshot.recentChanges.slice(0, 10)) {
        parts.push(`  ${change}`);
      }
    }

    return parts.join("\n");
  }

  /**
   * 从压缩字符串恢复上下文（简化版）
   */
  async restoreFromPrompt(compressed: string): Promise<Partial<ExecutionContext>> {
    // 简化实现：实际使用时由LLM从文本中提取
    return {
      workDir: this.extractField(compressed, "工作目录"),
      mode: compressed.includes("从0开始") ? Mode.GREENFIELD : Mode.BROWNFIELD,
    };
  }

  /**
   * 检查上下文是否过期（文件变化了）
   */
  async isStale(snapshot: ContextSnapshot): Promise<boolean> {
    const fs = require("fs");
    const path = require("path");

    // 检查文件是否被修改
    for (const file of snapshot.files) {
      try {
        const stat = fs.statSync(file.path);
        if (stat.mtimeMs !== new Date(file.lastModified).getTime()) {
          return true;
        }
      } catch {
        return true; // 文件被删除了
      }
    }

    return false;
  }

  /**
   * 获取最新的上下文快照
   */
  getLatestSnapshot(): ContextSnapshot | null {
    return this.snapshots.length > 0
      ? this.snapshots[this.snapshots.length - 1]
      : null;
  }

  // ---- Private helpers ----

  private async scanFiles(root: string): Promise<FileEntry[]> {
    const fs = require("fs");
    const path = require("path");
    const files: FileEntry[] = [];

    const walk = (dir: string, depth: number) => {
      if (depth > 4) return;
      try {
        for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
          if (entry.name.startsWith(".") || entry.name === "node_modules" || 
              entry.name === "dist" || entry.name === "target") continue;
          const fullPath = path.join(dir, entry.name);
          if (entry.isDirectory()) {
            walk(fullPath, depth + 1);
          } else {
            try {
              const stat = fs.statSync(fullPath);
              files.push({
                path: fullPath,
                language: path.extname(entry.name).slice(1) || "unknown",
                sizeBytes: stat.size,
                lastModified: stat.mtime.toISOString(),
              });
            } catch { /* skip */ }
          }
        }
      } catch { /* skip */ }
    };

    walk(root, 0);
    return files;
  }

  private async getRecentChanges(root: string): Promise<string[]> {
    try {
      const { execSync } = require("child_process");
      const log = execSync(
        'git log --oneline -15 --format="%h %s (%ar)"',
        { cwd: root, encoding: "utf-8", stdio: ["pipe", "pipe", "ignore"] }
      );
      return log.split("\n").filter(Boolean);
    } catch {
      return [];
    }
  }

  private async getDependencies(root: string): Promise<Record<string, string>> {
    const fs = require("fs");
    const path = require("path");
    const deps: Record<string, string> = {};

    // package.json
    const pkgPath = path.join(root, "package.json");
    if (fs.existsSync(pkgPath)) {
      try {
        const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf-8"));
        if (pkg.dependencies) {
          for (const [name, version] of Object.entries(pkg.dependencies)) {
            deps[name] = version as string;
          }
        }
      } catch { /* ignore */ }
    }

    return deps;
  }

  private async getConfigFiles(root: string): Promise<Record<string, string>> {
    const fs = require("fs");
    const path = require("path");

    const configNames = [
      "package.json", "tsconfig.json", ".gitignore",
      "README.md", "CLAUDE.md", "DESIGN.md", "ARCHITECTURE.md",
      ".env.example", "docker-compose.yml", "Dockerfile",
    ];

    const configs: Record<string, string> = {};
    for (const name of configNames) {
      const fullPath = path.join(root, name);
      if (fs.existsSync(fullPath)) {
        try {
          configs[name] = fs.readFileSync(fullPath, "utf-8").slice(0, 500);
        } catch { /* ignore */ }
      }
    }

    return configs;
  }

  private async calculateMetrics(root: string): Promise<ProjectMetrics> {
    const fs = require("fs");
    const path = require("path");

    let totalFiles = 0;
    let totalLines = 0;
    let testFiles = 0;
    let docFiles = 0;
    const languageBreakdown: Record<string, number> = {};

    const walk = (dir: string, depth: number) => {
      if (depth > 4) return;
      try {
        for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
          if (entry.name.startsWith(".") || entry.name === "node_modules" || 
              entry.name === "dist" || entry.name === "target") continue;
          const fullPath = path.join(dir, entry.name);
          if (entry.isDirectory()) {
            walk(fullPath, depth + 1);
          } else {
            totalFiles++;
            const ext = path.extname(entry.name).slice(1) || "other";
            languageBreakdown[ext] = (languageBreakdown[ext] || 0) + 1;

            if (entry.name.includes("test") || entry.name.includes("spec")) testFiles++;
            if (entry.name.endsWith(".md")) docFiles++;

            try {
              const content = fs.readFileSync(fullPath, "utf-8");
              totalLines += content.split("\n").length;
            } catch { /* binary file */ }
          }
        }
      } catch { /* skip */ }
    };

    walk(root, 0);
    return { totalFiles, totalLines, languageBreakdown, testFiles, documentationFiles: docFiles };
  }

  private extractField(text: string, field: string): string {
    const regex = new RegExp(`${field}:\\s*(.+?)(?:\\n|$)`);
    const match = text.match(regex);
    return match ? match[1].trim() : "";
  }
}

// ==================== 类型 ====================

export interface ContextDiff {
  added: string[];
  removed: string[];
  modified: string[];
  timestamp: string;
}
