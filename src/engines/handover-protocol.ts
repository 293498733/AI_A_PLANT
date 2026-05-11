// ============================================================
// 接管协议 — 半路接手已有工程的标准化流程
// ============================================================

import {
  ExecutionContext,
  Mode,
  ReconReport,
  DirNode,
  RepoState,
  MentalModel,
  EntityDef,
  DataFlow,
  HandoverRecommendation,
  RiskLevel,
  FileEntry,
} from "../types/index.ts";

export interface HandoverOptions {
  /** 仓库根路径 */
  repoRoot: string;
  /** 是否分析git历史 */
  analyzeGit: boolean;
  /** 是否分析构建系统 */
  analyzeBuild: boolean;
  /** 深度分析（详细模式 vs 快速概览） */
  depth: "quick" | "full";
}

const DEFAULT_OPTIONS: HandoverOptions = {
  repoRoot: "",
  analyzeGit: true,
  analyzeBuild: true,
  depth: "full",
};

/**
 * 接管协议 —— 这是整个系统中最关键的部分之一
 * 
 * 当面对一个已有工程时，agant需要：
 * 1. 先"侦察"（不要动手！）
 * 2. 再"理解"（建立心智模型）
 * 3. 最后"建议"（推荐介入策略）
 * 
 * 黄金法则：在完全理解之前，永远不要修改任何文件
 */
export class HandoverProtocol {
  private options: HandoverOptions;

  constructor(options?: Partial<HandoverOptions>) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
  }

  /**
   * 执行完整的接管流程
   * 
   * agent工作流：
   * 1. 调用 tree 工具分析目录结构
   * 2. 读取关键配置文件
   * 3. 读取README/CLAUDE.md/DESIGN.md
   * 4. 运行 git log 分析历史
   * 5. 使用 analyze 工具提取实体
   * 6. 生成接管报告
   */
  async execute(repoRoot: string): Promise<{
    context: ExecutionContext;
    report: ReconReport;
    mentalModel: MentalModel;
    recommendation: HandoverRecommendation;
  }> {
    this.options.repoRoot = repoRoot;

    // Phase 1: 仓库侦察
    console.log("[接管协议] Phase 1: 仓库侦察");
    const report = await this.recon(repoRoot);

    // Phase 2: 心智模型重建
    console.log("[接管协议] Phase 2: 心智模型重建");
    const mentalModel = await this.buildMentalModel(repoRoot, report);

    // Phase 3: 介入点推荐
    console.log("[接管协议] Phase 3: 介入点推荐");
    const recommendation = this.recommend(report, mentalModel);

    // 构建执行上下文
    const context: ExecutionContext = {
      mode: Mode.BROWNFIELD,
      workDir: repoRoot,
      repoRoot,
      branch: report.activeBranch,
    };

    return { context, report, mentalModel, recommendation };
  }

  // ---- Phase 1: 仓库侦察 ----

  private async recon(repoRoot: string): Promise<ReconReport> {
    const fs = require("fs");
    const path = require("path");

    // 1. 检测语言
    const languages = this.detectLanguages(repoRoot);

    // 2. 检测构建系统
    const buildSystem = this.detectBuildSystem(repoRoot);

    // 3. 检测测试框架
    const testFramework = this.detectTestFramework(repoRoot);

    // 4. 检测CI
    const hasCI = this.detectCI(repoRoot);

    // 5. 目录结构
    const dirStructure = this.getDirStructure(repoRoot, 3);

    // 6. 文件统计
    const fileCount = this.countFiles(repoRoot);

    // 7. Git活动
    const recentActivity = this.options.analyzeGit
      ? this.getRecentGitActivity(repoRoot)
      : "未分析";

    // 8. 活跃分支
    const activeBranch = this.options.analyzeGit
      ? this.getActiveBranch(repoRoot)
      : "未知";

    // 9. 依赖
    const dependencies = this.getDependencies(repoRoot);

    // 10. 文档
    const documentation = this.getDocumentation(repoRoot);

    // 11. 状态评估
    const state = this.assessRepoState(repoRoot);

    return {
      repoRoot,
      languages,
      buildSystem,
      testFramework,
      hasCI,
      fileCount,
      dirStructure,
      recentActivity,
      activeBranch,
      dependencies,
      documentation,
      state,
    };
  }

  private detectLanguages(root: string): string[] {
    const fs = require("fs");
    const path = require("path");
    const extMap: Record<string, string> = {
      ".ts": "TypeScript",
      ".tsx": "TypeScript React",
      ".js": "JavaScript",
      ".jsx": "JavaScript React",
      ".py": "Python",
      ".rs": "Rust",
      ".go": "Go",
      ".java": "Java",
      ".rb": "Ruby",
      ".php": "PHP",
      ".swift": "Swift",
      ".kt": "Kotlin",
      ".c": "C",
      ".cpp": "C++",
      ".cs": "C#",
      ".vue": "Vue",
      ".svelte": "Svelte",
    };

    const languages = new Set<string>();
    const walkDir = (dir: string, depth: number) => {
      if (depth > 4 || !fs.existsSync(dir)) return;
      try {
        for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
          if (entry.name.startsWith(".") || entry.name === "node_modules" || 
              entry.name === "dist" || entry.name === "build" || 
              entry.name === ".git" || entry.name === "target") continue;
          
          const fullPath = path.join(dir, entry.name);
          if (entry.isDirectory()) {
            walkDir(fullPath, depth + 1);
          } else {
            const ext = path.extname(entry.name);
            if (extMap[ext]) languages.add(extMap[ext]);
          }
        }
      } catch {
        // 跳过无权限目录
      }
    };

    walkDir(root, 0);
    return Array.from(languages);
  }

  private detectBuildSystem(root: string): string | null {
    const fs = require("fs");
    const path = require("path");

    const indicators: Record<string, string> = {
      "package.json": "npm/pnpm/yarn (Node.js)",
      "Cargo.toml": "Cargo (Rust)",
      "go.mod": "Go Modules",
      "CMakeLists.txt": "CMake",
      "Makefile": "Make",
      "pom.xml": "Maven (Java)",
      "build.gradle": "Gradle",
      "pyproject.toml": "PEP 517 (Python)",
      "setup.py": "setuptools (Python)",
      "Cargo.lock": "",
      "Gemfile": "Bundler (Ruby)",
      "mix.exs": "Mix (Elixir)",
      "rebar.config": "Rebar (Erlang)",
      "stack.yaml": "Stack (Haskell)",
      "cabal.project": "Cabal (Haskell)",
      "dune-project": "Dune (OCaml)",
      "*.csproj": "MSBuild (.NET)",
      "Project.assets.json": ".NET",
      "pubspec.yaml": "pub (Dart/Flutter)",
    };

    for (const [file, system] of Object.entries(indicators)) {
      const fullPath = path.join(root, file);
      if (fs.existsSync(fullPath)) return system;
    }
    return null;
  }

  private detectTestFramework(root: string): string | null {
    const fs = require("fs");
    const path = require("path");

    // 常见测试配置文件
    const testConfigs = [
      "jest.config.js", "jest.config.ts", "jest.config.json",
      "vitest.config.ts", "vitest.config.js",
      ".mocharc.yml", ".mocharc.json",
      "karma.conf.js", "karma.conf.ts",
      "cypress.json", "cypress.config.ts",
      "playwright.config.ts",
    ];

    for (const config of testConfigs) {
      if (fs.existsSync(path.join(root, config))) {
        const name = config.split(".")[0];
        return name.charAt(0).toUpperCase() + name.slice(1);
      }
    }

    // 检测测试目录
    const testDirs = ["tests", "test", "__tests__", "spec"];
    for (const dir of testDirs) {
      if (fs.existsSync(path.join(root, dir))) return "检测到测试目录";
    }

    return null;
  }

  private detectCI(root: string): boolean {
    const fs = require("fs");
    const path = require("path");

    const ciPaths = [
      ".github/workflows",
      ".gitlab-ci.yml",
      "Jenkinsfile",
      ".circleci/config.yml",
      ".travis.yml",
      "azure-pipelines.yml",
      "bitbucket-pipelines.yml",
      ".buildkite/pipeline.yml",
      "appveyor.yml",
      ".drone.yml",
      ".woodpecker.yml",
    ];

    return ciPaths.some((p) => {
      const fullPath = path.join(root, p);
      return fs.existsSync(fullPath);
    });
  }

  private getDirStructure(root: string, maxDepth: number): DirNode[] {
    const fs = require("fs");
    const path = require("path");
    const skipDirs = new Set([
      ".git", "node_modules", "dist", "build", "target", 
      ".next", ".nuxt", ".output", "coverage", ".cache",
      "__pycache__", ".venv", "venv", "env", ".tox",
      ".gradle", "vendor", ".dart_tool", ".packages",
    ]);

    const readDir = (dir: string, depth: number): DirNode[] => {
      if (depth > maxDepth || !fs.existsSync(dir)) return [];
      const result: DirNode[] = [];

      try {
        for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
          if (entry.name.startsWith(".") && !entry.name.startsWith(".env")) continue;
          if (skipDirs.has(entry.name)) continue;

          const fullPath = path.join(dir, entry.name);
          if (entry.isDirectory()) {
            result.push({
              name: entry.name,
              type: "dir",
              children: readDir(fullPath, depth + 1),
            });
          } else {
            try {
              const stat = fs.statSync(fullPath);
              result.push({
                name: entry.name,
                type: "file",
                size: stat.size,
              });
            } catch {
              result.push({ name: entry.name, type: "file" });
            }
          }
        }
      } catch {
        // 跳过无权限目录
      }

      return result;
    };

    return readDir(root, 0);
  }

  private countFiles(root: string): number {
    const fs = require("fs");
    const path = require("path");
    let count = 0;

    const walk = (dir: string, depth: number) => {
      if (depth > 5 || !fs.existsSync(dir)) return;
      try {
        for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
          if (entry.name === ".git" || entry.name === "node_modules" || entry.name === "dist") continue;
          const fullPath = path.join(dir, entry.name);
          if (entry.isDirectory()) {
            walk(fullPath, depth + 1);
          } else {
            count++;
          }
        }
      } catch { /* skip */ }
    };

    walk(root, 0);
    return count;
  }

  private getRecentGitActivity(root: string): string {
    try {
      const { execSync } = require("child_process");
      const log = execSync("git log --oneline -20", { cwd: root, encoding: "utf-8" });
      return log || "没有提交记录";
    } catch {
      return "Git不可用或不是Git仓库";
    }
  }

  private getActiveBranch(root: string): string {
    try {
      const { execSync } = require("child_process");
      return execSync("git branch --show-current", { cwd: root, encoding: "utf-8" }).trim();
    } catch {
      return "未知";
    }
  }

  private getDependencies(root: string): Record<string, string> {
    const fs = require("fs");
    const path = require("path");
    const deps: Record<string, string> = {};

    // Node.js
    const pkgPath = path.join(root, "package.json");
    if (fs.existsSync(pkgPath)) {
      try {
        const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf-8"));
        if (pkg.dependencies) Object.assign(deps, pkg.dependencies);
      } catch { /* ignore */ }
    }

    return deps;
  }

  private getDocumentation(root: string): string[] {
    const fs = require("fs");
    const path = require("path");

    const docFiles = [
      "README.md", "README", "README.txt",
      "CONTRIBUTING.md", "CONTRIBUTING",
      "ARCHITECTURE.md", "ARCHITECTURE",
      "DESIGN.md", "DESIGN",
      "CLAUDE.md", "CLAUDE",
      "CHANGELOG.md", "CHANGELOG",
      "CHANGELOG.md", "CHANGELOG",
      "TODOS.md",
      "docs/",
      "documentation/",
    ];

    return docFiles.filter((f) => {
      const fullPath = path.join(root, f);
      return fs.existsSync(fullPath);
    });
  }

  private assessRepoState(root: string): RepoState {
    const fs = require("fs");
    const path = require("path");

    // 判断标准
    const hasTests = fs.existsSync(path.join(root, "tests")) || 
                     fs.existsSync(path.join(root, "__tests__"));
    const hasCI = this.detectCI(root);
    const hasPackageJson = fs.existsSync(path.join(root, "package.json"));
    const hasLicense = fs.existsSync(path.join(root, "LICENSE")) || 
                       fs.existsSync(path.join(root, "LICENSE.txt")) || 
                       fs.existsSync(path.join(root, "LICENSE.md"));
    const hasChangelog = fs.existsSync(path.join(root, "CHANGELOG.md"));
    const hasCI = this.detectCI(root);
    const fileCount = this.countFiles(root);

    if (fileCount < 10) return RepoState.PROTOTYPE;
    if (!hasTests && !hasCI) return RepoState.PROTOTYPE;
    if (hasTests && hasCI && hasChangelog && hasLicense) return RepoState.STABLE;
    if (fileCount > 100 && !hasTests) return RepoState.LEGACY;
    return RepoState.ACTIVE_DEV;
  }

  // ---- Phase 2: 心智模型重建 ----

  private async buildMentalModel(root: string, report: ReconReport): Promise<MentalModel> {
    const entities = await this.extractEntities(root, report);
    const dataFlows = this.inferDataFlows(entities);
    const constraints = this.extractDesignConstraints(root);
    const techDebt = this.identifyTechDebt(root, report);

    return {
      domainEntities: entities,
      dataFlows,
      designConstraints: constraints,
      techDebt,
    };
  }

  private async extractEntities(root: string, report: ReconReport): Promise<EntityDef[]> {
    // 在实际运行中，这里会使用 analyze 工具（tree-sitter AST解析）
    // 提取类、函数、组件、路由等
    
    const entities: EntityDef[] = [];

    for (const lang of report.languages) {
      // 每个语言有对应的提取策略
      switch (lang) {
        case "TypeScript":
        case "TypeScript React":
          entities.push(
            ...await this.extractTSEntities(root)
          );
          break;
        case "Python":
          entities.push(
            ...await this.extractPyEntities(root)
          );
          break;
        // 更多语言支持...
      }
    }

    return entities;
  }

  private async extractTSEntities(root: string): Promise<EntityDef[]> {
    // 在实际运行中，用 `analyze` 工具 + tree-sitter 进行AST分析
    // 这里标记为agent驱动的操作
    return [];
  }

  private async extractPyEntities(root: string): Promise<EntityDef[]> {
    return [];
  }

  private inferDataFlows(entities: EntityDef[]): DataFlow[] {
    // 从实体依赖关系推断数据流
    const flows: DataFlow[] = [];
    for (const entity of entities) {
      for (const dep of entity.dependencies) {
        const target = entities.find(
          (e) => e.name === dep || e.file.includes(dep)
        );
        if (target) {
          flows.push({
            from: `${entity.file}::${entity.name}`,
            to: `${target.file}::${target.name}`,
            data: "inferred",
          });
        }
      }
    }
    return flows;
  }

  private extractDesignConstraints(root: string): string[] {
    const fs = require("fs");
    const path = require("path");
    const constraints: string[] = [];

    // 从架构文档中提取约束
    const docFiles = ["ARCHITECTURE.md", "DESIGN.md", "CLAUDE.md"];
    for (const doc of docFiles) {
      const docPath = path.join(root, doc);
      if (fs.existsSync(docPath)) {
        try {
          const content = fs.readFileSync(docPath, "utf-8");
          const constraintLines = content.match(/约束[：:].*/g) || 
                                  content.match(/Constraint[s]?[：:].*/gi) ||
                                  content.match(/Do not.*/gi) ||
                                  content.match(/不应[该]?.*/g);
          if (constraintLines) {
            constraints.push(...constraintLines);
          }
        } catch { /* ignore */ }
      }
    }

    return constraints;
  }

  private identifyTechDebt(root: string, report: ReconReport): string[] {
    const debt: string[] = [];

    // 检查常见的债务信号
    if (!report.hasCI) debt.push("缺少CI/CD配置");
    if (!report.testFramework) debt.push("缺少测试框架");
    if (report.state === RepoState.LEGACY) debt.push("可能积累了大量技术债务");

    // 更多检测...
    return debt;
  }

  // ---- Phase 3: 介入点推荐 ----

  private recommend(report: ReconReport, model: MentalModel): HandoverRecommendation {
    const entryPoints: string[] = [];
    
    // 根据仓库状态推荐介入策略
    switch (report.state) {
      case RepoState.PROTOTYPE:
        entryPoints.push("快速原型完善——尽快让功能可工作");
        entryPoints.push("添加测试基础设施——早期投资测试");
        break;
      case RepoState.ACTIVE_DEV:
        entryPoints.push("跟着已有的PR/issue走——最小化干扰当前开发");
        entryPoints.push("从文档中识别明确的待办事项");
        break;
      case RepoState.STABLE:
        entryPoints.push("阅读CHANGELOG了解最近发布");
        entryPoints.push("从issue tracker中找bug fix");
        entryPoints.push("新功能先做设计文档，不要直接改代码");
        break;
      case RepoState.LEGACY:
        entryPoints.push("先写测试作为安全网");
        entryPoints.push("小步重构，每次不超过3个文件");
        break;
    }

    // 如果有明确的文档提示，优先遵循
    if (report.documentation.includes("CLAUDE.md")) {
      entryPoints.unshift("读取CLAUDE.md了解开发规范和约束");
    }

    const riskLevel = report.state === RepoState.STABLE ? RiskLevel.HIGH :
                      report.state === RepoState.LEGACY ? RiskLevel.CRITICAL :
                      report.state === RepoState.ACTIVE_DEV ? RiskLevel.MEDIUM :
                      RiskLevel.LOW;

    return {
      mode: Mode.BROWNFIELD,
      entryPoints: [...new Set(entryPoints)],
      riskLevel,
      suggestedFirstAction: entryPoints[0] ?? "先读取README.md了解项目概况",
      reasoning: `仓库处于${report.state}状态，${report.languages.join("/")}项目` +
                 `${report.hasCI ? "，有CI配置" : "，无CI配置"}` +
                 `${report.testFramework ? `，使用${report.testFramework}` : "，无测试框架"}` +
                 `。建议优先${entryPoints[0]?.toLowerCase() ?? "理解项目结构"}`,
    };
  }
}
