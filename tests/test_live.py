"""Live tests — hit the real migros.com.tr product-bff API. Cautious: 4 requests, then stop.

Run:  pytest tests/test_live.py -v
Skip: pytest -m "not live"  (or set MIGROS_SKIP_LIVE=1)
"""
import json
import os
import pathlib
import sys
import time
import unittest

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from migros_mcp import http as _http
from migros_mcp import products as _p

pytestmark = pytest.mark.live
SKIP = os.environ.get("MIGROS_SKIP_LIVE") == "1"


@pytest.mark.skipif(SKIP, reason="MIGROS_SKIP_LIVE=1")
class TestLive(unittest.TestCase):
    def test_search_is_real(self):
        res = _p.parse_search(_http.search_products("süt", 0, "akilli-siralama"), "süt")
        self.assertGreater(res["hit_count"], 100)
        self.assertGreater(len(res["products"]), 10)
        first = res["products"][0]
        self.assertTrue(first["name"])
        self.assertGreater(first["price_tl"], 0)
        print(f"\nLIVE süt: {res['hit_count']} hits, first: {first['name']} "
              f"{first['price_tl']} TL")
        time.sleep(1)

    def test_product_detail_is_real(self):
        d = _p.parse_product_detail(_http.get_product(20000011010208))
        self.assertEqual(d["name"], "Sütaş Latte 1 L")
        self.assertGreater(d["price_tl"], 0)
        time.sleep(1)

    def test_categories_are_real(self):
        cats = _p.parse_categories(_http.list_categories())
        self.assertGreaterEqual(len(cats), 10)
        self.assertIn("Tüm İndirimli Ürünler", [c["name"] for c in cats])
        time.sleep(1)

    def test_discount_sort_returns_discounts(self):
        res = _p.parse_search(_http.search_discounted("süt"), "süt")
        discounted = [p for p in res["products"] if (p.get("money_discount_pct") or 0) > 0]
        self.assertGreater(len(discounted), 0)
        top = max(discounted, key=lambda p: p["money_discount_pct"])
        print(f"\nLIVE top Money discount for süt: {top['name']} "
              f"{top['money_discount_pct']}%")
