# FAQ

维护者按实际使用中遇到的问题整理。答案对应 v3.8.1 的代码行为。

## 如何自定义某个阶段的 Recipe？

改 `pipeline.yaml` 中对应 stage 的 `recipe:` 路径即可，阶段列表不需要改 Python 代码。

建议复制 `recipes/steps/` 下的模板改一份，保留原文件，再把 `recipe:` 指过去。阶段参数通过 `params:` 传入，recipe 里用 `{{ project_root }}` 这类占位符接收。

## 能跳过人工确认，全自动跑吗？

`--ci` 会跳过所有检查点并使用默认选项。但不建议无人值守：4 个检查点分别卡在需求、不确定项、方案、任务拆分上，目的是让人在这些位置拍板。管线适合的是"AI 起草、人审关键节点"，不是全自动。

## 恢复需要加 `--resume` 吗？

不需要。执行过的阶段会写入 `.ai-dev/.pipeline_stage`，重跑同一命令时自动从下一阶段继续；任务级状态在 `.ai-dev/task_state.json`。

`--resume` 是早期参数，当前未被代码读取——因为恢复始终是自动的。传不传结果相同。

## 中断后重跑，会重复执行已完成的任务吗？

不会。`completed`、`code_produced`、`skipped` 都计入已完成；崩溃时残留的 `in_progress` 会在启动时重置为 `pending`；失败任务按 `retry_limit`（默认 2）重试，超过上限后自动跳过或交给人工决策。

## 任务验证失败，代码还在吗？

在。状态记为 `code_produced`：文件已写入并提交，沙箱保留供排查，下游任务不会被阻塞。它和 `failed_no_output`（goose 没产出有效文件）是两种不同的失败。

## 支持哪些模型？

当前通过 goose CLI 调用，模型由 goose 的配置决定，项目默认使用 DeepSeek。多引擎（不依赖 goose 的抽象层）在 v4.0 计划中，尚未实现。

## Windows 上有哪些注意事项？

- 路径统一用 `pathlib.Path`，不手工拼字符串
- 子进程以 UTF-8 读写，坏字节替换而非抛错
- 进程终止用 `taskkill /F /T` 杀整棵进程树
- git worktree 路径受 260 字符限制，目标项目路径不宜过深

## 能用在非 Java / Vue 项目上吗？

编排层与语言无关。但 `recipes/steps/00-init-project.yaml` 默认扫描 Spring Boot / Vue 特征，`pipeline.yaml` 的验证参数也偏 Java / 前端。非这两类项目需要调整对应 recipe 和阶段 `params`。

## 为什么每个任务都要一次 git commit？

为了可回溯：任务失败时能定位到具体哪次改动，`git log` 就是任务执行记录。代价是提交数量多，适合在目标项目里单独使用分支。
