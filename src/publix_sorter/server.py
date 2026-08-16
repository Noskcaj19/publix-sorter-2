import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from publix_sorter.sorter import LocationCache, SorterError
from publix_sorter.todoist import TodoistError, sort_todoist_project


SORT_ENDPOINT = "/todoist/sort"

logger = logging.getLogger(__name__)


class TodoistSortHTTPServer(HTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        todoist_token: str,
        openrouter_api_key: str,
        cache_path: Path,
    ) -> None:
        super().__init__(server_address, TodoistSortHandler)
        self.todoist_token = todoist_token
        self.openrouter_api_key = openrouter_api_key
        self.cache_path = cache_path


class TodoistSortHandler(BaseHTTPRequestHandler):
    server: TodoistSortHTTPServer

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        request = urlsplit(self.path)
        if request.path != SORT_ENDPOINT:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Endpoint not found"})
            return

        project_values = parse_qs(request.query, keep_blank_values=True).get(
            "project", []
        )
        if len(project_values) != 1 or not project_values[0].strip():
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "Provide one non-empty project query parameter"},
            )
            return

        try:
            project, sorted_tasks = sort_todoist_project(
                project_values[0].strip(),
                self.server.todoist_token,
                self.server.openrouter_api_key,
                LocationCache(self.server.cache_path),
            )
        except (SorterError, TodoistError) as error:
            self._send_json(HTTPStatus.BAD_GATEWAY, {"error": str(error)})
            return

        self._send_json(
            HTTPStatus.OK,
            {
                "project": {"id": project.id, "name": project.name},
                "count": len(sorted_tasks),
                "items": [
                    {
                        "task_id": result.task.id,
                        "item": result.task.content,
                        "location": result.location,
                        "label": result.label,
                    }
                    for result in sorted_tasks
                ],
            },
        )

    def do_GET(self) -> None:
        request = urlsplit(self.path)
        status = (
            HTTPStatus.METHOD_NOT_ALLOWED
            if request.path == SORT_ENDPOINT
            else HTTPStatus.NOT_FOUND
        )
        message = (
            "Use POST"
            if status == HTTPStatus.METHOD_NOT_ALLOWED
            else "Endpoint not found"
        )
        self._send_json(status, {"error": message})

    def log_message(self, message: str, *args) -> None:
        logger.info("%s - %s", self.address_string(), message % args)


def create_server(
    host: str,
    port: int,
    todoist_token: str,
    openrouter_api_key: str,
    cache_path: Path,
) -> TodoistSortHTTPServer:
    return TodoistSortHTTPServer(
        (host, port), todoist_token, openrouter_api_key, cache_path
    )


def run_server(
    host: str,
    port: int,
    todoist_token: str,
    openrouter_api_key: str,
    cache_path: Path,
) -> None:
    server = create_server(host, port, todoist_token, openrouter_api_key, cache_path)
    bound_host, bound_port = server.server_address
    print(f"Serving Todoist sorter on {bound_host}:{bound_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
