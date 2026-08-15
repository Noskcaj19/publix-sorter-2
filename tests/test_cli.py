import json
import unittest
from urllib.parse import unquote

from publix_sorter.cli import (
    PublixError,
    _parse_products,
    _search_request,
)


class ParseProductsTests(unittest.TestCase):
    def test_parses_names_and_locations_from_search_payload(self) -> None:
        page = """
            <div :first-search-results="{&quot;storeProducts&quot;:[
                {&quot;title&quot;:&quot;Publix Pasta&quot;,
                 &quot;inStoreLocation&quot;:[&quot;Aisle 3 - Pasta&quot;]},
                {&quot;title&quot;:&quot;Fresh Pasta&quot;,
                 &quot;inStoreLocation&quot;:null}
            ]}"></div>
        """

        products = _parse_products(page)

        self.assertEqual(products[0].name, "Publix Pasta")
        self.assertEqual(products[0].location, "Aisle 3 - Pasta")
        self.assertEqual(products[1].name, "Fresh Pasta")
        self.assertEqual(products[1].location, "Location unavailable")

    def test_rejects_page_without_results_payload(self) -> None:
        with self.assertRaisesRegex(PublixError, "results were not found"):
            _parse_products("<html></html>")


class SearchRequestTests(unittest.TestCase):
    def test_builds_publix_search_for_store_228(self) -> None:
        request = _search_request("whole milk")

        self.assertEqual(
            request.full_url,
            "https://www.publix.com/search?searchTerm=whole+milk&srt=products",
        )
        cookie_name, cookie_value = request.get_header("Cookie").split("=", 1)
        self.assertEqual(cookie_name, "Store")
        store = json.loads(unquote(cookie_value))
        self.assertEqual(store["StoreNumber"], 228)
        self.assertEqual(store["StoreName"], "Chasewood Plaza")


if __name__ == "__main__":
    unittest.main()
