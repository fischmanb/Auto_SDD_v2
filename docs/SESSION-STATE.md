# Session State

> The single mandatory read for every new session.
> Overwritten each session to reflect current truth.
> Last updated: 2026-03-15 (session 7)

## Read order

1. This file
2. `architectural-inventory.md` — 12-phase pipeline reference
3. `architecture-principles.md` — P1–P7, DP-1, DP-2

Read code files only when working on them. Don't front-load 2000 lines of Python you won't touch.

## What exists and works

### Build loop (`py/auto_sdd/scripts/build_loop_v2.py`, ~970 lines)
- SELECT → BUILD → GATE → ADVANCE, end-to-end functional
- Roadmap parser now uses shared `_parse_roadmap_table()` from `validators.py`, then does its own topo sort
- Unified `_run_gate()` with `GateResult` dataclass, short-circuits on first failure
- Retry logic: attempt 0 = fix-in-place, attempt 1+ = git reset
- Campaign locking (fcntl.flock + PID stale detection) and resume state (skip completed features on crash recovery)
- Feature branches: setup from main, merge on success, delete on failure, post-campaign cleanup
- Codebase summary generated once per campaign, injected into all feature prompts
- Preflight summary printed to terminal, `--auto-approve` flag (default: require confirmation)
- CLI: `--pre-build`, `--vision-input`, `--auto-approve` / `AUTO_APPROVE`

### Pre-build phases (`py/auto_sdd/pre_build/`, new)
| Module | Phase | Lines | What it does |
|---|---|---|---|
| `validators.py` | all | 412 | Deterministic validators for phases 1-6. Shared `_parse_roadmap_table()` also used by build loop. |
| `prompts.py` | 1-5 | 202 | System/user prompt templates per phase |
| `runner.py` | 1-5 | 152 | Shared agent invocation + validate + retry pattern |
| `phase_vision.py` | 1 | 29 | Generates `.specs/vision.md` from user input |
| `phase_systems.py` | 2 | 31 | Generates `.specs/systems-design.md` from vision |
| `phase_design.py` | 3 | 31 | Generates `.specs/design-system/tokens.md` from vision |
| `phase_roadmap.py` | 4 | 28 | Generates `.specs/roadmap.md` from vision |
| `phase_spec.py` | 5 | 119 | Generates `.feature.md` per pending roadmap feature |
| `phase_red.py` | 6 | 272 | Deterministic Gherkin→test scaffold generator (no agent) |
| `orchestrator.py` | all | 101 | Runs phases 1→6 sequentially, skips valid outputs (resume) |

### Shared types (`py/auto_sdd/lib/types.py`, new)

### Operational infrastructure (`py/auto_sdd/lib/`, new)
| Module | Lines | What it does |
|---|---|---|
| `reliability.py` | 202 | Campaign locking (fcntl.flock + PID stale detection), ResumeState persistence (atomic write via tempfile+rename), read/write/clean state, new_campaign_id |
| `branch_manager.py` | 173 | Feature branch setup from main, merge (--no-ff) on success, force-delete on failure, cleanup_merged_branches post-campaign |
| `codebase_summary.py` | 265 | File tree generation (excluded dirs per L-00227), git tree hash cache, agent-generated structural summary, recent learnings reader |

### Shared types (`py/auto_sdd/lib/types.py`)
- `GateError(code, detail)` — structured error type. Tests assert on `code` (stable contract), `detail` is free-form.
- `PhaseResult(phase, passed, errors, artifacts)` — result type for pre-build phases.
- Existing EG modules still use `list[str]` for errors — migration is separate work (~25 call sites, ~15 test assertions).

### ExecGates (AgentSpec lineage — deterministic, agent-opaque, binary)
| EG | Module | Trigger | Status |
|---|---|---|---|
| EG1 | `eg1_tool_calls.py` (827 lines) | `before_action` per tool call | All 7 checks reviewed+hardened, protected_paths support added |
| EG2 | `eg2_signal_parse.py` (215 lines) | `agent_finish` | Reviewed — code block skip, spec content check, SOURCE_FILES disk validation added |
| EG3 | `eg3_build_check.py` (155 lines) | `agent_finish` artifact | v1 detection ported, full framework coverage |
| EG4 | `eg4_test_check.py` (185 lines) | `agent_finish` artifact | v1 detection ported, 6 framework parsers |
| EG5 | `eg5_commit_auth.py` (216 lines) | `agent_finish` state | Reviewed — 4 checks assessed, untracked file warning added |
| EG6 | reserved | `agent_finish` artifact+compliance | Design not started. Deterministic only. |

### Other completed work
- `model_config.py`, `local_agent.py`, YAML configs (step 1)
- `validate_tool_calling.py` — validated on Mac Studio, 14/15 pass (step 2)
- `module-map.md` — v1 function classification (step 3)
- `system-inventory.md` — codebase metrics + evaluation framework

## EG review status

Review protocol: for each check, state logic → classify (A/B/C) → identify gaps → decide (fix/defer/accept) → smoke test.

### EG1 — reviewed checks:
1. ✅ Command blocklist + first-token matching (26 tests)
2. ✅ Command allowlist, stack-aware (42 tests)
3. ✅ Path validation + containment (32 tests)
4. ✅ Command argument containment (32 tests)
5. ✅ Git branch protection (42 tests)
6. ✅ Unknown tool rejection — hardcoded else clause, sound (82 tests total)
7. ✅ Malformed argument rejection — added isinstance(str) checks on path for write_file + read_file (82 tests total)

### EG1 — not yet reviewed:
(none — all 7 checks reviewed)

### EG2 — reviewed:
1. ✅ Signal in code blocks — was matching inside fenced code blocks. Added ``` tracking, lines inside blocks skipped. 3 new tests.
2. ✅ SPEC_FILE content validation — now checks >25 chars (stripped). Empty/placeholder specs fail the gate. 3 new tests. Pre-build phases 1–5 generate specs; phase 6 scaffolds tests.
3. ✅ SOURCE_FILES disk validation — now gate-fails if any listed file doesn't exist or resolves outside project. Triggers retry. 3 new tests.

### EG3/EG4 — reviewed (v1 port complete):
- EG3: `detect_build_cmd()` ported from v1 with full framework detection (Next.js priority per L-00177, tsconfig.build.json, tsconfig.json, pyproject/setup.py, Cargo.toml, go.mod, package.json). 14 detection tests.
- EG4: `detect_test_cmd()` ported from v1 (package.json with "no test specified" filter, pytest.ini, pyproject.toml, setup.cfg, Cargo.toml, go.mod). 13 detection tests.
- EG4: `_parse_test_count` expanded with mocha (`N passing`), cargo test (`test result:...N passed`), go verbose (`--- PASS:` line counting). 7 new parse tests.
- Build loop stubs (`_detect_build_cmd`, `_detect_test_cmd`) removed, replaced with imports from EG modules.

### EG5 — reviewed:
1. ✅ HEAD advanced — sound. Amend-to-same-hash impossible (new hash always). Empty commits caught by EG3/EG4.
2. ✅ Tree clean — was silently ignoring untracked files. Added warning log. Gate still passes (untracked may be legitimate).
3. ✅ No contamination — sound. Defense-in-depth with EG1 path checks. Catches symlink escapes.
4. ✅ Test regression — count comparison works as implemented. Resolved: test files are write-protected via EG1 `protected_paths`.

### Unit test coverage
| Test file | Module | Tests |
|---|---|---|
| test_eg1.py | eg1_tool_calls.py | 88 |
| test_eg2.py | eg2_signal_parse.py | 24 |
| test_eg3.py | eg3_build_check.py | 24 |
| test_eg4.py | eg4_test_check.py | 31 |
| test_eg5.py | eg5_commit_auth.py | 19 |
| test_model_config.py | model_config.py | 9 |
| test_validators.py | pre_build/validators.py | 42 |
| test_phase_red.py | pre_build/phase_red.py | 30 |
| test_local_agent.py | local_agent.py | 31 |
| test_integration.py | cross-module integration | 41 |
| test_reliability.py | reliability.py | 20 |
| test_branch_manager.py | branch_manager.py | 16 |
| test_codebase_summary.py | codebase_summary.py | 23 |

## Open items

### Design work needed (no code exists)
- ~~RED phase scaffolder (phase 6)~~ — **Done**: `phase_red.py` (deterministic Gherkin→test generator, pytest + vitest, format-agnostic parser, 30 tests)
- EG6 spec adherence checker: which metadata fields are checkable, scoring model
- Build loop metrics (phases 7–12): all blank in `architectural-inventory.md`
- Structured error types: replace `errors: list[str]` with `errors: list[GateError]` across EG2, EG5, GateResult. ~25 call sites, ~15 test assertions. New pre-build code uses `GateError` natively; EG migration remains. Est. 2–3 hours.

### Pre-build known issues
- `runner.py` duplicates `BUILD_AGENT_TOOLS` array from `build_loop_v2.py`. Should be a single constant imported by both.
- `phase_spec.py` re-scans roadmap text line by line to extract domain because `_parse_roadmap_table()` doesn't return it. Parser should add domain to its return dict.
- Orchestrator skip logic is inverted readability: `validate_X()` returning empty list means valid/skip. Could confuse a reader.
- `prompts.py` templates are first-draft. Need tuning once an agent runs against them in real inference.
- No tests for `runner.py`, `orchestrator.py`, or phase 1-5 wrappers. All depend on `run_local_agent` which needs the OpenAI client mock (pattern now established in `test_local_agent.py`).

### V1 port steps remaining
| Step | What | Notes |
|---|---|---|
| 6a | Unit tests for EGs + model_config + local_agent | **Done**. EG1–EG5 + model_config + local_agent all covered. 284 tests total. |
| 6b | Integration tests | **Done**. 41 tests: BuildLoopV2 end-to-end (9), gate pipeline short-circuit (4), EG1 executor (5), roadmap parsing (5), test file discovery (3), EG2 disk validation (3), EG3/EG4 subprocess (5), EG5 git state (3), config/limits (4). 325 tests total. |
| 7a | reliability.py — resume state, locking | **Done**. fcntl.flock + PID stale detection, ResumeState, atomic write. Wired into build loop (lock/resume/clean). 20 tests. |
| 7b | branch_manager.py — feature branches, cleanup | **Done**. setup_feature_branch, merge_feature_branch, delete, cleanup_merged. allowed_branch wired to EG1. 16 tests. |
| 7c | build_gates.py → EG3/EG4 | **Done**: detect_build_cmd, detect_test_cmd ported; _parse_test_count expanded (mocha, cargo, go); build loop stubs removed. 24+31 tests. |
| 7d | prompt_builder.py — fix/retry variants | Deferred. Current inline prompts sufficient for first campaign. Tune after real run. |
| 7e | codebase_summary.py — agent summary, git tree cache | **Done**. File tree + cache + learnings + agent call. Preflight summary with --auto-approve. 23 tests. |

All v1 modules that referenced `claude_wrapper.py` or agent-reported results need adaptation for V2 architecture (P1: orchestrator runs tests, P4: tool calls through EG1).

### Design questions (undecided)
1. ~~Test content integrity~~ — **Resolved**: test files are write-protected via EG1 `protected_paths`. Agent cannot modify or delete them. EG5 count check remains as defense-in-depth.
2. ~~EG1 tool set extensibility~~ — **Resolved**: keep hardcoded {write_file, read_file, run_command}. Three tools cover any file-based build task. New tools require new EG1 validation code, not config. The else-clause rejection of unknown tools is a strength.
3. ~~Agent prompt awareness of EG constraints~~ — **Resolved**: reveal boundaries, conceal mechanism. System prompt tells the agent what it can do (writable paths, allowed commands) but not how EG1 validates. Reduces wasted tool calls without exposing internals.

## GPT-OSS implementation constraints (V1 port)

Model choice: **gpt-oss-120b** — selected for Harmony instruction hierarchy (system > developer > user > assistant > tool), a trained-in conflict resolution order unique to this model. No other competitive open-weight model has an equivalent. Evaluated against Qwen3-Coder-Next (stronger coding benchmarks, no hierarchy). Decision: Harmony's architectural enforcement properties outweigh unquantified coding gap. Re-evaluate with empirical data after first campaign.

V1 port items must account for:
- **7d (prompt_builder.py)**: Deferred. Current inline prompts sufficient for first campaign. Use `developer` role for orchestrator instructions, `user` role for task content when implemented.
- **7e (codebase_summary.py)**: **Done**. Budget concern noted — exclude SDD metadata from summaries (handled via _EXCLUDED_DIRS).
- **7a, 7b (reliability.py, branch_manager.py)**: **Done**. Model-agnostic.
- **local_agent.py** already handles: reasoning_content stripping (older turns), parallel tool call defense (sequential processing + warning), finish_reason routing (stop/tool_calls/length), defensive JSON parsing. 31 tests cover these paths.
- Serving: LM Studio on Mac Studio M3 Ultra 256GB at localhost:1234. Model ID: gpt-oss-120b-mlx.

## Key decisions in effect
- Pre-build test generation: Response B (structured Gherkin → deterministic scaffolding). No LLM in verification. Response A (LLM-authored frozen tests) eliminated as DP-2 adjacent.
- GATE short-circuits on first failure (Option A). No flat run of all checks.
- ExecGates are an expansion of AgentSpec (Wang et al., arXiv:2503.18666). Same pattern: trigger at agent boundary → deterministic predicate → binary enforce.
- Gherkin/RED cycle restored from Adrian's auto-sdd. Implemented in `phase_red.py` (deterministic generator, no agent).
- Structured error types (`GateError`) adopted for all new code; existing EG migration deferred.
- EG1 tool set: hardcoded {write_file, read_file, run_command}. New tools require new EG1 code, not config.
- Agent model: gpt-oss-120b via LM Studio (localhost:1234). Harmony format, `developer` role for orchestrator instructions. Re-evaluate Qwen3-Coder-Next after first campaign with empirical data.
- Agent prompt: reveal boundaries (writable paths, allowed commands), conceal mechanism (EG1 internals).
- P8: fixes must generalize. Every bug fix evaluated against "will this class of failure recur?" Instance fixes are incomplete.
- Gherkin parser: format-agnostic keyword extraction. No assumptions about LLM formatting.
- Roadmap dep matching: 3-tier fuzzy resolution (exact → normalized → token subset). Models don't write dep names precisely.
- EG1 runtime re-detection: writing a marker file (package.json, pyproject.toml, etc.) triggers re-scan. Handles project bootstrapping.
- 7d (prompt_builder.py) deferred: current inline prompts sufficient for first campaign. Tune fix/retry variants after real failure data.

## References
- `docs/architectural-inventory.md` — 12-phase pipeline
- `docs/architecture-principles.md` — P1–P7, DP-1, DP-2
- `docs/module-map.md` — v1 function classification
- `docs/system-inventory.md` — codebase metrics
- `docs/CHANGELOG.md` — decision lineage and change history
- Adrian's SDD repo: https://github.com/AdrianRogowski/auto-sdd
- Local clone: `/Users/sorel/adrian-auto-sdd/CLAUDE.md`
