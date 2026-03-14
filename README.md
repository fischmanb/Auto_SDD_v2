# Auto-SDD V2 — Simplified Build Loop

Stripped-down build loop for local model execution with deterministic ExecGate enforcement.

## Directory Structure

```
Auto_SDD_v2/
├── config/
│   └── models/              ← Model configs (YAML). Swap file to switch model.
│       ├── gpt-oss-120b.yaml   (primary)
│       └── gpt-oss-20b.yaml    (fallback)
├── py/
│   ├── auto_sdd/
│   │   ├── lib/             ← Core library modules
│   │   │   ├── model_config.py  ← [Step 1] ModelConfig dataclass
│   │   │   └── local_agent.py   ← [Step 1] Completion loop + EG1 boundary
│   │   ├── exec_gates/      ← [Step 5a] EG implementations
│   │   │   ├── eg1_tool_calls.py    ← Path/command validation + execution
│   │   │   ├── eg2_signal_parse.py  ← Mechanical signal extraction
│   │   │   └── eg3_commit_auth.py   ← Final commit authorization checks
│   │   └── scripts/
│   │       ├── build_loop_v2.py     ← [Step 4] Core loop: SELECT→BUILD→GATE→ADVANCE
│   └── tests/               ← [Step 6] Test suite
├── scripts/
│   └── validate_tool_calling.py ← [Step 2] LM Studio + GPT-OSS tool-call validation
├── docs/
│   └── module-map.md        ← [Step 3] Core vs extension classification
└── .venv/                   ← Python virtual env (openai, pyyaml)
```

## Implementation Steps

| Step | Status | Description |
|------|--------|-------------|
| 1    | ✅ Done | Model config contract + local agent client |
| 2    | ✅ Done | Tool-call validation script (test LM Studio + GPT-OSS) |
| 3    | ✅ Done | Module map (classify current build_loop.py: core vs extension) |
| 4    | ✅ Done | Skeleton (stripped four-step loop: SELECT→BUILD→GATE→ADVANCE) |
| 5a   | ✅ Done | ExecGate implementations (EG1: tool calls, EG2: signal parse, EG3: commit auth) |
| 5b   | ✅ Done | EGs wired into skeleton in Step 4 |
| 6a   | ⬜ Next | Unit tests for EGs + model_config + local_agent |
| 6b   | ⬜      | Integration tests |
| 7a   | ⬜      | v1 port: reliability.py (true topo sort, resume state, locking) |
| 7b   | ⬜      | v1 port: branch_manager.py (feature branches, cleanup) |
| 7c   | ⬜      | v1 port: build_gates.py (structured results, framework detection) |
| 7d   | ⬜      | v1 port: prompt_builder.py (codebase summary, learnings, fix/retry) |
| 7e   | ⬜      | v1 port: codebase_summary.py (agent-generated summary, git tree cache) |

## Core Loop: SELECT → BUILD → GATE → ADVANCE

The V2 loop is four steps with three ExecGate intercepts:

- **SELECT**: Read roadmap, topo-sort, pick next, build prompt
- **EG: prompt scope** → validates prompt before agent sees it
- **BUILD**: Fresh agent context, implement feature, commit + emit signals
- **EG: tool calls** → primary intercept at tool-call boundary (EG1)
- **EG: signal parse** → mechanical extraction of FEATURE_BUILT / SPEC_FILE (EG2)
- **GATE**: HEAD advanced, tree clean, tsc/build, tests pass
- **EG: commit auth** → final check before state advances (EG3)
- **ADVANCE**: Update roadmap, commit, next feature

## Prerequisites

**Hardware**: Mac Studio, 256GB unified memory (Apple Silicon)

**Python**: 3.11+ (tested on 3.13.5)

**Local model server**: LM Studio (primary, uses MLX on Apple Silicon)
- Download: https://lmstudio.ai
- Load GPT-OSS-120B (or 20B for faster inference)
- Server must be running on `localhost:1234` before running validation or the loop
- Ensure the model's tool-calling / function-calling mode is enabled

**Model weights** (download via LM Studio UI or CLI):
- Primary: `gpt-oss-120b` (~65-80GB in MXFP4/GGUF)
- Fallback: `gpt-oss-20b` (~16-40GB in GGUF Q4_K_M)

## Setup

```bash
cd ~/Auto_SDD_v2

# Create virtual environment
python3 -m venv .venv

# Activate
source .venv/bin/activate

# Install dependencies
pip install openai pyyaml

# Verify
python3 -c "import openai; import yaml; print('deps OK')"
```

### Python Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `openai` | >=1.0 | OpenAI-compatible client for Chat Completions API |
| `pyyaml` | >=6.0 | Model config YAML loading |

Future steps will add:
- `pytest` — test suite (Step 6)
- Additional deps TBD as EG implementations land (Step 5)

### Running the Validation Script (Step 2)

```bash
# Start LM Studio with GPT-OSS loaded, then:
source .venv/bin/activate
python scripts/validate_tool_calling.py

# Or with a specific model config:
python scripts/validate_tool_calling.py config/models/gpt-oss-20b.yaml
```

The script runs 6 tests: connectivity, simple completion, tool-call round trip,
multi-turn chains, blocked tool recovery, and run_local_agent integration.
All tests must pass before proceeding to build loop integration.

## Model Config

Models are interchangeable via YAML config files in `config/models/`.
The loop talks to `http://localhost:{port}/v1/chat/completions` —
whether LM Studio, Ollama, or llama.cpp is behind that endpoint
is a config value, not a code change.

### Switching models

Copy an existing config, change `model` and `name`, point the loop at it.
No code changes. The `base_url` can also change if running a different
server (Ollama defaults to `:11434`, llama.cpp to `:8080`).

## Step 7: v1 Library Ports

The Step 4 skeleton has working minimal implementations for roadmap parsing,
prompt construction, and build/test checks. Step 7 replaces these with the
full v1 modules, adding robustness and edge case handling. The skeleton runs
end-to-end without these — they make it production-grade.

**Priority order** (each substep is independently useful):

| Substep | v1 Module | Lines | What it adds over the skeleton |
|---------|-----------|-------|-------------------------------|
| 7a | `reliability.py` | ~600 | True topological sort (handles diamond deps), resume state (crash recovery), file locking (prevents concurrent runs), cycle detection |
| 7b | `branch_manager.py` | ~200 | Feature branch creation/cleanup, worktree management. Without this the agent commits to main. |
| 7c | `build_gates.py` | ~730 | Structured result types, auto-detection of build/test commands across frameworks, dependency health check. Replaces inline subprocess calls. |
| 7d | `prompt_builder.py` | ~575 | Codebase summary injection, learnings injection, filesystem boundary constraints, fix/retry prompt variants, context budget estimation. This is what makes the Nth feature smarter than the first. |
| 7e | `codebase_summary.py` | ~240 | Agent-generated project summary cached by git tree hash, injected into prompts. Depends on 7d. |

**What gets stripped during port** (per P6 — extensions deleted, not commented):
- `reliability.py`: DriftPair, run_parallel_drift_checks
- `build_gates.py`: check_dead_exports, check_lint (re-add as optional later)
- `branch_manager.py`: independent/sequential strategies (start with chained only)
- `prompt_builder.py`: eval sidecar feedback injection, pattern analysis context

**What gets adapted** (interface changes for V2):
- `claude_wrapper.py` references → `local_agent.py` (already done in skeleton)
- Prompt format: Claude CLI instructions → tool-use agent instructions
- Build gates: agent-reported results → orchestrator-executed results (P1)
