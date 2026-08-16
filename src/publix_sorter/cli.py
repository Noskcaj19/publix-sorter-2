import argparse
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
    return parser


def main(argv: list[str] | None = None) -> None:
    raw_arguments = list(sys.argv[1:] if argv is None else argv)
    if raw_arguments and raw_arguments[0] not in {"search", "sort", "-h", "--help"}:
        raw_arguments.insert(0, "search")
    parser = _build_parser()
    args = parser.parse_args(raw_arguments)

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
