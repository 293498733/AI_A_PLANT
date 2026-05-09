// ============================================================
// 代码执行器 — 执行计划中的任务
// ============================================================

import {
  Task,
  TaskResult,
  TaskStatus,
  ExecutionContext,
  ExecutionCommand,
  Mode,
  ChangeType,
} from "../types/index.ts";

export interface ExecutorOptions {
  /** 是否启用连续检查点（自动git提交） */
  continuousCheckpoint: boolean;
  /** 是否在变更前创建备份 */
  backupBeforeChange: boolean;
  /** 每次变更后的验证 */
  verifyAfterChange: boolean;
  /** 最大并发任务数（异步执行时） */
  maxConcurrency: number;
  /** 是否记录详细执行日志 */
  verbose: boolean;
}

const DEFAULT_OPTIONS: ExecutorOptions = {
  continuousCheckpoint: true,
  backupBeforeChange: true,
  verifyAfterChange: true,
  maxConcurrency: 1,
  verbose: true,
};

/**
 * 代码执行器
 * 
 * 核心设计哲学：
 * 1. **读-改-验**循环：每个任务都是 读文件 → 改代码 → 验证
 * 2. **原子变更**：每个任务最小化变更范围
 * 3. **可回滚**：变更前保存状态
 * 4. **连续检查点**：每个完成后自动git提交
 * 
 * 这个类不直接执行代码——它生成供agent执行的指令序列。
 * agent实际使用 write/edit/shell 等工具来实现。
 */
export class CodeExecutor {
  private options: ExecutorOptions;
  private executedTasks: Map<string, TaskResult> = new Map();

  constructor(options?: Partial<ExecutorOptions>) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
  }

  /**
   * 执行单个任务
   * 
   * 生成agent指令序列，agent按照指令使用对应工具执行。
   * 
   * 标准流程：
   * ```
   * 1. [读取] 读取要修改的文件
   * 2. [分析] 理解当前代码（如果是修改）
   * 3. [修改] 执行变更
   * 4. [验证] 编译检查
   * 5. [提交] git commit（连续检查点）
   * ```
   */
  async execute(task: Task, ctx: ExecutionContext): Promise<TaskResult> {
    task.status = TaskStatus.EXECUTING;
    
    console.log(`[执行器] 执行任务: ${task.id} - ${task.summary}`);

    const changedFiles: string[] = [];
    const commands: ExecutionCommand[] = [];

    try {
      // 步骤1: 生成执行指令
      const instructions = this.generateInstructions(task, ctx);

      // 步骤2: 执行指令（实际由agent执行）
      for (const instruction of instructions) {
        const result = await this.executeCommand(instruction, ctx);
        if (result.changedFiles) {
          changedFiles.push(...result.changedFiles);
        }
        commands.push(instruction);
      }

      // 步骤3: 备份（如果有修改）
      if (this.options.backupBeforeChange && changedFiles.length > 0) {
        await this.createBackup(changedFiles, ctx);
      }

      // 步骤4: 连续检查点
      if (this.options.continuousCheckpoint && changedFiles.length > 0) {
        await this.createCheckpoint(task, ctx);
      }

      const result: TaskResult = {
        success: true,
        changedFiles: [...new Set(changedFiles)],
      };

      task.status = TaskStatus.DONE;
      task.result = result;
      this.executedTasks.set(task.id, result);

      console.log(`[执行器] ✅ 任务完成: ${task.id} (${changedFiles.length} 个文件)`);
      return result;

    } catch (error) {
      task.status = TaskStatus.FAILED;
      const errorMsg = error instanceof Error ? error.message : String(error);
      
      console.error(`[执行器] ❌ 任务失败: ${task.id} - ${errorMsg}`);
      
      const result: TaskResult = {
        success: false,
        error: errorMsg,
        changedFiles,
      };
      
      task.result = result;
      return result;
    }
  }

  /**
   * 生成agent执行指令序列
   * 
   * 这是最核心的方法——将"任务"转化为"agent可执行的指令"
   */
  private generateInstructions(task: Task, ctx: ExecutionContext): ExecutionCommand[] {
    const instructions: ExecutionCommand[] = [];

    // 1. READ phase: 读取所有要修改的文件
    for (const file of task.files) {
      instructions.push({
        type: "read",
        params: { path: file },
        description: `读取 ${file} 了解当前内容`,
      });
    }

    // 2. ANALYZE phase: 分析代码结构
    if (task.files.length > 0) {
      instructions.push({
        type: "analyze",
        params: { path: this.getAnalyzePath(task.files, ctx) },
        description: "分析相关代码结构",
      });
    }

    // 3. MODIFY phase: 执行变更
    const modifyCmd: ExecutionCommand = {
      type: "edit",
      params: this.getEditParams(task, ctx),
      description: task.description || task.summary,
    };

    if (task.changeType === ChangeType.CREATE) {
      modifyCmd.type = "write";
    }
    instructions.push(modifyCmd);

    // 4. REVIEW phase: 审查变更
    if (this.options.verifyAfterChange) {
      instructions.push({
        type: "review",
        params: { 
          files: task.files,
          task: task.id,
        },
        description: `验证 ${task.summary} 的变更`,
      });
    }

    return instructions;
  }

  /**
   * 执行单个指令
   * 
   * 在生产环境中，这个方法不会被实际调用——
   * agent直接使用 write/edit/shell 工具。
   * 这里保留为框架完整性。
   */
  private async executeCommand(
    cmd: ExecutionCommand,
    ctx: ExecutionContext
  ): Promise<{ changedFiles?: string[] }> {
    // 标记：实际由agent执行
    // 返回格式让调度器知道哪些文件被修改了
    return {};
  }

  /** 并行执行多个任务（按依赖顺序） */
  async executeBatch(tasks: Task[], ctx: ExecutionContext): Promise<Map<string, TaskResult>> {
    const results = new Map<string, TaskResult>();
    const pending = new Set(tasks.map((t) => t.id));

    // 按依赖顺序执行
    const executeReadyTask = async (): Promise<void> => {
      for (const task of tasks) {
        if (task.status !== TaskStatus.PENDING && task.status !== TaskStatus.READY) continue;
        
        // 检查依赖是否全部完成
        const depsDone = task.dependencies.every((depId) => {
          const depResult = this.executedTasks.get(depId);
          return depResult?.success === true;
        });

        if (!depsDone) {
          // 检查是否有失败的依赖
          const depsFailed = task.dependencies.some((depId) => {
            const depResult = this.executedTasks.get(depId);
            return depResult?.success === false;
          });
          if (depsFailed) {
            task.status = TaskStatus.BLOCKED;
            console.log(`[执行器] ⛔ 任务阻塞: ${task.id} (依赖失败)`);
            continue;
          }
          task.status = TaskStatus.BLOCKED;
          continue;
        }

        task.status = TaskStatus.READY;
        const result = await this.execute(task, ctx);
        results.set(task.id, result);
        pending.delete(task.id);
      }
    };

    // 循环直到所有任务完成
    while (pending.size > 0) {
      await executeReadyTask();
      // 检测死锁
      const blocked = tasks.filter((t) => t.status === TaskStatus.BLOCKED);
      if (blocked.length === pending.size) {
        console.error(`[执行器] ⚠️ 检测到依赖死锁: ${blocked.map((t) => t.id).join(", ")}`);
        break;
      }
    }

    return results;
  }

  // ---- Checkpoint ----

  private async createBackup(files: string[], ctx: ExecutionContext): Promise<void> {
    // 由agent执行: 对每个文件创建 .bak 备份
    // 重要文件使用 git stash 或临时备份
    console.log(`[执行器] 备份 ${files.length} 个文件`);
  }

  private async createCheckpoint(task: Task, ctx: ExecutionContext): Promise<void> {
    // 由agent执行: git add + git commit
    // 提交格式:
    // WIP: <任务摘要>
    // [gstack-context]
    // Decisions: ...
    // Remaining: ...
    // [/gstack-context]
    console.log(`[执行器] 检查点: ${task.id}`);
  }

  // ---- Helpers ----

  private getAnalyzePath(files: string[], ctx: ExecutionContext): string {
    // 优先分析第一个文件的目录
    if (files.length === 0) return ctx.repoRoot;
    const dir = files[0].substring(0, files[0].lastIndexOf("/"));
    return dir || ctx.repoRoot;
  }

  private getEditParams(task: Task, ctx: ExecutionContext): Record<string, unknown> {
    return {
      files: task.files,
      changeType: task.changeType,
      description: task.description,
      mode: ctx.mode,
    };
  }

  /** 获取执行统计 */
  getStats(): { total: number; succeeded: number; failed: number } {
    let succeeded = 0;
    let failed = 0;
    
    for (const [_, result] of this.executedTasks) {
      if (result.success) succeeded++;
      else failed++;
    }

    return {
      total: this.executedTasks.size,
      succeeded,
      failed,
    };
  }
}
