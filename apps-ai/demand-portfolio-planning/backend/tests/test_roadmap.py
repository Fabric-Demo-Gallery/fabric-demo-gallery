"""The roadmap and project-plan timeline are deterministic, so the UI can draw an
honest Gantt and the plan never shows 'open'. These tests pin that behavior."""

import unittest
from datetime import date

from demand_portfolio_planning.roadmap import build_roadmap
from demand_portfolio_planning.timeline import build_prince2_timeline


class RoadmapTests(unittest.TestCase):
    def test_includes_every_portfolio_project_plus_new_demand(self) -> None:
        roadmap = build_roadmap(
            new_demand_id="new-demand",
            new_demand_name="Local payroll system",
            new_demand_area="HR & Payroll",
            new_demand_roles=["SAP FI Specialist"],
            language="en",
            today=date(2026, 6, 1),
        )
        new_entries = [e for e in roadmap.entries if e.is_new_demand]
        self.assertEqual(len(new_entries), 1)
        self.assertEqual(new_entries[0].name, "Local payroll system")
        self.assertEqual(new_entries[0].status, "new_demand")
        self.assertIsNotNone(new_entries[0].priority_rank)
        # Running projects appear with real dates and no priority rank.
        running = [e for e in roadmap.entries if e.status == "in_progress"]
        self.assertTrue(running)
        self.assertTrue(all(e.priority_rank is None for e in running))

    def test_every_entry_has_concrete_dates_and_months_grid(self) -> None:
        roadmap = build_roadmap(language="de", today=date(2026, 6, 1))
        self.assertTrue(roadmap.months)
        for entry in roadmap.entries:
            self.assertRegex(entry.start, r"^\d{4}-\d{2}-\d{2}$")
            self.assertRegex(entry.end, r"^\d{4}-\d{2}-\d{2}$")
            self.assertLessEqual(entry.start, entry.end)

    def test_without_new_demand_only_portfolio(self) -> None:
        roadmap = build_roadmap(language="en", today=date(2026, 6, 1))
        self.assertFalse(any(e.is_new_demand for e in roadmap.entries))


class TimelineTests(unittest.TestCase):
    def test_all_milestones_have_dates(self) -> None:
        timeline = build_prince2_timeline("de", today=date(2026, 6, 1))
        self.assertTrue(timeline.milestones)
        self.assertIsNotNone(timeline.planned_project_start)
        for milestone in timeline.milestones:
            self.assertIsNotNone(milestone.date)
            self.assertEqual(milestone.kind, "generated")

    def test_milestones_are_chronological(self) -> None:
        timeline = build_prince2_timeline("en", today=date(2026, 6, 1))
        dates = [m.date for m in timeline.milestones]
        self.assertEqual(dates, sorted(d for d in dates if d is not None))


if __name__ == "__main__":
    unittest.main()
