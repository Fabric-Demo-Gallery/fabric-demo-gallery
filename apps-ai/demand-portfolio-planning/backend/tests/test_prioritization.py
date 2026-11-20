import unittest

from demand_portfolio_planning.prioritization import rank_backlog


class PrioritizationTests(unittest.TestCase):
    def test_ranks_include_new_demand_and_are_sorted(self) -> None:
        result = rank_backlog(
            new_demand_id="new-demand",
            new_demand_name="Local payroll system",
            value=4,
            effort=2,
            urgency=4,
            roles=["SAP FI Specialist"],
            language="en",
        )
        self.assertGreater(result.total_items, 1)
        self.assertEqual(len(result.ranked), result.total_items)
        # Exactly one new-demand entry, with a rank in range.
        new_items = [i for i in result.ranked if i.is_new_demand]
        self.assertEqual(len(new_items), 1)
        self.assertEqual(new_items[0].rank, result.new_demand_rank)
        self.assertTrue(1 <= result.new_demand_rank <= result.total_items)
        # Sorted by score descending; ranks are contiguous 1..n.
        scores = [i.score for i in result.ranked]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual([i.rank for i in result.ranked], list(range(1, result.total_items + 1)))

    def test_only_proposed_backlog_competes(self) -> None:
        result = rank_backlog(
            new_demand_id="new-demand",
            new_demand_name="X",
            value=3,
            effort=3,
            urgency=3,
            roles=[],
            language="de",
        )
        # Running ("in_progress") projects are excluded from the competition.
        self.assertNotIn("prj-erp-s4-upgrade", {i.item_id for i in result.ranked})
        self.assertIn("new-demand", {i.item_id for i in result.ranked})
        self.assertTrue(result.method)


if __name__ == "__main__":
    unittest.main()
