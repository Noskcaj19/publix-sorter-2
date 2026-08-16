import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from publix_sorter.cli import (
    SorterError,
    _parse_grocery_items,
    _read_grocery_items,
    main,
)
from publix_sorter.sorter import SortedItem


class GroceryInputTests(unittest.TestCase):
    def test_parses_bulleted_and_numbered_lines(self) -> None:
        self.assertEqual(
            _parse_grocery_items(
                ["- grapes - green\n* apples x4", "3. penne pasta"]
            ),
            ["grapes - green", "apples x4", "penne pasta"],
        )

    def test_rejects_empty_list(self) -> None:
        with self.assertRaisesRegex(SorterError, "empty"):
            _read_grocery_items(["  "], None)

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"})
    @patch("publix_sorter.cli.LocationCache")
    @patch("publix_sorter.cli.sort_grocery_items")
    def test_prints_known_locations_as_comments(
        self, sort_mock, cache_mock
    ) -> None:
        sort_mock.return_value = [
            SortedItem("penne pasta", "Aisle 6 - Pasta & Pasta Sauce"),
            SortedItem("mystery item", "Location unavailable"),
        ]
        output = io.StringIO()

        with redirect_stdout(output):
            main(["sort", "penne pasta", "mystery item"])

        self.assertEqual(
            output.getvalue(),
            "- penne pasta  # Aisle 6 - Pasta & Pasta Sauce\n- mystery item\n",
        )
        cache_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
