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

_DEFAULTS = {
    "app": {"version": "0.1.0", "autostart": False},
    "audio": {"device_index": -1, "sample_rate": 16000, "channels": 1},
    "hotkey": {"modifiers": ["ctrl", "alt"], "key": "space"},
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
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load() -> dict:
    cfg = _deep_merge({}, _DEFAULTS)
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "rb") as f:
            on_disk = tomllib.load(f)
        cfg = _deep_merge(cfg, on_disk)
    if not cfg["groq"]["api_key"]:
        cfg["groq"]["api_key"] = os.environ.get("GROQ_API_KEY", "")
    return cfg


def save(cfg: dict) -> None:
    if _HAS_TOMLI_W:
        with open(CONFIG_PATH, "wb") as f:
            tomli_w.dump(cfg, f)
        return

    # Manual fallback writer for simple nested dicts
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
    cfg = load()
    cfg[section][key] = value
    save(cfg)
