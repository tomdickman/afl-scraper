import json
from pathlib import Path

from ..models.player import PlayerInfo, PlayerMapping, MatchResult
from ..storage import admin_connection_pool


def load_player_ids_from_json(source: str, year: int) -> list[PlayerInfo]:
    path = Path(f"data/mapping/{year}_{source}.json")
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with open(path) as f:
        data = json.load(f)

    return [PlayerInfo.model_validate(p) for p in data]


def normalize_name(name: str) -> str:
    return name.lower().strip().replace("'", "").replace("-", " ")


def teams_match(afl_team: str, tables_team: str) -> bool:
    afl = afl_team.lower().strip()
    tables = tables_team.lower().strip()

    team_aliases: dict[str, list[str]] = {
        "brisbane": ["brisbane lions", "brisbane"],
        "gws giants": ["gws giants", "greater western sydney", "gws"],
        "sydney swans": ["sydney swans", "sydney", "swans"],
        "west coast eagles": ["west coast eagles", "west coast"],
        "north melbourne": ["north melbourne", "north melbourne"],
        "western bulldogs": ["western bulldogs", "western bulldogs", "footscray"],
        "port adelaide": ["port adelaide", "port adelaide"],
    }

    for standard, aliases in team_aliases.items():
        if afl in aliases and tables in aliases:
            return True

    return afl == tables


def match_players(
    afl_players: list[PlayerInfo], tables_players: list[PlayerInfo]
) -> MatchResult:
    afl_by_name = {
        normalize_name(f"{p.first_name} {p.last_name}"): p for p in afl_players
    }
    tables_by_name = {
        normalize_name(f"{p.first_name} {p.last_name}"): p for p in tables_players
    }

    exact = []
    fuzzy = []
    matched_afl = set()
    matched_tables = set()

    for afl in afl_players:
        key = normalize_name(f"{afl.first_name} {afl.last_name}")

        if key in tables_by_name:
            tables = tables_by_name[key]
            if teams_match(afl.team, tables.team):
                exact.append({"afl": afl, "tables": tables})
                matched_afl.add(afl.id)
                matched_tables.add(tables.id)
            else:
                candidates = [
                    t for t in tables_players
                    if normalize_name(f"{t.first_name} {t.last_name}") == key
                ]
                fuzzy.append({"afl": afl, "tables": candidates})
                matched_afl.add(afl.id)
                for t in candidates:
                    matched_tables.add(t.id)

    unmatched_afl = [p for p in afl_players if p.id not in matched_afl]
    unmatched_tables = [p for p in tables_players if p.id not in matched_tables]

    return MatchResult(
        exact=[{"afl": m["afl"], "tables": m["tables"]} for m in exact],
        fuzzy=[{"afl": m["afl"], "tables": m["tables"]} for m in fuzzy],
        unmatched_afl=unmatched_afl,
        unmatched_tables=unmatched_tables,
    )


def save_matches_to_json(matches: MatchResult, year: int) -> Path:
    path = Path(f"data/mapping/{year}_to_review.json")
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        json.dump(matches.model_dump(by_alias=True), f, indent=2)

    return path


def upsert_mappings(mappings: list[PlayerMapping], year: int) -> int:
    inserted = 0

    with admin_connection_pool() as conn:
        for mapping in mappings:
            if mapping.afl_official_id and mapping.player_id:
                conn.execute(
                    """
                    INSERT INTO player_id_mapping (afl_official_id, player_id, year)
                    VALUES (%(afl_id)s, %(player_id)s, %(year)s)
                    ON CONFLICT (player_id, year) DO UPDATE
                    SET afl_official_id = EXCLUDED.afl_official_id,
                        updated_at = NOW()
                    """,
                    {
                        "afl_id": mapping.afl_official_id,
                        "player_id": mapping.player_id,
                        "year": year,
                    },
                )
                inserted += 1
            elif mapping.player_id and not mapping.afl_official_id:
                conn.execute(
                    """
                    INSERT INTO player_id_mapping (player_id, year)
                    VALUES (%(player_id)s, %(year)s)
                    ON CONFLICT (player_id, year) DO UPDATE
                    SET updated_at = NOW()
                    """,
                    {"player_id": mapping.player_id, "year": year},
                )
                inserted += 1

    return inserted
