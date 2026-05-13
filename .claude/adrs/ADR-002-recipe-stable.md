# ADR-002: Recipe 文件保持不变

**决策**: YAML Recipe 格式和内容不修改，作为稳定接口层。

**原因**: Recipe 是 AI 行为定义的核心契约，格式稳定可保证 goose 版本升级时兼容。
