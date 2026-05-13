import json
from pathlib import Path
from typing import Any

from ..storage import admin_connection_pool


def load_player_ids_from_json(source: str, year: int) -> list[dict[str, Any]]:
    path = Path(f"data/mapping/{year}_{source}.json")
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with open(path) as f:
        return json.load(f)


def normalize_name(name: str) -> str:
    return name.lower().strip().replace("'", "").replace("-", " ")


def teams_match(afl_team: str, tables_team: str) -> bool:
    afl = afl_team.lower().strip()
    tables = tables_team.lower().strip()

    team_aliases = {
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
    afl_players: list[dict[str, Any]], tables_players: list[dict[str, Any]]
) -> dict[str, list]:
    afl_index = {
        normalize_name(f"{p['firstName']} {p['lastName']}"): p for p in afl_players
    }
    tables_index = {
        normalize_name(f"{p['firstName']} {p['lastName']}"): p for p in tables_players
    }

    exact_matches = []
    fuzzy_matches = []
    unmatched_afl = []
    unmatched_tables = []

    matched_afl = set()
    matched_tables = set()

    for afl in afl_players:
        afl_key = normalize_name(f"{afl['firstName']} {afl['lastName']}")
        afl_full = f"{afl['firstName']} {afl['lastName']}"

        if afl_key in tables_index:
            tables = tables_index[afl_key]
            if teams_match(afl["team"], tables["team"]):
                exact_matches.append({"afl": afl, "tables": tables})
                matched_afl.add(afl["id"])
                matched_tables.add(tables["id"])
            else:
                fuzzy_matches.append(
                    {
                        "afl": afl,
                        "tables": [
                            t
                            for t in tables_players
                            if normalize_name(f"{t['firstName']} {t['lastName']}")
                            == afl_key
                        ],
                    }
                )
                matched_afl.add(afl["id"])
                for t in fuzzy_matches[-1]["tables"]:
                    matched_tables.add(t["id"])

    for afl in afl_players:
        if afl["id"] not in matched_afl:
            unmatched_afl.append(afl)

    for tables in tables_players:
        if tables["id"] not in matched_tables:
            unmatched_tables.append(tables)

    return {
        "exact": exact_matches,
        "fuzzy": fuzzy_matches,
        "unmatched_afl": unmatched_afl,
        "unmatched_tables": unmatched_tables,
    }


def save_matches_to_json(matches: dict[str, list], year: int) -> Path:
    path = Path(f"data/mapping/{year}_to_review.json")
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        json.dump(matches, f, indent=2)

    return path


def upsert_mappings(mappings: list[dict[str, Any]], year: int) -> int:
    inserted = 0

    with admin_connection_pool() as conn:
        for mapping in mappings:
            afl_id = mapping.get("afl_official_id")
            player_id = mapping.get("player_id")

            if afl_id and player_id:
                conn.execute(
                    """
                    INSERT INTO player_id_mapping (afl_official_id, player_id, year)
                    VALUES (%(afl_id)s, %(player_id)s, %(year)s)
                    ON CONFLICT (player_id, year) DO UPDATE
                    SET afl_official_id = EXCLUDED.afl_official_id,
                        updated_at = NOW()
                    """,
                    {"afl_id": afl_id, "player_id": player_id, "year": year},
                )
                inserted += 1
            elif player_id and not afl_id:
                conn.execute(
                    """
                    INSERT INTO player_id_mapping (player_id, year)
                    VALUES (%(player_id)s, %(year)s)
                    ON CONFLICT (player_id, year) DO UPDATE
                    SET updated_at = NOW()
                    """,
                    {"player_id": player_id, "year": year},
                )
                inserted += 1

    return inserted
