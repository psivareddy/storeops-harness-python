"""reports data access — deliberately read-only.

There is no ``add``, ``replace``, ``update`` or ``delete`` method here, and that absence is the
point. The read-only-reports rule is enforced by the *shape of this class*, not by a convention
someone has to remember: a Generator cannot write a report row through an API that does not
exist. ``tests/reports/test_reports_read_only.py`` asserts the absence by introspection so the
guarantee cannot be removed silently.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from app.reports.models import Report, ReportStatus, ReportType

_NOW = datetime(2026, 8, 31, 8, 0, tzinfo=UTC)

#: Method names that must never appear on this repository.
FORBIDDEN_WRITE_METHODS: Final[frozenset[str]] = frozenset(
    {"add", "create", "insert", "replace", "update", "upsert", "delete", "remove", "save"}
)


def _seed_reports() -> list[Report]:
    return [
        Report(
            id="report-1",
            report_type=ReportType.STORE_SUMMARY,
            status=ReportStatus.READY,
            scope_id="store-101",
            requested_by="user-2",
            created_at=_NOW,
        ),
        Report(
            id="report-2",
            report_type=ReportType.REGIONAL_ROLLUP,
            status=ReportStatus.PENDING,
            scope_id="North West",
            requested_by="user-1",
            created_at=_NOW,
        ),
    ]


class ReportRepository:
    """In-memory report store. Reads only."""

    def __init__(self) -> None:
        self._reports: dict[str, Report] = {}
        self.reset()

    def reset(self) -> None:
        """Restore seed data. Test helper -- not a domain write path."""
        self._reports = {report.id: report for report in _seed_reports()}

    def list_all(self, *, report_type: ReportType | None = None) -> list[Report]:
        reports = list(self._reports.values())
        if report_type is not None:
            reports = [report for report in reports if report.report_type is report_type]
        return sorted(reports, key=lambda report: report.id)

    def get(self, report_id: str) -> Report | None:
        return self._reports.get(report_id)

    def count(self) -> int:
        return len(self._reports)


report_repository = ReportRepository()
