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

    @patch.dict(
        "os.environ",
        {"OPENROUTER_API_KEY": "openrouter-key", "TODOIST_API_TOKEN": "todoist-key"},
    )
    @patch("publix_sorter.cli.LocationCache")
    @patch("publix_sorter.cli.sort_grocery_items")
    @patch("publix_sorter.cli.TodoistClient")
    def test_sorts_todoist_project_and_prints_location_labels(
        self, client_class, sort_mock, cache_mock
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
        client = client_class.return_value
        client.resolve_project.return_value = project
        client.tasks.return_value = [pasta, grapes]
        sort_mock.return_value = [
            SortedItem("green grapes", "Produce"),
            SortedItem("penne pasta", "Aisle 6"),
        ]
        client.apply_sort.return_value = [
            TodoistSortedTask(grapes, "Produce", "Publix: Produce"),
            TodoistSortedTask(pasta, "Aisle 6", "Publix: 6"),
        ]
        output = io.StringIO()

        with redirect_stdout(output):
            main(["todoist", "Groceries"])

        self.assertEqual(
            output.getvalue(),
            'Sorted 2 tasks in Todoist project "Groceries".\n'
            "- green grapes  # Publix: Produce\n"
            "- penne pasta  # Publix: 6\n",
        )
        sort_mock.assert_called_once()
        client.apply_sort.assert_called_once_with(
            [pasta, grapes], sort_mock.return_value
        )
        cache_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
