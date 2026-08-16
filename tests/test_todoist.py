import unittest
from unittest.mock import MagicMock

from publix_sorter.sorter import SortedItem
from publix_sorter.todoist import (
    MAX_LABEL_LENGTH,
    TodoistClient,
    TodoistError,
    TodoistProject,
    TodoistTask,
    location_label,
    require_flat_tasks,
)


def task(
    task_id: str,
    content: str,
    order: int,
    *,
    labels: tuple[str, ...] = (),
    section_id: str | None = None,
    parent_id: str | None = None,
) -> TodoistTask:
    return TodoistTask(
        id=task_id,
        content=content,
        project_id="project-1",
        section_id=section_id,
        parent_id=parent_id,
        child_order=order,
        labels=labels,
    )


class TodoistReadingTests(unittest.TestCase):
    def test_reads_all_project_pages(self) -> None:
        client = TodoistClient("token")
        client._request = MagicMock(
            side_effect=[
                {
                    "results": [{"id": "project-1", "name": "Groceries"}],
                    "next_cursor": "next page",
                },
                {
                    "results": [{"id": "project-2", "name": "Work"}],
                    "next_cursor": None,
                },
            ]
        )

        self.assertEqual(
            client.projects(),
            [
                TodoistProject("project-1", "Groceries"),
                TodoistProject("project-2", "Work"),
            ],
        )
        self.assertEqual(
            client._request.call_args_list[0].kwargs["query"], {"limit": 200}
        )
        self.assertEqual(
            client._request.call_args_list[1].kwargs["query"],
            {"limit": 200, "cursor": "next page"},
        )

    def test_resolves_project_by_id_or_case_insensitive_name(self) -> None:
        client = TodoistClient("token")
        client.projects = MagicMock(
            return_value=[TodoistProject("project-1", "Groceries")]
        )

        self.assertEqual(client.resolve_project("project-1").id, "project-1")
        self.assertEqual(client.resolve_project(" groceries ").id, "project-1")

    def test_rejects_ambiguous_project_name(self) -> None:
        client = TodoistClient("token")
        client.projects = MagicMock(
            return_value=[
                TodoistProject("project-1", "Groceries"),
                TodoistProject("project-2", "Groceries"),
            ]
        )

        with self.assertRaisesRegex(TodoistError, "use a project ID"):
            client.resolve_project("Groceries")

    def test_reads_tasks_in_their_existing_order(self) -> None:
        client = TodoistClient("token")
        client._get_all = MagicMock(
            return_value=[
                {
                    "id": "task-2",
                    "content": "penne pasta",
                    "project_id": "project-1",
                    "section_id": None,
                    "parent_id": None,
                    "child_order": 2,
                    "labels": ["weekly"],
                },
                {
                    "id": "task-1",
                    "content": "green grapes",
                    "project_id": "project-1",
                    "section_id": None,
                    "parent_id": None,
                    "child_order": 1,
                    "labels": [],
                },
            ]
        )

        tasks = client.tasks("project-1")

        self.assertEqual([row.id for row in tasks], ["task-1", "task-2"])
        self.assertEqual(tasks[1].labels, ("weekly",))
        client._get_all.assert_called_once_with(
            "tasks", {"project_id": "project-1"}
        )


class TodoistSortingTests(unittest.TestCase):
    def test_rejects_sections_and_subtasks(self) -> None:
        with self.assertRaisesRegex(TodoistError, "sections"):
            require_flat_tasks([task("1", "milk", 1, section_id="section-1")])
        with self.assertRaisesRegex(TodoistError, "subtasks"):
            require_flat_tasks([task("1", "milk", 1, parent_id="parent-1")])

    def test_reorders_tasks_and_replaces_only_publix_labels(self) -> None:
        client = TodoistClient("token")
        client._send_commands = MagicMock()
        tasks = [
            task(
                "pasta",
                "penne pasta",
                1,
                labels=("weekly", "Publix: Old location"),
            ),
            task("grapes", "green grapes", 2, labels=("organic",)),
        ]

        result = client.apply_sort(
            tasks,
            [
                SortedItem("green grapes", "Produce"),
                SortedItem("penne pasta", "Aisle 6 - Pasta & Pasta Sauce"),
            ],
        )

        self.assertEqual([row.task.id for row in result], ["grapes", "pasta"])
        commands = client._send_commands.call_args.args[0]
        updates = {
            command["args"]["id"]: command["args"]["labels"]
            for command in commands
            if command["type"] == "item_update"
        }
        self.assertEqual(updates["grapes"], ["organic", "Publix: Produce"])
        self.assertEqual(
            updates["pasta"],
            ["weekly", "Publix: 6"],
        )
        reorder = next(
            command for command in commands if command["type"] == "item_reorder"
        )
        self.assertEqual(
            reorder["args"]["items"],
            [
                {"id": "grapes", "child_order": 1},
                {"id": "pasta", "child_order": 2},
            ],
        )

    def test_unknown_location_removes_old_publix_label(self) -> None:
        client = TodoistClient("token")
        client._send_commands = MagicMock()

        result = client.apply_sort(
            [task("mystery", "mystery item", 1, labels=("Publix: Aisle 2",))],
            [SortedItem("mystery item", "Location unavailable")],
        )

        self.assertIsNone(result[0].label)
        commands = client._send_commands.call_args.args[0]
        self.assertEqual(commands[0]["args"]["labels"], [])

    def test_caps_location_labels_at_todoist_limit(self) -> None:
        label = location_label("A" * 100)

        self.assertIsNotNone(label)
        self.assertEqual(len(label or ""), MAX_LABEL_LENGTH)

    def test_aisle_label_contains_only_its_number(self) -> None:
        self.assertEqual(
            location_label("Aisle 12 - Canned Vegetables"), "Publix: 12"
        )
        self.assertEqual(location_label("Produce"), "Publix: Produce")

    def test_batches_at_most_one_hundred_sync_commands(self) -> None:
        client = TodoistClient("token")
        client._send_commands = MagicMock()
        tasks = [task(str(index), f"item {index}", index) for index in range(100)]
        sorted_items = [SortedItem(row.content, "Produce") for row in tasks]

        client.apply_sort(tasks, sorted_items)

        batches = [call.args[0] for call in client._send_commands.call_args_list]
        self.assertEqual([len(batch) for batch in batches], [100, 1])
        self.assertEqual(batches[-1][0]["type"], "item_reorder")

    def test_reports_sync_command_errors(self) -> None:
        client = TodoistClient("token")
        command = {"type": "item_update", "uuid": "command-1", "args": {}}
        client._request = MagicMock(
            return_value={
                "sync_status": {"command-1": {"error": "Permission denied"}}
            }
        )

        with self.assertRaisesRegex(TodoistError, "Permission denied"):
            client._send_commands([command])
        request = client._request.call_args
        self.assertEqual(request.args, ("sync",))
        self.assertEqual(request.kwargs["method"], "POST")
        self.assertEqual(
            request.kwargs["form"]["commands"],
            '[{"type":"item_update","uuid":"command-1","args":{}}]',
        )


if __name__ == "__main__":
    unittest.main()
