# ADR-004: Popen 替代 subprocess.run

**决策**: executor 使用 `subprocess.Popen` + 逐行读取 stdout。

**原因**: 实时输出对开发者可见，避免 subprocess.run 等待结束后才展示全部输出。
