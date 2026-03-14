"""Tests for ModelConfig."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from auto_sdd.lib.model_config import ModelConfig


class TestModelConfigDefaults:
    def test_default_values(self) -> None:
        cfg = ModelConfig()
        assert cfg.name == "gpt-oss-120b"
        assert cfg.base_url == "http://localhost:1234/v1"
        assert cfg.temperature == 1.0
        assert cfg.top_p == 1.0
        assert cfg.max_turns == 20
        assert cfg.use_developer_role is True
        assert cfg.strip_reasoning_older_turns is True

    def test_system_role_developer(self) -> None:
        cfg = ModelConfig(use_developer_role=True)
        assert cfg.system_role == "developer"

    def test_system_role_system(self) -> None:
        cfg = ModelConfig(use_developer_role=False)
        assert cfg.system_role == "system"

    def test_repr(self) -> None:
        cfg = ModelConfig(name="test", model="m", base_url="http://x")
        r = repr(cfg)
        assert "test" in r
        assert "http://x" in r


class TestModelConfigYaml:
    def test_from_yaml(self, tmp_path: Path) -> None:
        p = tmp_path / "cfg.yaml"
        p.write_text(yaml.dump({
            "name": "test-model",
            "model": "test-123",
            "base_url": "http://localhost:9999/v1",
            "max_turns": 10,
            "temperature": 0.5,
        }))
        cfg = ModelConfig.from_yaml(p)
        assert cfg.name == "test-model"
        assert cfg.model == "test-123"
        assert cfg.max_turns == 10
        assert cfg.temperature == 0.5

    def test_unknown_keys_ignored(self, tmp_path: Path) -> None:
        p = tmp_path / "cfg.yaml"
        p.write_text(yaml.dump({
            "name": "test",
            "model": "m",
            "totally_fake_key": True,
        }))
        cfg = ModelConfig.from_yaml(p)
        assert cfg.name == "test"
        assert not hasattr(cfg, "totally_fake_key")

    def test_invalid_yaml_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "cfg.yaml"
        p.write_text("not: a: valid: yaml: [")
        with pytest.raises(Exception):
            ModelConfig.from_yaml(p)


class TestModelConfigJson:
    def test_from_json(self, tmp_path: Path) -> None:
        p = tmp_path / "cfg.json"
        p.write_text(json.dumps({"name": "j", "model": "jm", "max_tokens": 4096}))
        cfg = ModelConfig.from_json(p)
        assert cfg.name == "j"
        assert cfg.max_tokens == 4096

    def test_to_dict_roundtrip(self) -> None:
        cfg = ModelConfig(name="rt", model="rtm")
        d = cfg.to_dict()
        assert d["name"] == "rt"
        assert d["model"] == "rtm"
        cfg2 = ModelConfig(**{k: v for k, v in d.items()})
        assert cfg2.name == cfg.name
