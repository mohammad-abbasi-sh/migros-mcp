"""Offline tests — parse real captured Migros product-bff JSON, no network."""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from migros_mcp import products

FIX = pathlib.Path(__file__).resolve().parent / "fixtures"


class TestParseSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = json.loads((FIX / "search_sut.json").read_text(encoding="utf-8"))
        cls.parsed = products.parse_search(payload, "sut")

    def test_hit_count(self):
        self.assertEqual(self.parsed["hit_count"], 371)
        self.assertEqual(self.parsed["query"], "sut")

    def test_product_count(self):
        self.assertEqual(self.parsed["count"], 5)

    def test_first_product(self):
        p = self.parsed["products"][0]
        self.assertEqual(p["name"], "Sütaş Latte 1 L")
        self.assertEqual(p["brand"], "Sütaş")
        self.assertEqual(p["price_tl"], 189.00)
        self.assertEqual(p["regular_price_tl"], 189.00)
        self.assertEqual(p["money_discount_pct"], 0)
        self.assertEqual(p["category"], "Uzun Ömürlü Süt")
        self.assertIn("Süt", p["category_path"])
        self.assertTrue(p["url"].startswith("https://www.migros.com.tr/urun/"))
        self.assertTrue((p["image_url"] or "").startswith("https://"))

    def test_kurus_conversion(self):
        # Torku Uht Süt 1 L: 7500 kuruş -> 75.00 TRY
        p = next(x for x in self.parsed["products"] if x["name"].startswith("Torku"))
        self.assertEqual(p["price_tl"], 75.00)

    def test_failed_payload(self):
        with self.assertRaises(ValueError):
            products.parse_search({"successful": False, "errorDetail": "boom"}, "x")


class TestParseDetail(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = json.loads((FIX / "product_detail.json").read_text(encoding="utf-8"))
        cls.d = products.parse_product_detail(payload)

    def test_detail_fields(self):
        self.assertEqual(self.d["name"], "Sütaş Latte 1 L")
        self.assertEqual(self.d["id"], 20000011010208)
        self.assertEqual(self.d["price_tl"], 189.00)

    def test_description_is_plain_text(self):
        self.assertNotIn("<p>", self.d["description"])
        self.assertIn("İçindekiler", self.d["description"])


class TestCategories(unittest.TestCase):
    def test_categories(self):
        payload = json.loads((FIX / "categories.json").read_text(encoding="utf-8"))
        cats = products.parse_categories(payload)
        self.assertEqual(len(cats), 11)
        names = [c["name"] for c in cats]
        self.assertIn("Tüm İndirimli Ürünler", names)
        self.assertIn("Süt, Kahvaltılık", names)
        self.assertTrue(all(c["id"] for c in cats))


class TestPriceStats(unittest.TestCase):
    def test_stats(self):
        payload = json.loads((FIX / "search_sut.json").read_text(encoding="utf-8"))
        parsed = products.parse_search(payload, "sut")
        s = products.price_stats(parsed["products"])
        self.assertEqual(s["count"], 5)
        self.assertEqual(s["min_tl"], 52.75)
        self.assertEqual(s["max_tl"], 249.90)
        self.assertEqual(s["median_tl"], 184.90)
        self.assertIn("%3 Yağlı", s["cheapest"]["name"])
        self.assertIn("Kakaolu Süt 9 x", s["priciest"]["name"])

    def test_empty_stats(self):
        self.assertEqual(products.price_stats([])["count"], 0)

    def test_sort_map(self):
        self.assertEqual(products.SORTS["discount"], "indirim-yuzdesine-gore")
        self.assertEqual(products.SORTS["price_asc"], "once-en-dusuk-fiyat")


if __name__ == "__main__":
    unittest.main()
