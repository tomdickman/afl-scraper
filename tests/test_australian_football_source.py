"""Contract tests for the AustralianFootball 2006-2011 adapter."""

from contextlib import contextmanager
from datetime import datetime, timezone
import importlib

import pytest
from bs4 import BeautifulSoup
from click.testing import CliRunner

import afl_scraper.cli as cli_module
from afl_scraper.scraper import australian_football as source


scraper_package = importlib.import_module("afl_scraper.scraper")


FINALS = (
    "Second Qualifying Final",
    "First Elimination Final",
    "Second Elimination Final",
    "First Qualifying Final",
    "Second Semi-final",
    "First Semi-final",
    "First Preliminary Final",
    "Second Preliminary Final",
    "Grand Final",
)


def season_html(year=2006, match_count=185):
    final_labels = FINALS + (("Grand Final Replay",) if year == 2010 else ())
    regular_rounds = 24 if year == 2011 else 22
    regular_season_matches = match_count - len(final_labels)
    links = iter(range(1, match_count + 1))
    sections = []
    for round_number in range(1, regular_rounds + 1):
        round_count = regular_season_matches // regular_rounds
        if round_number <= regular_season_matches % regular_rounds:
            round_count += 1
        round_links = "".join(
            f'<a href="/game/view/{next(links)}">[Stats]</a>'
            for _ in range(round_count)
        )
        sections.append(
            f"<h4>Round {round_number}<a>[Round Review]</a></h4>"
            f"<table><tr><td>{round_links}</td></tr></table>"
        )
    for label in final_labels:
        match_id = next(links)
        sections.append(
            f"<h4>{label}</h4><table><tr><td>"
            f'<a href="/game/view/{match_id}">[Stats]</a>'
            # Live final tables can repeat the same match link within a section.
            f'<a href="/game/view/{match_id}">details</a>'
            "</td></tr></table>"
        )
    return (
        "<html><head><title>Australian Football - AFL Premiership Season - "
        f"Season {year}</title></head><body>{''.join(sections)}</body></html>"
    )


def player_table(team, first_id):
    headers = "".join(
        f"<th>{header}</th>"
        for header in (
            "#",
            "Player",
            "K",
            "M",
            "H",
            "D",
            "G",
            "B",
            "HO",
            "T",
            "FF",
            "FA",
            "Age",
            "Games",
            "G",
        )
    )
    rows = []
    for index in range(22):
        player_id = first_id + index
        cells = [
            str(index + 1),
            f'<a href="/players/player/Player%2B{index}/{player_id}">'
            f"Family{index}, Given{index}</a>",
            "1",
            "1",
            "2",
            "3",
            "0",
            "0",
            "0",
            "1",
            "1",
            "0",
            "25y 1d",
            "20",
            "4",
        ]
        rows.append("<tr>" + "".join(f"<td>{value}</td>" for value in cells) + "</tr>")
    rows.append("<tr><td>Totals</td></tr>")
    return (
        '<table class="details_table stats"><thead>'
        f'<tr><th colspan="2">{team}</th><th colspan="11">Match Stats</th>'
        '<th colspan="2">Career</th></tr>'
        f"<tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def match_html(year=2006):
    return f"""
    <html>
      <head><title>Australian Football - Match Details: {year} R10 Collingwood vs Brisbane</title></head>
      <body>
        <h2>Collingwood vs Brisbane</h2>
        <table class="details_table">
          <tr><td>Round: 10 Venue: M.C.G. Date: Sat, 03-06-{year} 7:10 pm Crowd: 54,820</td></tr>
          <tr><td>Collingwood</td><td>3.5</td><td>6.6</td><td>11.10</td><td>16.13.109</td><td>C: Coach</td></tr>
          <tr><td>Brisbane</td><td>2.2</td><td>5.5</td><td>8.7</td><td>12.11.83</td><td>C: Coach</td></tr>
          <tr><td></td><td>COLL by 26</td></tr>
        </table>
        {player_table("Collingwood", 1000)}
        {player_table("Brisbane", 2000)}
      </body>
    </html>
    """


def test_2006_season_contract_discovers_all_matches_and_deduplicates_links(monkeypatch):
    original = source._round_match_ids
    parsed_headings = []

    def record_parse(heading):
        parsed_headings.append(source._round_label(heading))
        return original(heading)

    monkeypatch.setattr(source, "_round_match_ids", record_parse)
    manifest = source.parse_australian_football_season(
        season_html(),
        2006,
        discovered_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )

    assert manifest.match_count == 185
    assert len(manifest.rounds) == 31
    assert manifest.rounds[0].label == "Round 1"
    assert manifest.rounds[-1].label == "Grand Final"
    assert manifest.match_ids == list(range(1, 186))
    assert parsed_headings == [round_.label for round_ in manifest.rounds]


def test_season_contract_rejects_partial_and_cross_round_duplicate_results():
    with pytest.raises(ValueError, match="contains 184 matches; expected.*185"):
        source.parse_australian_football_season(season_html(match_count=184), 2006)

    soup = BeautifulSoup(season_html(), "html.parser")
    second_round_link = soup.find_all("h4")[1].find_next_sibling("table").find("a")
    second_round_link["href"] = "/game/view/1"
    with pytest.raises(ValueError, match="appeared in more than one round"):
        source.parse_australian_football_season(str(soup), 2006)


@pytest.mark.parametrize(
    ("year", "match_count", "group_count"),
    [(2010, 186, 32), (2011, 196, 33)],
)
def test_expansion_and_grand_final_replay_seasons_have_reviewed_totals(
    year, match_count, group_count
):
    manifest = source.parse_australian_football_season(
        season_html(year, match_count), year
    )

    assert manifest.match_count == match_count
    assert len(manifest.rounds) == group_count


def test_source_year_boundary_is_explicit():
    with pytest.raises(ValueError, match="supports 2006-2011"):
        source.australian_football_season_url(2005)
    with pytest.raises(ValueError, match="supports 2006-2011"):
        source.australian_football_season_url(2012)


def test_access_refusal_suggests_visible_browser_retry():
    class Page:
        url = source.australian_football_season_url(2006)

    class Response:
        ok = False
        status = 403

    with pytest.raises(RuntimeError) as error:
        source._validate_navigation(
            Page(), Response(), source.australian_football_season_url(2006), "season"
        )

    assert str(error.value) == (
        "AustralianFootball season page returned HTTP 403; if using headless mode, "
        "retry with a visible browser (`--no-headless`)"
    )


def test_match_contract_parses_stable_ids_and_only_published_statistics():
    match = source.parse_australian_football_match(match_html(), 2006)

    assert match.details.home_team == "Collingwood"
    assert match.details.away_team == "Brisbane"
    assert match.details.home_team_total == 109
    assert match.details.crowd == 54820
    assert len(match.home_team_stats) == len(match.away_team_stats) == 22
    first = match.home_team_stats[0]
    assert first.source_player_id == "1000"
    assert first.player_name == "Given0 Family0"
    assert first.kicks == 1
    assert first.handballs == 2
    assert first.disposals == 3
    assert first.free_kicks_for == 1
    assert "clearances" not in first.model_dump()
    assert "fantasy_points" not in first.model_dump()


def test_match_contract_accepts_source_spacing_inside_score_totals():
    spaced_scores = (
        match_html().replace("16.13.109", "16.13. 109").replace("12.11.83", "12.11. 83")
    )

    match = source.parse_australian_football_match(spaced_scores, 2006)

    assert match.details.home_team_total == 109
    assert match.details.away_team_total == 83


def test_match_contract_accepts_compact_finals_metadata():
    finals_page = match_html().replace("Round: 10 Venue:", "2EF Venue:")

    match = source.parse_australian_football_match(finals_page, 2006)

    assert match.details.round == "2EF"
    assert match.details.venue == "M.C.G."


@pytest.mark.parametrize("year", [2006, 2007, 2008])
def test_retrospective_north_melbourne_name_validates_against_each_era(year):
    historical_club = match_html(year).replace("Collingwood", "North Melbourne")

    match = source.parse_australian_football_match(historical_club, year)

    # Preserve the exact source value; the year-aware alias is validation-only.
    assert match.details.home_team == "North Melbourne"


def test_match_contract_rejects_wrong_year_score_drift_and_missing_player():
    with pytest.raises(ValueError, match="belongs to 2006, expected 2007"):
        source.parse_australian_football_match(match_html(), 2007)

    bad_score = match_html().replace("16.13.109", "16.13.108")
    with pytest.raises(ValueError, match="Home score total"):
        source.parse_australian_football_match(bad_score, 2006)

    soup = BeautifulSoup(match_html(), "html.parser")
    first_player_table = soup.select("table.stats")[0]
    first_player_table.select("tbody tr")[0].decompose()
    with pytest.raises(ValueError, match="Collingwood table has 21 players"):
        source.parse_australian_football_match(str(soup), 2006)


def test_match_contract_rejects_header_and_identity_drift():
    bad_header = match_html().replace("<th>FF</th>", "<th>Frees For</th>", 1)
    with pytest.raises(
        ValueError, match="Unexpected AustralianFootball player headers"
    ):
        source.parse_australian_football_match(bad_header, 2006)

    duplicate_player = match_html().replace(
        "/players/player/Player%2B0/2000",
        "/players/player/Player%2B0/1000",
    )
    with pytest.raises(ValueError, match="Players appeared for both teams"):
        source.parse_australian_football_match(duplicate_player, 2006)


def test_versioned_match_cache_round_trips_and_rejects_wrong_path(tmp_path):
    match = source.parse_australian_football_match(match_html(), 2006)
    source_path = source.save_australian_football_match(match, 13127, tmp_path)

    assert source.load_australian_football_match(13127, tmp_path) == match
    wrong_path = tmp_path / "match/13128/match.json"
    wrong_path.parent.mkdir(parents=True)
    wrong_path.write_text(source_path.read_text())
    with pytest.raises(ValueError, match="contains match 13127, expected 13128"):
        source.load_australian_football_match(13128, tmp_path)


def test_season_cache_resumes_missing_matches_and_fails_on_invalid_cache(
    monkeypatch, tmp_path
):
    manifest = source.parse_australian_football_season(season_html(), 2006)
    match = source.parse_australian_football_match(match_html(), 2006)
    live_calls = []
    progress = []

    monkeypatch.setattr(
        source,
        "load_australian_football_match",
        lambda match_id, _root: (
            match if match_id == 1 else (_ for _ in ()).throw(FileNotFoundError())
        ),
    )

    def scrape_live(_browser, match_id, _year, raw_root):
        live_calls.append(match_id)
        path = source.australian_football_match_cache_path(match_id, raw_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr(source, "scrape_australian_football_match", scrape_live)
    paths = source.cache_australian_football_season_matches(
        object(),
        manifest,
        delay_ms=0,
        progress=lambda *values: progress.append(values),
        raw_root=tmp_path,
    )

    assert len(paths) == 185
    assert live_calls == list(range(2, 186))
    assert progress[0] == (1, 185, 1, True)
    assert progress[-1] == (185, 185, 185, False)

    monkeypatch.setattr(
        source,
        "load_australian_football_match",
        lambda *_args: (_ for _ in ()).throw(ValueError("invalid cache")),
    )
    with pytest.raises(ValueError, match="invalid cache"):
        source.cache_australian_football_season_matches(
            object(), manifest, delay_ms=0, raw_root=tmp_path
        )


def test_historical_season_cli_keeps_full_match_scrape_explicit(monkeypatch, tmp_path):
    manifest = source.parse_australian_football_season(season_html(), 2006)
    cache_calls = []
    browser_modes = []

    @contextmanager
    def browser_context(headless):
        browser_modes.append(headless)
        yield object()

    monkeypatch.setattr(cli_module, "sync_browser_context", browser_context)
    monkeypatch.setattr(
        scraper_package,
        "discover_australian_football_season",
        lambda _browser, _year: manifest,
    )
    monkeypatch.setattr(
        scraper_package,
        "save_australian_football_manifest",
        lambda _manifest: tmp_path / "manifest.json",
    )
    monkeypatch.setattr(
        scraper_package,
        "cache_australian_football_season_matches",
        lambda *_args, **_kwargs: cache_calls.append(True) or [tmp_path] * 185,
    )

    manifest_only = CliRunner().invoke(
        cli_module.cli, ["scrape", "historical-season", "2006"]
    )
    assert manifest_only.exit_code == 0, manifest_only.output
    assert (
        "Saved historical season manifest covering 185 matches" in manifest_only.output
    )
    assert cache_calls == []

    with_matches = CliRunner().invoke(
        cli_module.cli,
        [
            "scrape",
            "historical-season",
            "2006",
            "--matches",
            "--delay-ms",
            "0",
        ],
    )
    assert with_matches.exit_code == 0, with_matches.output
    assert "Validated 185 historical match caches" in with_matches.output
    assert cache_calls == [True]
    assert browser_modes == [False, False]
