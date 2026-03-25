# Auto-SDD V2

Automated software development pipeline. LLM agents implement features from a roadmap in a topologically sorted build loop with deterministic enforcement gates. No LLM-as-judge. No probabilistic evaluation.

## What it does

Given a project with a roadmap of features and specs, Auto-SDD V2:

1. **Pre-build** (phases 1-6): Generates vision, systems design, design system, personas, design patterns, roadmap, feature specs, and test scaffolds from a user-provided description
2. **Build loop**: Topologically sorts features by dependency, creates a branch per feature, invokes a build agent, validates through six deterministic gates, and merges to main
3. **Knowledge capture**: Records gate failures into a graph database, promotes learnings through injection/outcome tracking, and feeds hardened clues back into future builds
4. **Parallel builds** (v2.2): Groups features by dependency level and builds independent features concurrently in git worktrees

The build agent writes code, runs builds, runs tests, commits, and emits completion signals. The orchestrator validates everything mechanically.

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

## Design principles

### Core principles (P1-P8)

- **P1: Agent's only output is committed code.** The agent writes files, runs commands, and commits. Everything after — test execution, build verification, signal validation — is the orchestrator's job. Agents self-report inaccurately; IFEval-style instruction following drops to ~36% on production-like constraints.
- **P2: Agent cannot reach the orchestrator.** Orchestrator and target project live in separate directory trees. All tool calls are path-contained to `project_root`. The agent cannot read ExecGate source, modify orchestrator code, or access files outside the project.
- **P3: Deterministic gates replace probabilistic judgment.** Every verification step that can be expressed as deterministic code must be. Agent judgment is reserved for genuinely creative tasks (writing implementation code).
- **P4: Agent proposes; gate disposes.** Every tool call is a request that passes through EG1 before execution. The gate validates, then either executes or rejects.
- **P5: Stack awareness is derived, not assumed.** Runtime commands are derived from project manifests (`package.json` → node, `pyproject.toml` → python, `Cargo.toml` → rust). Allowlists are immutable for the session.
- **P6: Extensions are stripped, not commented.** Features not on the core path are deleted, not commented out. Commented-out code is dead code that misleads readers.
- **P7: LLM judgment is irreducible in implementation.** Someone must decide what code to write. That decision is inherently LLM judgment. Deterministic gates catch everything mechanical, but the gap between "compiles and passes tests" and "actually implements the spec" requires judgment.
- **P8: Fixes must generalize.** Every bug fix evaluated against "will this class of failure recur?" If yes, the fix must address the class, not the instance.

### Design-level principles (DP-1, DP-2)

- **DP-1: No manual intervention.** The critical path — from "next pending feature" to "feature committed" — runs without human intervention. Humans author specs, configure the system, review campaign results, and improve the process.
- **DP-2: No LLM judgment in verification.** Verification and gating must be deterministic Python. LLM judgment in the verification path reintroduces the compliance band problem (~36% ceiling on production-like constraints).

## Architecture

```
PRE-BUILD → SELECT → BUILD → GATE → ADVANCE
```

**PRE-BUILD** (phases 1-6): Vision → systems design → design system + personas (parallel) → design patterns → roadmap → feature specs → test scaffolds (deterministic, no LLM).

**SELECT**: Parse roadmap, topo-sort by deps, skip features whose deps failed, build system+user prompts with spec path, codebase summary, knowledge injection, and previous error context (on retry).

**BUILD**: Fresh agent context per feature. Agent has three tools: `write_file`, `read_file`, `run_command`. Every tool call passes through EG1 before execution. Agent writes code, runs builds/tests, commits, emits `FEATURE_BUILT` signal.

**GATE**: Six deterministic checks, short-circuit on first failure:

```
EG1 (tool calls)     — inline during BUILD
EG2 (signal parse)   → EG3 (build) → EG4 (tests) → EG5 (commit auth) → EG6 (spec adherence)
```

**ADVANCE**: Merge feature branch to main via `--no-ff`. Update resume state. Refresh codebase summary. Next feature.

## Enforcement gates (EG1-EG6)

### EG1: Tool call interception

Primary enforcement layer. The Python orchestrator owns all tool execution. The agent proposes tool calls; EG1 validates and executes them.

- **Path containment**: All file operations scoped to project root. No escapes.
- **Command validation**: 7-layer validation — first-token blocklist, recursive rm detection, shell injection patterns, blocked tokens, git subcommand allowlist, npm/npx package scope, base command allowlist.
- **Tool translation**: Models using wrong tool names (`listdir`, `cat`, `view_file`) get translated to the correct 3-tool schema.
- **cd stripping**: `cd <project> && cmd` stripped to `cmd` (run_command already has cwd).
- **Git chains**: `git add && git commit` split and executed sequentially.
- **Safe chains**: `find X && find Y` (read-only commands) split, validated, all executed.
- **Fallback stripping**: `cmd || fallback` runs primary only.
- **Test runner exemption**: vitest/jest/pytest/mocha exempt from write-then-exec detection.
- **Protected paths**: Test files discovered at baseline cannot be overwritten.
- **Runtime re-detection**: Writing `package.json` triggers runtime re-scan.

### EG2: Signal parse

Extracts required signals from agent output. No agent self-assessment accepted.

- `FEATURE_BUILT` present, non-empty, matches expected feature name
- `SPEC_FILE` exists on disk within project root with >25 characters
- All `SOURCE_FILES` exist on disk within project root
- Signals inside code blocks (`` ``` ``) ignored to prevent false positives

### EG3: Build check

Orchestrator-side build verification. 300s timeout.

- Auto-detects build command by runtime: Next.js → `npm run build`, TypeScript → `npx tsc --noEmit`, Python → `py_compile`, Rust → `cargo check`, Go → `go build ./...`
- Next.js detection precedes generic TypeScript because `tsc --noEmit` misses server/client boundary violations

### EG4: Test check

Orchestrator-side test verification. 300s timeout.

- Auto-detects test command: Node.js → `npm test`, Python → `pytest`, Rust → `cargo test`, Go → `go test ./...`
- Parses test count from framework output (Jest/Vitest, Mocha, Pytest, Cargo, Go)

### EG5: Commit auth

Final state-level check before merge. Four deterministic checks:

1. **HEAD_ADVANCED**: HEAD moved past baseline commit
2. **TREE_CLEAN**: No uncommitted tracked changes (untracked files warn only)
3. **NO_CONTAMINATION**: No files modified outside project root
4. **TEST_REGRESSION**: Test count did not decrease below baseline

### EG6: Spec adherence

Post-build static analysis validating structural adherence to spec and systems-design metadata. All checks are deterministic Python — no LLM involvement. Runs after EG2-EG5 pass.

1. **SOURCE_MATCH**: `SOURCE_FILES` signal matches files actually changed in git diff
2. **FILE_PLACEMENT**: New files placed in directories matching `systems-design.md` directory structure
3. **TOKEN_EXISTENCE**: Design tokens referenced in code exist in `tokens.md` (scans Tailwind-style classes in .tsx/.jsx/.ts/.js/.css/.html)
4. **NAMING_CONVENTION**: React components use PascalCase, Python modules use snake_case, per `systems-design.md`

**Default mode**: warn-only (logs deviations but doesn't block builds). Use `--eg6-enforce` to block on failures.

## Pre-build pipeline

Six phases transform a user-provided description into build-ready specs and test scaffolds.

| Phase | Name | Input | Output |
|-------|------|-------|--------|
| 1 | Vision | User description | `.specs/vision.md` |
| 2 | Systems Design | Vision (tech stack, screens) | `.specs/systems-design.md` |
| 3 | Design System | Vision (personality, users) | `.specs/design-system/tokens.md` |
| 3b | Personas | Vision + tokens | `.specs/personas.md` |
| 3c | Design Patterns | Vision + tokens + personas | `.specs/design-system/patterns.md` |
| 4 | Roadmap | Vision (screens, tech stack) | `.specs/roadmap.md` |
| 5 | Spec-First | Roadmap + vision + tokens + systems | `.specs/features/{domain}/{feature}.feature.md` |
| 6 | Red (Test Scaffolds) | Feature specs (Gherkin) | Test files in project test directory |

- Phases 3 and 3b run **in parallel** (both depend only on vision + systems design)
- Phase 3c waits for both to complete
- Phase 6 is **deterministic Python** — no agent, no LLM. Converts Given/When/Then steps to test structure
- Each phase validates output deterministically before proceeding
- Resume-safe: completed phases are skipped on rerun

## Knowledge system

SQLite-backed graph database that captures gate failures, promotes learnings through injection/outcome tracking, and feeds hardened clues into future builds.

### Architecture

- **Store** (`knowledge_system/store.py`): SQLite + FTS5 full-text search. Node types: `universal`, `framework`, `technology`, `mistake`, `instance`, `meta`. Scored by type weight × status × recency decay (0.995^days).
- **Schema**: Tables for `nodes`, `edges`, `outcomes`, `fts_nodes`. Edge types include `learns_from`, `refines`, `contradicts`, `supports`, `similar_to`.
- **Build integration** (`build_integration.py`): Three injection points — hardened clues in system prompt (1000 token budget), relevant knowledge in user prompt (2000 tokens), spec learnings in spec prompt (500 tokens). All functions are None-safe.
- **Promotion** (`promotion.py`): Deterministic SQL-based promotion pipeline. `active` → `promoted` (≥1 injection with positive outcome) → `hardened` (≥3 successes with positive lift). No LLM in promotion logic (DP-2 compliant).
- **Migration** (`migration.py`): Imports historical markdown learnings into the graph. Idempotent.

### How it works

1. Gate failures (EG2-EG6) create `mistake` nodes with error pattern, gate name, campaign ID
2. Feature specs + error patterns queried via FTS with 16 synonym groups
3. Top-K results injected into agent prompts for next build attempt
4. Outcomes tracked per injection; positive lift promotes nodes through status hierarchy

## V2.2 parallel builds

Groups features by dependency level and builds independent features concurrently in git worktrees.

### Three-phase architecture

**Phase 1: BUILD (parallel in worktrees)**
- `_group_by_dep_level()` assigns features to levels: level 0 = no deps, level N = all deps in levels 0..N-1
- Multi-feature levels run in `ThreadPoolExecutor` with one worktree per feature
- Each agent gets an isolated filesystem via `git worktree add`
- EG1 enforces `readonly_paths` (existing `src/` files) to prevent scope collisions
- EG2 + EG5 run in worktree; EG3 + EG4 deferred to post-merge

**Phase 2: MERGE + POST-MERGE GATES (sequential on main)**
- For each successful worktree build: `git merge --no-ff`, then run EG3 (build) + EG4 (tests)
- On EG3/EG4 failure: `git reset` to pre-merge commit, add to retry list
- Codebase summary refreshed after each merge for subsequent features

**Phase 3: RETRY (sequential on main)**
- Failed features retried with full gate pipeline on main
- Treated as normal single-feature build from that point

### Results

- Sequential: 15 features in ~87 min
- Parallel (v2.2): 14 features in ~49 min (agent time parallelized, merge + gates sequential)

## Project structure

```
Auto_SDD_v2/
  config/models/              Model configs (YAML)
    claude-sonnet.yaml          Claude Sonnet 4.6 via Anthropic API (current)
    gpt-oss-120b.yaml           GPT-OSS-120B via LM Studio (local, failed)
    qwen3-coder-next.yaml       Qwen3-Coder-Next via LM Studio (local, failed)
    glm-4.7-flash.yaml          GLM-4.7-flash via LM Studio (local, failed)
  py/
    auto_sdd/
      lib/
        model_config.py         ModelConfig dataclass, env var expansion
        local_agent.py          Agent loop (OpenAI + Anthropic), nudge, context trimming
        reliability.py          Resume state, file locking, campaign IDs
        branch_manager.py       Feature branches, merge, cleanup
        codebase_summary.py     Agent-generated project summary, git tree cache
      exec_gates/
        eg1_tool_calls.py       Tool call interception + validation + execution
        eg2_signal_parse.py     Signal extraction (FEATURE_BUILT, SPEC_FILE, SOURCE_FILES)
        eg3_build_check.py      Build command subprocess
        eg4_test_check.py       Test command subprocess
        eg5_commit_auth.py      HEAD, tree clean, test regression, path escape
        eg6_spec_adherence.py   Spec adherence static analysis (SOURCE_MATCH, FILE_PLACEMENT, TOKEN_EXISTENCE, NAMING_CONVENTION)
      pre_build/
        orchestrator.py         Pre-build phases 1-6
        runner.py               Shared agent runner for phases 1-5
        phase_vision.py         Phase 1: Vision
        phase_systems.py        Phase 2: Systems design
        phase_design.py         Phase 3: Design system
        phase_personas.py       Phase 3b: Personas
        phase_design_patterns.py Phase 3c: Design patterns
        phase_roadmap.py        Phase 4: Roadmap
        phase_spec.py           Phase 5: Feature specs
        phase_red.py            Phase 6: Test scaffolds (deterministic, no LLM)
        validators.py           Deterministic output validators
      knowledge_system/
        store.py                SQLite + FTS5 graph database
        build_integration.py    Injection helpers for build loop
        schema.py               Database schema initialization
        promotion.py            Deterministic promotion pipeline
        migration.py            Markdown → SQLite import
      scripts/
        build_loop_v2.py        Core loop: SELECT→BUILD→GATE→ADVANCE
    tests/                      674 tests across 20 test files
  docs/
    CHANGELOG.md                Decision lineage and change history
    SESSION-STATE.md            Current state and open items
    architecture-principles.md  P1-P8, DP-1, DP-2 reference
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

### Flags

| Flag | Description |
|------|-------------|
| `--pre-build` | Run phases 1-6 before build loop. Skip on subsequent runs if specs haven't changed. |
| `--auto-approve` | Skip preflight confirmation prompt. |
| `--eg6-enforce` | Enable EG6 spec adherence enforcement (default: warn-only). |
| `--build-cmd CMD` | Override auto-detected build command. |
| `--test-cmd CMD` | Override auto-detected test command. |
| `--max-retries N` | Max retry attempts per feature (default: 2). |

### Resuming after interruption

Release the lock and rerun:

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

## Tests

```bash
cd Auto_SDD_v2
.venv/bin/python -m pytest py/tests/ -q
```

674 tests across 20 files covering EG1-EG6, integration, pre-build phases, knowledge system, codebase summary, reliability, branch manager, and local agent.
