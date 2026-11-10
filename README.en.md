# AI Dev Flow

> One command drives the full pipeline: requirements → analysis → design → code → review → delivery.
> Interruptible and resumable, with a human in the loop at every decision point.

**Status**: Active development (v3.10.0) · [中文文档](README.md)

---

## What this is

An orchestration layer for agentic coding, not a chat wrapper. It turns
requirements → design → coding → verification → delivery into a stateful,
resumable, auditable machine: decision points force human sign-off, all context
is externalized to files, every task ends in a git commit, and failures preserve
the working tree for inspection.

| Design goal | Trade-off |
|-------------|-----------|
| Process stays controlled | 5 mandatory checkpoints; AI drafts, humans decide. Not unattended automation |
| Context stays trustworthy | Requirements, design and `tasks.yaml` all live on disk; tasks never share conversation memory |
| Interruptions are recoverable | Stage and task state persist; rerunning the same command resumes from the break point |
| Changes stay traceable | One git commit per task; failed verification keeps the sandbox for debugging |

**Who it is for**: developers and small teams with existing Java / Vue / Python
codebases who want AI inside a real delivery process — and who need to answer
"who made this change, and under what constraints". **Not for**: IDE autocomplete,
throwaway scripts, or teams that refuse any manual confirmation step.

---

## Pipeline overview

```
ai-dev-flow --project /path/to/your/project

Phase 1 ─── requirement refinement (structured requirement doc)
  ⚠ Checkpoint A ─ confirm requirements
Phase 2 ─── analysis (features, data flow, open questions)
  ⚠ Checkpoint B ─ close open questions
Phase 3 ─── engineering design (architecture, interfaces, data model)
  ⚠ Checkpoint C ─ confirm design
Phase 3.5 ─ task decomposition (atomic tasks with context_notes)
  ⚠ Checkpoint C2 ─ confirm decomposition
█████████ task graph execution (each task = fresh session + git commit) █████████
Phase 5 ─── build + test
Phase 6 ─── code + security review
  ⚠ Checkpoint D ─ security sign-off (high-risk only)
Phase 7 ─── delivery (change list, build verification, review verdict)
```

---

## Quick start

### Prerequisites

| Dependency | Purpose |
|------------|---------|
| Python 3.9+ | orchestration engine |
| goose CLI >= 1.33 | AI execution engine |
| LLM API key | DeepSeek or any goose-compatible provider |

### Install

```bash
git clone https://github.com/293498733/AI_A_PLANT.git
cd AI_A_PLANT
pip install ai-dev-flow        # or: pip install -r requirements.txt

# supply the API key via environment variable
export CUSTOM_DEEPSEEK_API_KEY=your_key      # Windows: set CUSTOM_DEEPSEEK_API_KEY=your_key
```

### Usage

```bash
ai-dev-flow                                          # interactive start
ai-dev-flow --project /path/to/project               # target a project directory
ai-dev-flow --project . --from-stage phase3          # start from a specific stage
ai-dev-flow --project . --dry-run                    # preview stages without executing
```

---

## Core mechanisms

### Resume after interruption

Whatever stops the run — Ctrl+C, a reboot, a crashed engine — rerun the same
command and it continues from the break point. Global progress lives in
`.ai-dev/.pipeline_stage` inside the target project; per-task state lives in
`.ai-dev/task_state.json`.

### Task-driven execution with externalized context

Large projects are not written in a single AI session. Phase 3.5 decomposes the
design into atomic tasks in `tasks.yaml`. Each task:

- runs in a **fresh engine session** (20–60 turns) and never relies on chat memory
- gets all its context from **files** (`input_files` + `reference_docs` + `context_notes`)
- ends with an **automatic git commit**, so the change is traceable
- is individually resumable — a crash restarts the failed task, not the phase

### Error handling

Every AI stage offers 4 options on failure, and task-graph execution offers its
own 4: retry, fix/skip, write a note and exit, skip/abort.

---

## Project structure

```
ai-dev-flow/
├── pipeline.py              source-tree launcher (same as the `ai-dev-flow` command)
├── ai_dev_flow/             orchestration engine package
│   ├── cli.py               CLI entry point
│   └── data/                stage definitions, recipes, profile templates (installed with the package)
├── tests/                   212 tests
├── ARCHITECTURE.md          architecture design
└── CHANGELOG.md             release history
```

---

## Configuration

| Variable | Purpose |
|----------|---------|
| `CUSTOM_DEEPSEEK_API_KEY` | LLM API key used by the engine |

---

## License

MIT — see [LICENSE](LICENSE).
