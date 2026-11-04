"""Regression tests for deterministic player-game-stat schema migrations."""

from importlib import import_module
from pathlib import Path
from unittest.mock import MagicMock

import pytest

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
    assert "jumper_number int," in current_schema
    assert "jumper_number int not null" not in current_schema
    assert "fantasy_points >= 0" not in current_schema


def test_identity_migration_follows_and_transforms_legacy_schema():
    migration = (
        MIGRATIONS / "4f2a6c89d2ef_use_game_for_player_stats_identity.py"
    ).read_text()

    assert 'down_revision: str | Sequence[str] | None = "098560416458"' in migration
    assert 'op.drop_column("player_game_stats", "player_game_number")' in migration
    assert '["player_id", "game_id"]' in migration


def test_unavailable_stats_migration_is_latest_and_reversible():
    migration = (
        MIGRATIONS / "7d1d45f2a3c8_allow_unavailable_player_stats.py"
    ).read_text()

    assert 'down_revision: str | Sequence[str] | None = "81ca20df131b"' in migration
    assert "nullable=True" in migration
    assert "nullable=False" in migration


def test_historical_loader_migration_qualifies_identities_and_sparse_stats():
    migration = (
        MIGRATIONS / "b6df0c4a1e92_add_source_qualified_identities.py"
    ).read_text()
    current_schema = _normalized(TABLES / "player_game_stats.sql")

    assert 'down_revision: str | Sequence[str] | None = "7d1d45f2a3c8"' in migration
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


def test_hands_oval_venue_migration_follows_current_head_and_updates_seed():
    migration = (MIGRATIONS / "a4d9c2e71b30_add_hands_oval_venue.py").read_text()
    venue_seed = _normalized(REPO_ROOT / "afl_scraper/storage/data/init_venues.sql")

    assert 'down_revision: str | Sequence[str] | None = "b6df0c4a1e92"' in migration
    assert "hands oval" in migration.lower()
    assert "'hands oval', 'hands oval', 'bunbury', 'western australia'" in venue_seed


def test_unavailable_jumper_number_migration_follows_current_head():
    migration = (
        MIGRATIONS / "c8d4f6a2b901_allow_unavailable_jumper_numbers.py"
    ).read_text()

    assert 'down_revision: str | Sequence[str] | None = "a4d9c2e71b30"' in migration
    assert '"jumper_number"' in migration
    assert "nullable=True" in migration
    assert "nullable=False" in migration


def test_negative_fantasy_points_migration_replaces_legacy_check():
    migration = (
        MIGRATIONS / "d3c7f8a91b24_allow_negative_fantasy_points.py"
    ).read_text()

    assert 'down_revision: str | Sequence[str] | None = "c8d4f6a2b901"' in migration
    assert '"player_game_stats_check"' in migration
    assert "op.drop_constraint" in migration
    assert "op.create_check_constraint" in migration
    assert 'NON_NEGATIVE_STAT_CHECK + " AND fantasy_points >= 0"' in migration


def test_long_round_label_migration_follows_current_head():
    migration = (MIGRATIONS / "f2a68bfac932_allow_long_round_labels.py").read_text()

    assert 'down_revision: str | Sequence[str] | None = "d3c7f8a91b24"' in migration
    assert '"game"' in migration
    assert '"round"' in migration
    assert "type_=sa.Text()" in migration
    assert "type_=sa.String(length=20)" in migration
    assert "DROP VIEW IF EXISTS player_game_stats_with_career_number" in migration
    assert "player_game_stats_with_career_number.sql" in migration
    assert "WHERE CHAR_LENGTH(round) > 20" in migration
    assert "Cannot downgrade game.round to VARCHAR(20)" in migration
    upgrade = migration[
        migration.index("def upgrade") : migration.index("def downgrade")
    ]
    assert upgrade.index("_drop_career_game_view()") < upgrade.index("op.alter_column")
    assert upgrade.index("_create_career_game_view()") > upgrade.index(
        "op.alter_column"
    )
    downgrade = migration[migration.index("def downgrade") :]
    assert downgrade.index("_require_rounds_fit_legacy_column()") < downgrade.index(
        "_drop_career_game_view()"
    )

    current_schema = (REPO_ROOT / "afl_scraper/storage/tables/game.sql").read_text()
    assert "round TEXT NOT NULL" in current_schema


def test_long_round_label_downgrade_reports_values_that_do_not_fit(monkeypatch):
    migration = import_module(
        "afl_scraper.storage.migrations.versions."
        "f2a68bfac932_allow_long_round_labels"
    )
    bind = MagicMock()
    bind.execute.return_value.fetchall.return_value = [(17, 34)]
    drop_view = MagicMock()
    monkeypatch.setattr(migration.op, "get_bind", MagicMock(return_value=bind))
    monkeypatch.setattr(migration, "_drop_career_game_view", drop_view)

    with pytest.raises(RuntimeError, match=r"Cannot downgrade.*game 17 \(34 chars\)"):
        migration.downgrade()

    drop_view.assert_not_called()


def test_round_normalization_migration_updates_existing_rows_and_adds_constraint():
    migration = (MIGRATIONS / "6d2f319ec61a_normalize_game_rounds.py").read_text()
    current_schema = (REPO_ROOT / "afl_scraper/storage/tables/game.sql").read_text()

    assert 'down_revision: str | Sequence[str] | None = "f2a68bfac932"' in migration
    for source in (
        "round",
        "opening round",
        "qualifying & elimination finals",
        "finals week 1",
        "semi finals",
        "preliminary finals",
        "grand final",
    ):
        assert source in migration.lower()
    assert "game_round_format" in migration
    assert "game_round_format" in current_schema


def test_qe_merge_migration_removes_qe_from_canonical_rounds():
    migration = (MIGRATIONS / "a37bd1fd30ec_merge_qe_into_qf.py").read_text()
    current_schema = (REPO_ROOT / "afl_scraper/storage/tables/game.sql").read_text()

    assert 'down_revision: str | Sequence[str] | None = "6d2f319ec61a"' in migration
    assert "SET round = 'QF' WHERE round = 'QE'" in migration
    assert "|QE|" not in current_schema


def test_grouped_elimination_final_migration_uses_source_identities():
    migration = (
        MIGRATIONS / "c51e0f33a219_correct_grouped_elimination_finals.py"
    ).read_text()

    assert 'down_revision: str | Sequence[str] | None = "a37bd1fd30ec"' in migration
    assert "identity.source = 'afl_official'" in migration
    assert '"9022"' in migration
    assert '"9025"' in migration
    assert '_set_round("EF")' in migration
