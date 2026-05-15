# ADR-003: 数据驱动阶段定义

**决策**: 阶段定义从 Bat 中的 goto 标签迁移到 `pipeline.yaml`。

**原因**: 新增阶段只需编辑 YAML，无需修改 Python 代码。
