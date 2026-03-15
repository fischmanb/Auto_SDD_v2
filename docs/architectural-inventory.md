# Architectural Inventory — Goals & Metrics

> Last updated: 2026-03-14. Reconciled with `build_loop_v2.py` this session.

## PRE-BUILD:

### 1. VISION
Generate .specs/vision.md defining what the app is, who it's for, what problem it solves, key screens/areas, tech stack, and design principles.

**Input:** User-provided prompt or doc upload.

**Output:** .specs/vision.md with structured sections: overview, target users, problem statement, key screens, tech stack, design principles, out-of-scope.

**Goal:** Produce a single source of truth for what the app is, sufficient for a roadmap to be derived from it without further human clarification.

**Metric:** # of interventions needed to reach information sufficiency for ROADMAP.


### 2. SYSTEMS DESIGN
Define consistent implementation patterns, shared abstractions, and structural conventions tailored to the vision, written as .specs/systems-design.md. Feature specs and build agents reference this document to ensure cross-feature consistency in architecture, directory layout, and reuse of shared modules.

**Input:** .specs/vision.md (tech stack, key screens/areas).

**Output:** .specs/systems-design.md with sections: directory structure conventions, shared module locations and contracts, state management pattern, API/data access pattern, error handling pattern, naming conventions.

**Goal:** Downstream-generated features make use of consistent implementation patterns and minimize codebase inefficiencies across the final build.

**Metric:** % of features completed without systems design deviation per build.


### 3. DESIGN SYSTEM
Generate .specs/design-system/tokens.md defining the visual vocabulary (colors, spacing, typography, component patterns) that all features must reference.

**Input:** .specs/vision.md (app personality, target users, design principles).

**Output:** .specs/design-system/tokens.md with token categories: colors, spacing, typography, border radii, component patterns.

**Goal:** Establish a consistent visual vocabulary so all features reference the same token names and produce a coherent UI.

**Metric:** % of features completed without design system deviation per build.


### 4. ROADMAP
Decompose the vision into right-sized features (S/M/L), identify dependencies between them, topologically sort by dependency (with cycle detection), sequence into named phases, and write .specs/roadmap.md as a parseable, build-ready table.

**Input:** .specs/vision.md (key screens, tech stack), existing codebase state (optional, to mark already-built features as done).

**Output:** .specs/roadmap.md with parseable markdown table: ID, name, domain, deps, complexity (S/M/L), notes, status (⬜/✅/🔄/⏸️), grouped by named phases.

**Goal:** Produce an ordered, dependency-aware list of right-sized features that the build loop can consume sequentially without human reordering.

**Metric:** Sum of total agent retries + interventions necessary across the build phases to render all roadmap.md features bug-free and WAD (Working-as-Designed) once compiled.


### 5. SPEC-FIRST
For each feature on the roadmap, generate .specs/features/{domain}/{feature}.feature.md with YAML front matter (contracts, dependencies, personas, status) and Gherkin scenarios (Given/When/Then), user journey, and design token references.

**Input:** .specs/roadmap.md (feature name, complexity, deps), .specs/vision.md (context), .specs/design-system/tokens.md (visual vocabulary), .specs/systems-design.md (implementation patterns, shared modules, structural conventions).

**Output:** .specs/features/{domain}/{feature}.feature.md per pending feature, each with YAML front matter (feature, domain, status, deps, design_refs) and structured Gherkin scenarios (Given/When/Then with typed steps), user journey, design token references.

**Goal:** Produce a complete feature specification for each roadmap entry, structured enough for the build agent to implement without requiring additional context.

**Metric:** % of built features that adhere to SPEC-FIRST outputs across the output criteria.


### 6. RED (Test Scaffolding)
Deterministic Python generator converts Gherkin scenarios from each feature spec into runnable test files, placed in the project's test directory before the build agent runs.

**Input:** .specs/features/{domain}/{feature}.feature.md (Gherkin scenarios with typed Given/When/Then steps).

**Output:** Test files in the project's test directory, one per feature, containing scaffold tests derived mechanically from Gherkin steps. No LLM involvement.

**Goal:** Bind the build agent to design intent — the agent's job is to make pre-existing tests pass, not to write its own.

**Metric:** % of scaffolded test assertions that pass on first build attempt per feature.


---

## BUILD LOOP:

### 7. INITIALIZE
Load model configuration, resolve project directory, detect build/test commands and project runtimes, load resume state, and acquire campaign lock. TBD: resume state, campaign lock.

**Input:** Model config YAML path, project directory path, optional explicit build/test commands, optional environment variables.

**Output:** Fully configured BuildLoopV2 instance with resolved model config, project dir, build/test commands, detected runtimes, and initialized result tracking.

**Goal:** Establish a valid, locked runtime environment with all configuration resolved before any features are processed.

**Metric:** 


### 8. SELECT
Capture baseline HEAD commit and test count, set up the feature branch, construct system and user prompts, and create the EG1 executor scoped to this feature's build. TBD: branch creation, codebase summary injection, learnings injection, fix/retry prompt variants.

**Input:** Current Feature from the parsed list, project_dir, ModelConfig, .specs/features/{domain}/{feature}.feature.md.

**Output:** Baseline HEAD hash, baseline test count, system prompt string, user prompt string, configured BuildAgentExecutor instance.

**Goal:** Capture the pre-build state baseline and construct everything the agent needs to build exactly one feature.

**Metric:** 

### 9. BUILD (EG1)
Invoke the local agent with tool definitions; every tool call is intercepted by EG1, which validates paths, commands, runtime scope, git operations, and npm/npx scope before execution.

**Input:** ModelConfig, system prompt, user prompt, tool definitions (write_file, read_file, run_command), BuildAgentExecutor.

**Output:** AgentResult containing: final output text (with embedded signals), tool call records, turn count, finish reason, duration.

**Goal:** Agent implements the feature while every tool call is validated against deterministic safety and scope constraints before execution.

**Metric:** 

### 10. GATE
Run all verification checks in sequence; failure at any step short-circuits remaining checks. Each check is deterministic Python owned by the orchestrator — no agent judgment. All checks follow the AgentSpec enforcement pattern: trigger at agent boundary, deterministic predicate, binary enforce.

Checks are classified by failure type: Class A (malicious/dangerous, caught by EG1 during BUILD), Class B (structural/state violations), Class C (semantic/logic bugs, irreducible per P7).

**Check sequence (short-circuits on first failure):**
1. **EG2 — Signal parse (Class B):** Extract FEATURE_BUILT, SPEC_FILE, and SOURCE_FILES from agent output; validate required signals present and referenced files exist on disk.
2. **EG3 — Build check:** Run build_cmd as subprocess, capture pass/fail and output.
3. **EG4 — Test check:** Run test_cmd as subprocess, capture pass/fail, parse test count.
4. **EG5 — Commit auth (Class B):** Verify HEAD advanced past baseline, working tree clean, no files outside project root modified, test count not regressed below baseline.
5. **EG6 — Spec adherence (Class B):** Diff-based static analysis of committed changes against structured spec and systems-design metadata — file placement, import paths, naming conventions, route definitions, design token references. No LLM involvement. Reserved — deterministic implementation TBD.

**Input:** AgentResult.output, build_cmd, test_cmd, project_dir, baseline HEAD hash (from SELECT), baseline test count (from SELECT), .specs/features/{domain}/{feature}.feature.md, .specs/systems-design.md.

**Output:** GateResult with: EG2 signal validity (bool + errors), EG3 build pass/fail + output, EG4 test pass/fail + parsed test count + output, EG5 commit auth (bool + checks_passed + checks_failed), EG6 spec adherence (bool + deviations list, reserved), overall pass/fail, failed_gate ID. Fields for checks that didn't run (due to short-circuit) are None.

**Goal:** Verify the agent claimed completion, the code compiles, all tests pass, the git state is clean, and the committed changes adhere to spec and systems-design conventions — entirely through deterministic orchestrator-owned ExecGate checks (EG2–EG6) with zero agent involvement. Checks short-circuit on first failure.

**Metric:** 

### 11. ADVANCE
Record the feature result; on failure, retry with fix-in-place (attempt 1) or git reset (attempt 2+); on success, persist resume state, merge/cleanup the feature branch, and advance to the next feature. TBD: resume state persistence, branch merge/cleanup, roadmap status update.

**Input:** Feature, build attempt number, pass/fail from all preceding gates, baseline HEAD hash (for reset).

**Output:** FeatureRecord appended to results list; loop state updated (built/failed/skipped counters); on failure with retries: git reset + next attempt; on success: loop advances to next feature.

**Goal:** Record the outcome and either retry intelligently on failure or advance cleanly to the next feature on success.

**Metric:** 

### 12. SUMMARY
Write build-summary.json with per-feature records, campaign-level metrics, and tool call / gate activity logs. TBD: tool call records, blocked call logs, token usage, diff stats.

**Input:** All FeatureRecords from the campaign, campaign start time, ModelConfig metadata.

**Output:** logs/build-summary-{timestamp}.json with per-feature records (status, attempt, duration, test_count, error) and campaign totals (built, failed, skipped, total, duration).

**Goal:** Produce a complete, inspectable record of the entire campaign for human review and automated metric tracking.

**Metric:**
