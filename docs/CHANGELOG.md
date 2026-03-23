# Changelog

> Append-only, reverse-chronological. Each entry: date, what changed, why.
> Not required reading for new sessions. Consult when tracing decision lineage.

---

## 2026-03-19 (session 9)

### Parallel feature builds — deferred EG3/EG4 architecture (Auto_SDD_v2.2)

**Problem**: V2.2 introduced parallel builds via git worktrees. Failed because EG3/EG4 ran per-worktree. Each worktree is a snapshot of main at branch time — sibling features' output doesn't exist. `npm run build` validates the whole project, so worktrees with partial codebases always fail EG3.

**Root cause analysis**: The expensive part is the agent (minutes of API calls). The gate is seconds of subprocess. Parallelize the expensive part, validate sequentially after merge.

**Fix — three-phase parallel flow**:
1. **Phase 1 — Parallel BUILD**: Agents build in worktrees concurrently. `_run_gate` runs EG2+EG5 only (`skip_build_test=True`). EG1 active per tool call.
2. **Phase 2 — Sequential MERGE+GATE**: For each passing worktree, capture HEAD → merge to main → run EG3+EG4 on main (full project available) → if fail, `git reset` to pre-merge HEAD, add to retry list.
3. **Phase 3 — Sequential retry**: Features that failed post-merge EG3/EG4 re-run via `_build_feature` on main with full gates and retries.

**`_run_gate` changes** (`build_loop_v2.py`):
- New `skip_build_test: bool = False` parameter. When True, EG3/EG4 skipped.
- EG5 test regression handles None test count gracefully (already did).

**`_build_feature` changes** (`build_loop_v2.py`):
- Accepts and passes `skip_build_test` to both `_run_gate` calls (initial + auto-clean re-check).

### EG5 no_contamination symlink false positive fix

**Problem**: `_check_no_contamination` used `Path.resolve()` which follows symlinks. Orchestrator-created `node_modules` symlink in worktrees resolved to the main project directory, outside the worktree's `project_root`. EG5 flagged it as contamination.

**Fix** (`eg5_commit_auth.py`): Replaced `resolve()`-based check with literal `..` traversal detection in path components. EG1 already prevents the agent from creating symlinks, so the symlink escape defense was redundant here. Removes false positives from orchestrator-created symlinks.

### Merge conflict cascade fix

**Problem**: When a merge fails (conflict), git stays mid-merge. All subsequent merge attempts fail with "you need to resolve your current index first."

**Fix** (`branch_manager.py`): `merge_feature_branch` now runs `git merge --abort` before raising `BranchError`. Defense-in-depth — the scope enforcement fix below addresses the root cause.

### EG1 scope enforcement for parallel builds

**Problem**: Parallel agents all wrote `src/app/page.tsx` — a file belonging to App Shell. Merge conflicts when the first merged, siblings' versions conflicted. The class of problem: nothing enforced that an agent only writes files belonging to its feature.

**Fix — two layers (P8: belt and suspenders)**:

**EG1 `readonly_paths`** (`eg1_tool_calls.py`):
- New parameter alongside `protected_paths`. Any file in the set is blocked with: "already exists and is outside this feature's scope."
- `_discover_existing_source_files()` scans `src/` for `.ts/.tsx/.js/.jsx/.css` at executor creation time. Only active when `skip_build_test=True`.

**Prompt injection** (`build_loop_v2.py`):
- When readonly files exist, user prompt gets `## SCOPE CONSTRAINT (parallel build)` section listing every readonly file with "Do NOT write to them — writes will be rejected. Only create NEW files listed in your spec."

### Context window trimming tuned

**Problem**: `keep_recent=2` in `local_agent.py` was too aggressive. Agent reads spec, seed data, package.json, tsconfig, tokens.md (~5 files). By the 4th read, 1st and 2nd trimmed to `(trimmed)`. Agent re-reads. Loop.

**Fix** (`local_agent.py`): Bumped `keep_recent` from 2 to 8 on both OpenAI and Anthropic paths. 8 retained tool results × ~50KB max each = ~400KB before trimming. Sonnet's 200K window has room.

### First parallel campaign result (cre-pulse-ab-v2.2)

14 features, Claude Sonnet 4.6, 49 minutes. 10/14 built. 3 failed (merge conflicts from scope violation — `page.tsx` collision), 1 skipped (App Shell, dep cascade). EG3/EG4 deferral worked correctly. Property Overview merged + validated on main. Scope enforcement and merge abort fixes applied post-campaign.

### Persistent learning

The user expressed a desire to revive the knowledge graph work in /superloop to enable compounding knowledge from project learnings.

### Files changed (all in Auto_SDD_v2.2, uncommitted)
- `py/auto_sdd/exec_gates/eg1_tool_calls.py` — `readonly_paths` enforcement
- `py/auto_sdd/exec_gates/eg5_commit_auth.py` — symlink false positive fix
- `py/auto_sdd/lib/branch_manager.py` — worktree support + `merge --abort`
- `py/auto_sdd/lib/local_agent.py` — `keep_recent` 2→8
- `py/auto_sdd/scripts/build_loop_v2.py` — deferred EG3/EG4, post-merge validation, sequential retry, readonly scope, prompt injection

### Test status
435 tests passing (unchanged count — no new tests this session, all changes in wiring/enforcement).

---

## 2026-03-16 (session 8)

### Pre-build pipeline expansion: personas, design patterns, spec hardening

**Phase 3b: PERSONAS** (`phase_personas.py`, 35 lines)
- New phase between tokens (3) and design patterns (3c). Generates `.specs/personas.md`.
- Prompt requires 2-4 personas with structured fields: name/role, goals, device/environment, data density tolerance, critical interactions, frustration triggers, accessibility needs.
- Personas written AFTER tokens are set — can reference token decisions (e.g., dark theme serves low-light environments).
- Validator `validate_personas()`: checks file exists, has 5 required section keywords (role, goals, device, density, critical interactions).

**Phase 3c: DESIGN PATTERNS** (`phase_design_patterns.py`, 39 lines)
- New phase after personas. Generates `.specs/design-system/patterns.md`.
- Defines HOW tokens are applied (tokens.md defines WHAT the values are). Sections: Layout Grid, Component Anatomy, Spacing Relationships, Interaction States, Positive & Negative Space, Responsive Behavior, Overflow & Clipping Rules.
- All decisions must be justified against persona needs (density tolerance, device context).
- Validator `validate_design_patterns()`: checks file exists, has 5 required section keywords.

**Phase 5 prompt hardening** (`prompts.py`)
- `spec_first_user_prompt()` now requires:
  - Concrete token assertions in Gherkin Then/And steps (backtick-wrapped token names, not vague references)
  - `interaction_states` key in YAML front matter (list of UI states covered)
  - References to patterns.md and personas.md as inputs
- Explicitly tells agent: "Do NOT write vague assertions like 'uses the design tokens.'"

**Phase 5 validator hardening** (`validators.py`)
- `SPEC_NO_TOKEN_ASSERTIONS`: UI features (detected by "design token" in spec body) must have >=3 backtick-wrapped token names in Then/And Gherkin lines. Regex: `` `[a-z]+-[a-z0-9]+` `` pattern matching.
- `SPEC_NO_INTERACTION_STATES`: UI features must have `interaction_states` key in YAML front matter.
- Non-UI features (e.g., Data Loader) skip both checks.

**Orchestrator wiring** (`orchestrator.py`)
- Pipeline: 1 → 2 → 3 → 3b → 3c → 4 → 5 → 6. Phases 3b and 3c have skip-if-valid resume support.

**Tests** (`test_validators.py`)
- `TestValidatePersonas`: 4 tests (missing file, too short, missing sections, valid).
- `TestValidateDesignPatterns`: 4 tests (missing file, too short, missing sections, valid).
- `TestFeatureSpecTokenAssertions`: 5 tests (vague tokens fail, missing interaction_states, valid UI feature, non-UI skips checks, boundary at exactly 3 tokens).

**EG6 analysis and deferral**
- Reviewed cre-pulse campaign artifacts. Token enforcement already works end-to-end where Gherkin encodes specific values (Global Layout, Shared UI, Tenant Roster). Gap was spec quality, not gate infrastructure.
- EG6 deferred. Phase 5 hardening is the correct fix for the Class C gap identified in P7. Visual quality checks (overlap, spacing, clipping) deferred to Auto-QA (Playwright post-render, v1 port item).

**New artifacts produced per project:**
- `.specs/personas.md`
- `.specs/design-system/patterns.md`

---

## 2026-03-15 (session 7)

### V1 port steps completed
- **7a: reliability.py** (202 lines, 20 tests). fcntl.flock + PID stale detection (matches v1 pattern). ResumeState dataclass, atomic write via tempfile+rename. Wired into build loop: lock acquire/release in `run()` (try/finally), resume filtering in `_run_locked()`, per-feature state persistence on success, `clean_state` on full campaign success.
- **7b: branch_manager.py** (173 lines, 16 tests). Chained strategy only (independent/sequential stripped per P6). setup_feature_branch from main, merge_feature_branch (--no-ff), delete_feature_branch, cleanup_merged_branches. Build loop wired: branch per feature, merge on success, delete on all failure exits, post-campaign cleanup. `allowed_branch=""` TODO resolved.
- **7e: codebase_summary.py** (265 lines, 23 tests). File tree generation with _EXCLUDED_DIRS (incl SDD metadata dirs per L-00227). Git tree hash cache layer. Agent call via run_local_agent (no tools, single turn). Recent learnings reader. config=None skips agent (testable without model).

### Preflight summary
- Build loop prints preflight summary to terminal before starting: model, project, branch, commands, feature list.
- `--auto-approve` / `AUTO_APPROVE` env var. Default: require user confirmation. Rejection returns exit code 3.
- All 17 integration test instantiations updated with auto_approve=True.

### P8: fixes must generalize (new architecture principle)
- Added to architecture-principles.md. Every bug fix evaluated against "will this class of failure recur under different inputs?" Instance fixes are incomplete.
- Applied examples: Gherkin parser, roadmap dep matching, error message string matching.

### Gherkin parser rewrite (P8 applied)
- Replaced regex-based format matching with format-agnostic keyword extraction. Parser strips formatting noise (markdown headers, code fences, list markers, indentation) from each line, checks for bare Gherkin keywords.
- `_strip_line()`, `_is_scenario_header()`, `_is_step()` — no format assumptions.
- Handles: plain Gherkin, fenced code blocks, markdown h1-h4, indented, bullet lists, numbered lists, Scenario Outline, Scenario Template, case-insensitive steps.
- 10 new tests (5 format variants + 5 adversarial). 30 parser tests total.

### Fuzzy dep matching in roadmap parser (P8 applied)
- 3-tier resolution: exact match → normalized match (strip non-alnum) → token subset match (all dep words in feature name).
- Handles model-generated mismatches like "Global Layout" → "Global Layout & Theming". Ambiguous matches (multiple candidates) left unresolved to fail loudly.

### Topo sort cascade-skip fix
- When feature A is skipped (dep not in roadmap), features depending on A now cascade-skip instead of reporting false cycles. Propagation repeats until stable. Stale edges cleaned from in-degree after removal.

### EG1 runtime re-detection (P8 applied)
- `_refresh_runtimes()` extracted from constructor, re-callable. Called after `write_file` creates any runtime marker file (package.json, pyproject.toml, Cargo.toml, etc.).
- `_RUNTIME_MARKERS` frozenset lists all files that trigger re-scan. Handles project bootstrapping — agent can create package.json and use npm commands in the same session.
- 4 new tests: blocked without marker, npm allowed after writing package.json, python allowed after writing pyproject.toml, non-marker file no retrigger.

### EG1 redirect hints
- Blocked file-reading commands (cat, sed, head, tail, python, etc.) now append "Use the read_file tool to read files instead." to the rejection message.

### System prompt rewrite
- Explicitly documents all 3 tools (read_file, write_file, run_command) with usage guidance. Tells agent to use read_file for reading, not run_command with shell commands. run_command scoped to git, npm, build/test only.

### Package install fix
- pyproject.toml: added [build-system], [project], [tool.setuptools.packages.find]. `pip install -e .` makes `python -m auto_sdd.scripts.build_loop_v2` work.

### Test target project (cre-pulse)
- `/Users/sorel/cre-pulse/` — Next.js 14 dashboard for CRE market intelligence.
- data/seed.json: real CompStak data for 1 WTC (62 tenants, 40 quarterly tx rows, 6 comp properties).
- 7 features across 3 phases, topo-sorted. Pre-build phases 1-6 run successfully against GPT-OSS-120B.

### Test counts
- 398 tests total (was 325 at session start). New: reliability 20, branch_manager 16, codebase_summary 23, phase_red +10, eg1 +4.

### Commits
- `4a849f7` Sessions 3-6 bulk commit (5,516 insertions)
- `c4f8624` Step 7a: reliability.py
- `a99befb` Step 7b: branch_manager.py
- `11c3dc3` Step 7e: codebase_summary.py + preflight
- `081c4ca` Package install fix
- `dac8b5c` Gherkin parser generalize (first pass)
- `03fb82d` Gherkin parser rewrite (format-agnostic)
- `7519fa9` Topo sort cascade-skip fix
- `9962f78` P8 principle + fuzzy dep matching
- `bf257ad` System prompt + EG1 redirect hints
- `10b2e1b` EG1 runtime re-detection

### First live campaign — model evaluations
Three local models tested against cre-pulse (7 features). None completed a feature without architectural intervention.

**GPT-OSS-120B**: Failed. Repeatedly used `sed`, `cat`, `grep` via run_command despite system prompt explicitly saying "use read_file." EG1 blocked every bad call. Model never adapted within 20-turn sessions. Conclusion: Harmony instruction hierarchy does not help when the model ignores instructions entirely.

**Qwen3-Coder-Next** (80B MoE, 3B active, MLX 8-bit): Failed. Different pattern — invented tool names (`listdir`, `list_dir`, `list_directory`), used `cd /path && command` chaining. Faster inference (~2s/turn vs ~10s for GPT-OSS). Still couldn't follow 3-tool schema.

**GLM-4.7-flash**: Partially succeeded with translation layer. Read files correctly after translation, got nudged at turn 8, started writing code. Wrote `core/data-loader/index.ts` but failed at commit stage (write-then-exec false positive blocked `git add file.ts`, `&&` chaining blocked `git add && git commit`). After fixes: completed 12 turns, wrote files, but stopped without FEATURE_BUILT signals → EG2 failed.

### Cross-feature learning (`5566826`)
- `BuildAgentExecutor.blocked_patterns`: list of rejection summaries collected in execute().
- `BuildLoopV2._campaign_blocked`: accumulated across features.
- `_build_system_prompt`: appends "IMPORTANT — these tool calls were rejected in previous builds" section with up to 10 recent patterns.
- Feature 1 burns turns learning. Feature 2+ starts pre-warned.

### max_turns bump + model configs (`978f2b5`, `6e5e72f`, `afbfaa6`)
- `gpt-oss-120b.yaml`: max_turns 20→40. GPT-OSS wastes ~8 turns per feature on blocked calls.
- `qwen3-coder-next.yaml`: created. Model ID: `qwen3-coder-next-mlx`. 80B MoE, MLX 8-bit, tool-use capable.
- `glm-4.7-flash.yaml`: created. Model ID: `glm-4.7-flash-mlx`.

### cd prefix stripping (`8f7978a`, P8)
- `_strip_cd_prefix()`: strips `cd <project_dir> && command` → `command`. Models write this habitually; run_command already has cwd=project_root.
- Only strips when cd target resolves to project_root or within it. cd to outside paths left intact.
- 6 new tests.

### Tool call translation (`95525c3`, P8)
Three models failed at tool-use compliance — not because they lacked intent but because they couldn't map intent to the 3-tool schema. Translation layer in execute() before dispatch:
- `listdir`/`list_dir`/`list_directory`/`ls`/`dir` → `run_command(ls -la)`
- `cat`/`view`/`view_file`/`get_file`/`read` → `read_file(path)`
- `read_file(command='cat X')` → `read_file(path=X)`
- `run_command(sed/cat/head/tail/less)` → `read_file(extracted path)`
- `run_command(python -c open('X'))` → `read_file(X)`
- `run_command(ls -la X 2>/dev/null || echo)` → `run_command(ls -la X)`
- Security unchanged — translated calls pass through full EG1 validation.
- 11 new tests.

### Read-only nudge mechanism (`e01d752`)
- Models read specs and project files for 40 turns without writing code.
- After 8 consecutive turns with no write_file call, inject a user message: "Start implementing NOW by using write_file."
- Deterministic enforcement of forward progress.

### Turn-level logging (`0f91208`)
- Every turn: finish_reason, has_text, has_tools.
- Every tool call: name and argument summary (path or command preview).
- Agent completion: output length.

### Git chain handling + write-then-exec exemption + auto-complete (`d65cc8c`)
**Write-then-exec git exemption**: `git add file.ts` stages a file, doesn't execute it. All `git` commands now bypass write-then-exec detection.

**Git chain handling**: `git add -A && git commit -m '...'` split into sequential commands, each validated individually through full 7-layer validation. Non-git chaining still blocked.

**Auto-complete**: When agent writes files and stops without committing or emitting FEATURE_BUILT signals, Python auto-commits and injects signals from executor state (written files, feature name, spec path).

9 new tests (6 git chain, 3 write-then-exec exemption). 420 tests total.

### Pipe stripping in translation + config bumps
- Translation layer bug: `cat file | head -100` extracted path as `file | head -100`. Fixed: `re.split(r'\s*[|><;]', path)[0]` strips pipe/redirect suffixes before path is used.
- GLM config: `max_tokens` 8192→16384 (model hit output budget on turn 8 after nudge — trying to write entire file in one response). `max_turns` 40→60 (model needs ~8 turns reading + room to write + commit).
- 2 new tests: `cat file | head`, `head file | grep`. 422 tests total.

### Context window management
- **Input-side**: `_trim_old_tool_results()` in local_agent.py: after 2 most recent tool results, older ones truncated to metadata only (path, status, error — file contents replaced with "(trimmed)"). This is where context management actually lives.
- `read_file` returns full content (up to 50KB). Capping individual reads was wrong — it caused re-reads because the model saw `truncated: true` and looped back. Full reads + aggressive trimming of old results is the correct approach.
- GLM config: `max_tokens` 8192→16384, `max_turns` 40→60.

### Commits (session 7 continued, part 2)
- `10148a9` SESSION-STATE + CHANGELOG update
- `5566826` Cross-feature learning
- `978f2b5` max_turns 20→40 + qwen3 config
- `8f7978a` cd prefix stripping
- `6e5e72f` qwen3 model ID
- `afbfaa6` GLM config
- `95525c3` Tool call translation
- `e01d752` Read-only nudge
- `0f91208` Turn-level logging
- `d65cc8c` Git chain + write-then-exec exemption + auto-complete
- `e2c5780` Pipe stripping + GLM config bumps
- `86219dd` Context window management (read_file cap — reverted next commit)
- `ff38545` Revert read_file cap, fix trimming strategy (keep_recent=2)

### Anthropic API support
- `claude-sonnet.yaml` config. Uses `${ANTHROPIC_API_KEY}` env var (expanded at config load).
- `local_agent.py`: dispatch to `_run_anthropic_agent` when base_url contains `anthropic.com`. Uses `anthropic` Python SDK. Same loop logic (nudge, trimming, EG1 enforcement) adapted for Anthropic message/tool format.
- `model_config.py`: `${ENV_VAR}` expansion in all string config values.
- Existing OpenAI path untouched. Local model configs unmodified.

### Bugfixes from first Claude API run
- `AgentResult.success` is a read-only property (derived from `finish_reason == "stop"`). Anthropic path was assigning to it directly. Fixed: set `result.finish_reason = "stop"` instead.
- `codebase_summary.py` passes `max_turns=1` to `run_local_agent` but the function doesn't accept that kwarg. Fails silently (caught exception, returns empty summary). Known bug, not yet fixed.

### First successful end-to-end tool-calling loop
- Claude Sonnet completed Data Loader feature in 13 turns, 31.5 seconds on first run.
- Turn sequence: read package.json → find .ts files → ls project → ls data → read seed.json → find ts files (refined) → find src ts → ls project → read spec → write data-loader.ts → write useDataLoader hook → git add → git commit → stop with FEATURE_BUILT signal.
- Zero EG1 blocks. No translation needed. No nudge needed. Model followed 3-tool schema natively.
- Crashed at EG2 due to `success` property bug (above). After fix, full pipeline should complete.
- This validates the entire enforcement architecture: EG1-EG5 gates, branch management, resume state, preflight — all functional. The model was the bottleneck, not the infrastructure.

### Commits (session 7 continued, part 3)
- `eaa2d7a` Anthropic API support + claude-sonnet.yaml
- `43d9983` Fix AgentResult.success property assignment

### Air run + Mac Studio continuation (session 7 continued, part 4)

**Spec path fix** (`b988e5f`): Agent emitted `SPEC_FILE: Feature: Data Loader` instead of the actual path because the user prompt never included it. EG2 resolved to a nonexistent path. Fix: `_build_user_prompt` now includes `Spec file: .specs/features/core/data-loader.feature.md`.

**Retry error feedback** (`7adfbe3`): When gates fail and retry starts, the error was logged but never fed back to the agent. Retry agent flew blind. Fix: inject previous gate/build error into user prompt on retry as `## PREVIOUS ATTEMPT FAILED` section. Agent reads its own broken code and the exact TypeScript error.

**Retries bumped** (`7adfbe3`): Default 1→2 (3 total attempts). CLI default was overriding the class default — also fixed (`52896c3`).

**codebase_summary fix** (`10c4752`): `run_local_agent()` doesn't accept `max_turns` kwarg. Changed `tools=[]` to `tools=None`. Summary now generates successfully — 1948 chars of project context.

**Model string fix** (`a0ed623`): `claude-sonnet-4-20250514` → `claude-sonnet-4-6` (Sonnet 4.6, current generation).

**Sonnet 4.6 API fix** (`d0ccc0d`): Cannot set both `temperature` and `top_p`. Removed `top_p` from Anthropic API kwargs and config.

**First full gate pipeline pass** (on MacBook Air): Data Loader completed in 14 turns. EG2 passed (signals valid, spec path correct). EG3 passed (tsc --noEmit clean). EG4 passed (18 tests). EG5 blocked on `tsconfig.tsbuildinfo` (untracked build artifact). On retry: EG2-EG4 all passed again.

**Status formatting** (`52896c3`): `_status()` function with `\n\n` padding around major state changes — feature start, gate pass/fail (each EG individually), feature result, retry, build invocation, build loop complete.

**EG3 timeout** (`52896c3`): 120s→300s. First `npx tsc --noEmit` compiles all node_modules type definitions — easily exceeds 120s on first run.

**cre-pulse fixes**: Added `vitest.config.ts` (test discovery paths), `tsconfig.tsbuildinfo` to gitignore, excluded `vitest.config.ts` from tsc, fixed duplicate entries in gitignore. Force-pushed clean main to origin.

**Nudge threshold** (`1dd3fdc`): 8→12 turns. Claude Sonnet reads methodically — spec, seed data, package.json, tsconfig, vitest config. Useful context gathering, not aimless looping.

**Fallback chain stripping** (`1dd3fdc`): Models write `cmd1 || cmd2` as error handling. `_strip_fallback_chain()` runs the primary command only, strips `2>&1` and `2>/dev/null` stderr redirects (subprocess captures separately).

**Test runner exemption** (`1dd3fdc`): `vitest`, `jest`, `pytest`, `mocha`, `ava`, `tap` and their `npx`/`npm` variants exempt from write-then-exec detection. Test runners load files in a sandbox, not as raw script execution. Threat model is lazy hallucination not intentional malice.

### Commits (session 7 continued, part 4)
- `b988e5f` Spec file path in user prompt
- `7adfbe3` Retry error feedback + retries bump
- `10c4752` codebase_summary max_turns fix
- `a0ed623` Model string claude-sonnet-4-6
- `d0ccc0d` Sonnet 4.6 top_p fix
- `d694a4f` CHANGELOG + SESSION-STATE update (first Claude run)
- `52896c3` Status formatting + EG3 timeout + CLI retries default
- `1dd3fdc` Nudge 12 turns + fallback chain strip + test runner exemption

### First complete campaign + post-campaign fixes (session 7 continued, part 5)

**Safe chain execution** (`7e2a3ca`): `_split_safe_chain` / `_exec_safe_chain` — when all parts of a `&&` chain are read-only commands (find, ls, cat, grep, etc.), validate and execute ALL of them sequentially. Results from all commands returned to model. `||` chains still strip to primary only.

**max_turns 60** (`7e2a3ca`): Claude Sonnet config bumped from 40 to 60. Comp Set Benchmarks hit 40-turn limit 3x in a row before this fix.

**Dep cascade skip** (`0d910b4`): When a feature fails, all downstream features that depend on it are skipped with `⊘` status. Saves turns and API cost.

**Project dep warmup** (`0d910b4`): `_warmup_project_deps()` runs before first feature. Checks marker files (package.json, pyproject.toml, Cargo.toml, go.mod) against install dirs (node_modules, .venv, target, vendor). Runs install if missing. 300s timeout.

**Dynamic turn budget** (`0d910b4`): `_turns_for_complexity()` scales max_turns by feature size. S = base, M = 1.5x, L/XL = 2x. With base 60: S=60, M=90, L=120.

**README rewrite** (`6e226e4`): Complete rewrite reflecting current architecture, first campaign results, setup/running instructions, EG1 enforcement details, project structure, key principles.

**App entry point enforcement** (`2e8de53`): Pre-build roadmap phase now instructs the LLM to always include an App Shell as the final feature that creates the application entry point. Roadmap validator `_check_app_entry_point()` detects web apps (Next.js, React, Vue, Angular, Svelte via package.json) and returns GateError if no feature name or notes contains entry point keywords. Triggers retry with error context.

**EG5 auto-clean** (`9a012dc`): When EG5 fails on `tree_clean`, check if all uncommitted files are known framework artifacts (`next-env.d.ts`, `tsconfig.tsbuildinfo`, `__pycache__`, `.next`, `.pytest_cache`, etc). If so, amend the agent's commit to include them and re-run the gate. Zero agent turns burned. Unknown files fall through to normal retry.

**First complete V2 campaign**: 7/7 features built for cre-pulse (Next.js 14 CRE dashboard). 24 source files, 147 tests passing, ~36 minutes total. 4 first-try successes, 2 on retry 1, 1 on retry 2. EG3 caught hallucinated type properties. EG4 caught a real color token value mismatch. Both self-corrected on retry via error feedback.

### Post-campaign: Dashboard Shell + build prompt optimization (session 7 continued, part 6)

**Dep export scanner** (`0a9e2ae`): `_scan_dep_exports()` scans `src/` for all `.ts`/`.tsx` files, extracts export lines, and injects them into the user prompt as an "Available Imports" section when a feature has dependencies. Agent sees exact import paths and type signatures without burning turns reading files. First attempt for Dashboard Shell dropped from 60+ turns to 16 turns.

**Dead code fix** (`0a9e2ae`): `_build_system_prompt` had a `return` statement before the `blocked_patterns` injection block. Cross-feature learning was never reaching the agent in any previous campaign. Fixed by assigning to a variable first.

**Retry prompt fix** (`9c01a89`): Old retry prompt said "Read the files you wrote previously to understand what went wrong" which sent the agent into a 60-turn exploration loop re-reading all 24 existing files. New prompt: "Do NOT re-read files whose exports are listed above. Read ONLY your own files, then write corrected versions immediately."

**EG3 Next.js detection** (`3e3de59`): `detect_build_cmd` only checked for `next.config.*` files. Next.js 14+ works without config files, so detection fell through to `npx tsc --noEmit`, which doesn't catch server/client boundary violations (e.g., `import { readFileSync } from 'fs'` in a client component). Now also checks for `next` in package.json dependencies. Returns `npm run build` which runs the full Next.js compiler including webpack bundling.

**Dashboard Shell campaign**: Feature 8 added to cre-pulse roadmap. App Shell creates `app/layout.tsx` and `app/page.tsx`, imports and renders all 7 feature modules. First attempt: 16 turns, EG3 failed (implicit `any` types). Retry with error feedback succeeded. App renders in browser: property overview, tenant roster, lease velocity timeline, comp set benchmarks. Manual fix required for DataLoader `fs` import (server-only module used in client component) — would be caught by `npm run build` in future campaigns.

### Commits (session 7 continued, part 6)
- `0a9e2ae` Dep export scanner + dead code fix in system prompt
- `9c01a89` Retry prompt: stop telling agent to re-read all files
- `3e3de59` EG3 Next.js detection: check package.json deps

### Commits (session 7 continued, part 5)
- `013e9a2` CHANGELOG + SESSION-STATE update (part 4)
- `6d9aa7f` Read-only && chain splitting (run both sides)
- `7e2a3ca` Safe chain execution + max_turns 60
- `0d910b4` Dep cascade skip + warmup + dynamic turns
- `6e226e4` README rewrite
- `2e8de53` App entry point enforcement in pre-build
- `9a012dc` EG5 auto-clean framework artifacts without burning retries

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
