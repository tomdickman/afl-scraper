"""Resumable multi-year orchestration for historical database backfills."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..models import (
    HistoricalBackfillCheckpoint,
    HistoricalBackfillReport,
    HistoricalBackfillYear,
    HistoricalReconciliationReport,
)
from ..scraper.models.australian_football import MAX_SUPPORTED_YEAR, MIN_SUPPORTED_YEAR
from ..storage import admin_connection_pool
from .historical import (
    load_prepared_historical_season,
    preflight_historical_season,
    reconcile_historical_season,
    require_reconciled,
)


SOURCE = "australian_football"
ProgressCallback = Callable[[int, str], None]


@dataclass(frozen=True)
class HistoricalBackfillResult:
    checkpoint: HistoricalBackfillCheckpoint
    report: HistoricalBackfillReport
    checkpoint_path: Path
    report_path: Path


def validate_historical_year_range(start_year: int, end_year: int) -> list[int]:
    if start_year > end_year:
        raise ValueError("Historical backfill start year must not exceed end year")
    if start_year < MIN_SUPPORTED_YEAR or end_year > MAX_SUPPORTED_YEAR:
        raise ValueError(
            "AustralianFootball historical backfill supports "
            f"{MIN_SUPPORTED_YEAR}-{MAX_SUPPORTED_YEAR}; got "
            f"{start_year}-{end_year}"
        )
    return list(range(start_year, end_year + 1))


def historical_checkpoint_path(
    start_year: int,
    end_year: int,
    root: Path = Path("data/checkpoints/australian_football"),
) -> Path:
    validate_historical_year_range(start_year, end_year)
    return root / f"{start_year}-{end_year}.json"


def historical_report_path(
    start_year: int,
    end_year: int,
    root: Path = Path("data/reports/australian_football"),
) -> Path:
    validate_historical_year_range(start_year, end_year)
    return root / f"{start_year}-{end_year}.json"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}-{uuid4().hex}.tmp"
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def save_historical_checkpoint(
    checkpoint: HistoricalBackfillCheckpoint, path: Path
) -> None:
    _atomic_write(path, checkpoint.model_dump_json(indent=2) + "\n")


def load_historical_checkpoint(path: Path) -> HistoricalBackfillCheckpoint:
    return HistoricalBackfillCheckpoint.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def save_historical_report(report: HistoricalBackfillReport, path: Path) -> None:
    _atomic_write(path, report.model_dump_json(indent=2) + "\n")


def _new_checkpoint(years: list[int], now: datetime) -> HistoricalBackfillCheckpoint:
    return HistoricalBackfillCheckpoint(
        start_year=years[0],
        end_year=years[-1],
        created_at=now,
        updated_at=now,
        years={year: HistoricalBackfillYear(status="pending") for year in years},
    )


def _load_or_create_checkpoint(
    years: list[int], path: Path, resume: bool, now: datetime
) -> HistoricalBackfillCheckpoint:
    if not resume or not path.exists():
        return _new_checkpoint(years, now)
    checkpoint = load_historical_checkpoint(path)
    if (checkpoint.start_year, checkpoint.end_year) != (years[0], years[-1]):
        raise ValueError(
            f"Checkpoint {path} covers {checkpoint.start_year}-"
            f"{checkpoint.end_year}, expected {years[0]}-{years[-1]}"
        )
    return checkpoint


def _updated_year(
    checkpoint: HistoricalBackfillCheckpoint,
    year: int,
    state: HistoricalBackfillYear,
    now: datetime,
) -> HistoricalBackfillCheckpoint:
    years = dict(checkpoint.years)
    years[year] = state
    return checkpoint.model_copy(update={"years": years, "updated_at": now})


def _report(
    checkpoint: HistoricalBackfillCheckpoint,
    reconciliations: dict[int, HistoricalReconciliationReport],
    *,
    dry_run: bool,
    resume: bool,
    now: datetime,
) -> HistoricalBackfillReport:
    return HistoricalBackfillReport(
        start_year=checkpoint.start_year,
        end_year=checkpoint.end_year,
        dry_run=dry_run,
        resume=resume,
        generated_at=now,
        years=[reconciliations[year] for year in sorted(reconciliations)],
    )


def historical_backfill_pipeline(
    start_year: int = MIN_SUPPORTED_YEAR,
    end_year: int = MAX_SUPPORTED_YEAR,
    *,
    load: bool = False,
    resume: bool = True,
    checkpoint_path: Path | None = None,
    report_path: Path | None = None,
    progress: ProgressCallback | None = None,
) -> HistoricalBackfillResult:
    """Preflight the whole range, then load or verify each year resumably."""
    years = validate_historical_year_range(start_year, end_year)
    checkpoint_path = checkpoint_path or historical_checkpoint_path(
        start_year, end_year
    )
    report_path = report_path or historical_report_path(start_year, end_year)
    now = datetime.now(timezone.utc)
    checkpoint = _load_or_create_checkpoint(years, checkpoint_path, resume, now)
    previously_completed = {
        year
        for year, state in checkpoint.years.items()
        if state.status in {"loaded", "verified"}
    }

    prepared_by_year = {}
    reconciliations = {}
    with admin_connection_pool() as conn:
        # No database rows are written until the entire range passes preflight.
        for year in years:
            if progress:
                progress(year, "preflighting")
            try:
                prepared = preflight_historical_season(conn, year)
                reconciliation = reconcile_historical_season(conn, year, prepared)
                reconciliations[year] = reconciliation
                prepared_by_year[year] = prepared
                previous = checkpoint.years[year]
                was_completed = previous.status in {"loaded", "verified"}
                if was_completed:
                    status = "verified" if reconciliation.ok else "failed"
                else:
                    status = "validated"
                checkpoint = _updated_year(
                    checkpoint,
                    year,
                    HistoricalBackfillYear(
                        status=status,
                        expected_matches=len(prepared),
                        expected_player_stats=sum(
                            len(match.player_stats) for match in prepared
                        ),
                        database_matches=reconciliation.database_matches,
                        database_player_stats=reconciliation.database_player_stats,
                        differences=reconciliation.mismatch_count,
                        inserted_games=previous.inserted_games,
                        updated_games=previous.updated_games,
                        completed_at=previous.completed_at,
                        error=(
                            None
                            if reconciliation.ok or not was_completed
                            else "Previously completed year no longer reconciles"
                        ),
                    ),
                    datetime.now(timezone.utc),
                )
                save_historical_checkpoint(checkpoint, checkpoint_path)
            except Exception as exc:
                previous = checkpoint.years[year]
                checkpoint = _updated_year(
                    checkpoint,
                    year,
                    previous.model_copy(
                        update={"status": "failed", "error": str(exc)[:2000]}
                    ),
                    datetime.now(timezone.utc),
                )
                save_historical_checkpoint(checkpoint, checkpoint_path)
                save_historical_report(
                    _report(
                        checkpoint,
                        reconciliations,
                        dry_run=not load,
                        resume=resume,
                        now=datetime.now(timezone.utc),
                    ),
                    report_path,
                )
                raise

        if load:
            for year in years:
                prepared = prepared_by_year[year]
                current = checkpoint.years[year]
                reconciliation = reconciliations[year]
                if resume and reconciliation.ok:
                    if progress:
                        progress(year, "verified")
                    checkpoint = _updated_year(
                        checkpoint,
                        year,
                        current.model_copy(
                            update={
                                "status": "verified",
                                "completed_at": datetime.now(timezone.utc),
                                "error": None,
                            }
                        ),
                        datetime.now(timezone.utc),
                    )
                    save_historical_checkpoint(checkpoint, checkpoint_path)
                    continue

                if resume and year in previously_completed:
                    checkpoint = _updated_year(
                        checkpoint,
                        year,
                        current.model_copy(
                            update={
                                "status": "failed",
                                "error": (
                                    "Previously completed year no longer "
                                    "reconciles with the database"
                                ),
                            }
                        ),
                        datetime.now(timezone.utc),
                    )
                    save_historical_checkpoint(checkpoint, checkpoint_path)
                    save_historical_report(
                        _report(
                            checkpoint,
                            reconciliations,
                            dry_run=False,
                            resume=resume,
                            now=datetime.now(timezone.utc),
                        ),
                        report_path,
                    )
                    require_reconciled(reconciliation)

                if progress:
                    progress(year, "loading")
                try:
                    load_report = load_prepared_historical_season(conn, year, prepared)
                    reconciliation = reconcile_historical_season(conn, year, prepared)
                    reconciliations[year] = reconciliation
                    require_reconciled(reconciliation)
                    checkpoint = _updated_year(
                        checkpoint,
                        year,
                        HistoricalBackfillYear(
                            status="loaded",
                            expected_matches=load_report.matches,
                            expected_player_stats=load_report.player_stats,
                            database_matches=reconciliation.database_matches,
                            database_player_stats=(
                                reconciliation.database_player_stats
                            ),
                            differences=reconciliation.mismatch_count,
                            inserted_games=load_report.inserted_games,
                            updated_games=load_report.updated_games,
                            completed_at=datetime.now(timezone.utc),
                        ),
                        datetime.now(timezone.utc),
                    )
                    save_historical_checkpoint(checkpoint, checkpoint_path)
                    save_historical_report(
                        _report(
                            checkpoint,
                            reconciliations,
                            dry_run=False,
                            resume=resume,
                            now=datetime.now(timezone.utc),
                        ),
                        report_path,
                    )
                    if progress:
                        progress(year, "loaded")
                except Exception as exc:
                    current = checkpoint.years[year]
                    latest = reconciliations[year]
                    checkpoint = _updated_year(
                        checkpoint,
                        year,
                        current.model_copy(
                            update={
                                "status": "failed",
                                "database_matches": latest.database_matches,
                                "database_player_stats": (latest.database_player_stats),
                                "differences": latest.mismatch_count,
                                "error": str(exc)[:2000],
                            }
                        ),
                        datetime.now(timezone.utc),
                    )
                    save_historical_checkpoint(checkpoint, checkpoint_path)
                    save_historical_report(
                        _report(
                            checkpoint,
                            reconciliations,
                            dry_run=False,
                            resume=resume,
                            now=datetime.now(timezone.utc),
                        ),
                        report_path,
                    )
                    raise

    report = _report(
        checkpoint,
        reconciliations,
        dry_run=not load,
        resume=resume,
        now=datetime.now(timezone.utc),
    )
    save_historical_report(report, report_path)
    return HistoricalBackfillResult(
        checkpoint=checkpoint,
        report=report,
        checkpoint_path=checkpoint_path,
        report_path=report_path,
    )
