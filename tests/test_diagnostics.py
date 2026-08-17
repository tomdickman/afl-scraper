import pytest

from afl_scraper.diagnostics import summarize_identifiers


def test_identifier_summary_is_sorted_and_bounded_for_any_iterable():
    identifiers = {"delta", "alpha", "charlie", "bravo"}

    assert summarize_identifiers(identifiers, limit=3) == (
        "alpha, bravo, charlie (+1 more)"
    )


def test_identifier_summary_rejects_non_positive_limit():
    with pytest.raises(ValueError, match="must be positive"):
        summarize_identifiers(["alpha"], limit=0)
