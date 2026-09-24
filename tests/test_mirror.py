import copy
import json
import tempfile
import unittest
from pathlib import Path

import mirror


def sample():
    return {
        "schemaVersion": 1, "status": "online", "publisher": "Scout", "scoutVersion": "1.3.0",
        "generatedUtc": "2026-09-19T13:49:55Z", "project": "Scout", "receivedUtc": "2026-09-19T13:49:56Z",
        "searches": [{"id": "a", "name": "GPU", "query": "GPU", "checkedUtc": "2026-09-19T13:49:38Z",
                      "resultCount": 0, "pricing": {"calculatorVersion": 1, "target": 500,
                      "freshReferenceSources": 0, "currentConfidence": "None", "coverage30": "Insufficient",
                      "validDays30": 0, "coverage90": "Insufficient", "validDays90": 0,
                      "trend": "InsufficientData"}}]
    }


def encoded(value):
    return json.dumps(value).encode()


def with_result(url, source="Best Buy"):
    value = sample()
    value["searches"][0]["resultCount"] = 1
    value["searches"][0]["bestResult"] = {
        "title": "Reviewed product",
        "price": 499.99,
        "condition": "New",
        "source": source,
        "url": url,
        "buying": "Available",
        "lastSeenUtc": "2026-09-19T13:49:38Z",
    }
    return value


class MirrorTests(unittest.TestCase):
    def test_valid_schema_v1(self):
        self.assertEqual(mirror.decode(encoded(sample())), sample())

    def test_malformed_json(self):
        with self.assertRaises(ValueError):
            mirror.decode(b"{")

    def test_private_path_field(self):
        value = sample()
        value["searches"][0]["profilePath"] = "C:\\Users\\someone"
        with self.assertRaises(ValueError):
            mirror.decode(encoded(value))

    def test_private_path_in_allowed_text_field(self):
        value = sample()
        value["searches"][0]["name"] = "C:\\Users\\someone\\profile"
        with self.assertRaises(ValueError):
            mirror.decode(encoded(value))

    def test_token_field(self):
        value = sample()
        value["apiToken"] = "abc"
        with self.assertRaises(ValueError):
            mirror.decode(encoded(value))

    def test_postal_context_in_allowed_text_field(self):
        value = sample()
        value["searches"][0]["query"] = "ZIP 60601"
        with self.assertRaises(ValueError):
            mirror.decode(encoded(value))

    def test_unexpected_field(self):
        value = sample()
        value["newPublicField"] = "hello"
        with self.assertRaises(ValueError):
            mirror.decode(encoded(value))

    def test_best_buy_current_product_url(self):
        url = "https://www.bestbuy.com/product/reviewed-product/JJGGLH7RSP"
        self.assertEqual(mirror.decode(encoded(with_result(url)))["searches"][0]["bestResult"]["url"], url)

    def test_best_buy_product_url_without_query(self):
        url = "https://www.bestbuy.com/site/reviewed-product/6578510.p"
        self.assertEqual(mirror.decode(encoded(with_result(url)))["searches"][0]["bestResult"]["url"], url)

    def test_best_buy_matching_sku_query(self):
        url = "https://www.bestbuy.com/site/reviewed-product/6578510.p?skuId=6578510"
        self.assertEqual(mirror.decode(encoded(with_result(url)))["searches"][0]["bestResult"]["url"], url)

    def test_best_buy_mismatched_sku_query(self):
        url = "https://www.bestbuy.com/site/reviewed-product/6578510.p?skuId=1234567"
        with self.assertRaises(ValueError):
            mirror.decode(encoded(with_result(url)))

    def test_best_buy_nonnumeric_sku_query(self):
        url = "https://www.bestbuy.com/site/reviewed-product/6578510.p?skuId=not-a-sku"
        with self.assertRaises(ValueError):
            mirror.decode(encoded(with_result(url)))

    def test_best_buy_unrelated_query_parameter(self):
        url = "https://www.bestbuy.com/site/reviewed-product/6578510.p?ref=campaign"
        with self.assertRaises(ValueError):
            mirror.decode(encoded(with_result(url)))

    def test_best_buy_additional_query_parameter(self):
        url = "https://www.bestbuy.com/site/reviewed-product/6578510.p?skuId=6578510&ref=campaign"
        with self.assertRaises(ValueError):
            mirror.decode(encoded(with_result(url)))

    def test_best_buy_current_product_url_rejects_query(self):
        url = "https://www.bestbuy.com/product/reviewed-product/JJGGLH7RSP?skuId=6578510"
        with self.assertRaises(ValueError):
            mirror.decode(encoded(with_result(url)))

    def test_best_buy_fragment(self):
        url = "https://www.bestbuy.com/site/reviewed-product/6578510.p#details"
        with self.assertRaises(ValueError):
            mirror.decode(encoded(with_result(url)))

    def test_best_buy_http(self):
        url = "http://www.bestbuy.com/site/reviewed-product/6578510.p"
        with self.assertRaises(ValueError):
            mirror.decode(encoded(with_result(url)))

    def test_best_buy_credentials(self):
        url = "https://user:password@www.bestbuy.com/site/reviewed-product/6578510.p"
        with self.assertRaises(ValueError):
            mirror.decode(encoded(with_result(url)))

    def test_best_buy_lookalike_subdomain(self):
        url = "https://bestbuy.example.com/site/reviewed-product/6578510.p"
        with self.assertRaises(ValueError):
            mirror.decode(encoded(with_result(url)))

    def test_best_buy_lookalike_suffix(self):
        url = "https://www.bestbuy.com.evil.example/site/reviewed-product/6578510.p"
        with self.assertRaises(ValueError):
            mirror.decode(encoded(with_result(url)))

    def test_best_buy_non_product_page(self):
        url = "https://www.bestbuy.com/site/searchpage.jsp"
        with self.assertRaises(ValueError):
            mirror.decode(encoded(with_result(url)))

    def test_best_buy_noncanonical_product_path(self):
        url = "https://www.bestbuy.com/product/../JJGGLH7RSP"
        with self.assertRaises(ValueError):
            mirror.decode(encoded(with_result(url)))

    def test_existing_reviewed_retailer_urls(self):
        urls = {
            "eBay": "https://www.ebay.com/itm/123456789012",
            "Walmart": "https://www.walmart.com/ip/123456789",
            "Newegg": "https://www.newegg.com/p/N82E16814137861",
        }
        for source, url in urls.items():
            with self.subTest(source=source):
                self.assertEqual(mirror.decode(encoded(with_result(url, source)))["searches"][0]["bestResult"]["url"], url)

    def test_failed_best_buy_validation_preserves_prior(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scout-current.json"
            mirror.update(path, lambda: encoded(sample()))
            old = path.read_bytes()
            bad = with_result("https://www.bestbuy.com/site/searchpage.jsp")
            with self.assertRaises(ValueError):
                mirror.update(path, lambda: encoded(bad))
            self.assertEqual(path.read_bytes(), old)

    def test_identical_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scout-current.json"
            self.assertTrue(mirror.update(path, lambda: encoded(sample())))
            old = path.read_bytes()
            self.assertFalse(mirror.update(path, lambda: encoded(sample())))
            self.assertEqual(path.read_bytes(), old)

    def test_changed_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scout-current.json"
            mirror.update(path, lambda: encoded(sample()))
            changed = copy.deepcopy(sample())
            changed["searches"][0]["resultCount"] = 1
            self.assertTrue(mirror.update(path, lambda: encoded(changed)))
            self.assertEqual(json.loads(path.read_text())["searches"][0]["resultCount"], 1)

    def test_failed_fetch_preserves_prior(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scout-current.json"
            mirror.update(path, lambda: encoded(sample()))
            old = path.read_bytes()
            def fail():
                raise ConnectionError("source unavailable")
            with self.assertRaises(ConnectionError):
                mirror.update(path, fail)
            self.assertEqual(path.read_bytes(), old)

    def test_bad_payload_preserves_prior(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scout-current.json"
            mirror.update(path, lambda: encoded(sample()))
            old = path.read_bytes()
            with self.assertRaises(ValueError):
                mirror.update(path, lambda: b"not json")
            self.assertEqual(path.read_bytes(), old)


if __name__ == "__main__":
    unittest.main()
