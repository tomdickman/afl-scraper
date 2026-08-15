"""Validation and persistence for source-qualified player mappings."""

from ..models import SourcePlayerMapping
from ..storage import admin_connection_pool


def validate_source_mappings(mappings: list[SourcePlayerMapping]) -> None:
    source_ids: set[str] = set()
    player_ids: set[str] = set()
    for mapping in mappings:
        if mapping.source_player_id in source_ids:
            raise ValueError(f"Duplicate source player ID: {mapping.source_player_id}")
        if mapping.player_id in player_ids:
            raise ValueError(f"Duplicate canonical player ID: {mapping.player_id}")
        source_ids.add(mapping.source_player_id)
        player_ids.add(mapping.player_id)


def validate_source_mapping_coverage(
    required_source_ids: set[str], mappings: list[SourcePlayerMapping]
) -> None:
    validate_source_mappings(mappings)
    mapped = {mapping.source_player_id for mapping in mappings}
    missing = sorted(required_source_ids - mapped)
    extra = sorted(mapped - required_source_ids)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing {len(missing)}: {', '.join(missing)}")
        if extra:
            details.append(f"unexpected {len(extra)}: {', '.join(extra)}")
        raise ValueError("Source mapping coverage mismatch; " + "; ".join(details))


def upsert_source_mappings(
    mappings: list[SourcePlayerMapping], year: int, source: str
) -> int:
    validate_source_mappings(mappings)
    with admin_connection_pool() as conn:
        with conn.transaction():
            for mapping in mappings:
                conn.execute(
                    """
                    INSERT INTO player_source_identity
                      (source, source_player_id, player_id, year)
                    VALUES (%(source)s, %(source_player_id)s, %(player_id)s, %(year)s)
                    ON CONFLICT (source, source_player_id, year) DO UPDATE
                    SET player_id = EXCLUDED.player_id,
                        updated_at = NOW()
                    """,
                    {
                        "source": source,
                        "source_player_id": mapping.source_player_id,
                        "player_id": mapping.player_id,
                        "year": year,
                    },
                )
    return len(mappings)
