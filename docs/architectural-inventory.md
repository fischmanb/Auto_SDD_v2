# Architectural Inventory — Goals & Metrics

## PRE-BUILD:

### 1. VISION
**a)** Generate .specs/vision.md defining what the app is, who it's for, what problem it solves, key screens/areas, tech stack, and design principles.
**b) Goal:** Produce a single source of truth for what the app is, sufficient for a roadmap to be derived from it without further human clarification.
**c) Metric:** vision.md exists and contains all required sections (overview, target users, problem statement, key screens, tech stack, design principles). Downstream stage (ROADMAP) can consume it without error.

### 2. DESIGN SYSTEM
**a)** Generate .specs/design-system/tokens.md defining the visual vocabulary (colors, spacing, typography, component patterns) that all features must reference.
**b) Goal:** Establish a consistent visual vocabulary so all features reference the same token names and produce a coherent UI.
**c) Metric:** tokens.md exists with all token categories populated (colors, spacing, typography, component patterns). Every feature spec (stage 4) references only tokens defined in this file.

### 3. ROADMAP
**a)** Decompose the vision into right-sized features (S/M/L), identify dependencies between them, sequence into named phases, and write .specs/roadmap.md as a parseable table.
**b) Goal:** Produce an ordered, dependency-aware list of right-sized features that the build loop can consume sequentially without human reordering.
**c) Metric:** roadmap.md parses into a valid feature table; every feature has ID, name, complexity (S/M/L), deps, and status; no circular dependencies; no feature exceeds L complexity.

### 4. SPEC-FIRST
**a)** For each feature on the roadmap, generate .specs/features/{domain}/{feature}.feature.md with YAML front matter (contracts, dependencies, personas, status) and prose body (intent, scenarios, user journey, design token references).
**b) Goal:** Produce a complete feature specification for each roadmap entry, structured enough for the build agent to implement without requiring additional context.
**c) Metric:** Spec file exists for every pending feature on the roadmap; YAML front matter parses without error; required fields present (feature, domain, status); prose body is non-empty with at least one scenario.

---

## BUILD LOOP:

### 5. INITIALIZE
**a)** Load model configuration, resolve project directory, detect build/test commands and project runtimes, load resume state, and acquire campaign lock. TBD: resume state, campaign lock.
**b) Goal:** Establish a valid, locked runtime environment with all configuration resolved before any features are processed.
**c) Metric:** ModelConfig loads without error; project_dir exists and is a git repo; build and test commands resolved (detected or explicit); at least one project runtime detected.

### 6. PARSE ROADMAP
**a)** Read .specs/roadmap.md, topologically sort features by dependency, and return the ordered list of buildable features whose dependencies are all complete. TBD: true topological sort, cycle detection.
**b) Goal:** Produce a correctly ordered list of features that are ready to build, with all dependencies satisfied.
**c) Metric:** Returned feature list is non-empty (or campaign ends cleanly with log); no feature appears in the list before its dependencies; every returned feature has status=pending with all deps in status=done.

### 7. SELECT
**a)** Capture baseline HEAD commit and test count, set up the feature branch, construct system and user prompts, and create the EG1 executor scoped to this feature's build. TBD: branch creation, codebase summary injection, learnings injection, fix/retry prompt variants.
**b) Goal:** Capture the pre-build state baseline and construct everything the agent needs to build exactly one feature.
**c) Metric:** Baseline HEAD hash is non-empty; baseline test count captured (or explicitly null if no test command); system and user prompts are non-empty strings; EG1 executor initialized with correct project_root and detected runtimes.

### 8. BUILD (EG1)
**a)** Invoke the local agent with tool definitions; every tool call is intercepted by EG1, which validates paths, commands, runtime scope, git operations, and npm/npx scope before execution.
**b) Goal:** Agent implements the feature while every tool call is validated against deterministic safety and scope constraints before execution.
**c) Metric:** AgentResult.finish_reason == "stop" (agent completed voluntarily); agent completed within max_turns; zero EG1 blocks indicating sandbox escape attempts (legitimate blocks of forbidden operations are working-as-intended).

### 9. EG2: SIGNAL PARSE
**a)** Mechanically extract FEATURE_BUILT, SPEC_FILE, and SOURCE_FILES from agent output and validate that required signals are present and referenced files exist on disk.
**b) Goal:** Mechanically confirm the agent claims completion and the claimed artifacts exist on disk, with zero inference or interpretation.
**c) Metric:** ParsedSignals.valid == True; FEATURE_BUILT is non-empty and matches the feature name the agent was asked to build; SPEC_FILE exists on disk and resolves within project_dir.

### 10. GATE
**a)** Orchestrator runs the project's build check and test check as subprocesses, capturing pass/fail and test count independently of the agent.
**b) Goal:** Verify the committed code compiles and all existing tests pass, with execution and result capture fully owned by the orchestrator.
**c) Metric:** Build check returncode == 0; test check returncode == 0; test count parsed successfully (non-null integer).

### 11. EG3: COMMIT AUTH
**a)** Verify HEAD advanced past baseline, working tree is clean, no files outside project root were modified, and test count did not regress below baseline.
**b) Goal:** Verify the git state is clean and no regressions occurred before the loop state advances irreversibly.
**c) Metric:** CommitAuthResult.authorized == True; all 4 sub-checks pass: head_advanced, tree_clean, no_contamination, test_regression (current >= baseline).

### 12. ADVANCE
**a)** Record the feature result; on failure, retry with fix-in-place (attempt 1) or git reset (attempt 2+); on success, persist resume state, merge/cleanup the feature branch, and advance to the next feature. TBD: resume state persistence, branch merge/cleanup, roadmap status update.
**b) Goal:** Record the outcome and either retry intelligently on failure or advance cleanly to the next feature on success.
**c) Metric:** FeatureRecord written with correct status (built/failed/skipped) and timestamp; on failure with retries remaining: next attempt triggered; on success: loop index advances (or campaign completes); on final failure: feature recorded as failed and loop continues.

### 13. SUMMARY
**a)** Write build-summary.json with per-feature records, campaign-level metrics, and tool call / gate activity logs. TBD: tool call records, blocked call logs, token usage, diff stats.
**b) Goal:** Produce a complete, inspectable record of the entire campaign for human review and automated metric tracking.
**c) Metric:** build-summary.json written; contains per-feature records with status, attempt, duration, and test_count; campaign totals are arithmetically correct (built + failed + skipped == total); file is valid JSON.
