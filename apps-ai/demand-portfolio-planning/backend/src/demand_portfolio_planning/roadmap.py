"""Deterministic portfolio roadmap.

Places every portfolio project on one timeline: running projects use their real
start/end dates, the proposed backlog is sequenced by the same explainable
prioritization model used elsewhere, and the new demand is inserted at its rank.
Nothing here is invented by an LLM — the schedule is computed so the UI can draw
an honest, reproducible Gantt.
"""

from __future__ import annotations

from datetime import date, timedelta

from demand_portfolio_planning.models import Roadmap, RoadmapEntry
from demand_portfolio_planning.prioritization import rank_backlog
from demand_portfolio_planning.sources import get_portfolio


def _parse(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _add_weeks(start: date, weeks: int) -> date:
    return start + timedelta(weeks=weeks)


def _first_of_next_month(today: date) -> date:
    year = today.year + (1 if today.month == 12 else 0)
    month = 1 if today.month == 12 else today.month + 1
    return date(year, month, 1)


def _month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _month_range(start: date, end: date) -> list[str]:
    months: list[str] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}-{month:02d}")
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return months


def _running_end(start: date, effort: int) -> date:
    # No end date in the source system -> indicative end from effort.
    return _add_weeks(start, max(12, effort * 8))


def build_roadmap(
    *,
    new_demand_id: str | None = None,
    new_demand_name: str | None = None,
    new_demand_area: str | None = None,
    new_demand_roles: list[str] | None = None,
    value: int = 3,
    effort: int = 3,
    urgency: int = 3,
    planned_start: str | None = None,
    language: str = "de",
    today: date | None = None,
) -> Roadmap:
    """Build the portfolio roadmap. When ``new_demand_*`` is supplied the new
    demand is ranked against the proposed backlog and placed on the timeline."""
    today = today or date.today()
    portfolio = get_portfolio()
    by_id = {p.project_id: p for p in portfolio}
    entries: list[RoadmapEntry] = []

    # Lane 1: running projects use their real, sourced dates.
    for project in portfolio:
        if project.status != "in_progress":
            continue
        start = _parse(project.start) or today
        sourced_end = _parse(project.end)
        end = sourced_end or _running_end(start, project.effort)
        entries.append(
            RoadmapEntry(
                project_id=project.project_id,
                name=project.name,
                portfolio_area=project.portfolio_area,
                status="in_progress",
                start=start.isoformat(),
                end=end.isoformat(),
                indicative=project.start is None or sourced_end is None,
            )
        )

    # Lane 2: proposed backlog + the new demand, sequenced by prioritization.
    include_new = bool(new_demand_id and new_demand_name)
    priority = rank_backlog(
        new_demand_id=new_demand_id or "__none__",
        new_demand_name=new_demand_name or "",
        value=value,
        effort=effort,
        urgency=urgency,
        roles=new_demand_roles or [],
        language=language,
    )
    baseline = _first_of_next_month(today)
    planned_start_date = _parse(planned_start)
    placed = 0  # gapless index for contiguous scheduling and display ranks
    for item in priority.ranked:
        is_new = item.is_new_demand
        if is_new and not include_new:
            continue
        start = _add_weeks(baseline, placed * 3)
        if is_new and planned_start_date:
            start = planned_start_date
        duration_weeks = max(8, item.effort * 6)
        end = _add_weeks(start, duration_weeks)
        if is_new:
            name = new_demand_name or item.name
            area = new_demand_area or ("Noch offen" if language != "en" else "To be classified")
        else:
            proj = by_id.get(item.item_id)
            name = proj.name if proj else item.name
            area = proj.portfolio_area if proj else ""
        placed += 1
        entries.append(
            RoadmapEntry(
                project_id=item.item_id,
                name=name,
                portfolio_area=area,
                status="new_demand" if is_new else "proposed",
                start=start.isoformat(),
                end=end.isoformat(),
                indicative=True,
                priority_rank=placed,
                is_new_demand=is_new,
            )
        )

    starts = [_parse(e.start) or today for e in entries]
    ends = [_parse(e.end) or today for e in entries]
    grid_start = min([*starts, today])
    grid_end = max([*ends, today])
    months = _month_range(date(grid_start.year, grid_start.month, 1), grid_end)

    if language == "en":
        notes = [
            "Running projects use real start/end dates from the portfolio system; "
            "missing end dates are indicative (derived from effort).",
            "Proposed items and the new demand are scheduled in priority order — "
            "higher priority starts earlier. These planned dates are indicative.",
        ]
    else:
        notes = [
            "Laufende Projekte nutzen echte Start-/Enddaten aus dem Portfolio-System; "
            "fehlende Enddaten sind indikativ (aus dem Aufwand abgeleitet).",
            "Vorgeschlagene Einträge und die neue Demand werden nach Priorität "
            "eingeplant — höhere Priorität startet früher. Diese Plandaten sind indikativ.",
        ]

    return Roadmap(
        today=today.isoformat(),
        months=months,
        entries=entries,
        notes=notes,
        sources=["seed: portfolio dates", "seed: resource pool allocations"],
    )


__all__ = ["build_roadmap", "_month_key"]
