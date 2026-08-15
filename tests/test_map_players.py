"""Tests for cross-source player identity matching and review."""

import json
from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from afl_scraper.cli import cli
from afl_scraper.models.player import MatchResult, PlayerInfo, PlayerMapping
from afl_scraper.transform import map_players


def player(
    player_id: str,
    name: str = "Alex Smith",
    team: str = "Carlton",
) -> PlayerInfo:
    first_name, last_name = name.split(" ", 1)
    return PlayerInfo(
        id=player_id,
        firstName=first_name,
        lastName=last_name,
        team=team,
        year=2026,
    )


def test_exact_match_normalizes_names_and_team_aliases():
    result = map_players.match_players(
        [player("afl-1", "Darcy O'Brien", "Brisbane Lions")],
        [player("tables-1", "darcy obrien", "Brisbane")],
    )

    assert [(match.afl.id, match.tables.id) for match in result.exact] == [
        ("afl-1", "tables-1")
    ]
    assert not result.fuzzy
    assert not result.unmatched_afl
    assert not result.unmatched_tables


def test_historical_kangaroos_name_matches_north_melbourne():
    result = map_players.match_players(
        [player("afl-1", "Brent Harvey", "North Melbourne")],
        [player("tables-1", "Brent Harvey", "Kangaroos")],
    )

    assert [(match.afl.id, match.tables.id) for match in result.exact] == [
        ("afl-1", "tables-1")
    ]


def test_name_suffix_omitted_by_one_source_matches_within_same_team():
    result = map_players.match_players(
        [player("7536", "Robert Hansen Jr", "North Melbourne")],
        [player("Robert_Hansen", "Robert Hansen", "North Melbourne")],
    )

    assert [(match.afl.id, match.tables.id) for match in result.exact] == [
        ("7536", "Robert_Hansen")
    ]


def test_middle_initial_omitted_by_one_source_matches_within_same_team():
    result = map_players.match_players(
        [player("629", "Josh P. Kennedy", "Sydney Swans")],
        [player("Josh_Kennedy1", "Josh Kennedy", "Sydney")],
    )

    assert [(match.afl.id, match.tables.id) for match in result.exact] == [
        ("629", "Josh_Kennedy1")
    ]


def test_nickname_mismatch_with_same_team_and_surname_is_reviewable_not_exact():
    result = map_players.match_players(
        [player("1243", "Marty Mattner", "Sydney Swans")],
        [player("Martin_Mattner", "Martin Mattner", "Sydney")],
    )

    assert not result.exact
    assert [(match.afl.id, [p.id for p in match.tables]) for match in result.fuzzy] == [
        ("1243", ["Martin_Mattner"])
    ]
    assert not result.unmatched_afl


def test_duplicate_names_are_matched_deterministically_by_team():
    result = map_players.match_players(
        [player("afl-syd", team="Sydney Swans"), player("afl-gws", team="GWS Giants")],
        [
            player("tables-gws", team="Greater Western Sydney"),
            player("tables-syd", team="Sydney"),
        ],
    )

    assert {(match.afl.id, match.tables.id) for match in result.exact} == {
        ("afl-syd", "tables-syd"),
        ("afl-gws", "tables-gws"),
    }
    assert not result.fuzzy


def test_duplicate_name_and_team_remains_ambiguous_for_review():
    result = map_players.match_players(
        [player("afl-1"), player("afl-2")],
        [player("tables-1"), player("tables-2")],
    )

    assert not result.exact
    assert [match.afl.id for match in result.fuzzy] == ["afl-1", "afl-2"]
    assert all(
        [candidate.id for candidate in match.tables] == ["tables-1", "tables-2"]
        for match in result.fuzzy
    )
    assert not result.unmatched_afl
    assert not result.unmatched_tables


def test_duplicate_name_with_no_remaining_candidate_is_unmatched():
    result = map_players.match_players(
        [player("afl-carlton"), player("afl-essendon", team="Essendon")],
        [player("tables-carlton")],
    )

    assert [(match.afl.id, match.tables.id) for match in result.exact] == [
        ("afl-carlton", "tables-carlton")
    ]
    assert [item.id for item in result.unmatched_afl] == ["afl-essendon"]
    assert not result.fuzzy


def test_duplicate_source_ids_are_rejected_before_matching():
    with pytest.raises(ValueError, match="Duplicate AFL Official player ID: afl-1"):
        map_players.match_players(
            [player("afl-1"), player("afl-1", "Different Player")],
            [],
        )


def test_team_mismatch_is_presented_for_review_not_auto_approved():
    result = map_players.match_players(
        [player("afl-1", team="Carlton")],
        [player("tables-1", team="Essendon")],
    )

    assert not result.exact
    assert result.fuzzy[0].afl.id == "afl-1"
    assert [candidate.id for candidate in result.fuzzy[0].tables] == ["tables-1"]


def test_missing_team_is_not_auto_approved():
    result = map_players.match_players(
        [player("afl-1", team="")],
        [player("tables-1", team="")],
    )

    assert not result.exact
    assert [match.afl.id for match in result.fuzzy] == ["afl-1"]


def test_players_without_same_name_are_unmatched_on_the_correct_source():
    result = map_players.match_players(
        [player("afl-only", "AFL Only")],
        [player("tables-only", "Tables Different")],
    )

    assert [item.id for item in result.unmatched_afl] == ["afl-only"]
    assert [item.id for item in result.unmatched_tables] == ["tables-only"]
    assert not result.exact
    assert not result.fuzzy


@pytest.mark.parametrize(
    ("mappings", "message"),
    [
        (
            [
                PlayerMapping(afl_official_id="afl-1", player_id="tables-1"),
                PlayerMapping(afl_official_id="afl-2", player_id="tables-1"),
            ],
            "Duplicate AFL Tables player ID",
        ),
        (
            [
                PlayerMapping(afl_official_id="afl-1", player_id="tables-1"),
                PlayerMapping(afl_official_id="afl-1", player_id="tables-2"),
            ],
            "Duplicate AFL Official player ID",
        ),
    ],
)
def test_validate_mappings_rejects_one_to_many_output(mappings, message):
    with pytest.raises(ValueError, match=message):
        map_players.validate_mappings(mappings)


def test_player_mapping_trims_ids_and_rejects_blanks():
    mapping = PlayerMapping(afl_official_id=" afl-1 ", player_id=" tables-1 ")
    assert mapping.afl_official_id == "afl-1"
    assert mapping.player_id == "tables-1"

    with pytest.raises(ValueError, match="must not be blank"):
        PlayerMapping(player_id="  ")


def test_upsert_validates_before_opening_database(monkeypatch):
    open_pool = Mock()
    monkeypatch.setattr(map_players, "admin_connection_pool", open_pool)
    mappings = [
        PlayerMapping(afl_official_id="afl-1", player_id="tables-1"),
        PlayerMapping(afl_official_id="afl-2", player_id="tables-1"),
    ]

    with pytest.raises(ValueError, match="Duplicate AFL Tables player ID"):
        map_players.upsert_mappings(mappings, 2026)
    open_pool.assert_not_called()


def test_upsert_persists_only_real_source_identities(monkeypatch):
    connection = Mock()

    @contextmanager
    def pool():
        yield connection

    monkeypatch.setattr(map_players, "admin_connection_pool", pool)
    mappings = [
        PlayerMapping(afl_official_id="afl-1", player_id="tables-1"),
        PlayerMapping(player_id="tables-2"),
    ]

    assert map_players.upsert_mappings(mappings, 2026) == 1
    assert connection.execute.call_count == 1
    assert connection.execute.call_args_list[0].args[1] == {
        "source_player_id": "afl-1",
        "player_id": "tables-1",
        "year": 2026,
    }


def test_review_does_not_create_identity_rows_for_unmatched_players(tmp_path):
    matches = MatchResult(
        exact=[],
        fuzzy=[],
        unmatched_afl=[player("official-only", "AFL Only")],
        unmatched_tables=[player("tables-only", "Tables Only")],
    )
    review_file = tmp_path / "review.json"
    review_file.write_text(matches.model_dump_json(by_alias=True))

    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["map", "review", "--year", "2026", "--input", str(review_file)],
        )
        assert result.exit_code == 0, result.output
        approved = json.loads(
            (tmp_path.cwd() / "data/mapping/2026_approved.json").read_text()
        )

    assert approved == []
    assert "an AFL Tables player is required before mapping" in result.output


def test_review_skips_ambiguous_match_by_default(tmp_path):
    matches = MatchResult(
        exact=[],
        fuzzy=[
            {
                "afl": player("official-1"),
                "tables": [player("tables-1"), player("tables-2")],
            }
        ],
        unmatched_afl=[],
        unmatched_tables=[],
    )
    review_file = tmp_path / "review.json"
    review_file.write_text(matches.model_dump_json(by_alias=True))

    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["map", "review", "--year", "2026", "--input", str(review_file)],
            input="\n",
        )
        assert result.exit_code == 0, result.output
        output_path = tmp_path.cwd() / "data/mapping/2026_approved.json"
        assert json.loads(output_path.read_text()) == []
