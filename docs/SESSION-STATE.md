# Session State

> The single mandatory read for every new session.
> Overwritten each session to reflect current truth.
<<<<<<< HEAD
> Last updated: 2026-03-24 (session 13, continued)
=======
> Last updated: 2026-03-17 (session 9)
>>>>>>> origin/main

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
- **Retry prompt includes**: gate error (smart-truncated to 5000 chars), git diff of previous changes, error-code-specific guidance, structured reflection
- **Stalled agent detection**: 2 nudges at 12-turn intervals → hard-stop if no writes
- Campaign locking (fcntl.flock + PID stale detection) and resume state
- Feature branches: setup from main, merge on success, delete on failure, post-campaign cleanup
- Worktree support: `setup_feature_worktree`, `link_deps_to_worktree`, `remove_worktree` in `branch_manager.py`
- **Codebase summary refreshed after each merge** — subsequent features see up-to-date project context
- **Per-feature metrics**: duration, turn_count, tool_call_count tracked in FeatureRecord and summary JSON
- Preflight summary printed to terminal, `--auto-approve` flag
- CLI: `--pre-build`, `--pre-build-only`, `--vision-input`, `--auto-approve` / `AUTO_APPROVE`

### Pre-build phases (`py/auto_sdd/pre_build/`)
| Module | Phase | Lines | What it does |
|---|---|---|---|
| `validators.py` | all | ~535 | Deterministic validators for phases 1-6. Shared `_parse_roadmap_table()` also used by build loop. |
| `prompts.py` | 1-5 | ~344 | System/user prompt templates per phase. Hardened phase 5 with token assertion requirement, interaction_states, personas/patterns inputs. |
| `runner.py` | 1-5 | ~180 | Shared agent invocation + validate + retry pattern. **Protected paths**: each phase's agent blocked from overwriting other phases' outputs. |
| `phase_vision.py` | 1 | 29 | Generates `.specs/vision.md` from user input |
| `phase_systems.py` | 2 | 31 | Generates `.specs/systems-design.md` from vision |
| `phase_design.py` | 3 | 31 | Generates `.specs/design-system/tokens.md` from vision |
| `phase_personas.py` | 3b | 35 | Generates `.specs/personas.md` from vision + tokens |
| `phase_design_patterns.py` | 3c | 39 | Generates `.specs/design-system/patterns.md` from vision + tokens + personas |
| `phase_roadmap.py` | 4 | 28 | Generates `.specs/roadmap.md` from vision |
| `phase_spec.py` | 5 | 119 | Generates `.feature.md` per pending roadmap feature |
| `phase_red.py` | 6 | 272 | Deterministic Gherkin→test scaffold generator (no agent) |
| `orchestrator.py` | all | ~170 | Runs phases 1→2→{3∥3b}→3c→4→5→6. **Phases 3+3b run in parallel** (ThreadPoolExecutor). Skips valid outputs (resume). |

### Operational infrastructure (`py/auto_sdd/lib/`)
| Module | Lines | What it does |
|---|---|---|
| `reliability.py` | 202 | Campaign locking (fcntl.flock + PID stale detection), ResumeState persistence (atomic write via tempfile+rename) |
| `branch_manager.py` | ~250 | Feature branch setup, merge (--no-ff + --abort on conflict), force-delete, cleanup. **v2.2**: worktree support (`setup_feature_worktree`, `link_deps_to_worktree`, `remove_worktree`). |
| `codebase_summary.py` | 265 | File tree generation (excluded dirs), git tree hash cache, agent-generated structural summary |
| `local_agent.py` | — | OpenAI + Anthropic agent loops. `keep_recent=8` for context trimming. **Stalled agent detection**: 2 nudges → hard-stop. |

### Shared types (`py/auto_sdd/lib/types.py`)
- `GateError(code, detail)` — structured error type used across all gate modules. Tests assert on `code` (stable contract), `detail` is free-form.
- `PhaseResult(phase, passed, errors, artifacts)` — result type for pre-build phases.
- `WorktreeResult(branch_name, worktree_path)` — v2.2 worktree setup result.

### ExecGates (SAGE gates — deterministic, agent-opaque, binary)
| EG | Module | Trigger | Status |
|---|---|---|---|
| EG1 | `eg1_tool_calls.py` | `before_action` per tool call | All 7 checks reviewed+hardened. `protected_paths` (test files). **v2.2**: `readonly_paths` (existing source files in parallel builds). |
| EG2 | `eg2_signal_parse.py` | `agent_finish` | `list[GateError]` errors. Code block skip, spec content check, SOURCE_FILES disk validation. **`expected_feature` validation** — FEATURE_BUILT must match feature being built. |
| EG3 | `eg3_build_check.py` | `agent_finish` artifact | v1 detection ported. Error capture raised to 2000 chars. **v2.2**: skippable via `skip_build_test`, runs post-merge instead. |
| EG4 | `eg4_test_check.py` | `agent_finish` artifact | v1 detection ported, 6 framework parsers. Error capture raised to 2000 chars. **v2.2**: same skip/defer as EG3. |
| EG5 | `eg5_commit_auth.py` | `agent_finish` state | `list[GateError]` checks. **v2.2**: literal `..` check instead of `Path.resolve()`. |
| EG6 | `eg6_spec_adherence.py` | `agent_finish` artifact+compliance | **Implemented.** 4 checks: SOURCE_MATCH, FILE_PLACEMENT, TOKEN_EXISTENCE, NAMING_CONVENTION. All deterministic. |

### Knowledge system (`py/auto_sdd_v2/knowledge_system/`)
| Module | Lines | What it does |
|---|---|---|
| `store.py` | ~650 | KnowledgeStore: SQLite-backed graph with FTS5. **Synonym expansion** (16 groups) in keyword extraction. Nodes, edges, outcomes, promotion. DP-2 clean (no LLM in query/promote). |
| `build_integration.py` | ~400 | Injection helpers: `inject_knowledge_combined()` (single query, partitioned client-side), `inject_relevant_knowledge()`, `inject_hardened_clues()`, `inject_spec_learnings()`. Post-gate capture. **Gate-specific reflection templates** for 6 gate types. All None-safe. |
| `promotion.py` | ~50 | Standalone CLI runner for promotion job. |
| `migration.py` | ~320 | Markdown → KnowledgeStore import. Idempotent. |

- **170 nodes, 127 edges** (migrated from learnings files). All active — promoted/hardened tiers populate as campaigns run.
- **Failure capture**: Gate failures → mistake nodes with error pattern + gate name. Queryable by FTS on retries.
- **Promotion pipeline**: active → promoted (≥1 successful injection) → hardened (≥3 successes + positive lift) → demoted if lift drops. All deterministic SQL.
- **Three injection points**: hardened clues → system prompt, relevant knowledge → user prompt, promoted learnings → spec prompt.
- **Combined query**: `inject_knowledge_combined()` does one DB round-trip instead of two.
- **Synonym expansion**: FTS keyword extraction expands terms using 16 synonym groups (import↔module↔resolve, build↔compile↔tsc, etc.).

### Unit test coverage (~740 tests, 354 verified passing in this session)
| Test file | Module | Tests |
|---|---|---|
| test_eg1.py | eg1_tool_calls.py | 112 |
<<<<<<< HEAD
| test_eg2.py | eg2_signal_parse.py | 27 (+3 feature name validation) |
| test_eg3.py | eg3_build_check.py | 24 |
=======
| test_eg2.py | eg2_signal_parse.py | 24 |
| test_eg3.py | eg3_build_check.py | 25 |
>>>>>>> origin/main
| test_eg4.py | eg4_test_check.py | 31 |
| test_eg5.py | eg5_commit_auth.py | 19 (all passing, git signing fixed) |
| test_eg6.py | eg6_spec_adherence.py | 22 (new) |
| test_model_config.py | model_config.py | 9 |
| test_validators.py | pre_build/validators.py | ~62 |
| test_phase_red.py | pre_build/phase_red.py | 30 |
| test_local_agent.py | local_agent.py | 31 |
| test_integration.py | cross-module integration | 41 (git signing fixed) |
| test_reliability.py | reliability.py | 20 |
| test_branch_manager.py | branch_manager.py | 16 |
| test_codebase_summary.py | codebase_summary.py | 23 |
| test_knowledge_system/ | knowledge_system/ | 231 |

## Open items

### Code changes needed
- **Spec-first parallelism**: `phase_spec.py` generates specs one at a time. Independent features could run in parallel (ThreadPoolExecutor). ~3-4 hours.
- Auto-QA post-render validation (Playwright screenshots): v1 port item. Visual bugs that deterministic code analysis cannot catch.
- `runner.py` duplicates `BUILD_AGENT_TOOLS` from `build_loop_v2.py`. Should be single constant.
- `phase_spec.py` re-scans roadmap for domain. Parser should add domain to return dict.
- No tests for `runner.py`, `orchestrator.py`, or phase 1-5 wrappers.
- V2.2 changes uncommitted — need to merge back or formalize v2.2 as the active repo.
- `test_count` is null across all campaign runs — either `test_cmd` empty/skip or parser mismatch. Not yet investigated.

## Campaign history

<<<<<<< HEAD
### V2 sequential: cre-pulse (session 7)
8/8 features, Claude Sonnet 4.6, ~90 min. Full dashboard renders at localhost:3000.
=======
### Live campaign issues discovered
- ~~EG4 test check fails with exit code 127~~ — **Fixed**: vitest.config.ts added, npm install required before first run.
- `vision-input.txt` deleted by a failed branch cleanup — `cat` fails silently, pre-build skips vision phase because output already exists.
- ~~Auto-complete needs testing~~ — Not triggered with Claude Sonnet (model commits and signals natively).
- ~~`codebase_summary.py` max_turns kwarg~~ — **Fixed** (`10c4752`).
- ~~EG3 `npx tsc --noEmit` requires `node_modules` installed~~ — **Fixed** (`0d910b4`). `_warmup_project_deps()` runs before first feature, installs deps if marker file exists but install dir doesn't.
- ~~EG5 blocks on `tsconfig.tsbuildinfo` if not in gitignore~~ — **Fixed** (`9a012dc`). EG5 auto-clean commits known framework artifacts without burning retries. Also added `tsconfig.tsbuildinfo` and `next-env.d.ts` to cre-pulse gitignore.
- Stale local commits from previous runs confuse the agent (reads pre-existing code, loops). Must `git reset --hard origin/main` not just `git checkout -- .` between runs.
- Carpet-bombing project state between runs wastes money. When only the last feature needs a rerun, release the lock (`rm -f logs/.build-lock`) and rerun — resume state picks up where it left off. Do not nuke resume-state.json or source files unless truly needed.
- ~~EG3 `npm run build` fails before app dir exists~~ — **Fixed** (`c2365e3`). `detect_build_cmd` now checks for `app/`, `pages/`, `src/app/`, `src/pages/` before returning `npm run build`. Falls through to `npx tsc --noEmit` if none exist. Build loop re-detects build command before each EG3 gate so Dashboard Shell creating `app/` upgrades the check mid-campaign.
>>>>>>> origin/main

### V2.2 sequential baseline: cre-pulse-ab-v2 (session 9, 2026-03-17)
15/15 features, Claude Opus 4.6, 87 min. All `test_count` null.

### V2.2 parallel (first attempt): cre-pulse-ab-v2.2 (session 9, 2026-03-17)
Multiple failed runs. Root causes: EG3/EG4 ran per-worktree (no full project), EG5 symlink false positive, merge conflicts from scope collision (`page.tsx` written by multiple agents), Opus 500 errors.

### V2.2 parallel (post-fix): cre-pulse-ab-v2.2 (session 9, 2026-03-19)
14 features, Claude Sonnet 4.6, 49 min. 10/14 built. 3 failed (merge conflict cascade — `page.tsx` scope collision, before scope enforcement fix). 1 skipped (App Shell dep cascade). EG3/EG4 deferral and post-merge validation worked correctly. Scope enforcement (`readonly_paths` + prompt injection) applied after this run.

## Key decisions in effect
<<<<<<< HEAD

All session 7 decisions remain. Additions from sessions 9–13:

- **Parallel builds: deferred EG3/EG4**. Agents don't need the full project to write code. They need it to validate. Parallelize the expensive part (agent), validate sequentially after merge.
- **EG1 `readonly_paths`**: Parallel agents can only create new files. Existing source files are read-only. Prevents scope collisions (e.g. multiple agents writing `page.tsx`).
- **Prompt scope constraint**: When `readonly_paths` active, user prompt lists all read-only files with "writes will be rejected." Belt and suspenders with EG1 enforcement.
- **`git merge --abort` on conflict**: Prevents stale merge state from poisoning subsequent merges.
- **EG5 literal `..` check**: Replaced `Path.resolve()` with `..` traversal detection. EG1 blocks symlink creation; `resolve()` was causing false positives on orchestrator-created symlinks.
- **`keep_recent=8`**: Context trimming in `local_agent.py` bumped from 2 to 8. Agents read 5+ files before writing; aggressive trimming caused re-read loops.
- **Knowledge system: failure-based learning**. Mistake nodes from gate failures are the learning mechanism. Agent self-reported learnings (`LEARNING_CANDIDATE`) dropped — noisy and unreliable. Query, promotion, and injection are all deterministic SQL (DP-2 clean).
- **Stalled agent hard-stop after 2 nudges**: Prevents agents from burning max_turns in read-only loops. Force-stops with `finish_reason="error"` after 24+ consecutive read-only turns.
- **EG6 enforced**: Post-build structural adherence checks (source match, file placement, token existence, naming conventions). All deterministic.
- **EG2 feature name validation**: FEATURE_BUILT signal must match expected feature name (case-insensitive).
- **Auto-complete uses targeted git add**: Only stages files from `executor._written_files`, never `git add -A`.
- **Pre-build phases protect each other's outputs**: Each phase's agent can't overwrite other phases' files.
- **Codebase summary refreshed per feature**: No more stale summary after first merge.
- **Error-code-aware retry**: Retry guidance tailored to specific GateError codes, not generic "fix the error".

Prior session decisions still in effect (non-exhaustive, see CHANGELOG for full lineage):
- GATE short-circuits on first failure. ExecGates follow AgentSpec pattern (Wang et al., arXiv:2503.18666).
- Agent model: Claude Sonnet 4.6 via Anthropic API. Local models all failed tool-use compliance.
- EG1: hardcoded {write_file, read_file, run_command}. Tool call translation, cd stripping, git chain handling, safe && chains, runtime re-detection.
- P8: fixes must generalize. Instance fixes are incomplete.
- Dynamic turn budget: S = base, M = 1.5x, L/XL = 2x. Dep cascade skip. Project dep warmup.
- Cross-feature learning: blocked patterns injected into next feature's system prompt.
- Dep export scanner: injects import signatures into prompt. Cut Dashboard Shell from 60+ to 16 turns.
- Resume state is sacred. Don't nuke between runs.
- Pre-build pipeline: 1 → 2 → {3∥3b} → 3c → 4 → 5(hardened) → 6. Phase 5 enforces token assertions + interaction states.
=======
- Pre-build test generation: Response B (structured Gherkin → deterministic scaffolding). No LLM in verification. Response A (LLM-authored frozen tests) eliminated as DP-2 adjacent.
- GATE short-circuits on first failure (Option A). No flat run of all checks.
- ExecGates are an expansion of AgentSpec (Wang et al., arXiv:2503.18666). Same pattern: trigger at agent boundary → deterministic predicate → binary enforce.
- Gherkin/RED cycle restored from Adrian's auto-sdd. Implemented in `phase_red.py` (deterministic generator, no agent).
- Structured error types (`GateError`) adopted for all new code; existing EG migration deferred.
- EG1 tool set: hardcoded {write_file, read_file, run_command}. New tools require new EG1 code, not config.
- Agent model: Claude Sonnet 4.6 via Anthropic API (`claude-sonnet-4-6`). All three local models (GPT-OSS-120B, Qwen3-Coder-Next, GLM-4.7-flash) failed at tool-use compliance. Mac Studio runs orchestrator, gates, tests, git locally. API handles code generation only. Local model configs retained for future re-evaluation as open-weight tool-use improves.
- Agent prompt: reveal boundaries (writable paths, allowed commands), conceal mechanism (EG1 internals). Few-shot examples attempted via explicit tool documentation in system prompt.
- P8: fixes must generalize. Every bug fix evaluated against "will this class of failure recur?" Instance fixes are incomplete.
- EG1 tool call translation: meet models where they are. When model intent is clear but tool name/schema is wrong, translate to correct call rather than blocking. Security unchanged — translated calls pass through full validation.
- EG1 cd prefix stripping: `cd <project> && cmd` → `cmd`. Models write this habitually. run_command already has cwd.
- EG1 git chain handling: `git add && git commit` split and executed sequentially. Each command validated individually.
- EG1 write-then-exec git exemption: `git add file.ts` stages, doesn't execute. Git commands bypass write-then-exec detection.
- Read-only nudge: after 12 consecutive turns without write_file, inject "Start implementing NOW" message. Threshold raised from 8 — Claude Sonnet reads methodically and the early reads are useful context gathering.
- Auto-complete: when agent writes files but doesn't commit/signal, Python auto-commits and injects FEATURE_BUILT signals.
- Cross-feature learning: EG1 blocked patterns accumulated across features, injected into next feature's system prompt.
- Context window management: old tool results trimmed to metadata after 2 recent results. Individual reads return full content — capping reads caused re-read loops. Trimming stale history is the correct fix.
- Gherkin parser: format-agnostic keyword extraction. No assumptions about LLM formatting.
- Roadmap dep matching: 3-tier fuzzy resolution (exact → normalized → token subset). Models don't write dep names precisely.
- EG1 runtime re-detection: writing a marker file (package.json, pyproject.toml, etc.) triggers re-scan. Handles project bootstrapping.
- EG1 || fallback stripping: `cmd1 || cmd2` → run primary only. Also strips stderr redirects (`2>&1`, `2>/dev/null`). Model sees error from primary and can call fallback separately.
- EG1 test runner exemption from write-then-exec: vitest, jest, pytest, mocha, ava, tap and npx/npm variants. Threat model is lazy hallucination not intentional malice.
- Retry error feedback: gate/build errors injected into user prompt as `## PREVIOUS ATTEMPT FAILED` on retry. Agent reads its own broken code + the exact error.
- Spec file path in user prompt: `_build_user_prompt` includes `Spec file: .specs/features/core/data-loader.feature.md` so agent can emit correct SPEC_FILE signal.
- EG3 timeout: 300s (was 120s). First tsc run compiles all node_modules type defs.
- EG1 safe chain execution: `find X && find Y` (all read-only commands) split, validated, ALL executed, all results returned. Non-read-only `&&` chains still blocked.
- Dynamic turn budget: S = base config max_turns, M = 1.5x, L/XL = 2x. Complex features need more turns.
- Dep cascade skip: when a feature fails, all downstream dependents are skipped. Saves API cost.
- Project dep warmup: _warmup_project_deps() at campaign start. Detects package.json/pyproject.toml/Cargo.toml/go.mod without install dirs and runs install.
- App entry point enforcement: roadmap prompt instructs LLM to always include an App Shell feature. Roadmap validator checks web apps for entry point keywords, returns GateError if missing.
- EG5 auto-clean: when tree_clean fails and all uncommitted files are known framework artifacts (next-env.d.ts, tsconfig.tsbuildinfo, __pycache__, .next, etc), amend agent's commit and re-run gate. Zero retries burned. Unknown files fall through to normal retry.
- Resume state is sacred. Don't nuke `resume-state.json` between runs unless truly needed. Release lock only (`rm -f logs/.build-lock`).
- 7d (prompt_builder.py) deferred: current inline prompts sufficient for first campaign. Tune fix/retry variants after real failure data.
- Model configs: `config/models/` now has gpt-oss-120b.yaml, qwen3-coder-next.yaml, glm-4.7-flash.yaml, claude-sonnet.yaml. Model is a YAML config swap. Claude config uses Anthropic API via `${ANTHROPIC_API_KEY}` env var; all others are local via LM Studio at localhost:1234.
- 436 tests total (112 EG1, 30 phase_red, 25 EG3, 23 codebase_summary, 20 reliability, 16 branch_manager + others).
- Dep export scanner: `_scan_dep_exports()` scans src/ for all .ts/.tsx exports and injects them into the user prompt when a feature has deps. Agent sees exact import paths without burning turns reading files. Cut Dashboard Shell from 60+ turns to 16.
- Retry prompt must not instruct exploration. Old prompt said "Read the files you wrote previously" which sent the agent into a 60-turn loop. New prompt: "Do NOT re-read files whose exports are listed above."
- EG3 Next.js detection: also checks for `next` in package.json deps, not just `next.config.*` files. Next.js 14+ works without config files. Returns `npm run build` which catches server/client boundary violations that `npx tsc --noEmit` misses.
- Cross-feature learning dead code: `_build_system_prompt` had a `return` before the `blocked_patterns` injection. Fixed by assigning to variable first. Blocked patterns were never reaching the agent in any previous campaign.
- Pre-build pipeline expanded: 1 → 2 → 3(tokens) → 3b(personas) → 3c(design patterns) → 4 → 5(hardened) → 6. Personas written after tokens are set. Design patterns reference both tokens and personas.
- Phase 5 token enforcement: Gherkin scenarios for UI features must have >=3 backtick-wrapped token assertions in Then/And steps. Validator `SPEC_NO_TOKEN_ASSERTIONS` enforces mechanically.
- Phase 5 interaction states: UI features must declare `interaction_states` in YAML front matter. Validator `SPEC_NO_INTERACTION_STATES` enforces.
- EG6 deferred: analysis of cre-pulse campaign showed EG3/EG4 catch token violations transitively when specs encode them in Gherkin. Phase 5 prompt/validator hardening is the correct fix. Visual quality checks deferred to Auto-QA (Playwright post-render, v1 port item).
- EG3 app dir gate (`c2365e3`): `detect_build_cmd` checks for `app/`/`pages/`/`src/app/`/`src/pages/` before returning `npm run build`. Without app dir, falls through to `npx tsc --noEmit`. Build loop re-detects per gate, not once at init. Fixes regression where all features before Dashboard Shell failed EG3.
- Spatial design gaps (e.g., 160px dead space under lease velocity chart) are P7 gap. No deterministic visual evaluation exists. SageGate spatial design draft (`docs/sage-spatial-design-draft.md`) improves prompt quality but cannot enforce. Auto-QA (Playwright) is the only enforcement path, blocked until a deterministic rendered-layout evaluation method exists.
- Per-phase model routing evaluated: Haiku 4.5 sufficient for vision and roadmap (structured extraction). Sonnet required for all design-adjacent phases (tokens, personas, patterns, specs) and build loop. Deferred — marginal savings, config complexity not worth it yet.
- v2.1-test A/B experiment (session 9): prompt caching + no git in pre-build + parallel pre-build phases. **Result: v2 baseline won.** v2 finished at 01:16:03, v2.1-test at 01:18:32. Parallel API calls likely hit rate limits. Git stripping may have confused agent. Net negative.
- v2.2 parallel feature builds: code written in `/Users/sorel/Auto_SDD_v2.2/`, **not yet tested in a live run**. Uses git worktrees for filesystem isolation. `_group_by_dep_level()` groups topo-sorted features into parallel-executable levels. Single-feature levels run sequential (no overhead). Multi-feature levels run via `ThreadPoolExecutor` + worktrees. branch_manager.py extended with `setup_feature_worktree`, `remove_worktree`, `link_deps_to_worktree`.

## Filesystem clutter from session 9

| Path | Status | Action |
|---|---|---|
| `/Users/sorel/Auto_SDD_v2.1-test/` | Dead. v2.1-test lost A/B. | Delete |
| `/Users/sorel/cre-pulse-v2.1-test/` | Dead target for v2.1-test. | Delete |
| `/Users/sorel/Auto_SDD_v2.2/` | Parallel builds code, untested. | Keep if testing v2.2, else delete |
| `/Users/sorel/cre-pulse-v2.2/` | Target for v2.2 with specs copied from v2 run. | Keep if testing v2.2, else delete |
| `/Users/sorel/cre-pulse-v2/` | 15-feature Opus run. Intact, untouched. | Keep |
| `/Users/sorel/.zshenv` | Contains API key. **Key was leaked in session 9 chat. Rotate immediately.** | Rotate key, update file |
>>>>>>> origin/main

## References
- `docs/architectural-inventory.md` — 12-phase pipeline (expanded: 3b personas, 3c design patterns)
- `docs/architecture-principles.md` — P1–P8, DP-1, DP-2
- `docs/module-map.md` — v1 function classification
- `docs/system-inventory.md` — codebase metrics
- `docs/CHANGELOG.md` — decision lineage and change history
- Adrian's SDD repo: https://github.com/AdrianRogowski/auto-sdd
- Local clone: `/Users/sorel/adrian-auto-sdd/CLAUDE.md`
