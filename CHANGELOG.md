# Changelog

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [3.10.0] - 2026-11-10

发布到 PyPI：包重命名以避开同名冲突，数据文件随包分发，新增 console script。

### Added

- `pyproject.toml`：发行名 `ai-dev-flow`，console script `ai-dev-flow`，`python -m ai_dev_flow` 亦可。
- `ai_dev_flow/__main__.py`：模块入口。
- `pipeline.py`（根目录）保留为三行启动器，`python pipeline.py` 用法不变。

### Changed — **破坏性**

- 顶层包 `pipeline` 重命名为 `ai_dev_flow`。原因：PyPI 上已存在同名的 `pipeline` 包，安装后会与本项目互相覆盖。所有 import 路径随之改变（`from pipeline.x` → `from ai_dev_flow.x`）。
- `pipeline.yaml` / `recipes/` / `profiles/` 移入 `ai_dev_flow/data/`，作为包数据随 wheel 一起安装；此前从源码根目录解析，`pip install` 后必然找不到。
- 文档、CI 模板中的命令示例统一改为 `ai-dev-flow`。

### 升级注意

从源码树运行的用法不变（`python pipeline.py`）。若你在代码里 `from pipeline import ...`，改为 `from ai_dev_flow import ...`。

## [3.9.0] - 2026-11-10

开源发布准备：补齐许可证与英文文档，清理一个失效 CLI 参数。

### Added

- `LICENSE`（MIT）：此前 README 声明 MIT 但仓库无许可证文件，GitHub 无法识别。
- `README.en.md`：英文用户手册，覆盖定位、流程、安装、核心机制、配置项。

### Removed

- `--resume` 参数（`pipeline.py`）：自 v3.1 起从未被代码读取，阶段恢复始终自动进行。源码 docstring 与 `--help` 文本同步修正，`docs/FAQ.md` 对应条目更新为「已移除」。

### Changed

- README 增加中英文互链与 `LICENSE` 链接。

## [3.8.1] - 2026-10-23

测试覆盖补全，无功能变更。

### Added — 测试

- **循环依赖检测边界**（`tests/test_task_graph.py`）：空任务图返回 `None`；全部依赖指向图外任务时不误判；环内节点混合外部依赖时仍能检出环。
- **看门狗进程组判定**（`tests/test_watchdog.py`）：目标为进程组组长时使用 `killpg`；非组长时仅按 PID 终止，避免连带杀掉调用方；`getpgid` 失败时退化为按 PID 终止。锁定 v3.8.0 中 "POSIX 下看门狗避免误杀管线自身" 的行为。
- **执行器超时返回契约**（`tests/test_executor.py`）：看门狗触发时返回 `-1` 并注明原因，而非透传子进程退出码；未触发时正常透传。

测试总数 204 → 212（含 8 个新增用例），全部通过。

## [3.8.0] - 2026-05-15

可控性修复，来源为 2026-05-14 进销存 WMS 项目实战：任务图执行失败与 goose 卡死。

### Added

- `TaskConfig.verification` 字段：按任务 category 选择验证策略（D2）
- 三元任务状态：`completed` / `code_produced` / `failed_no_output`（D3）
- `pipeline.yaml` 阶段 `prerequisite` 字段与启动前前置守卫（D4）
- goose 输出循环检测：连续相同 stderr 达到阈值时终止进程（D5）
- 任务错误信息结构化输出（D6）

### Fixed

- JAVA_HOME pre-flight 检查 + PATH 注入加固（D1）
- POSIX 下使用独立会话启动 goose，看门狗超时不再波及管线自身进程组
- 看门狗回调用例改为轮询等待，消除 Windows 时序抖动
- 补齐模块级 `from __future__ import annotations`，恢复 Python 3.9 兼容
