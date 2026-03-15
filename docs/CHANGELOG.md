# Changelog

> Append-only, reverse-chronological. Each entry: date, what changed, why.
> Not required reading for new sessions. Consult when tracing decision lineage.

---

## 2026-03-15 (session 6)

### Code changes (step 6b: integration tests)
- Created `test_integration.py` (855 lines, 41 tests). Covers cross-module wiring with real git repos, real subprocess calls, real file I/O. Only `run_local_agent` is mocked (no LLM in CI).
- `TestBuildLoopIntegration` (9 tests): full loop success, agent failure, EG2/EG3/EG4/EG5 gate failures, retry with git reset, topo-ordered two-feature campaign, summary JSON output.
- `TestGatePipelineShortCircuit` (4 tests): verifies `_run_gate()` short-circuit — failed EG2 leaves EG3/4/5 as None, failed EG3 leaves EG4/5 as None, etc.
- `TestEG1ExecutorIntegration` (5 tests): write→read→command cycle through real `BuildAgentExecutor`, protected_paths blocking, path escape rejection, blocked command rejection, unknown tool rejection.
- `TestRoadmapParsingIntegration` (5 tests): real filesystem `_parse_roadmap` — single feature, topo sort deps, done exclusion, cycle ValueError, missing dep skip.
- `TestDiscoverTestFiles` (3 tests): glob discovery for jest (__tests__/*.test.ts), pytest (test_*.py, conftest.py), node_modules exclusion.
- `TestEG2DiskIntegration` (3 tests): `extract_and_validate` against real disk — valid signals, missing source file, spec outside project.
- `TestEG3EG4SubprocessIntegration` (5 tests): real subprocess `check_build`/`check_tests` — pass, fail, skip, count parse.
- `TestEG5GitIntegration` (3 tests): real git `authorize_commit` — commit authorized, no commit blocked, test regression blocked.
- `TestBuildLoopConfig` (4 tests): max_features limit, auto-detect build/test commands, explicit override, empty roadmap clean exit.
- Step 6b complete: 325 tests total (was 284).

---

## 2026-03-15 (session 5)

### Code changes (step 6a: local_agent.py unit tests)
- Created `test_local_agent.py` (445 lines, 31 tests). Covers: `ToolCallRecord`, `AgentResult`, `_parse_tool_arguments`, `_execute_with_gate`, `_strip_older_reasoning`, `_build_assistant_history_entry`, and `run_local_agent` (14 loop tests).
- `OpenAI` client patched via `unittest.mock.patch`; `FakeExecutor` implements `ToolExecutor` protocol for canned results and block simulation.
- Loop tests cover: stop on first turn, tool call → stop, blocked tool call fed back, `length` finish reason, `max_turns` exhaustion, API error, no-tools mode, developer/system role, reasoning strip integration, multiple tool calls in one turn, `extra_params` forwarding, duration population, unexpected `finish_reason` continuation.
- Step 6a complete: all unit-testable modules now covered. 284 tests total (was 253).

### Model evaluation review
- Reviewed GPT-OSS-120B implementation reference PDF (19-page guide): serving config, Harmony token protocol, tool calling caveats, context management, known issues. Confirmed `local_agent.py` is aligned with reference.
- Evaluated GPT-OSS-120B against current open-weight field (Qwen3-Coder-Next, GLM-4.7, Kimi K2.5, DeepSeek V3.2). All competitors score higher on SWE-bench Verified. No GPT-OSS score exists for SWE-bench Pro — comparison is not apples-to-apples.
- Confirmed Harmony instruction hierarchy (system > developer > user > assistant > tool) is unique to GPT-OSS. No other competitive open-weight model has an equivalent trained-in priority ordering.
- Decision: stick with gpt-oss-120b for Harmony's enforcement properties. Re-evaluate Qwen3-Coder-Next after first campaign with empirical failure data.
- Added GPT-OSS implementation constraints section to SESSION-STATE.md for V1 port guidance.

---

## 2026-03-15 (session 4)

### Design resolved
- Design question 2 (EG1 tool set extensibility): resolved — keep hardcoded. Three tools cover all file-based build tasks. Adding a tool means writing new EG1 validation logic, not toggling config. The else-clause rejection of unknown tools is a security feature.
- Design question 3 (agent prompt awareness): resolved — reveal boundaries, conceal mechanism. The agent's system prompt will state what paths are writable and what commands are allowed, but will not describe EG1's validation internals. Reduces wasted tool calls without exposing attack surface.

### Code changes (step 7c: EG3/EG4 v1 port)
- `eg3_build_check.py` (75→155 lines): added `detect_build_cmd()` ported from v1 `build_gates.py`. Detection order: Next.js configs (must precede tsconfig per L-00177), tsconfig.build.json, tsconfig.json, pyproject.toml/setup.py, Cargo.toml, go.mod, package.json build script. Override + skip support.
- `eg4_test_check.py` (108→185 lines): added `detect_test_cmd()` ported from v1. Covers package.json (filters "no test specified"), pytest.ini, pyproject.toml `[tool.pytest`, setup.cfg `[tool:pytest]`, pyproject.toml fallback, Cargo.toml, go.mod. Override + skip support.
- `eg4_test_check.py`: expanded `_parse_test_count` from 2 to 6 framework patterns: Jest/Vitest (`Tests:? N passed`), Mocha (`N passing`), Cargo test (`test result:...N passed`), Go verbose (`--- PASS:` line count), Pytest (`N passed`). Pytest moved last to avoid false matches.
- `build_loop_v2.py` (~863→~840 lines): removed inline `_detect_build_cmd()` and `_detect_test_cmd()` stubs. Now imports `detect_build_cmd` from `eg3_build_check` and `detect_test_cmd` from `eg4_test_check`.
- `test_eg3.py` (10→24 tests): 14 new tests for `detect_build_cmd` — override, Next.js (3 config variants + priority + fallthrough), TypeScript (2), Python, Rust, Go, package.json, no-detection.
- `test_eg4.py` (12→31 tests): 8 new parse tests (jest no-colon, vitest, pytest warnings, mocha ×2, cargo, go verbose), 11 new detection tests (override, Node ×3, Python ×4, Rust, Go, no-detection).
- Total: 253 tests passing across all modules (was 220).

---

## 2026-03-15 (session 3)

### Code changes
- EG1 check 7 fix: added `isinstance(str)` type checks on `path` argument in `_exec_write_file` and `_exec_read_file`. Previously only `content` (write_file) and `command` (run_command) were type-checked. Non-string path (e.g. list, int) would crash with unhandled TypeError instead of clean ToolCallBlocked.
- EG5 check 2 fix: `_check_tree_clean` now logs untracked files as a warning instead of silently ignoring them. No gate failure change — untracked files may be legitimate build artifacts.
- EG1 `protected_paths`: `BuildAgentExecutor` now accepts an optional `protected_paths` set at construction. Paths in this set are write-blocked — agent gets `ToolCallBlocked` on any `write_file` targeting them. Resolves design question 1 (test content integrity) by making test files immutable from the agent's perspective. 2 new tests (84 total for EG1).
- `_discover_test_files()` added to `build_loop_v2.py`: globs for test files by framework (pytest: `test_*.py`, `*_test.py`, `conftest.py`; JS/TS: `*.test.*`, `*.spec.*`, `__tests__/**`). Called in `_build_feature` before executor construction, result passed as `protected_paths`. Wiring is complete — protection is active in live runs.
- EG2 `parse_signals`: added fenced code block tracking. Lines inside ``` blocks are skipped — prevents false positive signal extraction from agent explanation text. 3 new tests.
- EG2 `validate_signals`: SPEC_FILE content check — spec must contain >25 stripped characters. Empty/placeholder specs fail the gate. 3 new tests.
- EG2 `validate_signals`: SOURCE_FILES disk validation — every file in SOURCE_FILES must exist on disk and resolve within project_dir. Missing files fail the gate (triggers retry). 3 new tests. Existing tests updated: spec content padded to >25 chars, end-to-end test creates source files on disk.

### Test file restructuring (step 6a)
- Renamed `test_eg3.py` → `test_eg5.py`: the file contained commit auth (EG5) tests but was named after EG3. Import fixed from `eg3_commit_auth` to `eg5_commit_auth`. 19 tests, all passing.
- Created `test_eg3.py`: 10 tests for `eg3_build_check.py` (skip, pass, fail, cwd, timeout, to_dict).
- Created `test_eg4.py`: 12 tests for `eg4_test_check.py` (count parsing for jest/pytest, skip, pass, fail, cwd, to_dict).
- Test file numbering now matches module numbering: test_eg1–test_eg5 correspond 1:1 with eg1–eg5.
- Total: 158 tests passing across all modules.

### Documented gap
- `local_agent.py` has no unit tests. The module makes HTTP calls to an OpenAI-compatible server; testing requires mocking the `OpenAI` client. Deferred — not blocking tier 1.

### Review completed
- EG1 check 6 (unknown tool rejection): classified A — sound. Hardcoded else clause blocks invented tool names.
- EG1 check 7 (malformed argument rejection): classified B — minor gap, now fixed. All 82 tests pass.
- EG5 all 4 checks reviewed: HEAD advanced (A), tree clean (B — fixed with warning log), contamination (A), test regression (A, deferred integrity question).

### Design resolved
- Design question 1 (test content integrity): resolved by adding `protected_paths` to EG1. Test files are write-blocked at the tool-call layer. Agent cannot delete, modify, or replace them. EG5 count check is now defense-in-depth, not primary defense.

### Noted (not fixed)
- Pre-build phases 1–6 (VISION through RED) have zero code implementation. architectural-inventory.md defines them as automated, but the build loop currently assumes all spec artifacts exist on disk as human-authored inputs.

### Design identified (no code)
- Structured error types: current `errors: list[str]` across EG2, EG5, GateResult should become `errors: list[GateError]` where `GateError` has a stable `code` field (e.g. `SPEC_TOO_SHORT`, `SOURCE_MISSING`) and a free-form `detail` field. ~25 error-producing call sites, ~15 test assertions. Benefits: tests become wording-independent, build summary gets machine-queryable failure codes, retry logic can branch on error type (e.g. `SOURCE_MISSING` → retry, `SPEC_TOO_SHORT` → don't). Est. 2–3 hours.

---

### Code changes
- Reconciled `build_loop_v2.py` against `architectural-inventory.md`
- Renumbered ExecGates: old EG3 (commit auth) → EG5. Created EG3 (build check) and EG4 (test check) as separate modules extracted from inline helpers
- Created `eg3_build_check.py` (75 lines) and `eg4_test_check.py` (108 lines)
- Renamed eg3_commit_auth → `eg5_commit_auth.py`, updated all internal references
- Added `GateResult` dataclass and `_run_gate()` method to `build_loop_v2.py` — single GATE entry point, short-circuits on first failure
- Replaced `_parse_roadmap()` single-pass dependency filter with true topological sort (Kahn's algorithm) + cycle detection. Pending features with dep chains now resolve in a single campaign.

### Decisions
- EG numbering expanded to cover all orchestrator-side verification: EG1 tool calls, EG2 signals, EG3 build, EG4 test, EG5 commit auth, EG6 spec adherence (reserved). All follow AgentSpec pattern (Wang et al., arXiv:2503.18666).
- GATE short-circuits on first failure (Option A over Option B flat-run). More efficient, matches code reality.
- True topo sort lives in `_parse_roadmap()` (build loop), not in ROADMAP phase or SPEC-FIRST. Orchestrator-owned, deterministic.

### Doc restructure
- Created `SESSION-STATE.md` (single mandatory read for new sessions, overwritten each session)
- Created `CHANGELOG.md` (this file — append-only history)
- Folded `handoff-execgate-review.md` content into `SESSION-STATE.md` EG review section
- Deleted `session-handoff-2026-03-14.md` and `handoff-execgate-review.md`

---

## 2026-03-14 (session 1)

### Architectural inventory changes
- Added SYSTEMS DESIGN as phase 2 (implementation patterns doc, twin of design system for code)
- Made Gherkin explicit in SPEC-FIRST — structured Given/When/Then, not prose scenarios
- Added RED (Test Scaffolding) as phase 6 — deterministic Gherkin-to-test generator
- Folded PARSE ROADMAP into ROADMAP (topo sort belongs in pre-build)
- Consolidated GATE with 5 sub-checks, added spec adherence check
- Filled pre-build metrics (phases 1–6), build loop metrics left blank

### Decisions
- Pre-build test generation: Response B selected (structured Gherkin AC → deterministic scaffolding). Response A (LLM-authored frozen tests) eliminated as DP-2 adjacent. Response C hybrid (LLM behavioral tier) eliminated as unnecessary.
- Gherkin/RED/GREEN/REFACTOR cycle traced to Adrian's auto-sdd. Restored in inventory doc, not yet in code.

### No code changes this session
- `build_loop_v2.py` was not reviewed or modified

---

## 2026-03-12

### EG1 review and hardening
- Reviewed and hardened EG1 checks 1–5: command blocklist, command allowlist (stack-aware), path validation, command argument containment, git branch protection
- 174 smoke tests passing across all reviewed checks
- Established review protocol: state logic → classify (A/B/C) → gaps → fix/defer/accept → smoke test
- Created `handoff-execgate-review.md` to track review state

---

## Pre-2026-03-12 (project setup)

- Steps 1–5b completed: model config, tool call validation, module map, build loop skeleton, ExecGates wired
- Architecture principles (P1–P7, DP-1, DP-2) established in `architecture-principles.md`
- V2 stripped from V1's 2,400-line build_loop.py to ~500-line four-step core per P6
