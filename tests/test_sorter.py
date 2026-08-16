import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from publix_sorter.publix import Product
from publix_sorter.sorter import (
    LocationCache,
    SYSTEM_PROMPT,
    SorterError,
    _location_lookup,
    _parse_sorted_items,
    sort_grocery_items,
)


class LocationCacheTests(unittest.TestCase):
    def test_stores_only_first_five_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "locations.csv"
            cache = LocationCache(path)
            products = [Product(f"Product {index}", f"Aisle {index}") for index in range(7)]

            cache.remember("pasta", products)

            self.assertEqual(len(cache.find("PASTA")), 5)
            with path.open(newline="", encoding="utf-8") as cache_file:
                self.assertEqual(len(list(csv.DictReader(cache_file))), 5)

    @patch("publix_sorter.sorter.search")
    def test_location_lookup_queries_publix_and_then_uses_cache(self, search_mock) -> None:
        search_mock.return_value = [Product("Penne", "Aisle 6")] * 6
        with tempfile.TemporaryDirectory() as directory:
            cache = LocationCache(Path(directory) / "locations.csv")

            first = _location_lookup("penne", cache)
            second = _location_lookup("penne", cache)

        self.assertEqual(len(first["results"]), 5)
        self.assertEqual(second, first)
        search_mock.assert_called_once_with("penne")


class ModelSortingTests(unittest.TestCase):
    def test_places_cheese_after_nine_and_other_dairy_after_all_aisles(
        self,
    ) -> None:
        aisle_nine = SYSTEM_PROMPT.index("Numbered aisles 1 through 9")
        cheese = SYSTEM_PROMPT.index("Cheese, except")
        aisle_ten = SYSTEM_PROMPT.index("Numbered aisles 10 and higher")
        other_dairy = SYSTEM_PROMPT.index("All other dairy products")

        self.assertLess(aisle_nine, cheese)
        self.assertLess(cheese, aisle_ten)
        self.assertLess(aisle_ten, other_dairy)

    @patch("publix_sorter.sorter._chat_completion")
    @patch("publix_sorter.sorter.search")
    def test_runs_location_tool_and_returns_model_order(
        self, search_mock, chat_mock
    ) -> None:
        search_mock.return_value = [Product("Boar's Head Cheddar", "Deli")]
        chat_mock.side_effect = [
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "grocery_location",
                                        "arguments": json.dumps(
                                            {"query": "cheddar cheese"}
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "items": [
                                        {
                                            "item": "cheddar cheese",
                                            "location": "Deli",
                                        },
                                        {
                                            "item": "penne pasta",
                                            "location": "Aisle 6",
                                        },
                                    ]
                                }
                            ),
                        }
                    }
                ]
            },
        ]

        with tempfile.TemporaryDirectory() as directory:
            cache = LocationCache(Path(directory) / "locations.csv")
            cache.remember("penne pasta", [Product("Penne", "Aisle 6")])
            with self.assertLogs("publix_sorter.sorter", level="DEBUG") as logs:
                result = sort_grocery_items(
                    ["penne pasta", "cheddar cheese"], "test-key", cache
                )

        self.assertEqual(
            [item.item for item in result], ["cheddar cheese", "penne pasta"]
        )
        trace = "\n".join(logs.output)
        self.assertIn("Sorting agent system input text", trace)
        self.assertIn("Sorting agent user input text", trace)
        self.assertIn("Sorting agent output text", trace)
        self.assertIn("Sorting agent tool call", trace)
        self.assertIn("Sorting agent tool result (grocery_location)", trace)
        self.assertIn("cheddar cheese", trace)
        search_mock.assert_called_once_with("cheddar cheese")
        self.assertEqual(chat_mock.call_count, 2)
        system_prompt = chat_mock.call_args_list[0].args[1]["messages"][0]["content"]
        self.assertIn("penne pasta,Penne,Aisle 6", system_prompt)
        messages = chat_mock.call_args_list[1].args[1]["messages"]
        tool_message = next(
            message for message in reversed(messages) if message["role"] == "tool"
        )
        self.assertEqual(tool_message["role"], "tool")
        self.assertEqual(len(json.loads(tool_message["content"])["results"]), 1)

    def test_rejects_model_output_that_changes_an_item(self) -> None:
        content = json.dumps(
            {"items": [{"item": "green grapes", "location": "Produce"}]}
        )
        with self.assertRaisesRegex(SorterError, "changed or omitted"):
            _parse_sorted_items(content, ["grapes - green"])


if __name__ == "__main__":
    unittest.main()
