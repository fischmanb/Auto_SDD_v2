"""Model configuration for local LLM agents.

Defines the ModelConfig dataclass and loading utilities. Configurations
are kept in separate YAML/JSON files so models are interchangeable —
switching from GPT-OSS-120B to 20B (or any OpenAI-compatible model)
is a config file swap, not a code change.

The loop and ExecGate layer consume ModelConfig but never own it.

Dependencies: pyyaml (optional, for YAML loading)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """Configuration for a local LLM served via OpenAI-compatible API.

    Covers connection, generation, context management, and timeout
    parameters. Deliberately model-agnostic — works with any server
    exposing /v1/chat/completions (LM Studio, Ollama, llama.cpp, vLLM).
    """

    # ── Identity ─────────────────────────────────────────────────────
    name: str = "gpt-oss-120b"

    # ── Connection ───────────────────────────────────────────────────
    base_url: str = "http://localhost:1234/v1"
    model: str = "gpt-oss-120b"
    api_key: str = "lm-studio"  # Local servers don't need a real key

    # ── Generation ───────────────────────────────────────────────────
    max_tokens: int = 8192
    temperature: float = 1.0
    top_p: float = 1.0
    reasoning_effort: str = "high"  # low | medium | high

    # ── Context management ───────────────────────────────────────────
    # GPT-OSS model card: "reasoning traces from past assistant turns
    # should be removed" in multi-turn conversations.
    strip_reasoning_older_turns: bool = True

    # ── Loop limits ──────────────────────────────────────────────────
    max_turns: int = 20  # Max tool-call round trips per agent run
    timeout_seconds: int = 600  # Per-completion HTTP timeout

    # ── Role mapping ─────────────────────────────────────────────────
    # Harmony spec uses "developer" for what other models call "system".
    # Set to False if the serving engine doesn't support "developer" role.
    use_developer_role: bool = True

    # ── Optional overrides ───────────────────────────────────────────
    eos_token_ids: list[int] = field(default_factory=list)
    extra_params: dict[str, Any] = field(default_factory=dict)

    # ── Factory methods ──────────────────────────────────────────────

    @classmethod
    def from_yaml(cls, path: Path | str) -> ModelConfig:
        """Load configuration from a YAML file."""
        try:
            import yaml
        except ImportError as exc:
            raise ImportError(
                "pyyaml is required for YAML config loading: "
                "pip install pyyaml"
            ) from exc

        path = Path(path)
        with path.open() as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError(f"Expected dict in {path}, got {type(data)}")

        return cls._from_dict(data, source=str(path))

    @classmethod
    def from_json(cls, path: Path | str) -> ModelConfig:
        """Load configuration from a JSON file."""
        path = Path(path)
        with path.open() as f:
            data = json.load(f)

        return cls._from_dict(data, source=str(path))

    @classmethod
    def _from_dict(cls, data: dict[str, Any], source: str = "") -> ModelConfig:
        """Construct from dict, ignoring unknown keys with a warning."""
        known = set(cls.__dataclass_fields__)
        unknown = set(data) - known
        if unknown:
            logger.warning(
                "Unknown config keys in %s (ignored): %s",
                source or "dict",
                ", ".join(sorted(unknown)),
            )
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    # ── Serialization ────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict (suitable for JSON/YAML dump)."""
        from dataclasses import asdict
        return asdict(self)

    # ── Helpers ──────────────────────────────────────────────────────

    @property
    def system_role(self) -> str:
        """Return the role string to use for system/developer messages."""
        return "developer" if self.use_developer_role else "system"

    def __repr__(self) -> str:
        return (
            f"ModelConfig(name={self.name!r}, model={self.model!r}, "
            f"base_url={self.base_url!r})"
        )
