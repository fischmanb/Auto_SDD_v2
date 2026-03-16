# System Inventory & Evaluation Framework

> Current state of Auto-SDD V2 as of 2026-03-15.
> What's built, what happens when, where the exposure is, what to track.

---

## Codebase Summary

| | Lines | Classes | Functions |
|---|------|---------|-----------|
| Production code | 2,474 | 11 | 61 |
| Test code | 701 | 22 | 95 |
| Validation script | 658 | 1 | 12 |
| **Total** | **3,833** | **34** | **168** |
| Tests passing | **422** | | |

---

## What Happens When (Pipeline Sequence)

### Phase 0: Initialization (once per campaign)

```
BuildLoopV2.__init__()
```

- Load ModelConfig from YAML (model name, base_url, timeout, generation params)
- Resolve project_dir
- Auto-detect build command (tsconfig.json → `npx tsc --noEmit`, package.json scripts → `npm run build`)
- Auto-detect test command (package.json scripts → `npm test`, pyproject.toml → `pytest`)
- Parse roadmap, filter to buildable features (deps satisfied)

**What's enforced**: Model config is validated at load time.
**What's NOT enforced**: No validation that the project is a git repo, no validation that specs exist for each feature, no resume state (v1 port 7a).

### Phase 1: SELECT (per feature)

```
_build_feature() entry → capture baselines → construct prompts → create executor
```

- Capture HEAD commit hash (baseline for EG3)
- Run test suite to capture baseline test count (P1: orchestrator runs tests)
- Build system prompt (agent rules, signal protocol, project root)
- Build user prompt (feature name, complexity, spec content from .feature.md)
- Create BuildAgentExecutor scoped to project_root with auto-detected runtimes

**What's enforced**: Baselines captured before agent touches anything.
**What's NOT enforced**: No branch creation (v1 port 7b), no codebase summary injection (v1 port 7e), no learnings injection (v1 port 7d), no prompt size estimation.

### Phase 2: BUILD (per feature)

```
run_local_agent() with EG1 intercepting every tool call
```

- Fresh agent context (no memory of prior features)
- 3 tools available: write_file, read_file, run_command
- Every tool call passes through BuildAgentExecutor (EG1):

| EG1 Layer | What it checks | Failure class |
|-----------|---------------|---------------|
| 1. First-token blocklist | 30+ dangerous executables | A: malicious |
| 2. Recursive rm | rm -r / rm -rf any target | A: destructive |
| 3. Shell injection | 17 patterns (substitution, pipes, chaining) | A: injection |
| 4. Blocked-anywhere tokens | chmod, chown, chgrp | A: escalation |
| 5. Argument containment | File args in cat/grep/ls stay within project | A: exfiltration |
| 6. Git subcommand + branch | push/merge/reset/checkout blocked | B: state violation |
| 7. npm/npx scope | install with args blocked, scripts validated against package.json | B: scope creep |
| 8. Runtime allowlist | Only detected stack commands allowed (node/python/rust/etc.) | B: scope creep |
| 9. Base command allowlist | Filesystem utilities only | A: safety net |
| Write-then-exec | Agent wrote .sh then tries to run it → blocked | A: bypass |
| Path validation | .env, .npmrc, .git/, system dirs, project containment | A+B: containment |

- Agent builds, writes files, commits, emits signals in final output
- AgentResult captures: output text, tool call records, turn count, finish reason, duration

**What's enforced**: Every tool call gated. Path containment. Command validation. Stack awareness.
**What's NOT enforced**: No limit on number of files agent creates. No limit on file sizes. No validation of file content quality. No constraint on which project files the agent modifies (within project root).

### Phase 3: EG2 — Signal Parse (per feature)

```
extract_and_validate(agent_output, project_dir)
```

- Mechanical line-by-line scan for FEATURE_BUILT, SPEC_FILE, SOURCE_FILES
- Last occurrence wins (agent may emit intermediate signals)
- FEATURE_BUILT: required, non-empty
- SPEC_FILE: required, must exist on disk, must resolve within project_dir (L-00217)
- SOURCE_FILES: parsed but not currently gating (informational)

**What's enforced**: Signal presence. Spec file existence. Path containment.
**What's NOT enforced**: Signal accuracy (agent says FEATURE_BUILT but feature is broken — Class C gap). SOURCE_FILES not validated against disk. No check that FEATURE_BUILT name matches the feature the agent was asked to build.

### Phase 4: GATE — Mechanical Checks (per feature, orchestrator-side)

```
_run_build_check() → _run_test_check()
```

- Build check: orchestrator runs build_cmd as subprocess, checks return code
- Test check: orchestrator runs test_cmd as subprocess, parses test count from output
- Both are orchestrator-executed per P1 — agent never touches test execution

**What's enforced**: Code compiles. Existing tests pass. Test count captured.
**What's NOT enforced**: No framework-specific detection (v1 port 7c). Test count parsing is basic regex (Jest/pytest patterns only). No dependency health check.

### Phase 5: EG3 — Commit Authorization (per feature)

```
authorize_commit(project_dir, branch_start_commit, current_test_count, baseline_test_count)
```

| Check | What it validates | Failure class |
|-------|------------------|---------------|
| HEAD advanced | Agent actually committed (HEAD != baseline) | B: structural |
| Tree clean | No tracked modifications left uncommitted | B: structural |
| No contamination | No files outside project root in diff | B: containment |
| Test regression | Test count >= baseline count | B+C: quality |

**What's enforced**: Commit happened. No leftover changes. No scope escape. Tests didn't decrease.
**What's NOT enforced**: Commit message quality. Test quality (count not content). No check that new code is covered by tests.

### Phase 6: ADVANCE (per feature)

- Record FeatureRecord (name, status, attempt, test count, timestamp)
- Loop to next feature

**What's enforced**: Result recorded.
**What's NOT enforced**: No roadmap update (feature still shows ⬜). No resume state persistence (v1 port 7a). No branch merge.

### Phase 7: Summary (end of campaign)

- Write build-summary-{timestamp}.json to logs/
- Log built/failed/skipped counts + per-feature details

---

## Exposure Map

These are the known gaps where failures can pass through all gates undetected.

### Class A: Safety (mostly covered)

| Exposure | Status | Gap |
|----------|--------|-----|
| Agent runs destructive commands | ✅ Covered | Edge cases in shell metacharacter bypass |
| Agent reads outside project | ✅ Covered | - |
| Agent writes outside project | ✅ Covered | - |
| Agent modifies orchestrator code | ✅ Covered | Agent can't reach Auto_SDD_v2 |
| Agent modifies its own gates | ✅ Covered | .specs/ not yet write-protected (TODO) |
| Agent exfiltrates data via network | ✅ Covered | curl/wget/ssh blocked |
| Agent escalates privileges | ✅ Covered | sudo/chmod blocked |

### Class B: Structural (mostly covered)

| Exposure | Status | Gap |
|----------|--------|-----|
| Agent claims commit but didn't | ✅ Covered | EG3 HEAD check |
| Agent leaves dirty tree | ✅ Covered | EG3 tree clean |
| Agent touches out-of-scope files | ✅ Covered | EG3 contamination |
| Agent deletes tests to pass | ⚠️ Partial | Test count regression catches deletion, but replacing a test with a trivial pass goes undetected |
| Agent pushes/merges/rebases | ✅ Covered | EG1 git subcommand gate |
| Agent installs arbitrary packages | ✅ Covered | npm install with args blocked |
| Agent modifies package.json scripts | ⚠️ Partial | Write-then-exec catches npm run after modification, but the modification itself is allowed |

### Class C: Semantic / Logic (the expensive gap, per P7)

| Exposure | Status | Why it's hard |
|----------|--------|---------------|
| Agent builds wrong feature | ❌ Not covered | Requires understanding spec intent (DP-2 violation to automate) |
| Agent builds partial feature | ❌ Not covered | Compiles and passes tests but missing functionality |
| Agent introduces subtle bugs | ❌ Not covered | Code is valid but logically wrong |
| Agent uses wrong architecture | ❌ Not covered | Valid implementation, wrong approach for the project |
| Agent creates dead code / unused exports | ❌ Not covered | No dead code analysis in V2 (stripped as extension) |
| Agent hardcodes values that should be configurable | ❌ Not covered | Requires design judgment |

**Per P7**: These require LLM judgment to detect. The orchestrator's job is the mechanical boundary. Class C coverage comes from better specs and the project's own test suite.

---

## What to Track Across Builds

### Per-Feature Metrics (captured in build-summary.json)

| Metric | Source | What it tells you |
|--------|--------|-------------------|
| `status` | FeatureRecord | built / failed / skipped |
| `attempt` | FeatureRecord | How many tries before success/failure (0 = first try) |
| `duration` | FeatureRecord | Wall time per feature |
| `test_count` | FeatureRecord | Test count after this feature (should be monotonically increasing) |
| `error` | FeatureRecord | Why it failed (EG2/EG3/build/test — categorize these) |
| `tool_call_count` | AgentResult | How many tool calls the agent made |
| `finish_reason` | AgentResult | stop / length / max_turns / error |

### Per-Campaign Metrics (derived from summary)

| Metric | Calculation | What it tells you |
|--------|-------------|-------------------|
| Success rate | built / total | Overall loop reliability |
| First-try rate | features where attempt=0 / built | How often the agent gets it right without retry |
| Retry effectiveness | (retry successes) / (total retries) | Are retries actually fixing problems or just wasting compute |
| Mean feature time | avg(duration) for built features | Throughput baseline |
| Gate failure distribution | count by error category | Where the loop is breaking — EG1? EG2? Build? Tests? EG3? |
| Tool calls per feature | avg(tool_call_count) for built features | Agent efficiency (more calls = more complex or more confused) |
| Test growth | test_count delta across campaign | Are tests accumulating as features are built |

### Per-Campaign Review Questions (manual, post-campaign)

These are the things no gate can answer automatically. Review after each campaign:

1. **Did the agent build what the specs intended?** — Open each built feature, compare to spec. This is the Class C check humans provide.
2. **Do the built features actually work at runtime?** — Boot the app, click around. Compilation != correctness.
3. **What did the retries look like?** — Read the error fields for failed attempts. Are they repeating the same mistake? Are they productive?
4. **What commands did EG1 block?** — Review tool call records. Were blocks legitimate enforcement or false positives that the agent had to work around?
5. **What's the test coverage trajectory?** — Is test count growing? Are the new tests meaningful or trivial?

---

## Data Not Yet Captured (needs implementation)

The skeleton writes build-summary.json but doesn't yet capture everything
listed above. Gaps to close before first real campaign:

| Data | Where it should live | Effort |
|------|---------------------|--------|
| Tool call records per feature | build-summary.json `features[].tool_calls` | Small — AgentResult already has this, just serialize it |
| EG1 block log | build-summary.json `features[].blocked_calls` | Small — ToolCallRecord already has `blocked` flag |
| Per-attempt error categorization | build-summary.json `features[].attempts[]` | Medium — currently only final attempt error is recorded |
| Token usage per feature | build-summary.json `features[].tokens` | Small — OpenAI response has usage field, capture in AgentResult |
| Git diff stats per feature | build-summary.json `features[].diff_stats` | Small — `git diff --stat` after commit |
| Baseline vs final test count | build-summary.json `features[].test_baseline`, `features[].test_final` | Small — already captured, just not serialized |

---

## Pending Work (prioritized)

### Must-do before first campaign

1. **Add .specs/ to EG1 write-protected paths** — one line change, prevents agent from modifying its own specs
2. **Capture tool call records + blocked calls in summary** — make the build data inspectable
3. **Capture token usage from OpenAI response** — needed for cost tracking and context budget estimation
4. **EG review completion** — EG1 checks 6-7, EG2 (3 checks), EG3 (4 checks) per handoff doc

### Should-do before production use

5. **v1 port 7a: reliability.py** — true topo sort, resume state, crash recovery
6. **v1 port 7b: branch_manager.py** — feature branches (currently commits to main)
7. **v1 port 7c: build_gates.py** — structured results, framework-specific detection
8. **Integration tests (6b)** — Layer 1 mocked-agent tests for the full pipeline

### Nice-to-have (iterate based on campaign data)

9. **v1 port 7d: prompt_builder.py** — codebase summary, learnings injection, context budget
10. **v1 port 7e: codebase_summary.py** — cross-feature context
11. **EG1 allowlist tuning** — based on actual block logs from campaigns
12. **Test count parsing** — expand beyond Jest/pytest to cover mocha, vitest, etc.

---

## Design Principles Governing Iteration

| ID | Principle | Implication for changes |
|----|-----------|----------------------|
| P1 | Agent's only output is committed code | Never add agent-reported metrics as gating inputs |
| P2 | Agent cannot reach orchestrator | Any new tool or path must be containment-checked |
| P3 | Deterministic gates only | New gates must be Python conditionals, not LLM calls |
| P4 | Agent proposes, gate disposes | New tools go through EG1, no exceptions |
| P5 | Stack awareness derived | New runtime support = add marker detection + token set |
| P6 | Extensions stripped, not commented | New features enter behind flags or as separate modules |
| DP-1 | No manual intervention in critical path | Automation gaps are bugs, not features |
| DP-2 | No LLM judgment in verification | Verification that requires interpretation is out of scope for the orchestrator |
| P7 | LLM judgment irreducible in implementation | Class C gap is managed by spec quality + project tests, not orchestrator gates |
