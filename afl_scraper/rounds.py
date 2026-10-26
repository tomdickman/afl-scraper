"""Canonical round labels shared by every match source."""

import re

CANONICAL_SPECIAL_ROUNDS = frozenset({"OR", "WF", "QE", "QF", "EF", "SF", "PF", "GF"})

_ALIASES = {
    "or": "OR",
    "opening round": "OR",
    "wf": "WF",
    "wcf": "WF",
    "wildcard final": "WF",
    "wildcard finals": "WF",
    "qe": "QE",
    "fw1": "QE",
    "finals week 1": "QE",
    "qualifying & elimination final": "QE",
    "qualifying & elimination finals": "QE",
    "qf": "QF",
    "qualifying final": "QF",
    "qualifying finals": "QF",
    "ef": "EF",
    "elimination final": "EF",
    "elimination finals": "EF",
    "sf": "SF",
    "fw2": "SF",
    "finals week 2": "SF",
    "semi final": "SF",
    "semi finals": "SF",
    "pf": "PF",
    "fw3": "PF",
    "finals week 3": "PF",
    "preliminary final": "PF",
    "preliminary finals": "PF",
    "gf": "GF",
    "gfr": "GF",
    "fw4": "GF",
    "finals week 4": "GF",
    "grand final": "GF",
    "grand finals": "GF",
    "grand final replay": "GF",
}
_NUMBERED_FINAL = re.compile(r"^[12](qf|ef|sf|pf)$")
_NAMED_FINAL = re.compile(
    r"^(?:(?:first|second|1st|2nd) )?"
    r"(qualifying|elimination|semi|preliminary|grand) finals?$"
)
_FINAL_CODES = {
    "qualifying": "QF",
    "elimination": "EF",
    "semi": "SF",
    "preliminary": "PF",
    "grand": "GF",
}


def normalize_round_label(value: str) -> str:
    """Return a source-neutral positive round number or finals-stage acronym."""
    normalized = " ".join(value.replace("\xa0", " ").split()).casefold()
    if normalized.startswith("round "):
        normalized = normalized.removeprefix("round ").strip()
    if normalized.isdigit() and int(normalized) > 0:
        return str(int(normalized))

    alias = _ALIASES.get(normalized)
    if alias is not None:
        return alias

    numbered = _NUMBERED_FINAL.fullmatch(normalized)
    if numbered is not None:
        return numbered.group(1).upper()

    named = _NAMED_FINAL.fullmatch(normalized)
    if named is not None:
        return _FINAL_CODES[named.group(1)]

    allowed = ", ".join(sorted(CANONICAL_SPECIAL_ROUNDS))
    raise ValueError(
        f"Unsupported round label {value!r}; expected a positive round number "
        f"or one of: {allowed}"
    )
