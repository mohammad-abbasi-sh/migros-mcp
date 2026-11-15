"""Offline tests for migros_mcp.account — local-session cart + start-checkout.

All HTTP is mocked (account._raw_request patched, plus the public
product-detail fetch); no network calls and no real session material
anywhere. Fake cookie values are obvious placeholders
("fake-uid", ...). Fixtures: account-gate.json (gate shapes RECORDED
live 2026-11-15: cart BFF bare 400 without a session, order BFF 401)
plus SYNTHETIC success responses shaped per the public JS findings
(the real authed response shapes are unverified without a live
account — parsers are defensive). Product data comes from the real
recorded product_detail.json fixture.
"""
import json
import os
import unittest
from unittest import mock

from migros_mcp import account as A

FIX = os.path.join(os.path.dirname(__file__), "fixtures")

FAKE_SESSION = (
    "uid=fake-uid; hmail=fake@example.com; "
    "XSRF-TOKEN=fake-xsrf-token; _cfuvid=fake-cfuvid"
)
FAKE_PRODUCT = 20000011010208
FAKE_STORE = 20000000000607
FAKE_UNIT = "PIECE"


def _read(name: str) -> str:
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def _read_json(name: str):
    return json.loads(_read(name))


class FakeHeaders(dict):
    def get_list(self, name):
        value = self.get(name.lower())
        if isinstance(value, list):
            return value
        return [value] if value else []


class FakeResponse:
    def __init__(self, status_code, body=None, headers=None):
        self.status_code = status_code
        self._body = body
        self.headers = FakeHeaders(headers or {})

    @property
    def text(self):
        if self._body is None:
            return ""
        if isinstance(self._body, str):
            return self._body
        return json.dumps(self._body)

    def json(self):
        return self._body


class AccountTestCase(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(
            os.environ, {A.SESSION_ENV: FAKE_SESSION}, clear=False
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.calls = []

    def _mock_raw(self, mapping=None):
        """Patch A._raw_request; mapping: (method, url) -> FakeResponse
        (or a list of responses served in order). Records every call."""
        mapping = mapping or {}

        def fake(method, url, headers, json_body=None, timeout=None):
            self.calls.append((method, url, dict(headers), json_body))
            key = (method, url)
            resp = mapping.get(key)
            if isinstance(resp, list):
                return resp.pop(0) if resp else FakeResponse(500, {})
            if resp is not None:
                return resp
            return FakeResponse(404, {"message": "not stubbed"})

        patcher = mock.patch.object(A, "_raw_request", side_effect=fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return fake

    def _mock_product(self, payload=None):
        """Patch the public product-detail fetch (default: the real
        recorded Sütaş fixture)."""
        if payload is None:
            payload = _read_json("product_detail.json")
        patcher = mock.patch(
            "migros_mcp.http.get_product", return_value=payload
        )
        started = patcher.start()
        self.addCleanup(patcher.stop)
        return started


class TestCookieParsing(AccountTestCase):
    def test_parse_cookies(self):
        session = A.Session(FAKE_SESSION)
        self.assertEqual(session.get("uid"), "fake-uid")
        self.assertEqual(session.get("hmail"), "fake@example.com")
        self.assertEqual(session.get("XSRF-TOKEN"), "fake-xsrf-token")
        self.assertIsNone(session.get("missing"))

    def test_parse_ignores_bare_flags(self):
        session = A.Session("uid=fake-uid; Secure; HttpOnly")
        self.assertEqual(session.get("uid"), "fake-uid")

    def test_cookie_header_roundtrip(self):
        session = A.Session(FAKE_SESSION)
        rebuilt = A._parse_cookie_header(session.cookie_header())
        self.assertEqual(rebuilt, A._parse_cookie_header(FAKE_SESSION))

    def test_get_session_reads_env_at_call_time(self):
        with mock.patch.dict(os.environ, {A.SESSION_ENV: "uid=second-fake"}):
            self.assertEqual(A.get_session().get("uid"), "second-fake")
        self.assertEqual(A.get_session().get("uid"), "fake-uid")

    def test_cart_headers(self):
        headers = A._cart_headers(A.get_session(), with_body=True)
        self.assertEqual(headers["Accept-Language"], "tr")
        self.assertEqual(headers["X-FORWARDED-REST"], "true")
        self.assertEqual(headers["X-PWA"], "true")
        self.assertEqual(headers["X-Device-PWA"], "true")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["X-XSRF-TOKEN"], "fake-xsrf-token")
        self.assertIn("uid=fake-uid", headers["Cookie"])
        self.assertIn("hmail=fake@example.com", headers["Cookie"])

    def test_headers_omit_xsrf_when_cookie_absent(self):
        session = A.Session("uid=only-uid")
        headers = A._cart_headers(session)
        self.assertNotIn("X-XSRF-TOKEN", headers)
        self.assertNotIn("Content-Type", headers)


class TestNoSession(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def _assert_inert(self, fn, *args, **kwargs):
        with mock.patch.object(
            A, "_raw_request", side_effect=AssertionError("network call made")
        ), mock.patch(
            "migros_mcp.http.get_product",
            side_effect=AssertionError("product fetch made"),
        ):
            with self.assertRaises(A.SessionNotConfigured) as ctx:
                fn(*args, **kwargs)
        self.assertIn("MIGROS_SESSION is not configured", str(ctx.exception))
        self.assertNotIn("fake-uid", str(ctx.exception))

    def test_all_account_tools_inert_without_session(self):
        self._assert_inert(A.view_cart)
        self._assert_inert(A.add_to_cart, FAKE_PRODUCT, 1)
        self._assert_inert(
            A.add_to_cart, FAKE_PRODUCT, 1,
            store_id=FAKE_STORE, unit=FAKE_UNIT,
        )
        self._assert_inert(A.remove_from_cart, FAKE_PRODUCT)
        self._assert_inert(A.update_cart_quantity, FAKE_PRODUCT, 2)
        self._assert_inert(A.start_checkout)


class TestServerToolsNoSession(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_server_tools_return_error_json(self):
        from migros_mcp import server as S

        for fn in (S.migros_view_cart, S.migros_create_order):
            out = json.loads(fn())
            self.assertIn("MIGROS_SESSION is not configured", out["error"])
        out = json.loads(S.migros_add_to_cart(FAKE_PRODUCT, 1, confirm=True))
        self.assertIn("MIGROS_SESSION is not configured", out["error"])


class TestConfirmation(AccountTestCase):
    def test_mutating_tools_require_confirm(self):
        from migros_mcp import server as S

        with mock.patch.object(
            A, "_raw_request", side_effect=AssertionError("network call made")
        ):
            cases = [
                S.migros_add_to_cart(FAKE_PRODUCT, 1),
                S.migros_remove_from_cart(FAKE_PRODUCT),
                S.migros_update_cart_quantity(FAKE_PRODUCT, 2),
                # Explicit confirm=False is the same as omitted.
                S.migros_remove_from_cart(FAKE_PRODUCT, confirm=False),
            ]
        for raw in cases:
            out = json.loads(raw)
            self.assertEqual(out["error"], "confirmation_required")
            self.assertIn("confirm=true", out["message"])

    def test_create_order_needs_no_confirm_it_only_returns_a_link(self):
        from migros_mcp import server as S

        self._mock_raw({
            ("GET", f"{A.CART_BFF}/carts?isCartPage=true"): FakeResponse(
                200, _read_json("account-cart.json")
            ),
        })
        out = json.loads(S.migros_create_order())
        self.assertEqual(out["checkout_url"], A.CHECKOUT_URL)
        self.assertEqual(out["total_item_count"], 3)


class TestValidation(AccountTestCase):
    def test_bad_product_id(self):
        for bad in (0, -1, 2.5, True, "20000011010208", None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                A.add_to_cart(bad, 1, store_id=FAKE_STORE, unit=FAKE_UNIT)
            with self.assertRaises(ValueError, msg=repr(bad)):
                A.remove_from_cart(bad, store_id=FAKE_STORE, unit=FAKE_UNIT)

    def test_quantity_bounds(self):
        for bad in (0, 100, -1, 2.5, True, "2"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                A.add_to_cart(
                    FAKE_PRODUCT, bad, store_id=FAKE_STORE, unit=FAKE_UNIT
                )
            with self.assertRaises(ValueError, msg=repr(bad)):
                A.update_cart_quantity(
                    FAKE_PRODUCT, bad, store_id=FAKE_STORE, unit=FAKE_UNIT
                )

    def test_quantity_edges_ok(self):
        self._mock_raw({
            ("PUT", f"{A.CART_BFF}/carts/items"): FakeResponse(
                200, _read_json("account-replace.json")
            ),
        })
        A.add_to_cart(
            FAKE_PRODUCT, 1, store_id=FAKE_STORE, unit=FAKE_UNIT
        )
        A.add_to_cart(
            FAKE_PRODUCT, 99, store_id=FAKE_STORE, unit=FAKE_UNIT
        )

    def test_bad_store_id_and_unit(self):
        with self.assertRaises(ValueError):
            A.add_to_cart(FAKE_PRODUCT, 1, store_id=0, unit=FAKE_UNIT)
        with self.assertRaises(ValueError):
            A.add_to_cart(FAKE_PRODUCT, 1, store_id="x", unit=FAKE_UNIT)
        with self.assertRaises(ValueError):
            A.add_to_cart(FAKE_PRODUCT, 1, store_id=FAKE_STORE, unit="  ")

    def test_max_amount_enforced_from_product_detail(self):
        # The recorded Sütaş fixture has maxAmount 8.
        self._mock_product()
        self._mock_raw({})
        with self.assertRaises(ValueError) as ctx:
            A.add_to_cart(FAKE_PRODUCT, 9)
        self.assertIn("exceeds this product's limit of 8", str(ctx.exception))
        self.assertEqual(self.calls, [])  # no cart call attempted


class TestResolveProduct(AccountTestCase):
    def test_resolve_from_real_fixture(self):
        self._mock_product()
        info = A.resolve_product(FAKE_PRODUCT)
        self.assertEqual(info["product_id"], FAKE_PRODUCT)
        self.assertEqual(info["name"], "Sütaş Latte 1 L")
        self.assertEqual(info["store_id"], FAKE_STORE)
        self.assertEqual(info["unit"], "PIECE")
        self.assertEqual(info["max_amount"], 8)

    def test_not_saleable_errors(self):
        payload = _read_json("product_detail.json")
        payload["data"]["saleable"] = False
        self._mock_product(payload)
        with self.assertRaises(A.AccountError) as ctx:
            A.resolve_product(FAKE_PRODUCT)
        self.assertIn("not saleable", str(ctx.exception))

    def test_missing_store_or_unit_errors(self):
        payload = _read_json("product_detail.json")
        del payload["data"]["storeId"]
        self._mock_product(payload)
        with self.assertRaises(A.AccountError) as ctx:
            A.resolve_product(FAKE_PRODUCT)
        self.assertIn("no store/unit info", str(ctx.exception))


class TestViewCart(AccountTestCase):
    def test_view_cart_parses_fixture(self):
        self._mock_raw({
            ("GET", f"{A.CART_BFF}/carts?isCartPage=true"): FakeResponse(
                200, _read_json("account-cart.json")
            ),
        })
        out = A.view_cart()
        self.assertEqual(len(out["items"]), 2)
        first = out["items"][0]
        self.assertEqual(first["cart_item_id"], "987654321")
        self.assertEqual(first["product_id"], FAKE_PRODUCT)
        self.assertEqual(first["name"], "Sütaş Latte 1 L")
        self.assertEqual(first["quantity"], 2)
        self.assertEqual(first["unit"], "PIECE")
        self.assertEqual(first["total_price_try"], 378.00)
        self.assertEqual(first["unit_price_try"], 189.00)
        self.assertEqual(out["items"][1]["total_price_try"], 75.00)
        self.assertEqual(out["total_item_count"], 3)
        self.assertEqual(out["total_product_price_try"], 453.00)
        self.assertEqual(out["total_price_try"], 453.00)
        self.assertEqual(out["delivery_fee_try"], 0.0)
        self.assertEqual(out["cart_url"], A.CART_URL)
        method, url, headers, _body = self.calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(headers["X-XSRF-TOKEN"], "fake-xsrf-token")

    def test_view_cart_empty_cart_is_not_an_error(self):
        self._mock_raw({
            ("GET", f"{A.CART_BFF}/carts?isCartPage=true"): FakeResponse(
                200, {"successful": True, "data": {"itemInfos": []}}
            ),
        })
        out = A.view_cart()
        self.assertEqual(out["items"], [])
        self.assertEqual(out["total_item_count"], 0)
        self.assertNotIn("note", out)

    def test_view_cart_unexpected_shape(self):
        self._mock_raw({
            ("GET", f"{A.CART_BFF}/carts?isCartPage=true"): FakeResponse(
                200, {"successful": True, "data": {"somethingElse": 1}}
            ),
        })
        out = A.view_cart()
        self.assertEqual(out["items"], [])
        self.assertEqual(out["note"], "unexpected response shape")
        self.assertEqual(out["response_keys"], ["somethingElse"])
        self.assertEqual(out["cart_url"], A.CART_URL)

    def test_view_cart_rejected_envelope_is_an_error(self):
        self._mock_raw({
            ("GET", f"{A.CART_BFF}/carts?isCartPage=true"): FakeResponse(
                200,
                {"successful": False, "errorCode": "31061",
                 "message": "Sepet bulunamadı"},
            ),
        })
        with self.assertRaises(A.AccountError) as ctx:
            A.view_cart()
        self.assertIn("rejected by Migros", str(ctx.exception))
        self.assertIn("31061", str(ctx.exception))


class TestAddToCart(AccountTestCase):
    def test_add_resolves_store_and_unit(self):
        fetch = self._mock_product()
        self._mock_raw({
            ("PUT", f"{A.CART_BFF}/carts/items"): FakeResponse(
                200, _read_json("account-replace.json")
            ),
        })
        out = A.add_to_cart(FAKE_PRODUCT, quantity=3)
        self.assertTrue(out["added"])
        self.assertEqual(out["product_id"], FAKE_PRODUCT)
        self.assertEqual(out["quantity"], 3)
        self.assertEqual(out["total_item_count"], 3)
        self.assertEqual(out["total_price_try"], 567.00)
        fetch.assert_called_once_with(FAKE_PRODUCT)
        method, url, headers, body = self.calls[0]
        self.assertEqual(method, "PUT")
        self.assertEqual(url, f"{A.CART_BFF}/carts/items")
        self.assertEqual(headers["X-XSRF-TOKEN"], "fake-xsrf-token")
        self.assertEqual(
            body,
            {"items": [{"productId": FAKE_PRODUCT, "storeId": FAKE_STORE,
                        "unit": "PIECE", "amount": 3}],
             "applyCrmDiscounts": False,
             "applySpecialDiscounts": False,
             "applyDeepDiscounts": False,
             "includeDeliveryFee": False,
             "applyFoodProductDiscounts": False},
        )

    def test_add_with_explicit_store_and_unit_skips_fetch(self):
        with mock.patch(
            "migros_mcp.http.get_product",
            side_effect=AssertionError("product fetch made"),
        ):
            self._mock_raw({
                ("PUT", f"{A.CART_BFF}/carts/items"): FakeResponse(
                    200, _read_json("account-replace.json")
                ),
            })
            out = A.add_to_cart(
                FAKE_PRODUCT, 2, store_id=FAKE_STORE, unit=FAKE_UNIT
            )
        self.assertTrue(out["added"])
        _m, _u, _h, body = self.calls[0]
        self.assertEqual(body["items"][0]["amount"], 2)


class TestRemoveAndUpdateCart(AccountTestCase):
    def test_remove_sends_amount_zero(self):
        self._mock_product()
        self._mock_raw({
            ("PUT", f"{A.CART_BFF}/carts/items"): FakeResponse(
                200, {"successful": True, "data": {"itemInfos": []}}
            ),
        })
        out = A.remove_from_cart(FAKE_PRODUCT)
        self.assertTrue(out["removed"])
        self.assertEqual(out["total_item_count"], 0)
        method, _url, _headers, body = self.calls[0]
        self.assertEqual(method, "PUT")
        self.assertEqual(
            body["items"],
            [{"productId": FAKE_PRODUCT, "storeId": FAKE_STORE,
              "unit": "PIECE", "amount": 0}],
        )

    def test_update_quantity(self):
        self._mock_raw({
            ("PUT", f"{A.CART_BFF}/carts/items"): FakeResponse(
                200, _read_json("account-replace.json")
            ),
        })
        out = A.update_cart_quantity(
            FAKE_PRODUCT, 3, store_id=FAKE_STORE, unit=FAKE_UNIT
        )
        self.assertTrue(out["updated"])
        self.assertEqual(out["quantity"], 3)
        self.assertEqual(out["total_price_try"], 567.00)
        _m, _u, _h, body = self.calls[0]
        self.assertEqual(body["items"][0]["amount"], 3)


class TestStartCheckout(AccountTestCase):
    def test_empty_cart_errors(self):
        self._mock_raw({
            ("GET", f"{A.CART_BFF}/carts?isCartPage=true"): FakeResponse(
                200, {"successful": True, "data": {"itemInfos": []}}
            ),
        })
        with self.assertRaises(A.AccountError) as ctx:
            A.start_checkout()
        self.assertIn("cart is empty", str(ctx.exception))

    def test_nonempty_cart_returns_checkout_link(self):
        self._mock_raw({
            ("GET", f"{A.CART_BFF}/carts?isCartPage=true"): FakeResponse(
                200, _read_json("account-cart.json")
            ),
        })
        out = A.start_checkout()
        self.assertEqual(out["checkout_url"], A.CHECKOUT_URL)
        self.assertEqual(out["cart_url"], A.CART_URL)
        self.assertEqual(out["total_item_count"], 3)
        self.assertEqual(out["total_price_try"], 453.00)
        self.assertIn("never places an order", out["note"])
        # Exactly one call (the cart read) — no order API call exists.
        self.assertEqual(len(self.calls), 1)


class TestErrorHandling(AccountTestCase):
    def test_401_is_session_expired(self):
        self._mock_raw({
            ("GET", f"{A.CART_BFF}/carts?isCartPage=true"): FakeResponse(401, {}),
        })
        with self.assertRaises(A.SessionExpired) as ctx:
            A.view_cart()
        self.assertIn("session expired", str(ctx.exception))

    def test_400_mentions_session_or_request(self):
        self._mock_raw({
            ("GET", f"{A.CART_BFF}/carts?isCartPage=true"): FakeResponse(400, ""),
        })
        with self.assertRaises(A.AccountError) as ctx:
            A.view_cart()
        self.assertIn("HTTP 400", str(ctx.exception))
        self.assertIn("session may be expired", str(ctx.exception))

    def test_429_and_500_messages(self):
        self._mock_raw({
            ("GET", f"{A.CART_BFF}/carts?isCartPage=true"): FakeResponse(429, {}),
        })
        with self.assertRaises(A.AccountError) as ctx:
            A.view_cart()
        self.assertIn("429", str(ctx.exception))

        self.calls.clear()
        self._mock_raw({
            ("GET", f"{A.CART_BFF}/carts?isCartPage=true"): FakeResponse(
                500, {"errorCode": "500", "message": "Internal error"}
            ),
        })
        with self.assertRaises(A.AccountError) as ctx:
            A.view_cart()
        self.assertIn("500", str(ctx.exception))
        self.assertIn("Internal error", str(ctx.exception))

    def test_errors_never_contain_session_material(self):
        self._mock_raw({
            ("GET", f"{A.CART_BFF}/carts?isCartPage=true"): FakeResponse(500, {}),
        })
        try:
            A.view_cart()
        except A.AccountError as e:
            self.assertNotIn("fake-uid", str(e))
            self.assertNotIn("fake@example.com", str(e))
            self.assertNotIn("fake-xsrf-token", str(e))
        else:
            self.fail("expected AccountError")


class TestGateFixture(unittest.TestCase):
    def test_recorded_gate_shapes(self):
        """The recorded 2026-11-15 probes: cart BFF bare-400s, order
        BFF 401s, PUT tarpit. Guards the documented gate story."""
        gate = _read_json("account-gate.json")
        by_url = {p["url"]: p for p in gate["probes"]}
        carts = by_url[
            "https://www.migros.com.tr/rest/grocery-cart-bff/carts?isCartPage=true"
        ]
        self.assertEqual(carts["status"], 400)
        self.assertEqual(carts["body"], "")
        self.assertEqual(carts["x-bff-app-name"], "grocery-cart-bff-app")
        active = by_url[
            "https://www.migros.com.tr/rest/order-bff/master-orders/users/active"
        ]
        self.assertEqual(active["status"], 401)
        put = by_url[
            "https://www.migros.com.tr/rest/grocery-cart-bff/carts/items"
        ]
        self.assertIn("timeout", str(put["status"]))


if __name__ == "__main__":
    unittest.main()
