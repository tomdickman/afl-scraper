"""Cache-only preflight for cross-source match metadata identity."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from afl_scraper.paths import data_path

from .australian_football import afl_official_cancelled_fixture
from .metadata_fallback import resolve_fallback_match_details
from .models import MatchMetadataCatalog, SeasonManifest


def audit_match_metadata(
    manifest: SeasonManifest,
    catalog: MatchMetadataCatalog,
) -> dict:
    """Check that every official fixture resolves to exactly one external match."""
    if manifest.year != catalog.year:
        raise ValueError(
            f"Manifest year {manifest.year} does not match catalogue {catalog.year}"
        )

    results = []
    for match_id in manifest.match_ids:
        cancellation = afl_official_cancelled_fixture(match_id, manifest.year)
        if cancellation is not None:
            results.append(
                {
                    "match_id": match_id,
                    "status": "expected_absence",
                    "reason": cancellation.reason,
                    "result_type": cancellation.result_type,
                    "australian_football_match_id": cancellation.match_id,
                    "evidence_urls": cancellation.evidence_urls,
                }
            )
            continue
        fixture = manifest.fixture_for(match_id)
        try:
            _details, provenance = resolve_fallback_match_details(fixture, catalog)
        except (KeyError, ValueError) as error:
            results.append(
                {
                    "match_id": match_id,
                    "status": "unresolved",
                    "error": str(error),
                }
            )
        else:
            results.append(
                {
                    "match_id": match_id,
                    "status": "resolved",
                    "external_url": provenance.match_details_url,
                    "cross_checked_fields": list(provenance.cross_checked_fields),
                }
            )

    resolved = sum(item["status"] == "resolved" for item in results)
    unresolved = sum(item["status"] == "unresolved" for item in results)
    expected_absences = [
        item for item in results if item["status"] == "expected_absence"
    ]
    return {
        "schema_version": 1,
        "year": manifest.year,
        "generated_at": datetime.now(UTC).isoformat(),
        "match_count": len(results),
        "completed_match_count": len(results) - len(expected_absences),
        "resolved_count": resolved,
        "unresolved_count": unresolved,
        "expected_absence_count": len(expected_absences),
        "expected_absences": expected_absences,
        "matches": results,
    }


def save_match_metadata_audit(
    report: dict,
    output_root: Path = data_path("reports", "match_metadata"),
) -> Path:
    """Atomically save a metadata audit report."""
    import json

    path = output_root / f"{report['year']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path
