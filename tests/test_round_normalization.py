import pytest

from afl_scraper.rounds import normalize_round_label


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("2", "2"),
        ("02", "2"),
        ("Round 2", "2"),
        ("Opening Round", "OR"),
        ("WCF", "WF"),
        ("Wildcard Finals", "WF"),
        ("Finals Week 1", "QE"),
        ("Qualifying & Elimination Finals", "QE"),
        ("1QF", "QF"),
        ("Second Qualifying Final", "QF"),
        ("2EF", "EF"),
        ("First Elimination Final", "EF"),
        ("1SF", "SF"),
        ("Semi Finals", "SF"),
        ("2PF", "PF"),
        ("Preliminary Finals", "PF"),
        ("GFR", "GF"),
        ("Grand Final Replay", "GF"),
    ],
)
def test_normalizes_provider_round_labels(source, expected):
    assert normalize_round_label(source) == expected


@pytest.mark.parametrize("source", ["", "Round 0", "Round Two", "Mystery Final"])
def test_rejects_unknown_or_non_positive_round_labels(source):
    with pytest.raises(ValueError, match="Unsupported round label"):
        normalize_round_label(source)
