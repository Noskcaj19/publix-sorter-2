import unittest

from publix_sorter.cli import (
    SorterError,
    _parse_grocery_items,
    _read_grocery_items,
)


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


if __name__ == "__main__":
    unittest.main()
