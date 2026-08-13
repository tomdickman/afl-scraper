"""Contract tests for the player career game-number view."""

from pathlib import Path


VIEW_SQL = Path("afl_scraper/storage/tables/player_game_stats_with_career_number.sql")
MIGRATION = Path(
    "afl_scraper/storage/migrations/versions/"
    "81ca20df131b_create_player_career_game_view.py"
)


def test_view_numbers_each_players_games_chronologically():
    sql = " ".join(VIEW_SQL.read_text().split()).lower()

    assert "create view player_game_stats_with_career_number" in sql
    assert "partition by player_stats.player_id" in sql
    assert "order by game.start_date, game.id" in sql
    assert "as career_game_number" in sql
    assert "join game on game.id = player_stats.game_id" in sql


def test_view_exposes_match_context_for_analysis():
    sql = VIEW_SQL.read_text().lower()

    assert "game.start_date" in sql
    assert "game.year" in sql
    assert "game.round" in sql


def test_migration_is_stacked_after_player_stat_identity_change():
    source = MIGRATION.read_text()

    assert 'down_revision: Union[str, Sequence[str], None] = "4f2a6c89d2ef"' in source
    assert "DROP VIEW IF EXISTS player_game_stats_with_career_number" in source
