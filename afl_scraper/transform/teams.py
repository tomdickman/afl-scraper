from ..normalization import canonical_team


def transform_team_name(value: str) -> str:
    """Backward-compatible name for canonical team normalization."""
    return canonical_team(value)
