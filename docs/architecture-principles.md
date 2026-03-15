# V2 Architecture Principles

> Governing design decisions for the Simplified Build Loop V2.
> These are not aspirational — they constrain what the code can do.

---

## P1: The agent's only meaningful output is committed code

The agent writes files, runs commands, and commits. Everything after
the commit — test execution, build verification, signal validation,
test count comparison — is the orchestrator's job. The agent does not
run tests, does not report test results, and does not decide whether
to continue after a failure.

**Why**: Agents self-report inaccurately. They "helpfully" modify tests
to make them pass, delete tests they can't fix, report partial results
as complete, and choose to continue past failures that should block.
IFEval-style instruction following drops from ~80% to ~36% on
production-like constraints (OctoCodingBench). The agent cannot be
trusted to evaluate its own work.

**Implementation**:

```
V1 (current):
  agent builds → agent runs tests → agent reports results → gate reads report
  (agent controls what gets reported)

V2 (required):
  agent builds → agent commits → orchestrator runs tests → gate reads results
  (agent never touches test execution)
```

The orchestrator captures test count BEFORE the agent runs (baseline),
then runs tests AFTER the agent commits (current), and compares. If
tests were deleted or modified to pass, the count delta reveals it.

**ExecGate enforcement**: EG5 (commit auth) owns test regression
detection. EG3 (`check_build()`) and EG4 (`check_tests()`) from
the exec_gates modules run as subprocess calls from the orchestrator,
not through the agent's tool calls.

---

## P2: The agent cannot reach the orchestrator

The orchestrator code (Auto_SDD_v2) and the target project are in
separate directory trees. The agent's tool calls are sandboxed to
`project_root` — file reads, writes, and command execution are all
path-contained. The agent cannot:

- Read the ExecGate source to learn restriction patterns
- Modify the orchestrator code to weaken gates
- Access the model config to change its own parameters
- Read files outside the project via allowed commands (cat, grep, etc.)

**Implementation**: EG1 validates every file path argument (both in
tool calls and in command arguments) against `project_root` containment.
`cat ~/Auto_SDD_v2/...` is blocked. `grep -r pattern /etc/` is blocked.
Symlink traversal is caught by `Path.resolve()` before containment check.

---

## P3: Deterministic Python gates replace probabilistic agent judgment

Every verification step that can be expressed as deterministic code
MUST be. Agent judgment is reserved only for genuinely creative tasks
(writing implementation code). Specifically:

| Check | V1 (agent) | V2 (orchestrator) |
|-------|------------|-------------------|
| Test execution | Agent runs, self-reports | Orchestrator subprocess |
| Build verification | Agent reports | `check_build()` subprocess |
| Signal extraction | Agent self-assessment | EG2 mechanical parse |
| Commit validation | Agent says "committed" | EG5 git state check |
| Scope containment | Prompt instruction | EG1 path validation |
| Test regression | Agent "notices" | EG5 count comparison |
| Command safety | Prompt instruction | EG1 9-layer validation |

The cost of deterministic checks is zero (microseconds of Python).
The cost of missing a check is a broken build, wasted compute, or
corrupted project state.

---

## P4: The agent proposes; the gate disposes

The agent never executes anything directly. Every tool call is a
REQUEST that passes through the EG1 intercept before execution.
The gate validates, then either executes or rejects. The rejection
reason is fed back to the agent so it can try a different approach.

```
model output → parse tool call → [EG1 intercept] → execute or block
                                       ↓
                              9 validation layers:
                              1. First-token blocklist
                              2. Recursive rm pattern
                              3. Shell injection patterns
                              4. Blocked-anywhere tokens
                              5. Command argument containment
                              6. Git subcommand + branch
                              7. npm/npx scope (from package.json)
                              8. Runtime allowlist (from stack)
                              9. Base command allowlist
```

---

## P5: Stack awareness is derived, not assumed

The executor does not hardcode what runtime commands are allowed.
It derives them from the project:

- `package.json` → node runtime commands + npm scripts + npx packages
- `pyproject.toml` → python runtime commands
- `Cargo.toml` → rust runtime commands
- Explicit `allowed_runtimes` parameter overrides auto-detection

A Python project cannot run npm. A Node project cannot run Python
(unless both markers are present). The executor is configured once
at construction and the allowlists are immutable for the session.

---

## P6: Extensions are stripped, not commented

V2 is the four-step core: SELECT → BUILD → GATE → ADVANCE.
Features from V1 that are not on this path (eval sidecar, drift
check, code review, CIS vectors, pattern analysis, auto-QA) are
deleted from the V2 codebase, not commented out. They can be
re-added when needed, behind feature flags, through the extension
interface. Commented-out code is dead code that misleads readers.


---

## DP-1: No manual intervention

The system must be autonomous end-to-end. Manual steps in the critical
path (writing gate files per feature, reviewing intermediate outputs,
approving transitions between phases) are design failures, not safety
features. If a step requires a human, the system isn't automated —
it's a tool with a human bottleneck.

This does not mean humans are absent. Humans author specs, configure
the system, review campaign results, and improve the process. But the
loop itself — from "next pending feature" to "feature committed" —
runs without human intervention.

---

## DP-2: No LLM judgment in verification

Verification and gating must be deterministic Python. LLM judgment
in the verification path reintroduces the compliance band problem
(36% OctoCodingBench ceiling) at the point where reliability matters
most. If a gate uses an LLM to decide pass/fail, the gate itself has
a ~36% chance of being wrong on production-like constraints.

This applies to all verification, regardless of where in the pipeline
it occurs: post-build drift checks, pre-build gate generation, spec
preprocessing that produces enforcement rules — if an LLM decides
whether the implementation is correct, it's a DP-2 violation.

---

## P7: LLM judgment is irreducible in implementation

Someone must decide what code to write. That decision is inherently
LLM judgment (or human judgment, which violates DP-1). This is not
a problem to solve — it's a boundary to accept.

The deterministic gates (EG1, EG2, EG3, EG4, EG5, build checks, test checks)
catch everything that can be caught mechanically:

- Agent didn't commit → EG5
- Agent broke existing tests → EG5 regression check
- Agent touched forbidden files → EG1 path gate
- Agent ran forbidden commands → EG1 command gate
- Agent didn't emit signals → EG2
- Code doesn't compile → EG3 build check
- Existing tests fail → EG4 test check

The gap between "compiles and passes tests" and "actually implements
the spec correctly" requires judgment. That judgment lives in the
build agent — the one place where LLM judgment is irreducible.

**Spreading judgment across phases does not reduce risk.** If a
pre-build phase uses LLM judgment to generate verification criteria,
and the build phase uses LLM judgment to implement, the two
interpretations can disagree. The disagreement manifests as false
build failures (valid implementation rejected by misaligned gates)
or as a new failure class: cross-phase drift. This is worse than
the original problem because it's harder to diagnose.

**The correct response to the Class C gap** ("agent built something
that compiles but isn't what the spec intended") is:

1. Write better specs (clearer intent = better agent output)
2. Write better project tests (acceptance criteria in the test suite
   itself, not in orchestrator gates)
3. Accept that no automated system can verify natural-language intent
   with 100% reliability

The orchestrator's job is to enforce the mechanical boundary. The
spec author's job is to make intent unambiguous. The test suite's
job is to encode acceptance criteria. These are separate concerns
and mixing them (by having the orchestrator generate or evaluate
acceptance criteria) violates both DP-2 and separation of concerns.
