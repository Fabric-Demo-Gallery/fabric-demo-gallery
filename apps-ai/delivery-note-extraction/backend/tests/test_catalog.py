import unittest
from unittest.mock import patch

from delivery_note_extraction.catalog import ModelOption
from delivery_note_extraction.catalog import reasoning_efforts_for_model
from delivery_note_extraction.catalog import resolve_reasoning_effort


class ReasoningEffortsTests(unittest.TestCase):
    def test_gpt5_efforts_are_version_specific(self) -> None:
        self.assertEqual(
            reasoning_efforts_for_model("gpt-5"),
            ("minimal", "low", "medium", "high"),
        )
        self.assertEqual(
            reasoning_efforts_for_model("gpt-5.1"),
            ("none", "low", "medium", "high"),
        )
        self.assertEqual(
            reasoning_efforts_for_model("gpt-5.4-mini"),
            ("none", "low", "medium", "high", "xhigh"),
        )
        self.assertEqual(
            reasoning_efforts_for_model("gpt-5.6-sol"),
            ("none", "low", "medium", "high", "xhigh", "max"),
        )

    @patch("delivery_note_extraction.catalog.get_settings")
    @patch("delivery_note_extraction.catalog.list_model_options")
    def test_invalid_configured_default_falls_back_to_model_minimum(
        self, list_options: unittest.mock.Mock, get_settings: unittest.mock.Mock
    ) -> None:
        list_options.return_value = [
            ModelOption(
                name="delivery-model",
                model="gpt-5.4",
                reasoning_efforts=("none", "low", "medium", "high", "xhigh"),
            )
        ]
        get_settings.return_value.azure_foundry_reasoning_effort = "minimal"

        self.assertEqual(resolve_reasoning_effort("delivery-model", None), "none")

    @patch("delivery_note_extraction.catalog.get_settings")
    @patch("delivery_note_extraction.catalog.list_model_options")
    def test_invalid_requested_effort_is_rejected(
        self, list_options: unittest.mock.Mock, get_settings: unittest.mock.Mock
    ) -> None:
        list_options.return_value = [
            ModelOption(
                name="delivery-model",
                model="gpt-5.4",
                reasoning_efforts=("none", "low", "medium", "high", "xhigh"),
            )
        ]
        get_settings.return_value.azure_foundry_reasoning_effort = "none"

        with self.assertRaisesRegex(ValueError, "minimal.*not supported"):
            resolve_reasoning_effort("delivery-model", "minimal")


if __name__ == "__main__":
    unittest.main()
