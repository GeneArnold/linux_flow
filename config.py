"""Config loader and writer for linux_flow.toml.

The TOML file lives next to this module. On first run it may not exist —
_DEFAULTS covers every key so the app starts safely without it.

Key design decisions:
- _deep_merge lets the on-disk file override only the keys it declares;
  missing keys fall back to defaults automatically.
- GROQ_API_KEY env var is a fallback so CI/server use works without a toml.
- tomli_w (optional) writes proper TOML. If absent, the manual fallback
  writer handles simple nested dicts (all we need).

When adding new settings, add them to _DEFAULTS first so old configs
without that key still work.
"""

import os
import tomllib
from pathlib import Path
from typing import Any

try:
    import tomli_w

    _HAS_TOMLI_W = True
except ImportError:
    _HAS_TOMLI_W = False

CONFIG_PATH = Path(__file__).parent / "linux_flow.toml"

# Default values for every setting. The on-disk TOML is merged on top of these,
# so any missing key silently falls back to the default here.
_DEFAULTS = {
    "app": {"version": "0.1.0", "autostart": False},
    "audio": {"device_index": -1, "sample_rate": 16000, "channels": 1},
    "hotkey": {"modifiers": ["ctrl"], "key": "space"},
    "groq": {
        "api_key": "",
        "whisper_model": "whisper-large-v3",
        "llm_model": "llama-3.3-70b-versatile",
    },
    "enhancement": {"mode": "clean"},
    "output": {"auto_paste": True, "save_history": True},
    "ui": {"overlay_position": "bottom"},
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict.
    Nested dicts are merged; all other values are replaced by override.
    """
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load() -> dict:
    """Load config from disk merged with defaults.
    Safe to call repeatedly — reads from disk each time (no caching).
    """
    cfg = _deep_merge({}, _DEFAULTS)
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "rb") as f:
            on_disk = tomllib.load(f)
        cfg = _deep_merge(cfg, on_disk)
    # Allow API key to come from environment (useful for CI or server deployments)
    if not cfg["groq"]["api_key"]:
        cfg["groq"]["api_key"] = os.environ.get("GROQ_API_KEY", "")
    return cfg


def save(cfg: dict) -> None:
    """Write the full config dict to disk as TOML.
    Prefer tomli_w if available; fall back to a manual serialiser for simple cases.
    """
    if _HAS_TOMLI_W:
        with open(CONFIG_PATH, "wb") as f:
            tomli_w.dump(cfg, f)
        return

    # Manual fallback — handles bool, str, list[str], and numeric values.
    # Sufficient for our config structure; does not handle nested lists or None.
    lines = []
    for section, values in cfg.items():
        lines.append(f"\n[{section}]")
        for k, v in values.items():
            if isinstance(v, bool):
                lines.append(f"{k} = {'true' if v else 'false'}")
            elif isinstance(v, str):
                lines.append(f'{k} = "{v}"')
            elif isinstance(v, list):
                items = ", ".join(f'"{i}"' for i in v)
                lines.append(f"{k} = [{items}]")
            else:
                lines.append(f"{k} = {v}")
    CONFIG_PATH.write_text("\n".join(lines).lstrip() + "\n")


def set_value(section: str, key: str, value: Any) -> None:
    """Update a single key in a section and save. Used by UI settings pages."""
    cfg = load()
    cfg[section][key] = value
    save(cfg)
