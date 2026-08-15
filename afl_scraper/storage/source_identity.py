"""Database helpers for source-qualified player and match identities."""

from collections.abc import Iterable


def _validate_source_identity(source: str, source_id: str) -> None:
    if not source.strip() or not source_id.strip():
        raise ValueError("Source and source ID must not be blank")


def load_player_source_id_map(
    conn,
    source: str,
    year: int,
    source_player_ids: Iterable[str],
) -> dict[str, str]:
    if not source.strip():
        raise ValueError("Source must not be blank")
    identifiers = sorted(set(source_player_ids))
    if not identifiers:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT source_player_id, player_id
            FROM player_source_identity
            WHERE source = %(source)s
              AND year = %(year)s
              AND source_player_id = ANY(%(source_player_ids)s)
            """,
            {
                "source": source,
                "year": year,
                "source_player_ids": identifiers,
            },
        )
        mappings = dict(cur.fetchall())

    missing = sorted(set(identifiers) - set(mappings))
    if missing:
        raise ValueError(
            f"Missing {len(missing)} {source} player mappings for {year}: "
            f"{', '.join(missing)}"
        )
    return mappings


def allocate_game_id(conn, source: str, source_match_id: str) -> tuple[int, bool]:
    """Resolve an internal game ID while serialising concurrent first loads."""
    _validate_source_identity(source, source_match_id)
    identity = f"{source}:{source_match_id}"
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%(identity)s, 0))",
            {"identity": identity},
        )
        cur.execute(
            """
            SELECT game_id
            FROM game_source_identity
            WHERE source = %(source)s AND source_match_id = %(source_match_id)s
            """,
            {"source": source, "source_match_id": source_match_id},
        )
        row = cur.fetchone()
        if row is not None:
            return row[0], False
        cur.execute("SELECT nextval('game_internal_id_seq')")
        return cur.fetchone()[0], True


def save_game_source_identity(
    conn, source: str, source_match_id: str, game_id: int
) -> None:
    _validate_source_identity(source, source_match_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO game_source_identity (source, source_match_id, game_id)
            VALUES (%(source)s, %(source_match_id)s, %(game_id)s)
            ON CONFLICT (source, source_match_id) DO UPDATE
            SET game_id = EXCLUDED.game_id
            WHERE game_source_identity.game_id = EXCLUDED.game_id
            """,
            {
                "source": source,
                "source_match_id": source_match_id,
                "game_id": game_id,
            },
        )
        if cur.rowcount != 1:
            raise RuntimeError(
                f"Game identity {source}:{source_match_id} is already bound "
                "to a different internal game"
            )
