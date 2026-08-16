import io
import logging
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from publix_sorter.cli import (
    SorterError,
    _parse_grocery_items,
    _read_grocery_items,
    main,
)
from publix_sorter.sorter import SortedItem
from publix_sorter.todoist import (
    TodoistProject,
    TodoistSortedTask,
    TodoistTask,
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

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"})
    @patch("publix_sorter.cli.logging.basicConfig")
    @patch("publix_sorter.cli.LocationCache")
    @patch("publix_sorter.cli.sort_grocery_items")
    def test_prints_known_locations_as_comments(
        self, sort_mock, cache_mock, logging_mock
    ) -> None:
        sort_mock.return_value = [
            SortedItem("penne pasta", "Aisle 6 - Pasta & Pasta Sauce"),
            SortedItem("mystery item", "Location unavailable"),
        ]
        output = io.StringIO()

        with redirect_stdout(output):
            main(["sort", "--debug", "penne pasta", "mystery item"])

        self.assertEqual(
            output.getvalue(),
            "- penne pasta  # Aisle 6 - Pasta & Pasta Sauce\n- mystery item\n",
        )
        cache_mock.assert_called_once()
        logging_mock.assert_called_once_with(
            level=logging.DEBUG, format="[debug] %(message)s"
        )

    @patch.dict(
        "os.environ",
        {"OPENROUTER_API_KEY": "openrouter-key", "TODOIST_API_TOKEN": "todoist-key"},
    )
    @patch("publix_sorter.cli.LocationCache")
    @patch("publix_sorter.cli.sort_todoist_project")
    def test_sorts_todoist_project_and_prints_location_labels(
        self, sort_project_mock, cache_mock
    ) -> None:
        project = TodoistProject("project-1", "Groceries")
        pasta = TodoistTask(
            id="task-1",
            content="penne pasta",
            project_id=project.id,
            section_id=None,
            parent_id=None,
            child_order=1,
            labels=(),
        )
        grapes = TodoistTask(
            id="task-2",
            content="green grapes",
            project_id=project.id,
            section_id=None,
            parent_id=None,
            child_order=2,
            labels=(),
        )
        sort_project_mock.return_value = (
            project,
            [
                TodoistSortedTask(grapes, "Produce", "Publix: Produce"),
                TodoistSortedTask(pasta, "Aisle 6", "Publix: 6"),
            ],
        )
        output = io.StringIO()

        with redirect_stdout(output):
            main(["todoist", "Groceries"])

        self.assertEqual(
            output.getvalue(),
            'Sorted 2 tasks in Todoist project "Groceries".\n'
            "- green grapes  # Publix: Produce\n"
            "- penne pasta  # Publix: 6\n",
        )
        sort_project_mock.assert_called_once_with(
            "Groceries",
            "todoist-key",
            "openrouter-key",
            cache_mock.return_value,
        )
        cache_mock.assert_called_once()

    @patch.dict(
        "os.environ",
        {"OPENROUTER_API_KEY": "openrouter-key", "TODOIST_API_TOKEN": "todoist-key"},
    )
    @patch("publix_sorter.cli.run_server")
    def test_starts_http_server(self, run_server_mock) -> None:
        main(
            [
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                "8765",
                "--cache",
                "test-cache.csv",
            ]
        )

        run_server_mock.assert_called_once_with(
            "127.0.0.1",
            8765,
            "todoist-key",
            "openrouter-key",
            Path("test-cache.csv"),
        )


if __name__ == "__main__":
    unittest.main()
