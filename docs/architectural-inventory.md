# Architectural Inventory — Goals & Metrics

## PRE-BUILD:

### 1. VISION
Generate .specs/vision.md defining what the app is, who it's for, what problem it solves, key screens/areas, tech stack, and design principles.

**Input:** User-provided prompt or doc upload.

**Output:** .specs/vision.md with structured sections: overview, target users, problem statement, key screens, tech stack, design principles, out-of-scope.

**Goal:** Produce a single source of truth for what the app is, sufficient for a roadmap to be derived from it without further human clarification.

**Metric:** 


### 2. DESIGN SYSTEM
Generate .specs/design-system/tokens.md defining the visual vocabulary (colors, spacing, typography, component patterns) that all features must reference.

**Input:** .specs/vision.md (app personality, target users, design principles).

**Output:** .specs/design-system/tokens.md with token categories: colors, spacing, typography, border radii, component patterns.

**Goal:** Establish a consistent visual vocabulary so all features reference the same token names and produce a coherent UI.

**Metric:** 


### 3. ROADMAP
Decompose the vision into right-sized features (S/M/L), identify dependencies between them, sequence into named phases, and write .specs/roadmap.md as a parseable table.

**Input:** .specs/vision.md (key screens, tech stack), existing codebase state (optional, to mark already-built features as done).

**Output:** .specs/roadmap.md with parseable markdown table: ID, name, domain, deps, complexity (S/M/L), notes, status (⬜/✅/🔄/⏸️), grouped by named phases.

**Goal:** Produce an ordered, dependency-aware list of right-sized features that the build loop can consume sequentially without human reordering.

**Metric:** 


### 4. SPEC-FIRST
For each feature on the roadmap, generate .specs/features/{domain}/{feature}.feature.md with YAML front matter (contracts, dependencies, personas, status) and prose body (intent, scenarios, user journey, design token references).

**Input:** .specs/roadmap.md (feature name, complexity, deps), .specs/vision.md (context), .specs/design-system/tokens.md (visual vocabulary).

**Output:** .specs/features/{domain}/{feature}.feature.md per pending feature, each with YAML front matter (feature, domain, status, deps, design_refs) and prose body (intent, scenarios, user journey).

**Goal:** Produce a complete feature specification for each roadmap entry, structured enough for the build agent to implement without requiring additional context.

**Metric:** 


---

## BUILD LOOP:

### 5. INITIALIZE
Load model configuration, resolve project directory, detect build/test commands and project runtimes, load resume state, and acquire campaign lock. TBD: resume state, campaign lock.

**Input:** Model config YAML path, project directory path, optional explicit build/test commands, optional environment variables.

**Output:** Fully configured BuildLoopV2 instance with resolved model config, project dir, build/test commands, detected runtimes, and initialized result tracking.

**Goal:** Establish a valid, locked runtime environment with all configuration resolved before any features are processed.

**Metric:** 


### 6. PARSE ROADMAP
Read .specs/roadmap.md, topologically sort features by dependency, and return the ordered list of buildable features whose dependencies are all complete. TBD: true topological sort, cycle detection.

**Input:** .specs/roadmap.md on disk within project_dir.

**Output:** Ordered list[Feature] of pending features whose dependencies are all satisfied, ready for sequential building.

**Goal:** Produce a correctly ordered list of features that are ready to build, with all dependencies satisfied.

**Metric:** 

### 7. SELECT
Capture baseline HEAD commit and test count, set up the feature branch, construct system and user prompts, and create the EG1 executor scoped to this feature's build. TBD: branch creation, codebase summary injection, learnings injection, fix/retry prompt variants.

**Input:** Current Feature from the parsed list, project_dir, ModelConfig, .specs/features/{domain}/{feature}.feature.md.

**Output:** Baseline HEAD hash, baseline test count, system prompt string, user prompt string, configured BuildAgentExecutor instance.

**Goal:** Capture the pre-build state baseline and construct everything the agent needs to build exactly one feature.

**Metric:** 

### 8. BUILD (EG1)
Invoke the local agent with tool definitions; every tool call is intercepted by EG1, which validates paths, commands, runtime scope, git operations, and npm/npx scope before execution.

**Input:** ModelConfig, system prompt, user prompt, tool definitions (write_file, read_file, run_command), BuildAgentExecutor.

**Output:** AgentResult containing: final output text (with embedded signals), tool call records, turn count, finish reason, duration.

**Goal:** Agent implements the feature while every tool call is validated against deterministic safety and scope constraints before execution.

**Metric:** 

### 9. EG2: SIGNAL PARSE
Mechanically extract FEATURE_BUILT, SPEC_FILE, and SOURCE_FILES from agent output and validate that required signals are present and referenced files exist on disk.

**Input:** AgentResult.output (raw text from agent), project_dir.

**Output:** ParsedSignals with feature_name, spec_file, source_files, valid (bool), errors (list).

**Goal:** Mechanically confirm the agent claims completion and the claimed artifacts exist on disk, with zero inference or interpretation.

**Metric:** 

### 10. GATE
Orchestrator runs the project's build check and test check as subprocesses, capturing pass/fail and test count independently of the agent.

**Input:** build_cmd, test_cmd, project_dir.

**Output:** Build pass/fail + output, test pass/fail + parsed test count + output.

**Goal:** Verify the committed code compiles and all existing tests pass, with execution and result capture fully owned by the orchestrator.

**Metric:** 

### 11. EG3: COMMIT AUTH
Verify HEAD advanced past baseline, working tree is clean, no files outside project root were modified, and test count did not regress below baseline.

**Input:** project_dir, baseline HEAD hash (from SELECT), current test count (from GATE), baseline test count (from SELECT).

**Output:** CommitAuthResult with authorized (bool), checks_passed (list), checks_failed (list), summary.

**Goal:** Verify the git state is clean and no regressions occurred before the loop state advances irreversibly.

**Metric:**


### 12. ADVANCE
Record the feature result; on failure, retry with fix-in-place (attempt 1) or git reset (attempt 2+); on success, persist resume state, merge/cleanup the feature branch, and advance to the next feature. TBD: resume state persistence, branch merge/cleanup, roadmap status update.

**Input:** Feature, build attempt number, pass/fail from all preceding gates, baseline HEAD hash (for reset).

**Output:** FeatureRecord appended to results list; loop state updated (built/failed/skipped counters); on failure with retries: git reset + next attempt; on success: loop advances to next feature.

**Goal:** Record the outcome and either retry intelligently on failure or advance cleanly to the next feature on success.

**Metric:** 

### 13. SUMMARY
Write build-summary.json with per-feature records, campaign-level metrics, and tool call / gate activity logs. TBD: tool call records, blocked call logs, token usage, diff stats.

**Input:** All FeatureRecords from the campaign, campaign start time, ModelConfig metadata.

**Output:** logs/build-summary-{timestamp}.json with per-feature records (status, attempt, duration, test_count, error) and campaign totals (built, failed, skipped, total, duration).

**Goal:** Produce a complete, inspectable record of the entire campaign for human review and automated metric tracking.

**Metric:**
