# Module Map: build_loop.py Classification

> Step 3 of the Simplified Build Loop V2 plan.
> Every function, class, and import in the current `build_loop.py` (2,412 lines)
> classified as **CORE** (keeps in V2) or **EXTENSION** (strips from V2).
>
> Criteria: V2 is the four-step path — SELECT → BUILD → GATE → ADVANCE —
> with ExecGate intercepts. Anything not on that path is an extension.

---

## Classification Summary

| Category | Count | Lines |
|----------|-------|-------|
| CORE (keeps) | 17 functions/methods | ~700 |
| EXTENSION (strips) | 19 functions/methods | ~1,200 |
| REPLACED (new impl) | 3 functions/methods | ~300 |
| SHARED (from lib/) | 4 modules | ~2,150 |

---

## Top-Level Functions

| Function | Lines | Classification | Rationale |
|----------|-------|---------------|-----------|
| `_parse_signal` | 10 | **CORE** | EG2: signal extraction. Used directly by GATE step. |
| `_validate_required_signals` | 29 | **CORE** | EG2: validates FEATURE_BUILT + SPEC_FILE signals exist. |
| `_format_duration` | 10 | **CORE** | Logging utility, trivial, keep. |
| `_parse_token_usage` | 16 | **EXTENSION** | Claude-specific token parsing. V2 gets tokens from OpenAI response objects. |
| `_check_contamination` | 52 | **CORE** | GATE step: verifies agent didn't write outside project root. |
| `_check_repo_contamination` | 39 | **EXTENSION** | Protects auto-sdd's own repo tree. V2 is a separate repo. |
| `_protect_repo_tree` | 23 | **EXTENSION** | chmod protection for auto-sdd source dirs. V2 doesn't need this. |
| `_restore_repo_tree` | 18 | **EXTENSION** | Restores permissions. Paired with `_protect_repo_tree`. |
| `_detect_dep_excludes` | 11 | **CORE** | Used by git clean to avoid deleting node_modules etc. |
| `derive_component_types` | 52 | **EXTENSION** | CIS vector store: classifies files into component types. |
| `_load_env_local` | 26 | **CORE** | Config loading from `.env.local`. Adapt for V2 (may use YAML instead). |
| `_env_str` / `_env_int` / `_env_bool` | 18 | **CORE** | Env-var parsing helpers. Trivial, keep. |
| `_get_head` | 13 | **CORE** | Git HEAD retrieval. Used by GATE step. |
| `main()` | 18 | **REPLACED** | Entry point. V2 writes its own main. |

---

## FeatureRecord (dataclass, 10 lines)

**CORE** — Simple record of build results. Used by ADVANCE step.

---

## BuildLoop Class Methods (1,863 lines)

| Method | Lines | Classification | Rationale |
|--------|-------|---------------|-----------|
| `__init__` | 170 | **REPLACED** | V2 __init__ is much simpler: reads ModelConfig, project_dir, roadmap path. Strips env-var sprawl (170→~40 lines). CIS vector store, eval sidecar config, agent model strings, review model — all stripped. |
| `_cleanup` | 7 | **CORE** | Lock release + atexit. Keep (simplified). |
| `run` | 61 | **CORE** | Entry point: topo sort → preflight → loop. Core of SELECT step. Strips eval sidecar start and "both" mode dispatch. |
| `_run_single_mode` | 46 | **CORE** | Orchestrates build loop + summary + cleanup. Adapt for V2 (strips auto-QA, post-campaign-verify). |
| `_run_both_mode` | 48 | **EXTENSION** | Runs chained pass then independent pass. V2 has one strategy. |
| `_record_build_result` | 129 | **CORE** | Records feature outcome, writes resume state. Strips CIS vector store writes (~50 lines), keeps result recording + state write (~80 lines). |
| `_run_pattern_analysis` | 23 | **EXTENSION** | CIS pattern analysis. |
| `_run_build_loop` | 571 | **CORE (heavy adapt)** | The main per-feature loop. This is the heart. Contains SELECT (branch setup, prompt build), BUILD (agent invocation), GATE (post-build checks), ADVANCE (record + next). V2 rewrites this with: (a) `run_local_agent` replacing `run_claude`, (b) EG intercepts at boundaries, (c) signal fallback inference paths stripped (paths 2 & 3 — ~120 lines), (d) CIS vector writes stripped (~40 lines), (e) eval sidecar injection stripped (~20 lines). Estimated V2 size: ~300 lines. |
| `_run_post_build_gates` | 170 | **CORE** | The GATE step. HEAD check, tree clean, contamination, deps, build, test, drift, code review, dead exports, lint. V2 keeps gates 0-2 (HEAD, tree, contamination) + build + test. Strips: drift check (~30 lines), code review (~25 lines), dead exports, lint (non-blocking, re-add later). Estimated V2: ~80 lines. |
| `_run_auto_qa` | 47 | **EXTENSION** | Post-campaign validation pipeline. |
| `_post_campaign_verify` | 55 | **EXTENSION** | Post-campaign verification. |
| `_run_independent_pass` | 168 | **EXTENSION** | "Both" mode independent pass. |
| `write_build_summary` | 69 | **CORE** | JSON summary output. Keep (minor adapt). |
| `start_eval_sidecar` | 53 | **EXTENSION** | Eval sidecar lifecycle. |
| `stop_eval_sidecar` | 60 | **EXTENSION** | Eval sidecar lifecycle. |
| `_check_sidecar_health` | 20 | **EXTENSION** | Eval sidecar health check. |
| `_cleanup_branch_on_no_features` | 27 | **CORE** | Branch cleanup when no features match. |
| `_cleanup_failed_branch` | 41 | **CORE** | Branch cleanup on build failure. |
| `_print_progress` | 40 | **CORE** | Progress display during loop. |
| `_print_timings` | 6 | **CORE** | Timing summary. |

---

## Imports: What V2 Keeps vs Strips

### KEEPS (adapt)

| Module | What V2 Uses |
|--------|-------------|
| `reliability.py` (602 lines) | `Feature`, `ResumeState`, `emit_topo_order`, `acquire_lock`, `release_lock`, `read_state`, `write_state`, `clean_state`, `check_circular_deps` — all core loop infrastructure. `DriftPair`, `run_parallel_drift_checks` stripped. |
| `build_gates.py` (730 lines) | `check_build`, `check_tests`, `check_deps`, `check_working_tree_clean`, `detect_build_check`, `detect_test_check`, `should_run_step`, `run_cmd_safe`. Strips: `check_dead_exports`, `check_lint` (re-add as optional later). |
| `prompt_builder.py` (575 lines) | `build_feature_prompt`, `build_fix_prompt`, `build_retry_prompt`, `show_preflight_summary`, `BuildConfig`. All core — prompt construction is the SELECT step. Will need adaptation for tool-use prompt format vs Claude CLI format. |
| `branch_manager.py` (200 lines) | Branch setup/cleanup for chained/independent/sequential. V2 starts with one strategy (likely chained). Keep `setup_branch_chained`, `cleanup_branch_chained`, `cleanup_merged_branches`. Strip independent/sequential until needed. |
| `codebase_summary.py` (240 lines) | `generate_codebase_summary` — injected into build prompts for cross-feature context. Keep. |

### STRIPS (not imported in V2)

| Module | Rationale |
|--------|-----------|
| `claude_wrapper.py` (260 lines) | Replaced entirely by `local_agent.py` + `model_config.py`. |
| `drift.py` (530 lines) | Drift check, code review. Extension — re-add later. |
| `learnings_writer.py` | Writes to learnings corpus. Extension. |
| `pattern_analysis.py` | CIS pattern analysis. Extension. |
| `vector_store.py` | CIS vector store. Extension. |
| `eval_sidecar.py` (740 lines) | Async eval. Extension. |
| `project_config.py` | Project-level config. V2 uses ModelConfig + env vars. |

---

## The V2 Skeleton Shape (Step 4 preview)

Based on this classification, `build_loop_v2.py` will contain:

```
build_loop_v2.py (~500-600 lines estimated)
├── _parse_signal()                    ← from current (10 lines)
├── _validate_required_signals()       ← from current (29 lines)
├── _format_duration()                 ← from current (10 lines)
├── _check_contamination()             ← from current (52 lines)
├── _get_head()                        ← from current (13 lines)
├── _detect_dep_excludes()             ← from current (11 lines)
├── _load_env_local()                  ← from current (26 lines)
├── _env_str/_env_int/_env_bool()      ← from current (18 lines)
├── FeatureRecord                      ← from current (10 lines)
├── BuildLoopV2
│   ├── __init__()                     ← NEW (~40 lines, reads ModelConfig)
│   ├── run()                          ← adapted (~40 lines, no eval sidecar)
│   ├── _run_loop()                    ← adapted from _run_build_loop (~300 lines)
│   │   ├── SELECT: branch + prompt
│   │   ├── BUILD: run_local_agent() + EG1
│   │   ├── EG2: _validate_required_signals()
│   │   ├── GATE: _run_post_build_gates()
│   │   └── ADVANCE: _record_build_result()
│   ├── _run_post_build_gates()        ← adapted (~80 lines, core gates only)
│   ├── _record_build_result()         ← adapted (~80 lines, no CIS vectors)
│   ├── write_build_summary()          ← from current (~69 lines)
│   ├── _cleanup_branch_*()            ← from current (~68 lines)
│   └── _print_progress/timings()      ← from current (~46 lines)
└── main()                             ← NEW (~20 lines)
```

### Library modules copied/adapted for V2:

```
py/auto_sdd/lib/
├── model_config.py        ← NEW (Step 1) — ModelConfig dataclass
├── local_agent.py         ← NEW (Step 1) — Completion loop + ToolExecutor
├── reliability.py         ← COPY from v1, strip DriftPair/parallel drift
├── build_gates.py         ← COPY from v1, strip dead exports/lint
├── prompt_builder.py      ← COPY from v1, adapt prompt format for tool-use
├── branch_manager.py      ← COPY from v1, strip independent/sequential
└── codebase_summary.py    ← COPY from v1, no changes needed
```

### ExecGate modules (new, Step 5):

```
py/auto_sdd/exec_gates/
├── __init__.py
├── eg1_tool_calls.py      ← ToolExecutor impl: path restrictions, cmd allowlist
├── eg2_signal_parse.py    ← Mechanical signal extraction + validation
└── eg3_commit_auth.py     ← Final check: test regression, scope violation
```
