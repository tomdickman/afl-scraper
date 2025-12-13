from .constants import team_mappings


def transform_team_name(input: str) -> str:
    try:
        id = team_mappings[str.lower(input)]
    except KeyError:
        raise Exception(f"No team ID mapping found for {input}")
    else:
        return id
