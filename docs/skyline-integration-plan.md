# Selective Integration Plan: Skyline → Auto_SDD_v2

Source: `/Users/sorel/Downloads/Skyline_Vault_Share-main/`
Target: `/Users/sorel/Auto_SDD_v2/`

---

## TAKE — deterministic, tested, no LLM dependency

### 1. Quarantine runtime gates → new EG7

Source: `services/quarantine_runtime/governed_quarantine_gates.py` (388 lines, tested)
Also: `governed_quarantine_contract.py`, `governed_quarantine_preflight.py`, `types.py`, `mount_path_validation.py`

Purpose: Pre/post execution gates for running foreign code in isolation. SHA256 content hashing, provenance validation, mount policy enforcement, secret grant coherence, artifact scanning, network admissibility.

Integration point: When Auto_SDD_v2 runs agent-generated code in sandbox (EG3/EG4), wrap execution with quarantine pre-gate (validate spec before running) and post-gate (validate outputs before merging). Currently EG3/EG4 run subprocess directly — quarantine gates add provenance tracking and output artifact scanning.

New module: `py/auto_sdd/exec_gates/eg7_quarantine.py`
Adapt: Strip Docker/Apple Container backends. Keep the gate logic. Wire `QuarantineGovernedRunSpec` to Auto_SDD_v2's `Feature` dataclass. Pre-gate runs before `check_build()`, post-gate runs after `check_tests()`.

### 2. Deterministic validation layer → EG6 enhancement

Source: `services/equity/validation/deterministic.py` (108 lines, tested)
Also: `services/real_estate/validation/deterministic.py` (same pattern)

Purpose: Schema contract enforcement, internal state coherence checks, evidence packet required-field validation, artifact existence verification. No LLM.

Integration point: EG6 (spec adherence) currently checks SOURCE_MATCH, FILE_PLACEMENT, TOKEN_EXISTENCE, NAMING_CONVENTION. Add contract validation pattern: verify that agent-emitted signals have required fields, that spec front matter is internally consistent, that referenced files exist. Skyline's `_check_packet_contract()` pattern maps directly to validating `.feature.md` front matter fields.

Extend: `py/auto_sdd/exec_gates/eg6_spec_adherence.py` with contract checks adapted from Skyline's deterministic validators.

### 3. Doctrine store → knowledge system alternative persistence

Source: `services/doctrine/store.py` (195 lines, tested)
Also: `services/doctrine/models.py`, `capture.py`, `normalize.py`, `gaps.py`

Purpose: File-based knowledge persistence with topics, normalized rules, patch proposals (approve/reject), append-only history. Simpler than SQLite+FTS5.

Integration point: Auto_SDD_v2's knowledge system uses SQLite+FTS5 (`knowledge_system/store.py`, 650 lines). Doctrine's file-based approach is useful as a secondary persistence layer — human-readable JSON files alongside the SQLite DB. When the knowledge system promotes a clue to hardened status, also write a doctrine topic file. When a gate failure creates a mistake node, also write a doctrine patch proposal. This gives an inspectable, git-trackable knowledge trail.

New module: `py/auto_sdd_v2/knowledge_system/doctrine_export.py`
Wire: Call after `_kg_post_gate()` in build loop. Read-only for the build loop — doctrine files are for human inspection and cross-project portability.

### 4. Policy files → build loop configuration

Source: `policies/` directory (30+ YAML files)
Key files: `approval_rules.yaml`, `agent_permissions.yaml`, `budget_limits.yaml`, `environment_rules.yaml`

Purpose: Declarative policy definitions — what agents can do, spending limits, which tools are allowed, approval thresholds.

Integration point: Auto_SDD_v2 currently hardcodes EG1 allowlists, retry limits, and turn budgets in Python. Extract these to YAML policy files. `agent_permissions.yaml` maps to EG1's allowlist. `budget_limits.yaml` maps to `max_retries`, `max_turns`, API cost caps. `environment_rules.yaml` maps to `readonly_paths`, `protected_paths`.

New directory: `config/policies/`
Adapt: Don't adopt Skyline's schema verbatim — translate to Auto_SDD_v2 concepts. `ModelConfig` already loads YAML; extend the pattern.

### 5. Bootstrap enforcement → campaign startup hardening

Source: `bootstrap/enforce.py`, `bootstrap/handshake.py`, `bootstrap/config.py` (tested, 51 tests)

Purpose: Gatekeeper pattern — block system startup if prerequisites are unavailable. Config validation, secrets availability check, health models.

Integration point: `BuildLoopV2.__init__()` currently does minimal validation. Adopt the `enforce_handshake_or_exit(strict=True)` pattern: verify API key is set, project is a git repo, specs directory exists, model config is valid, resume state is readable — all before preflight. Currently some of these fail silently mid-campaign.

Extend: Add preflight checks to `build_loop_v2.py` `__init__()` using the handshake pattern.

### 6. Skill intake airlock → external tool onboarding for knowledge system

Source: `services/skill_intake/airlock.py`, `static_audit.py`, `security_precheck_card.py`, `intake.py`

Purpose: Governed pipeline for bringing external code into the system. Static audit, security precheck, quarantine trial, capability classification, governor review.

Integration point: When Auto_SDD_v2 encounters a new stack or framework it hasn't built for before, the airlock pattern can gate whether to proceed. Static audit scans for dangerous patterns before the agent touches the project. Security precheck validates that the target project doesn't contain hostile code. This is relevant for the `--project-dir` entry point — currently Auto_SDD_v2 trusts the target project entirely.

New module: `py/auto_sdd/lib/project_audit.py`
Scope: Static checks only. No quarantine trial (overkill for target projects). Scan for suspicious patterns in package.json scripts, Makefile targets, pre/post-install hooks.

---

## SKIP — LLM-as-judge, wrong pattern, or not applicable

### Governor agent (LLM gate)

Source: `services/governor/agent.py`
Reason: Uses Claude to decide PROCEED/BLOCK/REQUIRE_HUMAN. Violates P3 (deterministic gates replace probabilistic judgment). The quarantine gates underneath it are deterministic and valuable — the governor wrapper is not.

### CrewAI orchestrator

Source: `services/orchestrator.py`
Reason: Linear Architect→Governor→Builder→Sandbox→Evaluator flow with no retry, no dep sorting, no parallel execution, no resume state. Auto_SDD_v2's build loop is strictly more capable. The orchestrator pattern (single-task crews) is also inefficient — one CrewAI kickoff per step.

### Scout / extraction / browser automation

Source: `services/scout/`, `services/extraction/`, all playwright-dependent code
Reason: Domain-specific to equity research and web scraping. Not applicable to code generation. The extraction protocols (Finviz, Seeking Alpha, SEC EDGAR) are Charlie's business logic.

### Equity / real estate workflows

Source: `services/equity/`, `services/real_estate/`
Reason: Domain-specific research and evaluation pipelines. The deterministic validation layers inside them are taken (item 2 above), but the workflow orchestration and LLM critique layers are not applicable.

### Coach / teacher agents

Source: `services/coach_lite/`, `services/teacher/`
Reason: LLM-based recommendation and coaching. Auto_SDD_v2's knowledge system handles learning through deterministic promotion (SQL lift calculation), not LLM coaching.

### Streamlit operator console

Source: `apps/operator_console/`
Reason: UI layer. Valuable concept but wrong integration path — would need to be built for Auto_SDD_v2's data model, not adapted from Skyline's. Defer to when Auto_SDD_v2 needs a dashboard.

### Discord bot

Source: `services/discord/`
Reason: Conversational interface to Skyline workflows. Not applicable to build loop.

---

## Implementation order

1. Bootstrap enforcement (smallest, immediate value, no new modules)
2. Policy files (config change, no code logic)
3. Deterministic validation → EG6 (extends existing gate)
4. Quarantine gates → EG7 (new gate, tested pattern)
5. Doctrine export (new module, additive, non-blocking)
6. Project audit airlock (new module, optional safety layer)

Estimated scope: ~800 lines new code, ~200 lines adapted from Skyline, 6 sessions.
