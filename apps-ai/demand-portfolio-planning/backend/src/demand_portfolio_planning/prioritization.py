"""Deterministic, explainable backlog sequencing.

The customer's hardest question is ordering: "70 ideas, 3 people — in which order?".
We keep the math transparent (a small weighted score over value, urgency, effort and
resource contention) so the agent can *explain* a sequence rather than assert one.
The LLM never invents the ranking; it only narrates this deterministic output.
"""

from __future__ import annotations

from demand_portfolio_planning.models import (
    PriorityRankedItem,
    PrioritySuggestion,
)
from demand_portfolio_planning.sources import get_portfolio, get_resource_pool

# score = W_VALUE*value + W_URGENCY*urgency - W_EFFORT*effort - W_CONTENTION*contention
_W_VALUE = 2.0
_W_URGENCY = 1.5
_W_EFFORT = 1.0
_W_CONTENTION = 1.0


def _contention(roles: list[str]) -> int:
    """1-5 estimate of how scarce the people for these roles are right now.

    Driven by the current allocation of pool members who hold the required roles.
    Heavily booked specialists -> higher contention. Unknown -> neutral 3.
    """
    if not roles:
        return 3
    wanted = {r.lower() for r in roles}
    allocations = [
        person.allocation_pct
        for person in get_resource_pool()
        if wanted & {role.lower() for role in person.roles}
    ]
    if not allocations:
        return 4  # no one obviously holds the role -> scarce
    avg = sum(allocations) / len(allocations)
    return max(1, min(5, round(avg / 20)))


def _score(value: int, urgency: int, effort: int, contention: int) -> float:
    return round(
        _W_VALUE * value
        + _W_URGENCY * urgency
        - _W_EFFORT * effort
        - _W_CONTENTION * contention,
        2,
    )


def _rationale(language: str, value: int, urgency: int, effort: int, contention: int) -> str:
    if language == "en":
        return (
            f"value {value}, urgency {urgency}, effort {effort}, "
            f"resource contention {contention}/5"
        )
    return (
        f"Wert {value}, Dringlichkeit {urgency}, Aufwand {effort}, "
        f"Ressourcen-Engpass {contention}/5"
    )


def _method(language: str) -> str:
    if language == "en":
        return (
            "Deterministic score = 2·value + 1.5·urgency − 1·effort − 1·resource_contention. "
            "Higher score ranks earlier. Only proposed/backlog items compete; running "
            "projects are excluded."
        )
    return (
        "Deterministischer Score = 2·Wert + 1.5·Dringlichkeit − 1·Aufwand − "
        "1·Ressourcen-Engpass. Höherer Score = frühere Reihenfolge. Es konkurrieren nur "
        "vorgeschlagene/Backlog-Einträge; laufende Projekte sind ausgenommen."
    )


def rank_backlog(
    *,
    new_demand_id: str,
    new_demand_name: str,
    value: int,
    effort: int,
    urgency: int,
    roles: list[str],
    language: str = "de",
) -> PrioritySuggestion:
    """Rank the proposed backlog plus the new demand into an explainable sequence."""
    items: list[PriorityRankedItem] = []

    for project in get_portfolio():
        if project.status != "proposed":
            continue
        contention = _contention(project.roles)
        items.append(
            PriorityRankedItem(
                rank=0,
                item_id=project.project_id,
                name=project.name,
                score=_score(project.value, project.urgency, project.effort, contention),
                value=project.value,
                effort=project.effort,
                urgency=project.urgency,
                resource_contention=contention,
                rationale=_rationale(
                    language, project.value, project.urgency, project.effort, contention
                ),
            )
        )

    new_contention = _contention(roles)
    items.append(
        PriorityRankedItem(
            rank=0,
            item_id=new_demand_id,
            name=new_demand_name,
            score=_score(value, urgency, effort, new_contention),
            value=value,
            effort=effort,
            urgency=urgency,
            resource_contention=new_contention,
            rationale=_rationale(language, value, urgency, effort, new_contention),
            is_new_demand=True,
        )
    )

    # Sort by score desc; tie-break deterministically by item_id for stable output.
    items.sort(key=lambda i: (-i.score, i.item_id))
    for index, item in enumerate(items, start=1):
        item.rank = index

    new_rank = next(i.rank for i in items if i.is_new_demand)
    return PrioritySuggestion(
        new_demand_rank=new_rank,
        total_items=len(items),
        ranked=items,
        method=_method(language),
        sources=["seed: portfolio backlog", "seed: resource pool allocations"],
    )
