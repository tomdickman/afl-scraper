"""Regression tests for deterministic player-game-stat schema migrations."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TABLES = REPO_ROOT / "afl_scraper/storage/tables"
MIGRATIONS = REPO_ROOT / "afl_scraper/storage/migrations/versions"


def _normalized(path: Path) -> str:
    return " ".join(path.read_text().split()).lower()


def test_initial_migration_uses_immutable_legacy_schema_snapshot():
    migration = (
        MIGRATIONS / "9fe22a591a68_create_player_game_stats_table.py"
    ).read_text()
    legacy_schema = _normalized(TABLES / "player_game_stats_v1.sql")

    assert "player_game_stats_v1.sql" in migration
    assert "player_game_number int not null" in legacy_schema
    assert "primary key (player_id, player_game_number)" in legacy_schema
    assert "unique (player_id, game_id)" in legacy_schema


def test_current_schema_represents_post_migration_identity():
    current_schema = _normalized(TABLES / "player_game_stats.sql")

    assert "player_game_number" not in current_schema
    assert "primary key (player_id, game_id)" in current_schema
    assert "rebound_50s int," in current_schema
    assert "rebound_50s int not null" not in current_schema


def test_identity_migration_follows_and_transforms_legacy_schema():
    migration = (
        MIGRATIONS / "4f2a6c89d2ef_use_game_for_player_stats_identity.py"
    ).read_text()

    assert (
        'down_revision: Union[str, Sequence[str], None] = "098560416458"' in migration
    )
    assert 'op.drop_column("player_game_stats", "player_game_number")' in migration
    assert '["player_id", "game_id"]' in migration


def test_unavailable_stats_migration_is_latest_and_reversible():
    migration = (
        MIGRATIONS / "7d1d45f2a3c8_allow_unavailable_player_stats.py"
    ).read_text()

    assert (
        'down_revision: Union[str, Sequence[str], None] = "81ca20df131b"' in migration
    )
    assert "nullable=True" in migration
    assert "nullable=False" in migration


def test_historical_loader_migration_qualifies_identities_and_sparse_stats():
    migration = (
        MIGRATIONS / "b6df0c4a1e92_add_source_qualified_identities.py"
    ).read_text()
    current_schema = _normalized(TABLES / "player_game_stats.sql")

    assert (
        'down_revision: Union[str, Sequence[str], None] = "7d1d45f2a3c8"' in migration
    )
    assert "player_source_identity.sql" in migration
    assert "game_source_identity.sql" in migration
    assert "game_internal_id_seq" in migration
    for column in (
        "clearances",
        "goal_assists",
        "time_on_ground_percent",
        "fantasy_points",
    ):
        assert f"{column} int not null" not in current_schema
