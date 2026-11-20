"""Deterministic seed for the mock "systems of record".

These stand in for the portfolio tool (e.g. LeanIX), an HR/resource system, and a
demand intake. Everything here is synthetic and carries no customer or account
names. The agent may only reason over this data plus user input — it never invents
facts beyond what is seeded.
"""

from __future__ import annotations

from demand_portfolio_planning.models import (
    Person,
    PortfolioProject,
    SeedDemand,
    SkillRating,
)

# --------------------------------------------------------------------------- #
# Resource pool with a small skill matrix and current commitments.
# The SAP FI capability is deliberately scarce and over-committed: it is the
# bottleneck the customer described (same few specialists do assessment AND
# delivery, and allocation after the board is the real constraint).
# --------------------------------------------------------------------------- #

_PEOPLE: list[Person] = [
    Person(
        person_id="p-anders",
        name="Alex Anders",
        roles=["SAP FI Specialist", "Integration Engineer"],
        skills=[
            SkillRating(skill="SAP FI", level="expert"),
            SkillRating(skill="Payment Run Integration", level="expert"),
            SkillRating(skill="Integration", level="advanced"),
        ],
        allocation_pct=90,
        commitments=["prj-fin-consolidation", "prj-erp-s4-upgrade"],
    ),
    Person(
        person_id="p-roth",
        name="Robin Roth",
        roles=["HR Systems Specialist", "Payroll SME"],
        skills=[
            SkillRating(skill="SAP SuccessFactors", level="expert"),
            SkillRating(skill="Payroll", level="advanced"),
            SkillRating(skill="Integration", level="intermediate"),
        ],
        allocation_pct=65,
        commitments=["prj-hr-onboarding"],
    ),
    Person(
        person_id="p-keller",
        name="Sam Keller",
        roles=["Enterprise Architect"],
        skills=[
            SkillRating(skill="Enterprise Architecture", level="expert"),
            SkillRating(skill="Integration", level="advanced"),
            SkillRating(skill="Cloud/Azure", level="intermediate"),
        ],
        allocation_pct=55,
        commitments=["prj-app-rationalization"],
    ),
    Person(
        person_id="p-vogt",
        name="Jamie Vogt",
        roles=["PMO", "Project Manager"],
        skills=[
            SkillRating(skill="Project Management", level="expert"),
            SkillRating(skill="Change Management", level="advanced"),
        ],
        allocation_pct=50,
        commitments=["prj-pmo-uplift"],
    ),
    Person(
        person_id="p-lang",
        name="Chris Lang",
        roles=["Integration Engineer"],
        skills=[
            SkillRating(skill="Integration", level="expert"),
            SkillRating(skill="Cloud/Azure", level="advanced"),
            SkillRating(skill="SAP FI", level="beginner"),
        ],
        allocation_pct=80,
        commitments=["prj-ecom-replatform", "prj-data-lakehouse"],
    ),
    Person(
        person_id="p-wolf",
        name="Toni Wolf",
        roles=["SAP FI Consultant"],
        skills=[
            SkillRating(skill="SAP FI", level="advanced"),
            SkillRating(skill="Payment Run Integration", level="intermediate"),
            SkillRating(skill="Payroll", level="beginner"),
        ],
        allocation_pct=45,
        commitments=["prj-fin-consolidation"],
    ),
    Person(
        person_id="p-haas",
        name="Robin Haas",
        roles=["HR Process Owner"],
        skills=[
            SkillRating(skill="Payroll", level="expert"),
            SkillRating(skill="SAP SuccessFactors", level="intermediate"),
            SkillRating(skill="Change Management", level="intermediate"),
        ],
        allocation_pct=35,
        commitments=[],
    ),
    Person(
        person_id="p-sommer",
        name="Kim Sommer",
        roles=["Data Engineer"],
        skills=[
            SkillRating(skill="Data Analytics", level="expert"),
            SkillRating(skill="Cloud/Azure", level="advanced"),
        ],
        allocation_pct=70,
        commitments=["prj-data-lakehouse"],
    ),
    Person(
        person_id="p-frei",
        name="Andrea Frei",
        roles=["Business Analyst"],
        skills=[
            SkillRating(skill="Requirements Engineering", level="advanced"),
            SkillRating(skill="Process Harmonization", level="advanced"),
        ],
        allocation_pct=40,
        commitments=["prj-pmo-uplift"],
    ),
    Person(
        person_id="p-meyer",
        name="Nico Meyer",
        roles=["ITSM Specialist"],
        skills=[
            SkillRating(skill="ServiceNow/ITSM", level="expert"),
            SkillRating(skill="Integration", level="intermediate"),
        ],
        allocation_pct=60,
        commitments=["prj-itsm-consolidation"],
    ),
    Person(
        person_id="p-braun",
        name="Luca Braun",
        roles=["Cloud Engineer"],
        skills=[
            SkillRating(skill="Cloud/Azure", level="expert"),
            SkillRating(skill="Integration", level="advanced"),
            SkillRating(skill="Security", level="intermediate"),
        ],
        allocation_pct=75,
        commitments=["prj-ecom-replatform", "prj-zero-trust"],
    ),
    Person(
        person_id="p-kraus",
        name="Mika Kraus",
        roles=["Manufacturing IT Specialist"],
        skills=[
            SkillRating(skill="Manufacturing/MES", level="expert"),
            SkillRating(skill="Supply Chain", level="advanced"),
        ],
        allocation_pct=50,
        commitments=["prj-mes-rollout"],
    ),
]


# --------------------------------------------------------------------------- #
# Existing project portfolio (~18 items). Some have unknown resources/dates on
# purpose, to dramatize the limited portfolio transparency the customer flagged.
# value/effort/urgency drive the deterministic prioritization model.
# --------------------------------------------------------------------------- #

_PORTFOLIO: list[PortfolioProject] = [
    PortfolioProject(
        project_id="prj-erp-s4-upgrade",
        name="ERP S/4 Core Upgrade",
        portfolio_area="Finance & ERP",
        status="in_progress",
        owner="Finance IT",
        roles=["SAP FI Specialist", "Integration Engineer"],
        start="2026-01-15",
        end="2026-11-30",
        value=5,
        effort=5,
        urgency=4,
    ),
    PortfolioProject(
        project_id="prj-fin-consolidation",
        name="Group Financial Consolidation",
        portfolio_area="Finance & ERP",
        status="in_progress",
        owner="Group Finance",
        roles=["SAP FI Specialist"],
        start="2026-03-01",
        end=None,
        value=4,
        effort=4,
        urgency=3,
    ),
    PortfolioProject(
        project_id="prj-hr-onboarding",
        name="HR Onboarding Self-Service",
        portfolio_area="HR & Payroll",
        status="in_progress",
        owner="HR",
        roles=["HR Systems Specialist"],
        start="2026-02-10",
        end="2026-07-31",
        value=3,
        effort=2,
        urgency=3,
    ),
    PortfolioProject(
        project_id="prj-app-rationalization",
        name="Application Portfolio Rationalization",
        portfolio_area="IT Strategy",
        status="in_progress",
        owner="Enterprise Architecture",
        roles=["Enterprise Architect"],
        start=None,
        end=None,
        value=4,
        effort=3,
        urgency=2,
    ),
    PortfolioProject(
        project_id="prj-pmo-uplift",
        name="PMO Operating Model Uplift",
        portfolio_area="IT Strategy",
        status="in_progress",
        owner="PMO",
        roles=["PMO", "Business Analyst"],
        start="2026-01-01",
        end="2026-09-30",
        value=3,
        effort=3,
        urgency=4,
    ),
    PortfolioProject(
        project_id="prj-ecom-replatform",
        name="E-Commerce Replatform",
        portfolio_area="Customer & Sales",
        status="in_progress",
        owner="Digital",
        roles=["Integration Engineer", "Cloud Engineer"],
        start="2025-11-01",
        end="2026-08-15",
        value=5,
        effort=5,
        urgency=4,
    ),
    PortfolioProject(
        project_id="prj-data-lakehouse",
        name="Enterprise Data Lakehouse",
        portfolio_area="Data & Analytics",
        status="in_progress",
        owner="Data Office",
        roles=["Data Engineer", "Integration Engineer"],
        start="2026-02-01",
        end=None,
        value=4,
        effort=5,
        urgency=3,
    ),
    PortfolioProject(
        project_id="prj-itsm-consolidation",
        name="ITSM Tool Consolidation",
        portfolio_area="IT Operations",
        status="in_progress",
        owner="IT Operations",
        roles=["ITSM Specialist"],
        start="2026-04-01",
        end="2026-12-31",
        value=3,
        effort=3,
        urgency=2,
    ),
    PortfolioProject(
        project_id="prj-zero-trust",
        name="Zero Trust Network Rollout",
        portfolio_area="Security",
        status="in_progress",
        owner="Security",
        roles=["Cloud Engineer"],
        start="2026-01-20",
        end=None,
        value=4,
        effort=4,
        urgency=5,
    ),
    PortfolioProject(
        project_id="prj-mes-rollout",
        name="MES Rollout Plant 2",
        portfolio_area="Manufacturing",
        status="in_progress",
        owner="Operations",
        roles=["Manufacturing IT Specialist"],
        start=None,
        end=None,
        value=4,
        effort=4,
        urgency=3,
    ),
    PortfolioProject(
        project_id="prj-payroll-harmonization",
        name="Payroll Process Harmonization (EU)",
        portfolio_area="HR & Payroll",
        status="proposed",
        owner="HR",
        roles=["Payroll SME", "Business Analyst"],
        start=None,
        end=None,
        value=3,
        effort=3,
        urgency=2,
    ),
    PortfolioProject(
        project_id="prj-travel-expense",
        name="Travel & Expense Modernization",
        portfolio_area="Finance & ERP",
        status="proposed",
        owner="Finance",
        roles=["SAP FI Consultant"],
        start=None,
        end=None,
        value=2,
        effort=2,
        urgency=2,
    ),
    PortfolioProject(
        project_id="prj-crm-rollout",
        name="CRM Regional Rollout",
        portfolio_area="Customer & Sales",
        status="proposed",
        owner="Sales Ops",
        roles=["Integration Engineer"],
        start=None,
        end=None,
        value=3,
        effort=4,
        urgency=3,
    ),
    PortfolioProject(
        project_id="prj-supplier-portal",
        name="Supplier Collaboration Portal",
        portfolio_area="Supply Chain",
        status="proposed",
        owner="Procurement",
        roles=["Integration Engineer"],
        start=None,
        end=None,
        value=3,
        effort=3,
        urgency=2,
    ),
    PortfolioProject(
        project_id="prj-iam-modernization",
        name="Identity & Access Modernization",
        portfolio_area="Security",
        status="in_progress",
        owner="Security",
        roles=["Cloud Engineer"],
        start="2026-03-15",
        end=None,
        value=4,
        effort=3,
        urgency=4,
    ),
    PortfolioProject(
        project_id="prj-reporting-bi",
        name="Self-Service BI Reporting",
        portfolio_area="Data & Analytics",
        status="proposed",
        owner="Controlling",
        roles=["Data Engineer"],
        start=None,
        end=None,
        value=3,
        effort=2,
        urgency=3,
    ),
    PortfolioProject(
        project_id="prj-warehouse-automation",
        name="Warehouse Automation Pilot",
        portfolio_area="Supply Chain",
        status="proposed",
        owner="Logistics",
        roles=["Manufacturing IT Specialist"],
        start=None,
        end=None,
        value=4,
        effort=5,
        urgency=2,
    ),
    PortfolioProject(
        project_id="prj-intranet-refresh",
        name="Intranet & Collaboration Refresh",
        portfolio_area="Workplace",
        status="proposed",
        owner="Internal Comms",
        roles=["Business Analyst"],
        start=None,
        end=None,
        value=2,
        effort=2,
        urgency=1,
    ),
]


# --------------------------------------------------------------------------- #
# Seeded demands. The payroll demand mirrors the use case's worked example so
# the "mark unknowns, don't invent" behaviour is demonstrable end-to-end.
# --------------------------------------------------------------------------- #

_DEMANDS: list[SeedDemand] = [
    SeedDemand(
        demand_id="payroll-local",
        title="Neues lokales Payroll-System einführen (Landesgesellschaft)",
        known_process_owner="HR (Payroll)",
        raw_demand=(
            "Eine Landesgesellschaft möchte ein neues lokales Payroll-System einführen. "
            "Zentral ist das risikoarm, weil Payroll eine lokale, landesspezifische Lösung "
            "ist und es keinen zentralen Ansatz gibt. Es braucht aber Integrationen: HR über "
            "SuccessFactors und die ERP-/SAP-FI-Seite für die Zahlungsläufe. Process Owner "
            "ist HR (Payroll). Wir sind unsicher, ob die SAP-FI-Integration wirklich im Scope "
            "ist und zu welchem Portfolio-Bereich das gehört. Budget, Timeline und konkrete "
            "Ressourcen sind noch offen."
        ),
    ),
    SeedDemand(
        demand_id="bi-reporting",
        title="Excel-Reporting durch Analytics-Dashboard ablösen",
        known_process_owner=None,
        raw_demand=(
            "Das Controlling pflegt monatliche Berichte in komplexen Excel-Dateien. Wir "
            "möchten das durch ein Self-Service-Analytics-Dashboard ablösen, damit Fachbereiche "
            "Kennzahlen selbst auswerten können. Datenquellen sind ERP und ein paar lokale "
            "Systeme. Wer das fachlich verantwortet, ist noch nicht final geklärt."
        ),
    ),
    SeedDemand(
        demand_id="incident-tool",
        title="Einheitliches Incident-Management-Tool einführen",
        known_process_owner="IT Operations",
        raw_demand=(
            "Wir möchten ein einheitliches Incident-Management-Tool einführen, weil Tickets "
            "heute über mehrere Kanäle laufen. Aktuell betreibt ein externer Managed-Service-"
            "Provider das ITSM-Tooling, und es läuft bereits ein Projekt zur ITSM-Tool-"
            "Konsolidierung. Möglicherweise ist der Bedarf damit schon abgedeckt."
        ),
    ),
]


def get_resource_pool() -> list[Person]:
    return [p.model_copy(deep=True) for p in _PEOPLE]


def get_portfolio() -> list[PortfolioProject]:
    return [p.model_copy(deep=True) for p in _PORTFOLIO]


def get_seed_demands() -> list[SeedDemand]:
    return [d.model_copy(deep=True) for d in _DEMANDS]


def get_seed_demand(demand_id: str) -> SeedDemand | None:
    for demand in _DEMANDS:
        if demand.demand_id == demand_id:
            return demand.model_copy(deep=True)
    return None


def get_project_name_map() -> dict[str, str]:
    """project_id -> human-readable name, so agents and UI never surface raw
    identifiers like ``prj-fin-consolidation``."""
    return {p.project_id: p.name for p in _PORTFOLIO}


def project_names(ids: list[str]) -> list[str]:
    """Map a list of project ids to names (falling back to the id if unknown)."""
    names = get_project_name_map()
    return [names.get(pid, pid) for pid in ids]


def get_skill_matrix() -> dict[str, list[dict[str, str]]]:
    """skill -> list of {person_id, name, level} for compact prompt context."""
    matrix: dict[str, list[dict[str, str]]] = {}
    for person in _PEOPLE:
        for rating in person.skills:
            matrix.setdefault(rating.skill, []).append(
                {"person_id": person.person_id, "name": person.name, "level": rating.level}
            )
    return matrix
