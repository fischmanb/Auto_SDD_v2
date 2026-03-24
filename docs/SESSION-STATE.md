# Session State

> The single mandatory read for every new session.
> Overwritten each session to reflect current truth.
> Last updated: 2026-03-24 (session 13)

## Read order

1. This file
2. `architectural-inventory.md` — 12-phase pipeline reference
3. `architecture-principles.md` — P1–P8, DP-1, DP-2

Read code files only when working on them. Don't front-load 2000 lines of Python you won't touch.

## Active development: Auto_SDD_v2.2

V2.2 lives at `/Users/BrianFischman/Auto_SDD_v2.2/`. It is a fork of v2 (`/Users/BrianFischman/Auto_SDD_v2/`) with parallel feature build support. V2.2 has uncommitted changes across 5 files — not yet merged back. V2 remains the canonical repo for docs (CHANGELOG, SESSION-STATE). V2.2 has no `.venv`; runs via `PYTHONPATH` pointing at v2.2's `py/` using v2's venv interpreter.

Run command: `bash /Users/BrianFischman/Auto_SDD_v2.2/run_build.sh`

## What exists and works

### Build loop (`py/auto_sdd/scripts/build_loop_v2.py`)
- SELECT → BUILD → GATE → ADVANCE, end-to-end functional
- **Parallel builds (v2.2)**: Features grouped by dep level. Same-level features build concurrently in git worktrees. Three-phase flow:
  1. Parallel BUILD in worktrees (EG1+EG2+EG5 only, `skip_build_test=True`)
  2. Sequential MERGE+GATE on main (EG3+EG4 post-merge, revert on fail)
  3. Sequential retry on main for post-merge failures (full gates)
- Single-feature levels use the original sequential path (no worktree overhead)
- `_group_by_dep_level()` groups topo-sorted features into parallelizable levels
- Roadmap parser uses shared `_parse_roadmap_table()` from `validators.py`, then does its own topo sort
- Unified `_run_gate()` with `GateResult` dataclass, short-circuits on first failure
- Retry logic: attempt 0 = fix-in-place, attempt 1+ = git reset
- Campaign locking (fcntl.flock + PID stale detection) and resume state
- Feature branches: setup from main, merge on success, delete on failure, post-campaign cleanup
- Worktree support: `setup_feature_worktree`, `link_deps_to_worktree`, `remove_worktree` in `branch_manager.py`
- Codebase summary generated once per campaign, injected into all feature prompts
- Preflight summary printed to terminal, `--auto-approve` flag
- CLI: `--pre-build`, `--pre-build-only`, `--vision-input`, `--auto-approve` / `AUTO_APPROVE`

### Pre-build phases (`py/auto_sdd/pre_build/`)
| Module | Phase | Lines | What it does |
|---|---|---|---|
| `validators.py` | all | ~535 | Deterministic validators for phases 1-6. Shared `_parse_roadmap_table()` also used by build loop. |
| `prompts.py` | 1-5 | ~344 | System/user prompt templates per phase. Hardened phase 5 with token assertion requirement, interaction_states, personas/patterns inputs. |
| `runner.py` | 1-5 | 152 | Shared agent invocation + validate + retry pattern |
| `phase_vision.py` | 1 | 29 | Generates `.specs/vision.md` from user input |
| `phase_systems.py` | 2 | 31 | Generates `.specs/systems-design.md` from vision |
| `phase_design.py` | 3 | 31 | Generates `.specs/design-system/tokens.md` from vision |
| `phase_personas.py` | 3b | 35 | Generates `.specs/personas.md` from vision + tokens |
| `phase_design_patterns.py` | 3c | 39 | Generates `.specs/design-system/patterns.md` from vision + tokens + personas |
| `phase_roadmap.py` | 4 | 28 | Generates `.specs/roadmap.md` from vision |
| `phase_spec.py` | 5 | 119 | Generates `.feature.md` per pending roadmap feature |
| `phase_red.py` | 6 | 272 | Deterministic Gherkin→test scaffold generator (no agent) |
| `orchestrator.py` | all | ~144 | Runs phases 1→3→3b→3c→4→5→6 sequentially, skips valid outputs (resume) |

### Operational infrastructure (`py/auto_sdd/lib/`)
| Module | Lines | What it does |
|---|---|---|
| `reliability.py` | 202 | Campaign locking (fcntl.flock + PID stale detection), ResumeState persistence (atomic write via tempfile+rename) |
| `branch_manager.py` | ~250 | Feature branch setup, merge (--no-ff + --abort on conflict), force-delete, cleanup. **v2.2**: worktree support (`setup_feature_worktree`, `link_deps_to_worktree`, `remove_worktree`). |
| `codebase_summary.py` | 265 | File tree generation (excluded dirs), git tree hash cache, agent-generated structural summary |
| `local_agent.py` | — | OpenAI + Anthropic agent loops. `keep_recent=8` for context trimming (bumped from 2 in session 9). |

### Shared types (`py/auto_sdd/lib/types.py`)
- `GateError(code, detail)` — structured error type. Tests assert on `code` (stable contract), `detail` is free-form.
- `PhaseResult(phase, passed, errors, artifacts)` — result type for pre-build phases.
- `WorktreeResult(branch_name, worktree_path)` — v2.2 worktree setup result.

### ExecGates (AgentSpec lineage — deterministic, agent-opaque, binary)
| EG | Module | Trigger | Status |
|---|---|---|---|
| EG1 | `eg1_tool_calls.py` | `before_action` per tool call | All 7 checks reviewed+hardened. `protected_paths` (test files). **v2.2**: `readonly_paths` (existing source files in parallel builds). |
| EG2 | `eg2_signal_parse.py` | `agent_finish` | Reviewed — code block skip, spec content check, SOURCE_FILES disk validation. |
| EG3 | `eg3_build_check.py` | `agent_finish` artifact | v1 detection ported. **v2.2**: skippable via `skip_build_test`, runs post-merge instead. |
| EG4 | `eg4_test_check.py` | `agent_finish` artifact | v1 detection ported, 6 framework parsers. **v2.2**: same skip/defer as EG3. |
| EG5 | `eg5_commit_auth.py` | `agent_finish` state | Reviewed. **v2.2**: `_check_no_contamination` uses literal `..` check instead of `Path.resolve()` (symlink false positive fix). |
| EG6 | reserved | `agent_finish` artifact+compliance | Deferred. |

### Knowledge system (`py/auto_sdd_v2/knowledge_system/`)
| Module | Lines | What it does |
|---|---|---|
| `store.py` | ~600 | KnowledgeStore: SQLite-backed graph with FTS5. Nodes, edges, outcomes, promotion. DP-2 clean (no LLM in query/promote). |
| `build_integration.py` | ~310 | Injection helpers (3 points: system prompt, user prompt, spec prompt) + post-gate capture. All None-safe. |
| `promotion.py` | ~50 | Standalone CLI runner for promotion job. |
| `migration.py` | ~320 | Markdown → KnowledgeStore import. Idempotent. |

- **170 nodes, 127 edges** (migrated from learnings files). All active — promoted/hardened tiers populate as campaigns run.
- **Failure capture**: Gate failures → mistake nodes with error pattern + gate name. Queryable by FTS on retries.
- **Promotion pipeline**: active → promoted (≥1 successful injection) → hardened (≥3 successes + positive lift) → demoted if lift drops. All deterministic SQL.
- **Three injection points**: hardened clues → system prompt, relevant knowledge → user prompt, promoted learnings → spec prompt.

### Unit test coverage (~620 tests, all passing)
| Test file | Module | Tests |
|---|---|---|
| test_eg1.py | eg1_tool_calls.py | 112 |
| test_eg2.py | eg2_signal_parse.py | 24 |
| test_eg3.py | eg3_build_check.py | 24 |
| test_eg4.py | eg4_test_check.py | 31 |
| test_eg5.py | eg5_commit_auth.py | 19 |
| test_model_config.py | model_config.py | 9 |
| test_validators.py | pre_build/validators.py | ~62 |
| test_phase_red.py | pre_build/phase_red.py | 30 |
| test_local_agent.py | local_agent.py | 31 |
| test_integration.py | cross-module integration | 41 |
| test_reliability.py | reliability.py | 20 |
| test_branch_manager.py | branch_manager.py | 16 |
| test_codebase_summary.py | codebase_summary.py | 23 |
| test_knowledge_system/ | knowledge_system/ | 185 |

## Open items

### Code changes needed
- Structured error types: replace `errors: list[str]` with `errors: list[GateError]` across EG2, EG5, GateResult. ~25 call sites, ~15 test assertions.
- Auto-QA post-render validation (Playwright screenshots): v1 port item. Visual bugs that deterministic code analysis cannot catch.
- `runner.py` duplicates `BUILD_AGENT_TOOLS` from `build_loop_v2.py`. Should be single constant.
- `phase_spec.py` re-scans roadmap for domain. Parser should add domain to return dict.
- No tests for `runner.py`, `orchestrator.py`, or phase 1-5 wrappers.
- V2.2 changes uncommitted — need to merge back or formalize v2.2 as the active repo.
- `test_count` is null across all campaign runs — either `test_cmd` empty/skip or parser mismatch. Not yet investigated.

## Campaign history

### V2 sequential: cre-pulse (session 7)
8/8 features, Claude Sonnet 4.6, ~90 min. Full dashboard renders at localhost:3000.

### V2.2 sequential baseline: cre-pulse-ab-v2 (session 9, 2026-03-17)
15/15 features, Claude Opus 4.6, 87 min. All `test_count` null.

### V2.2 parallel (first attempt): cre-pulse-ab-v2.2 (session 9, 2026-03-17)
Multiple failed runs. Root causes: EG3/EG4 ran per-worktree (no full project), EG5 symlink false positive, merge conflicts from scope collision (`page.tsx` written by multiple agents), Opus 500 errors.

### V2.2 parallel (post-fix): cre-pulse-ab-v2.2 (session 9, 2026-03-19)
14 features, Claude Sonnet 4.6, 49 min. 10/14 built. 3 failed (merge conflict cascade — `page.tsx` scope collision, before scope enforcement fix). 1 skipped (App Shell dep cascade). EG3/EG4 deferral and post-merge validation worked correctly. Scope enforcement (`readonly_paths` + prompt injection) applied after this run.

## Key decisions in effect

All session 7 decisions remain. Additions from sessions 9–13:

- **Parallel builds: deferred EG3/EG4**. Agents don't need the full project to write code. They need it to validate. Parallelize the expensive part (agent), validate sequentially after merge.
- **EG1 `readonly_paths`**: Parallel agents can only create new files. Existing source files are read-only. Prevents scope collisions (e.g. multiple agents writing `page.tsx`).
- **Prompt scope constraint**: When `readonly_paths` active, user prompt lists all read-only files with "writes will be rejected." Belt and suspenders with EG1 enforcement.
- **`git merge --abort` on conflict**: Prevents stale merge state from poisoning subsequent merges.
- **EG5 literal `..` check**: Replaced `Path.resolve()` with `..` traversal detection. EG1 blocks symlink creation; `resolve()` was causing false positives on orchestrator-created symlinks.
- **`keep_recent=8`**: Context trimming in `local_agent.py` bumped from 2 to 8. Agents read 5+ files before writing; aggressive trimming caused re-read loops.
- **Knowledge system: failure-based learning**. Mistake nodes from gate failures are the learning mechanism. Agent self-reported learnings (`LEARNING_CANDIDATE`) dropped — noisy and unreliable. Query, promotion, and injection are all deterministic SQL (DP-2 clean).

Prior session decisions still in effect (non-exhaustive, see CHANGELOG for full lineage):
- GATE short-circuits on first failure. ExecGates follow AgentSpec pattern (Wang et al., arXiv:2503.18666).
- Agent model: Claude Sonnet 4.6 via Anthropic API. Local models all failed tool-use compliance.
- EG1: hardcoded {write_file, read_file, run_command}. Tool call translation, cd stripping, git chain handling, safe && chains, runtime re-detection.
- P8: fixes must generalize. Instance fixes are incomplete.
- Dynamic turn budget: S = base, M = 1.5x, L/XL = 2x. Dep cascade skip. Project dep warmup.
- Cross-feature learning: blocked patterns injected into next feature's system prompt.
- Dep export scanner: injects import signatures into prompt. Cut Dashboard Shell from 60+ to 16 turns.
- Resume state is sacred. Don't nuke between runs.
- Pre-build pipeline: 1 → 2 → 3 → 3b → 3c → 4 → 5(hardened) → 6. Phase 5 enforces token assertions + interaction states.

## References
- `docs/architectural-inventory.md` — 12-phase pipeline (expanded: 3b personas, 3c design patterns)
- `docs/architecture-principles.md` — P1–P8, DP-1, DP-2
- `docs/module-map.md` — v1 function classification
- `docs/system-inventory.md` — codebase metrics
- `docs/CHANGELOG.md` — decision lineage and change history
- Adrian's SDD repo: https://github.com/AdrianRogowski/auto-sdd
- Local clone: `/Users/sorel/adrian-auto-sdd/CLAUDE.md`
