import json
from collections import defaultdict, deque
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from publix_sorter.sorter import SortedItem


TODOIST_API_URL = "https://api.todoist.com/api/v1"
LOCATION_LABEL_PREFIX = "Publix: "
MAX_LABEL_LENGTH = 60
MAX_SYNC_COMMANDS = 100
UNAVAILABLE_LOCATIONS = {"", "unknown", "location unavailable"}


@dataclass(frozen=True)
class TodoistProject:
    id: str
    name: str


@dataclass(frozen=True)
class TodoistTask:
    id: str
    content: str
    project_id: str
    section_id: str | None
    parent_id: str | None
    child_order: int
    labels: tuple[str, ...]


@dataclass(frozen=True)
class TodoistSortedTask:
    task: TodoistTask
    location: str
    label: str | None


class TodoistError(RuntimeError):
    """Raised when a Todoist project cannot be read or updated."""


def require_flat_tasks(tasks: list[TodoistTask]) -> None:
    if any(task.section_id is not None for task in tasks):
        raise TodoistError(
            "Todoist sorting only supports flat projects; move tasks out of "
            "sections first"
        )
    if any(task.parent_id is not None for task in tasks):
        raise TodoistError(
            "Todoist sorting only supports flat projects; move subtasks to the "
            "project root first"
        )


def location_label(location: str) -> str | None:
    normalized = location.strip()
    if normalized.casefold() in UNAVAILABLE_LOCATIONS:
        return None
    available_length = MAX_LABEL_LENGTH - len(LOCATION_LABEL_PREFIX)
    normalized = normalized[:available_length].rstrip()
    return f"{LOCATION_LABEL_PREFIX}{normalized}" if normalized else None


def _updated_labels(task: TodoistTask, label: str | None) -> tuple[str, ...]:
    prefix = LOCATION_LABEL_PREFIX.casefold()
    labels = [
        existing
        for existing in task.labels
        if not existing.casefold().startswith(prefix)
    ]
    if label is not None:
        labels.append(label)
    return tuple(labels)


def _match_sorted_tasks(
    tasks: list[TodoistTask], sorted_items: list[SortedItem]
) -> list[TodoistSortedTask]:
    tasks_by_content: dict[str, deque[TodoistTask]] = defaultdict(deque)
    for task in tasks:
        tasks_by_content[task.content].append(task)

    result = []
    for sorted_item in sorted_items:
        matching_tasks = tasks_by_content[sorted_item.item]
        if not matching_tasks:
            raise TodoistError("The sorted list does not match the Todoist tasks")
        result.append(
            TodoistSortedTask(
                task=matching_tasks.popleft(),
                location=sorted_item.location,
                label=location_label(sorted_item.location),
            )
        )

    if len(result) != len(tasks) or any(tasks_by_content.values()):
        raise TodoistError("The sorted list does not match the Todoist tasks")
    return result


class TodoistClient:
    def __init__(self, token: str) -> None:
        self.token = token

    def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        query: dict[str, str | int] | None = None,
        form: dict[str, str] | None = None,
    ) -> dict:
        url = f"{TODOIST_API_URL}/{path.lstrip('/')}"
        if query:
            url = f"{url}?{urlencode(query)}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        data = None
        if form is not None:
            data = urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = Request(url, data=data, headers=headers, method=method)

        try:
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except HTTPError as error:
            message = f"HTTP {error.code}"
            try:
                body = json.load(error)
                detail = body.get("error")
                if isinstance(detail, str) and detail:
                    message = detail
            except (json.JSONDecodeError, AttributeError):
                pass
            raise TodoistError(f"Todoist returned {message}") from error
        except URLError as error:
            raise TodoistError(f"Could not reach Todoist: {error.reason}") from error
        except TimeoutError as error:
            raise TodoistError("The request to Todoist timed out") from error
        except json.JSONDecodeError as error:
            raise TodoistError("Todoist returned an unrecognized response") from error

        if not isinstance(payload, dict):
            raise TodoistError("Todoist returned an unrecognized response")
        return payload

    def _get_all(
        self, path: str, query: dict[str, str | int] | None = None
    ) -> list[dict]:
        parameters = dict(query or {})
        parameters["limit"] = 200
        rows = []
        while True:
            payload = self._request(path, query=dict(parameters))
            page = payload.get("results")
            if not isinstance(page, list):
                raise TodoistError("Todoist returned an unrecognized list response")
            rows.extend(page)
            cursor = payload.get("next_cursor")
            if cursor is None:
                return rows
            if not isinstance(cursor, str) or not cursor:
                raise TodoistError("Todoist returned an invalid pagination cursor")
            parameters["cursor"] = cursor

    def projects(self) -> list[TodoistProject]:
        projects = []
        for row in self._get_all("projects"):
            try:
                project_id = row["id"]
                name = row["name"]
            except (KeyError, TypeError) as error:
                raise TodoistError("Todoist returned an invalid project") from error
            if not isinstance(project_id, str) or not isinstance(name, str):
                raise TodoistError("Todoist returned an invalid project")
            projects.append(TodoistProject(id=project_id, name=name))
        return projects

    def resolve_project(self, reference: str) -> TodoistProject:
        projects = self.projects()
        id_matches = [project for project in projects if project.id == reference]
        if id_matches:
            return id_matches[0]

        name = reference.strip().casefold()
        name_matches = [
            project for project in projects if project.name.strip().casefold() == name
        ]
        if not name_matches:
            raise TodoistError(f'Todoist project not found: "{reference}"')
        if len(name_matches) > 1:
            raise TodoistError(
                f'Multiple Todoist projects are named "{reference}"; use a project ID'
            )
        return name_matches[0]

    def tasks(self, project_id: str) -> list[TodoistTask]:
        tasks = []
        for row in self._get_all("tasks", {"project_id": project_id}):
            try:
                task_id = row["id"]
                content = row["content"]
                row_project_id = row["project_id"]
                section_id = row.get("section_id")
                parent_id = row.get("parent_id")
                child_order = row["child_order"]
                labels = row.get("labels", [])
            except (KeyError, TypeError) as error:
                raise TodoistError("Todoist returned an invalid task") from error
            if not (
                isinstance(task_id, str)
                and isinstance(content, str)
                and isinstance(row_project_id, str)
                and (section_id is None or isinstance(section_id, str))
                and (parent_id is None or isinstance(parent_id, str))
                and isinstance(child_order, int)
                and isinstance(labels, list)
                and all(isinstance(label, str) for label in labels)
            ):
                raise TodoistError("Todoist returned an invalid task")
            tasks.append(
                TodoistTask(
                    id=task_id,
                    content=content,
                    project_id=row_project_id,
                    section_id=section_id,
                    parent_id=parent_id,
                    child_order=child_order,
                    labels=tuple(labels),
                )
            )
        return sorted(tasks, key=lambda task: task.child_order)

    def _send_commands(self, commands: list[dict]) -> None:
        payload = self._request(
            "sync",
            method="POST",
            form={"commands": json.dumps(commands, separators=(",", ":"))},
        )
        statuses = payload.get("sync_status")
        if not isinstance(statuses, dict):
            raise TodoistError("Todoist returned an unrecognized sync response")

        failures = []
        for command in commands:
            status = statuses.get(command["uuid"])
            if status != "ok":
                message = status.get("error") if isinstance(status, dict) else None
                failures.append(message or "unknown update error")
        if failures:
            raise TodoistError(f"Todoist could not apply updates: {failures[0]}")

    def apply_sort(
        self, tasks: list[TodoistTask], sorted_items: list[SortedItem]
    ) -> list[TodoistSortedTask]:
        require_flat_tasks(tasks)
        sorted_tasks = _match_sorted_tasks(tasks, sorted_items)

        label_commands = []
        for result in sorted_tasks:
            labels = _updated_labels(result.task, result.label)
            if labels != result.task.labels:
                label_commands.append(
                    {
                        "type": "item_update",
                        "uuid": str(uuid4()),
                        "args": {"id": result.task.id, "labels": list(labels)},
                    }
                )

        reorder_command = {
            "type": "item_reorder",
            "uuid": str(uuid4()),
            "args": {
                "items": [
                    {"id": result.task.id, "child_order": order}
                    for order, result in enumerate(sorted_tasks, start=1)
                ]
            },
        }
        batches = [
            label_commands[index : index + MAX_SYNC_COMMANDS]
            for index in range(0, len(label_commands), MAX_SYNC_COMMANDS)
        ]
        if not batches:
            batches.append([reorder_command])
        elif len(batches[-1]) < MAX_SYNC_COMMANDS:
            batches[-1].append(reorder_command)
        else:
            batches.append([reorder_command])

        for batch in batches:
            self._send_commands(batch)
        return sorted_tasks
