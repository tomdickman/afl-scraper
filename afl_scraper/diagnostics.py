"""Shared bounded formatting helpers for operator-facing diagnostics."""


def summarize_identifiers(identifiers: list[str], limit: int = 10) -> str:
    """Format a deterministic bounded identifier sample for diagnostics."""
    if limit <= 0:
        raise ValueError("identifier summary limit must be positive")
    sample = ", ".join(identifiers[:limit])
    remaining = len(identifiers) - limit
    return sample if remaining <= 0 else f"{sample} (+{remaining} more)"
