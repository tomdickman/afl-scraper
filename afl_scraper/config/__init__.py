"""Packaged, validated application configuration."""

from functools import cache
from importlib.resources import files
from pathlib import Path
from typing import Any

import json5


@cache
def load_jsonc_path(path: Path) -> dict[str, Any]:
    """Load a JSON-with-comments document once per filesystem path."""
    value = json5.loads(path.read_text(encoding="utf-8"), allow_duplicate_keys=False)
    if not isinstance(value, dict):
        raise ValueError(f"Configuration must contain a JSON object: {path}")
    return value


@cache
def load_config(name: str) -> dict[str, Any]:
    """Load a named configuration resource bundled with the package."""
    resource = files(__package__).joinpath(name)
    value = json5.loads(
        resource.read_text(encoding="utf-8"), allow_duplicate_keys=False
    )
    if not isinstance(value, dict):
        raise ValueError(f"Configuration must contain a JSON object: {name}")
    return value


__all__ = ["load_config", "load_jsonc_path"]
