# ADR-007: 增量扫描 + 语义摘要 + 知识积累 (v3.1.0, 2026-05-12)

**决策**: 上下文管理从"文件截断"升级为"语义外化"三件套——项目快照增量扫描、代码语义结构提取、跨任务知识自动积累。

**原因**:
- 用户反馈每次扫描全项目费时费 token → SnapshotManager 存文件树 hash，后续只读变更文件
- ContextAssembler 原本只做前 300 行截断，丢失关键信息 → SemanticSummarizer 按语言规则提取类/函数签名，零 AI 成本
- 人工 .pipeline_note 无法规模化 → KnowledgeAccumulator 自动从每个任务产出提取 Key Decisions，下游任务注入

**新增模块**:
- `pipeline/snapshot.py` — 文件树 hash + mtime/size 变更检测
- `pipeline/semantic_summarizer.py` — 支持 8 种语言的结构提取
- `pipeline/knowledge_accumulator.py` — 按 category 查询注入历史决策

**权衡**: 摘要器是规则驱动而非 AI 驱动，复杂语义无法提取。未来可升级为 AI 驱动。
