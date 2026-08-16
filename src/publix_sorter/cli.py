import argparse
import logging
import os
import re
import sys
from pathlib import Path

from publix_sorter.publix import (
    STORE_NAME,
    STORE_NUMBER,
    Product,
    PublixError,
    search,
)
from publix_sorter.sorter import (
    LocationCache,
    SorterError,
    default_cache_path,
    sort_grocery_items,
)
from publix_sorter.todoist import (
    TodoistClient,
    TodoistError,
    require_flat_tasks,
)


def _print_products(products: list[Product]) -> None:
    if not products:
        print("No products found.")
        return

    name_width = max(len("Product"), *(len(product.name) for product in products))
    location_width = max(
        len("Location"), *(len(product.location) for product in products)
    )
    print(f"{'Product':<{name_width}}  Location")
    print(f"{'-' * name_width}  {'-' * location_width}")
    for product in products:
        print(f"{product.name:<{name_width}}  {product.location}")


def _parse_grocery_items(values: list[str]) -> list[str]:
    items = []
    for value in values:
        for line in value.splitlines():
            item = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", line).strip()
            if item:
                items.append(item)
    return items


def _read_grocery_items(values: list[str], file_name: str | None) -> list[str]:
    if values and file_name:
        raise SorterError("Use grocery item arguments or --file, not both")
    if file_name:
        try:
            content = (
                sys.stdin.read()
                if file_name == "-"
                else Path(file_name).read_text(encoding="utf-8")
            )
        except OSError as error:
            raise SorterError(f"Could not read grocery list: {file_name}") from error
        items = _parse_grocery_items([content])
    elif values:
        items = _parse_grocery_items(values)
    else:
        items = _parse_grocery_items([sys.stdin.read()])
    if not items:
        raise SorterError("The grocery list is empty")
    return items


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Search or sort groceries at Chasewood Plaza (Publix store 228)."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    search_parser = commands.add_parser(
        "search", help="find product names and in-store locations"
    )
    search_parser.add_argument(
        "search_term",
        nargs="+",
        help="product to search for, for example: pasta",
    )

    sort_parser = commands.add_parser(
        "sort", help="sort a grocery list into store walking order"
    )
    sort_parser.add_argument(
        "items",
        nargs="*",
        help="grocery items; when omitted, read newline-separated items from stdin",
    )
    sort_parser.add_argument(
        "-f", "--file", help="read grocery items from a text file, or - for stdin"
    )
    sort_parser.add_argument(
        "--cache",
        type=Path,
        default=default_cache_path(),
        help="location cache CSV path (default: %(default)s)",
    )
    sort_parser.add_argument(
        "--debug",
        action="store_true",
        help="log sorting-agent inputs, outputs, and tool calls to stderr",
    )

    todoist_parser = commands.add_parser(
        "todoist", help="sort and label a flat Todoist grocery project"
    )
    todoist_parser.add_argument("project", help="Todoist project name or ID")
    todoist_parser.add_argument(
        "--cache",
        type=Path,
        default=default_cache_path(),
        help="location cache CSV path (default: %(default)s)",
    )
    todoist_parser.add_argument(
        "--debug",
        action="store_true",
        help="log sorting-agent inputs, outputs, and tool calls to stderr",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    raw_arguments = list(sys.argv[1:] if argv is None else argv)
    if raw_arguments and raw_arguments[0] not in {
        "search",
        "sort",
        "todoist",
        "-h",
        "--help",
    }:
        raw_arguments.insert(0, "search")
    parser = _build_parser()
    args = parser.parse_args(raw_arguments)
    if getattr(args, "debug", False):
        logging.basicConfig(level=logging.DEBUG, format="[debug] %(message)s")

    if args.command == "search":
        search_term = " ".join(args.search_term)
        try:
            products = search(search_term)
        except PublixError as error:
            parser.exit(1, f"error: {error}\n")

        print(f"Store: {STORE_NAME} (#{STORE_NUMBER})")
        print(f'Search: "{search_term}"\n')
        _print_products(products)
        return

    if args.command == "todoist":
        try:
            todoist_token = os.environ.get("TODOIST_API_TOKEN")
            if not todoist_token:
                raise TodoistError("TODOIST_API_TOKEN is not set")
            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                raise SorterError("OPENROUTER_API_KEY is not set")

            client = TodoistClient(todoist_token)
            project = client.resolve_project(args.project)
            tasks = client.tasks(project.id)
            if not tasks:
                raise TodoistError(f'Todoist project "{project.name}" has no active tasks')
            require_flat_tasks(tasks)
            sorted_items = sort_grocery_items(
                [task.content for task in tasks],
                api_key,
                LocationCache(args.cache.expanduser()),
            )
            sorted_tasks = client.apply_sort(tasks, sorted_items)
        except (SorterError, TodoistError) as error:
            parser.exit(1, f"error: {error}\n")

        print(f'Sorted {len(sorted_tasks)} tasks in Todoist project "{project.name}".')
        for result in sorted_tasks:
            comment = f"  # {result.label}" if result.label else ""
            print(f"- {result.task.content}{comment}")
        return

    try:
        items = _read_grocery_items(args.items, args.file)
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise SorterError("OPENROUTER_API_KEY is not set")
        sorted_items = sort_grocery_items(
            items, api_key, LocationCache(args.cache.expanduser())
        )
    except SorterError as error:
        parser.exit(1, f"error: {error}\n")

    for item in sorted_items:
        location = item.location.strip()
        comment = (
            f"  # {location}"
            if location.casefold() not in {"", "unknown", "location unavailable"}
            else ""
        )
        print(f"- {item.item}{comment}")


if __name__ == "__main__":
    main()
