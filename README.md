# Auto-SDD V2

Automated software development pipeline. LLM agents implement features from a roadmap in a topologically sorted build loop with deterministic enforcement gates.

## What it does

Given a project with a roadmap of features and specs, Auto-SDD V2:

1. Parses the roadmap and topologically sorts features by dependency
2. For each feature: creates a branch, invokes a build agent, validates the output through five deterministic gates, and merges to main
3. Resumes from where it left off if interrupted
4. Skips features whose dependencies failed

The build agent writes code, runs builds, runs tests, commits, and emits completion signals. The orchestrator validates everything mechanically. No LLM-as-judge. No probabilistic evaluation.

## First campaign result

7/7 features built for [cre-pulse](https://github.com/fischmanb/cre-pulse) (Next.js 14 CRE dashboard). 24 source files, 147 tests passing, ~36 minutes total.

| Feature | Attempts | Tests |
|---------|----------|-------|
| Data Loader | 1 | -- |
| Global Layout & Theming | 1 | 23 |
| Shared UI Components | 2 | 65 |
| Property Overview Card | 3 | 65 |
| Tenant Roster Table | 1 | 94 |
| Lease Velocity Timeline | 1 | 120 |
| Comp Set Benchmarks | 2 | 147 |

## Architecture

```
SELECT -> BUILD -> GATE -> ADVANCE
```

**SELECT**: Parse roadmap, topo-sort by deps, skip features whose deps failed, build system+user prompts with spec path, codebase summary, and previous error context (on retry).

**BUILD**: Fresh agent context per feature. Agent has three tools: `write_file`, `read_file`, `run_command`. Every tool call passes through EG1 before execution. Agent writes code, runs builds/tests, commits, emits `FEATURE_BUILT` signal.

**GATE**: Five deterministic checks, short-circuit on first failure:
- **EG1** (tool calls): Path containment, command allowlisting, write-then-exec detection, git chain handling, safe chain splitting, runtime-aware validation. Runs inline during BUILD.
- **EG2** (signal parse): Agent emitted FEATURE_BUILT, SPEC_FILE, SOURCE_FILES. Files exist on disk.
- **EG3** (build check): `npx tsc --noEmit` or equivalent passes. 300s timeout.
- **EG4** (test check): `npm test` or equivalent passes. Test count extracted.
- **EG5** (commit auth): HEAD advanced from baseline, working tree clean, no test regression, no path escapes.

**ADVANCE**: Merge feature branch to main via `--no-ff`. Update resume state. Next feature.

## EG1 enforcement details

EG1 is the primary enforcement layer. The Python orchestrator owns all tool execution. The agent proposes tool calls; EG1 validates and executes them.

- **Path containment**: All file operations scoped to project root. No escapes.
- **Command validation**: 7-layer validation (blocklist, allowlist, path checks, branch protection, runtime awareness, npm/npx package allowlists, write-then-exec detection).
- **Tool translation**: Models that use wrong tool names (`listdir`, `cat`, `view_file`) get translated to the correct 3-tool schema.
- **cd stripping**: `cd <project> && cmd` stripped to `cmd` (run_command already has cwd).
- **Git chains**: `git add && git commit` split and executed sequentially.
- **Safe chains**: `find X && find Y` (read-only commands) split, validated, all executed.
- **Fallback stripping**: `cmd || fallback` runs primary only.
- **Test runner exemption**: vitest/jest/pytest/mocha exempt from write-then-exec.
- **Protected paths**: Test files discovered at baseline cannot be overwritten.
- **Runtime re-detection**: Writing package.json triggers runtime re-scan.

## Project structure

```
Auto_SDD_v2/
  config/models/           Model configs (YAML). Swap file to switch model.
    claude-sonnet.yaml       Claude Sonnet 4.6 via Anthropic API (current)
    gpt-oss-120b.yaml       GPT-OSS-120B via LM Studio (local, failed at compliance)
    qwen3-coder-next.yaml   Qwen3-Coder-Next via LM Studio (local, failed)
    glm-4.7-flash.yaml      GLM-4.7-flash via LM Studio (local, failed)
  py/
    auto_sdd/
      lib/
        model_config.py      ModelConfig dataclass, env var expansion
        local_agent.py       Agent loop (OpenAI + Anthropic), nudge, context trimming
        reliability.py       Resume state, file locking, campaign IDs
        branch_manager.py    Feature branches, merge, cleanup
        codebase_summary.py  Agent-generated project summary, git tree cache
      exec_gates/
        eg1_tool_calls.py    Tool call interception + validation + execution
        eg2_signal_parse.py  FEATURE_BUILT / SPEC_FILE / SOURCE_FILES extraction
        eg3_build_check.py   Build command subprocess
        eg4_test_check.py    Test command subprocess
        eg5_commit_auth.py   HEAD, tree clean, test regression, path escape
      pre_build/
        orchestrator.py      Pre-build phases 1-6
        phase_red.py         Gherkin to test scaffold (deterministic)
      scripts/
        build_loop_v2.py     Core loop: SELECT->BUILD->GATE->ADVANCE
    tests/                   422 tests
  docs/
    CHANGELOG.md             Decision lineage and change history
    SESSION-STATE.md         Current state and open items
    architectural-inventory.md  12-phase pipeline reference
```

## Setup

```bash
git clone https://github.com/fischmanb/Auto_SDD_v2.git
cd Auto_SDD_v2
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install anthropic pyyaml pytest
```

## Running

Set your API key and point at a project:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."

python -m auto_sdd.scripts.build_loop_v2 \
  --project-dir /path/to/your/project \
  --model-config config/models/claude-sonnet.yaml \
  --pre-build \
  --auto-approve
```

The project needs:
- A roadmap at `.specs/roadmap.md` (markdown table with Name, Complexity, Dependencies, Domain columns)
- Feature specs in `.specs/features/` (one `.feature.md` per feature)
- A `package.json`, `pyproject.toml`, or equivalent (for runtime detection)

`--pre-build` runs phases 1-6 (vision, systems design, design system, roadmap, specs, test scaffolds). Skip on subsequent runs if specs haven't changed.

`--auto-approve` skips the preflight confirmation prompt.

### Resuming after interruption

Just release the lock and rerun:

```bash
rm -f /path/to/project/logs/.build-lock

python -m auto_sdd.scripts.build_loop_v2 \
  --project-dir /path/to/your/project \
  --model-config config/models/claude-sonnet.yaml \
  --auto-approve
```

Resume state in `logs/resume-state.json` tracks completed features. The loop picks up where it left off.

### Switching models

Model is a YAML config swap. Claude Sonnet 4.6 is the only model that has completed a full campaign. Local models (GPT-OSS-120B, Qwen3-Coder-Next, GLM-4.7-flash) all failed at tool-use compliance despite translation layers and behavioral enforcement.

## Key principles

- **P1**: Agent's only output is committed code. Tests run by orchestrator.
- **P2**: Agent cannot reach orchestrator. Path-contained sandbox.
- **P3**: Deterministic gates replace probabilistic judgment.
- **P4**: Agent proposes; gate disposes.
- **P8**: Fixes must generalize. Every bug fix evaluated against "will this class of failure recur?"

## Tests

```bash
cd Auto_SDD_v2
.venv/bin/python -m pytest py/tests/ -q
```

422 tests covering EG1 (112), EG2, EG3, EG4, EG5, integration, phase_red, codebase_summary, reliability, branch_manager, and local_agent.
