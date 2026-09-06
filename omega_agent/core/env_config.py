"""Environment variable helpers for OMEGA Config."""

import os
from typing import Optional


def env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None or not str(raw).strip().isdigit():
        return default
    return int(raw)


def env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def env_optional_str(key: str) -> Optional[str]:
    raw = os.environ.get(key)
    return raw.strip() if raw else None
