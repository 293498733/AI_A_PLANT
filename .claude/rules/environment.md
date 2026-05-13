# 环境要求

- Python 3.9+
- goose CLI >= 1.33
- PyYAML >= 6.0 (`pip install pyyaml`)
- pytest + pytest-mock (`pip install -r requirements-dev.txt`)

## 环境变量

| 变量 | 用途 |
|------|------|
| `CUSTOM_DEEPSEEK_API_KEY` | LLM API 密钥（当前硬编码，v4.0 改为 `AI_MODEL_PROVIDER` 切换） |

## Windows 注意事项

- 路径使用 `pathlib.Path`，不用字符串拼接
- 子进程 `subprocess.Popen` 用 `encoding="utf-8"`, `errors="replace"`
- `taskkill /F /T /PID` 杀进程树
- git worktree 路径注意 MAX_PATH（260 字符限制）
