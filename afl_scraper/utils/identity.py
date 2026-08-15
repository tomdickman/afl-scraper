"""Shared conservative identity normalization helpers."""

import re


_TERMINAL_NAME_SUFFIXES = {
    "jr",
    "jnr",
    "junior",
    "sr",
    "snr",
    "senior",
}


def normalize_person_name(name: str) -> str:
    """Normalize source formatting differences without resolving nicknames."""
    without_apostrophes = re.sub(r"['’]", "", name.casefold())
    parts = without_apostrophes.replace("-", " ").split()
    if parts and parts[-1].rstrip(".") in _TERMINAL_NAME_SUFFIXES:
        parts.pop()
    return " ".join(
        part
        for index, part in enumerate(parts)
        if not (0 < index < len(parts) - 1 and len(part.rstrip(".")) == 1)
    )
