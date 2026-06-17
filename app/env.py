"""Minimal .env loader — stdlib only, no dotenv dependency.

Reads a .env file and sets variables into os.environ using setdefault, so
already-set environment variables are never overwritten. Call load_env() once
at process startup (app/run.py) before any os.environ.get() calls.

Supported syntax:
    KEY=value
    KEY="value with spaces"
    KEY='value with spaces'
    # comment lines are ignored
    blank lines are ignored
    inline # comments are NOT supported (kept simple intentionally)
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_COMMENT = re.compile(r"^\s*#")
_PAIR = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$")


def _strip_quotes(value: str) -> str:
    """Remove a matching pair of leading/trailing quotes if present."""
    if len(value) >= 2:
        if (value[0] == '"' and value[-1] == '"') or \
           (value[0] == "'" and value[-1] == "'"):
            return value[1:-1]
    return value


def load_env(path: str | Path = ".env") -> dict[str, str]:
    """Load key=value pairs from *path* into os.environ (setdefault).

    Returns the dict of variables that were actually set (already-present vars
    are excluded). Missing .env file is silently ignored — the project runs
    fine with variables set through the shell or CI environment instead.
    """
    env_path = Path(path)
    if not env_path.is_file():
        return {}

    loaded: dict[str, str] = {}
    with env_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip() or _COMMENT.match(line):
                continue
            m = _PAIR.match(line)
            if not m:
                continue
            key, raw_value = m.group(1), m.group(2).strip()
            value = _strip_quotes(raw_value)
            if os.environ.setdefault(key, value) == value:
                loaded[key] = value   # only record what we actually set

    return loaded
