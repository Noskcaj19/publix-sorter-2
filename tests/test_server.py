import json
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from unittest.mock import patch

from publix_sorter.server import SORT_ENDPOINT, create_server
from publix_sorter.todoist import TodoistProject, TodoistSortedTask, TodoistTask


class TodoistSortServerTests(unittest.TestCase):
    @patch("publix_sorter.server.sort_todoist_project")
    def test_triggers_todoist_sort_from_project_query(self, sort_mock) -> None:
        project = TodoistProject("project-1", "Weekly Groceries")
        task = TodoistTask(
            id="task-1",
            content="penne pasta",
            project_id=project.id,
            section_id=None,
            parent_id=None,
            child_order=1,
            labels=(),
        )
        sort_mock.return_value = (
            project,
            [TodoistSortedTask(task, "Aisle 6", "Publix: 6")],
        )
        cache_path = Path("test-cache.csv")
        server = create_server(
            "127.0.0.1", 0, "todoist-key", "openrouter-key", cache_path
        )
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        port = server.server_address[1]
        query = urlencode({"project": "Weekly Groceries"})

        try:
            request = Request(
                f"http://127.0.0.1:{port}{SORT_ENDPOINT}?{query}", method="POST"
            )
            with urlopen(request, timeout=5) as response:
                body = json.load(response)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

        self.assertEqual(response.status, 200)
        self.assertEqual(
            body["project"],
            {"id": "project-1", "name": "Weekly Groceries"},
        )
        self.assertEqual(body["count"], 1)
        self.assertEqual(
            body["items"],
            [
                {
                    "task_id": "task-1",
                    "item": "penne pasta",
                    "location": "Aisle 6",
                    "label": "Publix: 6",
                }
            ],
        )
        call = sort_mock.call_args
        self.assertEqual(
            call.args[:3],
            ("Weekly Groceries", "todoist-key", "openrouter-key"),
        )
        self.assertEqual(call.args[3].path, cache_path)

    @patch("publix_sorter.server.sort_todoist_project")
    def test_rejects_missing_project_query(self, sort_mock) -> None:
        server = create_server(
            "127.0.0.1",
            0,
            "todoist-key",
            "openrouter-key",
            Path("test-cache.csv"),
        )
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        port = server.server_address[1]

        try:
            request = Request(
                f"http://127.0.0.1:{port}{SORT_ENDPOINT}", method="POST"
            )
            with self.assertRaises(HTTPError) as raised:
                urlopen(request, timeout=5)
            body = json.load(raised.exception)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

        self.assertEqual(raised.exception.code, 400)
        self.assertIn("project query parameter", body["error"])
        sort_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
