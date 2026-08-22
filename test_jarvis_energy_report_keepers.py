"""Keepers and energy-score spec for the soon-to-be-86'd report.

get_professional_outcomes_updates lives in jarvis_clickup_strategy so it
survives deletion of jarvis_energy_report. The sleep-score cases document
the formula a ClickUp agent must replicate.
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import jarvis_clickup_strategy as jcs
from jarvis_energy_report import (
    compute_sleep_score,
    compute_task_stats,
    parse_category,
    parse_sleep_data,
)


class ProfessionalOutcomesKeepersTests(unittest.TestCase):
    def test_returns_all_when_no_since(self):
        tasks = [{"id": "1", "date_updated": "1"}, {"id": "2", "date_updated": "2"}]
        with patch.object(jcs, "get_list_tasks", return_value=tasks) as mock_get:
            result = jcs.get_professional_outcomes_updates("key")
        mock_get.assert_called_once_with("key", jcs.OUTSTANDING_LIST_ID)
        self.assertEqual(result, tasks)

    def test_filters_by_date_updated(self):
        since = datetime(2026, 8, 1, tzinfo=timezone.utc)
        since_ms = int(since.timestamp() * 1000)
        tasks = [
            {"id": "old", "date_updated": str(since_ms - 1)},
            {"id": "new", "date_updated": str(since_ms)},
            {"id": "newer", "date_updated": str(since_ms + 1)},
        ]
        with patch.object(jcs, "get_list_tasks", return_value=tasks):
            result = jcs.get_professional_outcomes_updates("key", since)
        self.assertEqual([t["id"] for t in result], ["new", "newer"])

    def test_exported_from_shared_module_not_energy_report(self):
        import jarvis_energy_report as jer

        self.assertIs(
            jer.get_professional_outcomes_updates,
            jcs.get_professional_outcomes_updates,
        )
        self.assertFalse(hasattr(jer, "OUTSTANDING_LIST_ID"))


class EnergyScoreSpecTests(unittest.TestCase):
    def test_parse_category(self):
        self.assertEqual(parse_category("Write report — Work — due today"), "Work")
        self.assertEqual(parse_category("no delimiter"), "Other")

    def test_parse_sleep_data(self):
        items = [{"name": "Sleep - sleep6:y rested:n strenuous:u"}]
        self.assertEqual(
            parse_sleep_data(items),
            {"slept_6plus": True, "rested": False, "strenuous_prior_day": None},
        )

    def test_score_full_rest_no_strain(self):
        items = [{"name": "Sleep - sleep6:y rested:y strenuous:n"}]
        self.assertEqual(compute_sleep_score(items)["score"], 10.0)

    def test_score_strenuous_penalty(self):
        items = [{"name": "Sleep - sleep6:y rested:y strenuous:y"}]
        self.assertEqual(compute_sleep_score(items)["score"], 8.0)

    def test_score_partial_core_signal(self):
        items = [{"name": "Sleep - sleep6:y rested:u strenuous:n"}]
        self.assertEqual(compute_sleep_score(items)["score"], 2.5)

    def test_score_missing_sleep_item(self):
        self.assertIsNone(compute_sleep_score([{"name": "Email — Work — due"}])["score"])

    def test_task_stats(self):
        items = [
            {"name": "A — Work — due", "resolved": True},
            {"name": "B — Personal — due", "resolved": False},
        ]
        stats = compute_task_stats(items)
        self.assertEqual(stats["completed"], 1)
        self.assertEqual(stats["carried_over"], 1)
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["completion_rate"], 0.5)
        self.assertEqual(stats["category_breakdown"]["Work"]["completed"], 1)
        self.assertEqual(stats["category_breakdown"]["Personal"]["total"], 1)


if __name__ == "__main__":
    unittest.main()
