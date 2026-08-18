import json
import re
from collections import defaultdict
from pathlib import Path

from ..models.player import PlayerInfo, PlayerMapping, MatchResult
from ..storage import admin_connection_pool
from ..utils.identity import normalize_person_name


_QUOTED_NICKNAME_PATTERN = re.compile(r'(?:"[^"]+"|[\'’][^\'’]+[\'’])')


def load_player_ids_from_json(source: str, year: int) -> list[PlayerInfo]:
    path = Path(f"data/mapping/{year}_{source}.json")
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with open(path) as f:
        data = json.load(f)

    return [PlayerInfo.model_validate(p) for p in data]


def normalize_name(name: str) -> str:
    """Normalize harmless name punctuation and whitespace across both sources."""
    return normalize_person_name(name)


def normalize_family_name(player: PlayerInfo) -> str:
    """Normalize a surname for review candidates, never for exact matching."""
    without_quoted_nicknames = _QUOTED_NICKNAME_PATTERN.sub(" ", player.last_name)
    normalized = normalize_person_name(f"given {without_quoted_nicknames}")
    return normalized.removeprefix("given ").replace(" ", "")


_TEAM_ALIASES = {
    "adelaide": "adelaide",
    "adelaide crows": "adelaide",
    "brisbane": "brisbane",
    "brisbane lions": "brisbane",
    "carlton": "carlton",
    "collingwood": "collingwood",
    "essendon": "essendon",
    "fremantle": "fremantle",
    "fremantle dockers": "fremantle",
    "geelong": "geelong",
    "geelong cats": "geelong",
    "gold coast": "gold coast",
    "gold coast suns": "gold coast",
    "greater western sydney": "gws",
    "gws": "gws",
    "gws giants": "gws",
    "hawthorn": "hawthorn",
    "melbourne": "melbourne",
    "kangaroos": "north melbourne",
    "north melbourne": "north melbourne",
    "port adelaide": "port adelaide",
    "richmond": "richmond",
    "st. kilda": "st kilda",
    "st kilda": "st kilda",
    "sydney": "sydney",
    "sydney swans": "sydney",
    "swans": "sydney",
    "west coast": "west coast",
    "west coast eagles": "west coast",
    "western bulldogs": "western bulldogs",
    "footscray": "western bulldogs",
}


def normalize_team(team: str) -> str:
    normalized = " ".join(team.casefold().strip().split())
    return _TEAM_ALIASES.get(normalized, normalized)


def teams_match(afl_team: str, tables_team: str) -> bool:
    afl = normalize_team(afl_team)
    tables = normalize_team(tables_team)
    return bool(afl and tables) and afl == tables


def _players_by_name(players: list[PlayerInfo]) -> dict[str, list[PlayerInfo]]:
    grouped: dict[str, list[PlayerInfo]] = defaultdict(list)
    for player in players:
        grouped[normalize_name(player.display_name())].append(player)
    return {
        key: sorted(value, key=lambda player: player.id)
        for key, value in grouped.items()
    }


def _validate_unique_player_ids(players: list[PlayerInfo], source: str) -> None:
    seen: set[str] = set()
    for player in players:
        if player.id in seen:
            raise ValueError(f"Duplicate {source} player ID: {player.id}")
        seen.add(player.id)


def match_players(
    afl_players: list[PlayerInfo], tables_players: list[PlayerInfo]
) -> MatchResult:
    _validate_unique_player_ids(afl_players, "AFL Official")
    _validate_unique_player_ids(tables_players, "AFL Tables")
    afl_by_name = _players_by_name(afl_players)
    tables_by_name = _players_by_name(tables_players)

    exact = []
    fuzzy = []
    matched_afl = set()
    matched_tables = set()

    for key in sorted(set(afl_by_name) & set(tables_by_name)):
        remaining_afl = list(afl_by_name[key])
        remaining_tables = list(tables_by_name[key])

        # Resolve only pairs that are unique in both directions. This handles
        # duplicate names on different teams without guessing when duplicates
        # share a team or the source team values disagree.
        while True:
            candidates = {
                afl.id: [
                    tables
                    for tables in remaining_tables
                    if teams_match(afl.team, tables.team)
                ]
                for afl in remaining_afl
            }
            unique_pairs = []
            for afl in remaining_afl:
                if len(candidates[afl.id]) != 1:
                    continue
                tables = candidates[afl.id][0]
                reverse_matches = [
                    other for other in remaining_afl if tables in candidates[other.id]
                ]
                if len(reverse_matches) == 1:
                    unique_pairs.append((afl, tables))

            if not unique_pairs:
                break
            for afl, tables in unique_pairs:
                exact.append({"afl": afl, "tables": tables})
                matched_afl.add(afl.id)
                matched_tables.add(tables.id)
                remaining_afl.remove(afl)
                remaining_tables.remove(tables)

        for afl in remaining_afl:
            team_candidates = [
                tables
                for tables in remaining_tables
                if teams_match(afl.team, tables.team)
            ]
            # Each fuzzy result owns its candidate collection. In particular,
            # do not expose the shared working list when falling back after a
            # team mismatch.
            review_candidates = team_candidates or list(remaining_tables)
            if not review_candidates:
                continue
            fuzzy.append({"afl": afl, "tables": review_candidates})
            matched_afl.add(afl.id)
            matched_tables.update(tables.id for tables in review_candidates)

    # Different given-name forms (for example Marty/Martin) must not be
    # auto-approved. Present same-team, same-surname candidates for explicit
    # review instead of leaving the official identity impossible to resolve.
    remaining_afl = [p for p in afl_players if p.id not in matched_afl]
    remaining_tables = [p for p in tables_players if p.id not in matched_tables]
    for afl in remaining_afl:
        review_candidates = [
            tables
            for tables in remaining_tables
            if teams_match(afl.team, tables.team)
            and normalize_family_name(afl) == normalize_family_name(tables)
        ]
        if not review_candidates:
            continue
        review_candidates.sort(key=lambda player: player.id)
        fuzzy.append({"afl": afl, "tables": review_candidates})
        matched_afl.add(afl.id)
        matched_tables.update(tables.id for tables in review_candidates)

    unmatched_afl = [p for p in afl_players if p.id not in matched_afl]
    unmatched_tables = [p for p in tables_players if p.id not in matched_tables]

    return MatchResult(
        exact=[{"afl": m["afl"], "tables": m["tables"]} for m in exact],
        fuzzy=[{"afl": m["afl"], "tables": m["tables"]} for m in fuzzy],
        unmatched_afl=unmatched_afl,
        unmatched_tables=unmatched_tables,
    )


def validate_mappings(mappings: list[PlayerMapping]) -> None:
    """Ensure approved mappings obey the database's one-to-one constraints."""
    player_ids: set[str] = set()
    official_ids: set[str] = set()
    for mapping in mappings:
        if mapping.player_id in player_ids:
            raise ValueError(f"Duplicate AFL Tables player ID: {mapping.player_id}")
        player_ids.add(mapping.player_id)
        if mapping.afl_official_id is None:
            continue
        if mapping.afl_official_id in official_ids:
            raise ValueError(
                f"Duplicate AFL Official player ID: {mapping.afl_official_id}"
            )
        official_ids.add(mapping.afl_official_id)


def validate_mapping_coverage(
    required_players: list[PlayerInfo], mappings: list[PlayerMapping]
) -> None:
    """Require a canonical mapping for every participating official player."""
    validate_mappings(mappings)
    required_ids = {player.id for player in required_players}
    mapped_ids = {
        mapping.afl_official_id
        for mapping in mappings
        if mapping.afl_official_id is not None
    }
    missing = sorted(required_ids - mapped_ids)
    if missing:
        raise ValueError(
            f"Missing {len(missing)} participating AFL official mappings: "
            f"{', '.join(missing)}"
        )


def save_matches_to_json(matches: MatchResult, year: int) -> Path:
    path = Path(f"data/mapping/{year}_to_review.json")
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        json.dump(matches.model_dump(by_alias=True), f, indent=2)

    return path


def upsert_mappings(mappings: list[PlayerMapping], year: int) -> int:
    validate_mappings(mappings)
    inserted = 0

    with admin_connection_pool() as conn:
        for mapping in mappings:
            if mapping.afl_official_id is None:
                continue
            conn.execute(
                """
                INSERT INTO player_source_identity
                  (source, source_player_id, player_id, year)
                VALUES ('afl_official', %(source_player_id)s, %(player_id)s, %(year)s)
                ON CONFLICT (source, source_player_id, year) DO UPDATE
                SET player_id = EXCLUDED.player_id,
                    updated_at = NOW()
                """,
                {
                    "source_player_id": mapping.afl_official_id,
                    "player_id": mapping.player_id,
                    "year": year,
                },
            )
            inserted += 1

    return inserted
