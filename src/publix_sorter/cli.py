import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


SEARCH_URL = "https://www.publix.com/search"
STORE_NAME = "Chasewood Plaza"
STORE_NUMBER = 228
STORE_OPTIONS = "ACDFJNORTUV"


@dataclass(frozen=True)
class Product:
    name: str
    location: str


class PublixError(RuntimeError):
    """Raised when Publix cannot be queried or parsed."""


class _SearchResultsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results_json: str | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        for name, value in attrs:
            if name == ":first-search-results":
                self.results_json = value
                return


def _store_cookie() -> str:
    store = {
        "CreationDate": datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "Option": STORE_OPTIONS,
        "ShortStoreName": STORE_NAME,
        "StoreName": STORE_NAME,
        "StoreNumber": STORE_NUMBER,
    }
    value = quote(json.dumps(store, separators=(",", ":")), safe="")
    return f"Store={value}"


def _search_request(search_term: str) -> Request:
    query = urlencode({"searchTerm": search_term, "srt": "products"})
    return Request(
        f"{SEARCH_URL}?{query}",
        headers={
            "Accept": "text/html",
            "Cookie": _store_cookie(),
            "User-Agent": "Mozilla/5.0 (compatible; publix-sorter/0.1)",
        },
    )


def _parse_products(page: str) -> list[Product]:
    parser = _SearchResultsParser()
    parser.feed(page)
    if parser.results_json is None:
        raise PublixError(
            "Publix search results were not found; the page may have changed"
        )

    try:
        results = json.loads(parser.results_json)
        store_products = results["storeProducts"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise PublixError("Publix returned unrecognized search results") from error

    products = []
    for item in store_products:
        locations = item.get("inStoreLocation") or []
        location = ", ".join(locations) or "Location unavailable"
        products.append(Product(name=item["title"], location=location))
    return products


def search(search_term: str) -> list[Product]:
    try:
        with urlopen(_search_request(search_term), timeout=30) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            page = response.read().decode(charset)
    except HTTPError as error:
        raise PublixError(f"Publix returned HTTP {error.code}") from error
    except URLError as error:
        raise PublixError(f"Could not reach Publix: {error.reason}") from error
    except TimeoutError as error:
        raise PublixError("The request to Publix timed out") from error

    return _parse_products(page)


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Search Publix products at Chasewood Plaza (store 228) and show "
            "their in-store locations."
        )
    )
    parser.add_argument(
        "search_term",
        nargs="+",
        help="product to search for, for example: pasta",
    )
    args = parser.parse_args()
    search_term = " ".join(args.search_term)

    try:
        products = search(search_term)
    except PublixError as error:
        parser.exit(1, f"error: {error}\n")

    print(f"Store: {STORE_NAME} (#{STORE_NUMBER})")
    print(f'Search: "{search_term}"\n')
    _print_products(products)


if __name__ == "__main__":
    main()
