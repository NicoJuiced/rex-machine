"""Configuration management for rex-machine.

Config hierarchy (later wins):
  1. Global config:  ~/.config/rex-machine/config.json  (credentials, provider)
  2. Project config: .rex-machine.json in analyzed repo  (model, output, options)
  3. Env vars:       ANTHROPIC_API_KEY, etc.              (credentials override)
  4. CLI flags:      --model, --provider, etc.            (override everything)
"""

from __future__ import annotations

import json
from pathlib import Path

_CONFIG_DIR = Path.home() / ".config" / "rex-machine"
_GLOBAL_CONFIG = _CONFIG_DIR / "config.json"
_PROJECT_FILE = ".rex-machine.json"

DEFAULT_PROJECT_CONFIG = {
    "model": "claude-sonnet-4-6",
    "output": "console",
    "max_tool_calls": 30,
}


def global_config_path() -> Path:
    return _GLOBAL_CONFIG


def load_global() -> dict:
    if _GLOBAL_CONFIG.is_file():
        return json.loads(_GLOBAL_CONFIG.read_text(encoding="utf-8"))
    return {}


def save_global(config: dict) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    _GLOBAL_CONFIG.write_text(json.dumps(config, indent=2), encoding="utf-8")
    try:
        _GLOBAL_CONFIG.chmod(0o600)
    except OSError:
        pass


def load_project(repo_path: str | Path) -> dict:
    p = Path(repo_path) / _PROJECT_FILE
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def save_project(repo_path: str | Path, config: dict) -> Path:
    p = Path(repo_path) / _PROJECT_FILE
    p.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return p


def merge(repo_path: str | Path) -> dict:
    """Merge global + project configs. Project wins on overlap."""
    g = load_global()
    p = load_project(repo_path)
    merged = {**g, **p}
    return merged
