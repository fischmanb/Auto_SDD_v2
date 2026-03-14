# Session Handoff — ExecGate Review

> Last updated: 2026-03-12
> Purpose: Maintain rigor across sessions when reviewing/hardening ExecGates.
> A new session reads this FIRST before touching any EG code.
> After each review session: update this file, commit, push.

---

## Review Protocol

Walk through every check in every ExecGate module one at a time. For each:
1. State the logic (what it does mechanically)
2. Classify by failure type: A (malicious), B (structural), C (semantic/logic)
3. Identify gaps (what it doesn't catch, false positives, bypasses)
4. Decide: implement fix, defer, or accept risk
5. Test: every fix gets a smoke test before commit

The principle: these are deterministic Python on the orchestrator — zero
token cost, microsecond execution. Be as comprehensive as possible.

---

## Architecture Principles Established (docs/architecture-principles.md)

- **P1**: Agent's only meaningful output is committed code. Tests run by orchestrator.
- **P2**: Agent cannot reach orchestrator code (path-contained sandbox).
- **P3**: Deterministic Python gates replace probabilistic agent judgment.
- **P4**: Agent proposes; gate disposes (9-layer validation).
- **P5**: Stack awareness derived from project markers, not assumed.
- **P6**: Extensions stripped, not commented.

---

## EG1: Tool Call Gate (eg1_tool_calls.py, 806 lines) — REVIEW IN PROGRESS

### Checks REVIEWED and HARDENED:

**Check 1: Command blocklist + first-token matching** ✅
- 30+ blocked first tokens (dd, sudo, curl, eval, open, osascript, etc.)
- First-token extraction (no substring collisions — "dd" no longer matches "git add")
- Recursive rm pattern blocked regardless of target
- 17 shell injection patterns (command substitution, pipes, chaining, background)
- chmod/chown/chgrp blocked via word-boundary regex
- Write-then-exec tracking (agent writes .sh then tries to run it → blocked)
- package.json modification + npm run → blocked
- Smoke tested: 26 tests passing

**Check 2: Command allowlist (stack-aware)** ✅
- Runtime commands derived from project markers (package.json→node, pyproject.toml→python, etc.)
- npm install: only no-args (uses existing package.json). `npm install lodash` → blocked.
- npm run: validated against scripts in package.json. Unknown scripts → blocked.
- npx: validated against devDependencies + runtime binary aliases. Unknown packages → blocked.
- No package.json + no runtime detected → npm/npx entirely blocked.
- Python project cannot run npm. Node project cannot run python. Mixed project gets both.
- Smoke tested: 42 tests passing (full regression)

**Check 3: Path validation + containment** ✅
- System dirs blocked: /etc/, /usr/, /bin/, /sbin/, /var/, /System/, /Library/, /tmp/
- Exact filename blocking: .env, .env.local, .env.production, .env.staging, .npmrc, .yarnrc, .netrc
- .env.example and .env.development.template ALLOWED (not exact match)
- node_modules/.cache blocked (build cache tampering)
- .git/ blocked (no direct git internals manipulation)
- Path containment: absolute paths and .. traversal resolved and checked against project_root
- Symlink escape: caught by Path.resolve() before containment check
- Smoke tested: 32 tests passing

**Check 4: Command argument containment** ✅
- cat, ls, find, grep, head, tail, cp, mv, mkdir, touch — all non-flag arguments
  are checked against project_root. Agent cannot `cat ~/Auto_SDD_v2/exec_gates/...`
  or `grep -r password /etc/`.
- Blocks: absolute paths, ~ expansion, .. traversal, $ variable expansion
- Allows: relative paths within project, glob patterns (shell expands relative to cwd)
- Smoke tested: 32 tests passing

**Check 5: Git branch protection** ✅
- Allowed subcommands: add, commit, status, diff, log, show, rev-parse, branch (list only)
- Blocked with specific messages: push, merge, rebase, reset, checkout, switch, stash,
  pull, fetch, remote, config, clean
- git branch -d/-D (delete) and -m/-M (rename) blocked
- Orchestrator owns push/merge/reset/checkout operations
- Smoke tested: 42 tests passing (full regression)

### Checks NOT YET REVIEWED:

**Check 6: Unknown tool rejection**
- Current: if tool name not in {write_file, read_file, run_command} → blocked
- Needs review: Should the tool set be configurable? What if GPT-OSS
  invents tool names that don't match our definitions?

**Check 7: Malformed argument rejection**
- Current: if `_parse_error` key in arguments dict → blocked
- Needs review: What happens if arguments have valid JSON but wrong types?
  e.g., path is an int, content is a list. Currently only checked for
  write_file (isinstance str check). read_file and run_command need
  similar type validation.

---

## EG2: Signal Parse (eg2_signal_parse.py, 171 lines) — NOT YET REVIEWED

Three checks to walk through:

**Check 1: FEATURE_BUILT extraction + required presence**
- Logic: scan for `FEATURE_BUILT: <value>` lines, last occurrence wins
- Review needed: What if the agent embeds the signal in a code block or
  quotes? Should we require it on its own line? What about partial matches
  like `FEATURE_BUILT_PARTIAL: ...`?

**Check 2: SPEC_FILE extraction + disk existence + containment**
- Logic: scan for `SPEC_FILE: <path>`, resolve against project_dir (L-00217), check exists
- Review needed: What if agent emits a path to a file it just created
  (not the real spec file)? The existence check passes but the content
  could be anything. Should we validate the file content looks like a spec?

**Check 3: SOURCE_FILES extraction**
- Logic: scan for `SOURCE_FILES: <comma or space separated list>`
- Review needed: This is informational only (not gating). Should it be?
  If the agent claims it wrote files that don't exist on disk, that's a
  signal of hallucination. Could add disk-existence validation for source
  files too.

---

## EG3: Commit Auth (eg3_commit_auth.py, 207 lines) — NOT YET REVIEWED

Four checks to walk through:

**Check 1: HEAD advanced**
- Logic: compare current HEAD against branch_start_commit
- Review needed: What if the agent made a commit and then amended/reset
  it to the same hash? (reset is blocked by EG1, but this is defense in depth)

**Check 2: Tree clean (no tracked modifications)**
- Logic: `git status --porcelain`, filter out `??` (untracked)
- Review needed: Should untracked files be a warning or failure? Current
  behavior is warning only. An untracked file could be an agent artifact
  that should have been committed (missing from the commit) or should have
  been cleaned up. V1 treats untracked as warning — same risk tolerance?

**Check 3: No contamination (files outside project root)**
- Logic: `git diff --name-only start..HEAD`, resolve each path
- Review needed: This duplicates _check_contamination in EG1's path
  validation. Is the duplication intentional (defense in depth) or
  should they share implementation? The EG1 check is per-tool-call;
  the EG3 check is post-commit (catches anything that slipped through).

**Check 4: Test count regression**
- Logic: compare current_test_count vs baseline_test_count
- Review needed: Per P1 (architecture principles), the ORCHESTRATOR
  runs tests, not the agent. So the flow is:
    1. Orchestrator captures baseline test count BEFORE agent runs
    2. Agent builds + commits
    3. Orchestrator runs tests AFTER commit (via check_tests())
    4. EG3 compares counts
  This means check_tests() must return a reliable count. Need to verify
  build_gates.py's test count parsing handles all frameworks (jest,
  vitest, pytest, mocha, etc.) or at minimum the ones we'll encounter.
  Also: test count is necessary but not sufficient. Agent could delete
  a failing test and add a trivial passing test — count unchanged but
  coverage decreased. Should we add a test file hash comparison?

---

## Open Design Questions (for next session)

1. **Test content integrity**: Test count alone doesn't catch test
   deletion + replacement. Options: file hash comparison of test dir,
   diff of test files specifically, or accept the risk for V2 and add
   coverage tracking later.

2. **EG1 tool set extensibility**: The current tool set (write_file,
   read_file, run_command) is hardcoded. Should this be configurable
   per-project? For example, a project might want a `list_directory`
   tool or a `search_codebase` tool.

3. **Agent prompt awareness of EG constraints**: Should the agent be
   TOLD about the ExecGate restrictions in its system prompt? Pro:
   fewer wasted tool calls (agent knows not to try `git push`).
   Con: reveals the restriction set, enabling targeted evasion.
   Current lean: tell the agent about allowed tools and their
   constraints, but don't reveal the enforcement mechanism.

---

## Project State Summary

| Step | Status | Files |
|------|--------|-------|
| 1 | ✅ Done | model_config.py, local_agent.py, YAML configs |
| 2 | ✅ Done | validate_tool_calling.py (run on Studio machine to validate LM Studio) |
| 3 | ✅ Done | docs/module-map.md |
| 4 | ✅ Done | Skeleton (747 lines) — SELECT→BUILD→GATE→ADVANCE with EGs wired |
| 5a | ✅ Done (review in progress) | eg1 (806 lines), eg2 (171 lines), eg3 (207 lines) |
| 5b | ✅ Done | EGs wired into skeleton in Step 4 |
| 6a | ⬜ Next | Unit tests for EGs + model_config + local_agent |
| 6b | ⬜ Blocked | Integration tests (after Step 4) |

### To resume the EG review:
1. Read this file
2. Read docs/architecture-principles.md
3. Start at "Checks NOT YET REVIEWED" section above (EG1 checks 6-7, then EG2, then EG3)
4. Follow the review protocol at the top of this file
5. Update this file after each check is reviewed
