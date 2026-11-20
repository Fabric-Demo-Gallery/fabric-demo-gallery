"""The provenance trust contract is enforced deterministically, not left to the
model. These tests pin the invariants that the rendered pills depend on."""

import unittest

from demand_portfolio_planning.models import (
    PRINCE_THEMES,
    AssessmentSummary,
    DemandRecord,
    PreCheckReport,
    ProjectPlanningHandoff,
    ReadinessCriterion,
    TrackedField,
    TrackedItem,
)


def _readiness(**status: str) -> list[ReadinessCriterion]:
    return [
        ReadinessCriterion(theme=theme, status=status.get(theme, "covered"))  # type: ignore[arg-type]
        for theme in PRINCE_THEMES
    ]


class TrustContractTests(unittest.TestCase):
    def test_empty_field_cannot_be_a_fact(self) -> None:
        # The exact bug from the demo: an empty slot mislabeled "fact".
        record = DemandRecord(
            resource_needs=TrackedField(value=None, kind="fact"),
            timeline=TrackedField(value="   ", kind="fact"),
        )
        self.assertEqual(record.resource_needs.kind, "unknown")
        self.assertIsNone(record.resource_needs.value)
        self.assertEqual(record.timeline.kind, "unknown")
        self.assertIsNone(record.timeline.value)

    def test_empty_open_question_field_is_preserved(self) -> None:
        record = DemandRecord(portfolio_area=TrackedField(value=None, kind="open_question"))
        self.assertEqual(record.portfolio_area.kind, "open_question")

    def test_concrete_fact_is_untouched(self) -> None:
        record = DemandRecord(
            process_owner=TrackedField(value="HR (Payroll)", kind="fact", source="x")
        )
        self.assertEqual(record.process_owner.kind, "fact")
        self.assertEqual(record.process_owner.value, "HR (Payroll)")

    def test_open_questions_list_is_forced_to_open_question(self) -> None:
        # The LLM (or the TrackedItem default) tagged these "fact".
        record = DemandRecord(
            open_questions=[
                TrackedItem(value="Is SAP FI in scope?", kind="fact"),
                TrackedItem(value="Which portfolio area?"),
            ]
        )
        self.assertTrue(all(q.kind == "open_question" for q in record.open_questions))

    def test_assessment_summary_enforced(self) -> None:
        summary = AssessmentSummary(
            timeline=TrackedField(value=None, kind="fact"),
            open_questions=[TrackedItem(value="Budget?", kind="fact")],
            confirmed_facts=[TrackedItem(value="Payroll is local", kind="fact")],
        )
        self.assertEqual(summary.timeline.kind, "unknown")
        self.assertEqual(summary.open_questions[0].kind, "open_question")
        # Confirmed facts keep their kind.
        self.assertEqual(summary.confirmed_facts[0].kind, "fact")

    def test_handoff_open_questions_enforced(self) -> None:
        handoff = ProjectPlanningHandoff(
            open_questions=[TrackedItem(value="Go-live date?", kind="generated")]
        )
        self.assertEqual(handoff.open_questions[0].kind, "open_question")


class PrinceReadinessTests(unittest.TestCase):
    """The PRINCE2 readiness gate is deterministic: ready only when every theme
    is covered, regardless of the status the model proposed."""

    def test_all_covered_is_ready(self) -> None:
        report = PreCheckReport(status="more_info_needed", readiness=_readiness())
        self.assertEqual(report.status, "ready")

    def test_any_missing_blocks_ready(self) -> None:
        report = PreCheckReport(status="ready", readiness=_readiness(plans_timeline="missing"))
        self.assertEqual(report.status, "more_info_needed")

    def test_partial_blocks_ready(self) -> None:
        report = PreCheckReport(status="ready", readiness=_readiness(resources="partial"))
        self.assertEqual(report.status, "more_info_needed")

    def test_explicit_block_is_preserved(self) -> None:
        report = PreCheckReport(status="blocked", readiness=_readiness())
        self.assertEqual(report.status, "blocked")

    def test_no_readiness_leaves_status_untouched(self) -> None:
        report = PreCheckReport(status="more_info_needed")
        self.assertEqual(report.status, "more_info_needed")

    def test_invalid_status_coerces_to_missing(self) -> None:
        crit = ReadinessCriterion(theme="risk", status="weird")  # type: ignore[arg-type]
        self.assertEqual(crit.status, "missing")


class KindCoercionTests(unittest.TestCase):
    """LLMs sometimes emit a neighbouring enum value as a provenance kind; the
    models coerce anything invalid to 'unknown' rather than failing validation."""

    def test_invalid_item_kind_becomes_unknown(self) -> None:
        item = TrackedItem(value="x", kind="missing")  # type: ignore[arg-type]
        self.assertEqual(item.kind, "unknown")

    def test_invalid_field_kind_becomes_unknown(self) -> None:
        field = TrackedField(value="y", kind="covered")  # type: ignore[arg-type]
        self.assertEqual(field.kind, "unknown")

    def test_valid_kind_is_preserved(self) -> None:
        self.assertEqual(TrackedItem(value="x", kind="assumption").kind, "assumption")


if __name__ == "__main__":
    unittest.main()
