"""Deterministic PRINCE2 project-plan timeline.

The planner LLM must never invent specific dates, so the forward-looking project
plan (the milestones a PM picks up after board approval) is built here from a
fixed PRINCE2 stage cadence anchored on today. Dates are clearly indicative
(``kind="generated"``) but always concrete — the plan never shows "open".
"""

from __future__ import annotations

from datetime import date, timedelta

from demand_portfolio_planning.models import Milestone, TimelineDraft

# PRINCE2 stage milestones with a week offset from the planned project start.
# (label_de, label_en, week_offset)
_STAGES: tuple[tuple[str, str, int], ...] = (
    ("Projektinitiierung (Initiierungsphase)", "Project initiation (Initiation Stage)", 0),
    ("Initiierung abgeschlossen – PID freigegeben", "Initiation complete – PID approved", 3),
    (
        "Lieferstufe 1: Konzept & Integrationsdesign",
        "Delivery stage 1: Concept & integration design",
        4,
    ),
    ("Phasenübergang (Stage Boundary)", "Stage boundary", 11),
    ("Lieferstufe 2: Umsetzung & Integration", "Delivery stage 2: Build & integration", 12),
    ("Lieferung / Go-Live", "Delivery / Go-live", 22),
    ("Projektabschluss (Closing a Project)", "Project closure (Closing a Project)", 26),
)


def _planned_start(today: date) -> date:
    """Indicative project start: the Monday of the week after next, so the plan
    always reads as starting in the near future rather than 'today'."""
    monday = today - timedelta(days=today.weekday())
    return monday + timedelta(weeks=2)


def build_prince2_timeline(
    language: str,
    *,
    today: date | None = None,
    precheck: str | None = None,
    assessment: str | None = None,
) -> TimelineDraft:
    today = today or date.today()
    start = _planned_start(today)
    status_label = "geplant" if language != "en" else "planned"
    milestones = [
        Milestone(
            label=(label_en if language == "en" else label_de),
            date=(start + timedelta(weeks=weeks)).isoformat(),
            status=status_label,
            kind="generated",
        )
        for label_de, label_en, weeks in _STAGES
    ]
    return TimelineDraft(
        precheck=precheck or today.isoformat(),
        assessment=assessment or today.isoformat(),
        planned_project_start=start.isoformat(),
        milestones=milestones,
        missing_dates=[],
        resource_constraint_impact=[],
        sources=["system: PRINCE2 stage cadence (indicative)"],
    )


__all__ = ["build_prince2_timeline"]
