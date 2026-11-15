"""Live account tests — probe Migros's real gate shapes WITHOUT a session.

Run:  pytest tests/test_live_account.py -v
Skip: pytest -m "not live"  (or set MIGROS_SKIP_LIVE=1)

No session material anywhere: every probe runs cookie-less. The cart
BFF's documented gate shape is a bare HTTP 400 (empty body) — real and
nonexistent paths alike (see tests/fixtures/account-gate.json) — so
these tests assert the gate, not a 401. The order BFF's user-scoped
paths DO return 401. Mutating verbs without a session hang (WAF
tarpit): the PUT probe accepts a timeout or a 4xx. Authed behaviour
cannot be verified from a sandbox at all (any Cookie header hangs —
even on the public homepage) and needs the owner's own smoke test.
"""
import os
import pathlib
import sys
import time
import unittest

import pytest
from curl_cffi import requests as _r

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from migros_mcp import account as _A

pytestmark = pytest.mark.live
SKIP = os.environ.get("MIGROS_SKIP_LIVE") == "1"

_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "tr",
    "X-Requested-With": "XMLHttpRequest",
    "X-FORWARDED-REST": "true",
    "X-PWA": "true",
    "X-Device-PWA": "true",
}

_FAKE_PRODUCT = 20000011010208


@pytest.mark.skipif(SKIP, reason="MIGROS_SKIP_LIVE=1")
class TestLiveAccountGates(unittest.TestCase):
    def test_cart_get_gate_is_bare_400(self):
        resp = _r.get(
            f"{_A.CART_BFF}/carts?isCartPage=true",
            impersonate="chrome120", headers=_HEADERS, timeout=30,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.text, "")
        self.assertEqual(
            resp.headers.get("x-bff-app-name"), "grocery-cart-bff-app"
        )
        print("\nLIVE cart GET gate: bare 400, grocery-cart-bff-app")
        time.sleep(1)

    def test_order_bff_users_active_is_401(self):
        resp = _r.get(
            f"{_A.ORDER_BFF}/master-orders/users/active",
            impersonate="chrome120", headers=_HEADERS, timeout=30,
        )
        self.assertEqual(resp.status_code, 401)
        print("\nLIVE order-bff users/active gate: 401")
        time.sleep(1)

    def test_cart_put_tarpits_without_session(self):
        """Mutating verbs without a session hang (WAF tarpit) — accept
        a timeout or any 4xx; a 2xx without a session would be news."""
        try:
            resp = _r.request(
                "PUT", f"{_A.CART_BFF}/carts/items",
                impersonate="chrome120", headers=_HEADERS,
                json={"items": []}, timeout=15,
            )
        except Exception as e:
            print(f"\nLIVE cart PUT gate: timed out as documented ({e})")
            return
        self.assertGreaterEqual(resp.status_code, 400)
        print(f"\nLIVE cart PUT gate: HTTP {resp.status_code} (no tarpit)")
        time.sleep(1)

    def test_product_resolver_live(self):
        info = _A.resolve_product(_FAKE_PRODUCT)
        self.assertEqual(info["store_id"], 20000000000607)
        self.assertEqual(info["unit"], "PIECE")
        self.assertEqual(info["max_amount"], 8)
        print(
            f"\nLIVE resolver: {info['name']} store={info['store_id']} "
            f"unit={info['unit']} max={info['max_amount']}"
        )


if __name__ == "__main__":
    unittest.main()
