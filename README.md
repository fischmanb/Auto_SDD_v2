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
│   │   ├── exec_gates/      ← [Step 5] EG implementations
│   │   └── scripts/         ← [Step 4] build_loop_v2.py entry point
│   └── tests/               ← [Step 6] Test suite
├── scripts/
│   └── validate_tool_calling.py ← [Step 2] LM Studio + GPT-OSS tool-call validation
├── docs/                    ← Architecture notes, module map
└── .venv/                   ← Python virtual env (openai, pyyaml)
```

## Implementation Steps

| Step | Status | Description |
|------|--------|-------------|
| 1    | ✅ Done | Model config contract + local agent client |
| 2    | ✅ Done | Tool-call validation script (test LM Studio + GPT-OSS) |
| 3    | ⬜ Next | Module map (classify current build_loop.py: core vs extension) |
| 4    | ⬜      | Skeleton (stripped four-step loop: SELECT→BUILD→GATE→ADVANCE) |
| 5    | ⬜      | ExecGate implementations (EG1: tool calls, EG2: signal parse, EG3: commit auth) |
| 6    | ⬜      | Tests (adapted from existing suite, covering core loop only) |

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

## Model Config

Models are interchangeable via YAML config files in `config/models/`.
The loop talks to `http://localhost:{port}/v1/chat/completions` —
whether LM Studio, Ollama, or llama.cpp is behind that endpoint
is a config value, not a code change.
