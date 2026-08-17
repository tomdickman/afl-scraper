"""Shared bounded formatting helpers for operator-facing diagnostics."""

from collections.abc import Iterable


def summarize_identifiers(identifiers: Iterable[str], limit: int = 10) -> str:
    """Format a deterministic bounded identifier sample for diagnostics."""
    if limit <= 0:
        raise ValueError("identifier summary limit must be positive")
    ordered = sorted(identifiers)
    sample = ", ".join(ordered[:limit])
    remaining = len(ordered) - limit
    return sample if remaining <= 0 else f"{sample} (+{remaining} more)"
