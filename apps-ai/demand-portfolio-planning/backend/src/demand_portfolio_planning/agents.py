"""Foundry-backed agents. Each agent owns one cognitive step of the funnel and
returns a typed artifact. Production wiring lives here; the workflow consumes
plain callables so tests can inject fakes without touching Foundry."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.core.credentials import TokenCredential
from azure.identity import (
    AzureCliCredential,
    AzureDeveloperCliCredential,
    ChainedTokenCredential,
    DefaultAzureCredential,
)
from pydantic import BaseModel

from demand_portfolio_planning.models import (
    PRINCE_THEMES,
    AssessmentSummary,
    ChatRouterOutput,
    DemandRecord,
    PortfolioFit,
    PreCheckReport,
    PrinceTheme,
    ProjectPlanningHandoff,
    ReadinessCriterion,
    ResourceMatch,
    SeedDemand,
)
from demand_portfolio_planning.settings import get_settings
from demand_portfolio_planning.sources import (
    get_portfolio,
    get_resource_pool,
    get_skill_matrix,
    project_names,
)

_INSTRUCTIONS_DIR = Path(
    os.environ.get(
        "AGENT_INSTRUCTIONS_DIR",
        Path(__file__).resolve().parents[3] / "agent-instructions",
    )
)


def _load_instructions(name: str) -> str:
    return (_INSTRUCTIONS_DIR / name).read_text(encoding="utf-8")


def _credential() -> TokenCredential:
    settings = get_settings()
    tenant = settings.azure_tenant_id
    subscription = settings.azure_ai_subscription_id
    if not (tenant or subscription):
        return DefaultAzureCredential()

    if subscription:
        cli = AzureCliCredential(subscription=subscription)
    elif tenant:
        cli = AzureCliCredential(tenant_id=tenant)
    else:
        cli = AzureCliCredential()
    azd = (
        AzureDeveloperCliCredential(tenant_id=tenant)
        if tenant
        else AzureDeveloperCliCredential()
    )
    return ChainedTokenCredential(
        cli,
        azd,
        DefaultAzureCredential(
            exclude_cli_credential=True,
            exclude_developer_cli_credential=True,
        ),
    )


@lru_cache
def _chat_client() -> FoundryChatClient:
    settings = get_settings()
    return FoundryChatClient(
        project_endpoint=settings.azure_ai_project_endpoint,
        model=settings.azure_foundry_model,
        credential=_credential(),
    )


def _agent(agent_id: str, description: str, instructions_file: str) -> Agent:
    return Agent(
        client=_chat_client(),
        id=agent_id,
        name=agent_id,
        description=description,
        instructions=_load_instructions(instructions_file),
        default_options={"store": False},
    )


@lru_cache
def get_intake_agent() -> Agent:
    return _agent(
        "intake_structurer",
        "Structure a free-text business demand into a typed demand record.",
        "intake_structurer.txt",
    )


@lru_cache
def get_record_editor_agent() -> Agent:
    return _agent(
        "demand_record_editor",
        "Apply a single human edit to an existing demand record, preserving the rest.",
        "demand_record_editor.txt",
    )


@lru_cache
def get_precheck_agent() -> Agent:
    return _agent(
        "precheck_evaluator",
        "Assess demand completeness and readiness for assessment.",
        "precheck_evaluator.txt",
    )


@lru_cache
def get_assessment_agent() -> Agent:
    return _agent(
        "assessment_facilitator",
        "Draft a demand assessment separating facts, assumptions and open questions.",
        "assessment_facilitator.txt",
    )


@lru_cache
def get_portfolio_agent() -> Agent:
    return _agent(
        "portfolio_planner",
        "Place a demand in portfolio context against the existing project portfolio.",
        "portfolio_planner.txt",
    )


@lru_cache
def get_resource_agent() -> Agent:
    return _agent(
        "resource_matcher",
        "Match required roles to the resource pool via the skill matrix.",
        "resource_matcher.txt",
    )


@lru_cache
def get_planner_agent() -> Agent:
    return _agent(
        "planner",
        "Generate the project planning handoff from the assessed demand.",
        "planner.txt",
    )


@lru_cache
def get_assistant_agent() -> Agent:
    return _agent(
        "assistant",
        "Conversational assistant that edits the editable artifact or answers questions.",
        "assistant.txt",
    )


def _language_label(language: str) -> str:
    return {"en": "English", "de": "German"}.get(language, "German")


# PRINCE2 readiness questions per theme, used to backfill any theme the model
# omits so the checklist always shows all six gates the board expects.
_READINESS_QUESTIONS: dict[PrinceTheme, dict[str, str]] = {
    "business_case": {
        "de": "Business Case: Ist der geschäftliche Nutzen/Grund klar?",
        "en": "Business case: is the business value/justification clear?",
    },
    "organization": {
        "de": "Organisation: Sind Process Owner und benötigte Rollen/SMEs benannt?",
        "en": "Organization: are the process owner and required roles/SMEs identified?",
    },
    "scope_product": {
        "de": "Scope & Produkt: Ist beschrieben, was geliefert werden soll (In/Out of Scope)?",
        "en": "Scope & product: is it described what will be delivered (in/out of scope)?",
    },
    "plans_timeline": {
        "de": "Pläne & Timeline: Gibt es einen groben Zeitrahmen/Zieltermin?",
        "en": "Plans & timeline: is there an indicative timeframe/target date?",
    },
    "risk": {
        "de": "Risiken: Sind wesentliche Risiken, Abhängigkeiten und Konflikte erkannt?",
        "en": "Risk: are key risks, dependencies and conflicts identified?",
    },
    "resources": {
        "de": "Ressourcen: Sind Ressourcenbedarf und Machbarkeit berücksichtigt?",
        "en": "Resources: are resource needs and feasibility considered?",
    },
}


def _readiness_question(theme: PrinceTheme, language: str) -> str:
    return _READINESS_QUESTIONS[theme]["en" if language == "en" else "de"]


def _finalize_precheck(report: PreCheckReport, language: str) -> PreCheckReport:
    """Ensure all six PRINCE2 themes are present in canonical order with a
    localized question, then re-derive the deterministic readiness status."""
    existing = {c.theme: c for c in report.readiness}
    ordered: list[ReadinessCriterion] = []
    for theme in PRINCE_THEMES:
        crit = existing.get(theme)
        if crit is None:
            crit = ReadinessCriterion(
                theme=theme, status="missing", question=_readiness_question(theme, language)
            )
        elif not crit.question.strip():
            crit = crit.model_copy(update={"question": _readiness_question(theme, language)})
        ordered.append(crit)
    data = report.model_dump()
    data["readiness"] = [c.model_dump() for c in ordered]
    return PreCheckReport.model_validate(data)


def _extract_json(text: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        value = "\n".join(lines[1:-1]).strip()
    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        value = value[start : end + 1]
    return value


async def _run_json[T: BaseModel](
    agent: Agent, payload: Mapping[str, object], model: type[T]
) -> T:
    result = await agent.run(json.dumps(payload, indent=2, ensure_ascii=False))
    return model.model_validate_json(_extract_json(result.text))


def _compact_portfolio() -> list[dict[str, object]]:
    return [
        {
            "project_id": p.project_id,
            "name": p.name,
            "portfolio_area": p.portfolio_area,
            "status": p.status,
            "roles": p.roles,
        }
        for p in get_portfolio()
    ]


def _compact_pool() -> list[dict[str, object]]:
    return [
        {
            "person_id": p.person_id,
            "name": p.name,
            "roles": p.roles,
            "skills": [{"skill": s.skill, "level": s.level} for s in p.skills],
            "allocation_pct": p.allocation_pct,
            "commitments": project_names(p.commitments),
        }
        for p in get_resource_pool()
    ]


def _add_revision_instruction(payload: dict[str, object], instruction: str | None) -> None:
    if instruction:
        payload["revision_instruction"] = instruction
        payload["revision_note"] = "Revise this single artifact using the existing inputs."


async def structure_demand(
    agent: Agent,
    demand: SeedDemand,
    language: str,
    instruction: str | None = None,
) -> DemandRecord:
    payload: dict[str, object] = {
        "demand_title": demand.title,
        "raw_demand": demand.raw_demand,
        "known_process_owner": demand.known_process_owner,
        "response_language": _language_label(language),
    }
    _add_revision_instruction(payload, instruction)
    return await _run_json(agent, payload, DemandRecord)


async def edit_demand_record(
    agent: Agent,
    record: DemandRecord,
    instruction: str,
    language: str,
) -> DemandRecord:
    """Apply ONE human edit to an existing demand record without re-deriving it
    from scratch — untouched fields keep their value, kind and source."""
    payload: dict[str, object] = {
        "current_record": record.model_dump(),
        "edit_instruction": instruction,
        "response_language": _language_label(language),
        "source_label": "user input" if language == "en" else "Nutzereingabe",
    }
    return await _run_json(agent, payload, DemandRecord)


async def evaluate_precheck(
    agent: Agent,
    record: DemandRecord,
    language: str,
    instruction: str | None = None,
) -> PreCheckReport:
    payload: dict[str, object] = {
        "demand_record": record.model_dump(),
        "response_language": _language_label(language),
    }
    _add_revision_instruction(payload, instruction)
    report = await _run_json(agent, payload, PreCheckReport)
    return _finalize_precheck(report, language)


async def run_assessment(
    agent: Agent,
    record: DemandRecord,
    report: PreCheckReport,
    language: str,
    instruction: str | None = None,
) -> AssessmentSummary:
    payload: dict[str, object] = {
        "demand_record": record.model_dump(),
        "precheck_report": report.model_dump(),
        "response_language": _language_label(language),
    }
    _add_revision_instruction(payload, instruction)
    return await _run_json(agent, payload, AssessmentSummary)


async def fit_portfolio(
    agent: Agent,
    record: DemandRecord,
    summary: AssessmentSummary,
    language: str,
    instruction: str | None = None,
) -> PortfolioFit:
    payload: dict[str, object] = {
        "demand_record": record.model_dump(),
        "assessment_summary": summary.model_dump(),
        "portfolio": _compact_portfolio(),
        "response_language": _language_label(language),
    }
    _add_revision_instruction(payload, instruction)
    return await _run_json(agent, payload, PortfolioFit)


async def match_resources(
    agent: Agent,
    record: DemandRecord,
    summary: AssessmentSummary,
    portfolio_fit: PortfolioFit,
    language: str,
    instruction: str | None = None,
) -> ResourceMatch:
    payload: dict[str, object] = {
        "demand_record": record.model_dump(),
        "assessment_summary": summary.model_dump(),
        "portfolio_fit": portfolio_fit.model_dump(),
        "resource_pool": _compact_pool(),
        "skill_matrix": get_skill_matrix(),
        "response_language": _language_label(language),
    }
    _add_revision_instruction(payload, instruction)
    return await _run_json(agent, payload, ResourceMatch)


async def draft_plan(
    agent: Agent,
    record: DemandRecord,
    summary: AssessmentSummary,
    portfolio_fit: PortfolioFit,
    resource_match: ResourceMatch,
    language: str,
    instruction: str | None = None,
) -> ProjectPlanningHandoff:
    payload: dict[str, object] = {
        "demand_record": record.model_dump(),
        "assessment_summary": summary.model_dump(),
        "portfolio_fit": portfolio_fit.model_dump(),
        "resource_match": resource_match.model_dump(),
        "response_language": _language_label(language),
        "note": (
            "Leave resource_allocation and priority as defaults; they are injected "
            "deterministically by the system."
        ),
    }
    _add_revision_instruction(payload, instruction)
    return await _run_json(agent, payload, ProjectPlanningHandoff)


async def route_chat(agent: Agent, context: Mapping[str, object]) -> ChatRouterOutput:
    """Decide how to act on a chat message: edit the editable artifact or answer."""
    return await _run_json(agent, context, ChatRouterOutput)
