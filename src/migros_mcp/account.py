"""Local-session account actions (cart + start-checkout) for migros_mcp.

Session model: the user pastes their raw Cookie header value (copied
from their browser DevTools) into the MIGROS_SESSION env var in their
MCP client config. The server reads it from os.environ at call time
(not import time). The session never leaves the user's machine except
to migros.com.tr hosts: it is never logged, printed, persisted, or
included in any tool output or error message — not even redacted
fragments. There is no refresh flow: Migros auth is purely
cookie-based (the storefront sends no Authorization header and keeps
no token in localStorage), so an expired session means copying fresh
cookies from the browser (see README 'Account actions').

Endpoints (reverse-engineered from Migros's own public JS bundles —
the Angular storefront's generated OpenAPI clients, assets.migrosone.com
/sanalmarket-pweb-app, build 1.0.0-revert-4084-f-maya-382-4131998 —
and verified live 2026-11-15; base URLs from the storefront's own
env.js):
- Cart BFF https://www.migros.com.tr/rest/grocery-cart-bff
  GET /carts?isCartPage=true (view cart; get3 in the generated client,
  called by cartService.getCart)
  PUT /carts/items (add / update / remove; the generated `replace`
  method, called by cartService._updateCartViaRestService with
  {items: [{id?, productId, storeId, unit, amount, note?}],
  applyCrmDiscounts/applySpecialDiscounts/applyDeepDiscounts/
  includeDeliveryFee/applyFoodProductDiscounts: false}; amount 0
  removes the item — see the cart page's deleteItem, which calls
  update({productId, quantity: 0, unit, storeId}))
- Checkout page https://www.migros.com.tr/odeme (route verified in the
  storefront JS; order creation itself is a multi-step checkout flow —
  address, delivery slot, payment method — with no single verified
  "create order" call, so migros_create_order stops at the checkout
  link and never places an order or touches payment)

Live gate shapes (probed 2026-11-15, no session): the cart BFF
answers every cookie-less request with a bare HTTP 400 (empty body,
x-bff-app-name: grocery-cart-bff-app) — real and nonexistent paths
alike, so the 400 proves the base URL + session gate, not the path;
the path + method + body shape come from the JS bundles above.
Mutating verbs without a session hang (WAF tarpit). The order BFF
answers its user-scoped paths with HTTP 401 without a session
(GET /master-orders/users/active, GET /orders/users/active). From
this sandbox ANY request to migros.com.tr carrying a Cookie header
hangs — even the public homepage and product-bff with a junk cookie —
so authed end-to-end behaviour cannot be verified here and needs the
owner's own smoke test with a real session; it is never faked.

Response envelope (all BFF calls): {"successful": bool, "data": ...,
"errorCode": ..., "violations": ...}. HTTP 200 with successful=false
is an application error. Prices in cart responses are kuruş
(1/100 TRY) — the storefront formats (totalPrice/100). Response
shapes are UNVERIFIED without a live account, so all parsing here is
defensive: unknown shapes return an explicit note, never fabricated
data. Deliberately NOT implemented: coupons, notes, clear-cart
(POST /carts/reset), checkout-screen creation (bean shape unverified),
any /purchase/* payment endpoint.
"""
from __future__ import annotations

import json
import os
import time

from curl_cffi import requests as _r

from . import http as _http

SESSION_ENV = "MIGROS_SESSION"

CART_BFF = "https://www.migros.com.tr/rest/grocery-cart-bff"
ORDER_BFF = "https://www.migros.com.tr/rest/order-bff"

CART_URL = "https://www.migros.com.tr/sepetim"
CHECKOUT_URL = "https://www.migros.com.tr/odeme"

TIMEOUT = 30.0
MIN_INTERVAL = 0.8  # seconds between requests — be polite

_NO_SESSION_MSG = (
    "MIGROS_SESSION is not configured — account actions need your "
    "browser session cookie. See README 'Account actions' for setup."
)
_EXPIRED_MSG = (
    "session expired — copy fresh cookies from your browser "
    "(see README 'Account actions')"
)


class AccountError(RuntimeError):
    """Account-action failure. Never carries session material."""


class SessionNotConfigured(AccountError):
    pass


class SessionExpired(AccountError):
    pass


# ---------------------------------------------------------------- session

def _parse_cookie_header(raw: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies[name.strip()] = value.strip()
    return cookies


class Session:
    """In-memory holder for the user's browser session cookies.

    The raw env value is never stored or exposed; only the parsed
    name/value map, kept in process memory.
    """

    def __init__(self, raw: str):
        self.cookies = _parse_cookie_header(raw)

    def get(self, name: str) -> str | None:
        return self.cookies.get(name)

    def cookie_header(self) -> str:
        return "; ".join(f"{k}={v}" for k, v in self.cookies.items())


def get_session() -> Session:
    """Read the session from the environment at call time."""
    raw = os.environ.get(SESSION_ENV, "").strip()
    if not raw:
        raise SessionNotConfigured(_NO_SESSION_MSG)
    return Session(raw)


# ---------------------------------------------------------------- transport

_PROFILES = ("chrome120", "chrome131", "safari17_0")
_MAX_ATTEMPTS = 2  # one retry with the next profile
_RETRY_BACKOFF = 1.0  # seconds between attempts
_profile_idx = 0  # sticky: profile that last succeeded
_last_fetch = 0.0


def _throttle() -> None:
    global _last_fetch
    wait = MIN_INTERVAL - (time.monotonic() - _last_fetch)
    if wait > 0:
        time.sleep(wait)
    _last_fetch = time.monotonic()


def _raw_request(method: str, url: str, headers: dict, json_body=None,
                 timeout: float = TIMEOUT):
    """One HTTP call with Chrome TLS impersonation + profile rotation.

    Returns the curl_cffi response. Tests monkeypatch this function.
    Retries (once, next profile) on HTTP 403/429 — the server rejected
    the request, so retrying is safe even for mutations. Transport
    errors retry only for GET: a failed mutating call may already have
    been applied server-side.
    """
    global _profile_idx
    _throttle()
    last_exc: Exception | None = None
    for k in range(_MAX_ATTEMPTS):
        profile = _PROFILES[(_profile_idx + k) % len(_PROFILES)]
        try:
            resp = _r.request(
                method, url, impersonate=profile, headers=headers,
                json=json_body, timeout=timeout,
            )
        except Exception as e:
            last_exc = e
            if method == "GET" and k + 1 < _MAX_ATTEMPTS:
                time.sleep(_RETRY_BACKOFF)
                continue
            raise AccountError(
                f"network error calling migros API: {e}"
            ) from e
        if resp.status_code in (403, 429):
            if k + 1 < _MAX_ATTEMPTS:
                time.sleep(_RETRY_BACKOFF)
                continue
            return resp
        _profile_idx = (_profile_idx + k) % len(_PROFILES)
        return resp
    raise AccountError(
        f"network error calling migros API: {last_exc}"
    ) from last_exc


def _parse_json_body(resp):
    """Parsed JSON body, or None when the body is empty / not JSON."""
    try:
        text = resp.text
    except Exception:
        return None
    if not text or not text.strip():
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _server_message(resp) -> str:
    """Short server error detail (errorCode / message / first
    violation), if any. Only short fields are surfaced, truncated —
    never the full body."""
    data = _parse_json_body(resp)
    if not isinstance(data, dict):
        return ""
    parts: list[str] = []
    code = data.get("errorCode")
    if code:
        parts.append(f"errorCode {code}")
    msg = data.get("message") or data.get("errorDetail")
    if isinstance(msg, str) and msg:
        parts.append(msg)
    violations = data.get("violations")
    if isinstance(violations, list) and violations:
        first = violations[0]
        if isinstance(first, dict):
            detail = first.get("message") or first.get("detail")
            if isinstance(detail, str) and detail:
                parts.append(detail)
        elif isinstance(first, str):
            parts.append(first)
    return "; ".join(str(p) for p in parts)[:200]


def _handle_response(resp, endpoint: str):
    """Map an HTTP response to parsed JSON or a safe AccountError.

    Note the cart BFF's gate shape: a request with NO session gets a
    bare HTTP 400, so a 400 here (session configured) means the
    session was not accepted or the request was invalid.
    """
    status = resp.status_code
    if 200 <= status < 300:
        data = _parse_json_body(resp)
        if data is None:
            return {}
        if isinstance(data, dict) and data.get("successful") is False:
            msg = _server_message(resp)
            raise AccountError(
                f"{endpoint} was rejected by Migros"
                + (f": {msg}" if msg else "")
            )
        return data
    if status == 401:
        raise SessionExpired(_EXPIRED_MSG)
    if status == 400:
        msg = _server_message(resp)
        raise AccountError(
            f"{endpoint} was rejected (HTTP 400) — the session may be "
            "expired or the request invalid; copy fresh cookies and retry"
            + (f" ({msg})" if msg else "")
        )
    if status == 403:
        raise AccountError(
            f"{endpoint} refused the request (HTTP 403) — the session may "
            "lack access or the request was blocked"
        )
    if status == 429:
        raise AccountError(
            f"{endpoint} rate-limited the request (HTTP 429) — try again later"
        )
    msg = _server_message(resp)
    raise AccountError(
        f"{endpoint} returned unexpected HTTP {status}"
        + (f": {msg}" if msg else "")
    )


# ---------------------------------------------------------------- auth headers

def _cart_headers(session: Session, with_body: bool = False) -> dict:
    """Headers the storefront sends on every BFF request (from its
    interceptors): PWA markers + Accept-Language: tr, the session
    Cookie, and — when the browser has an XSRF-TOKEN cookie — the
    X-XSRF-TOKEN header Angular's HttpClientXsrfModule derives from
    it."""
    headers = {
        "Accept": "application/json",
        "Accept-Language": "tr",
        "X-Requested-With": "XMLHttpRequest",
        "X-FORWARDED-REST": "true",
        "X-PWA": "true",
        "X-Device-PWA": "true",
        "Cookie": session.cookie_header(),
    }
    if with_body:
        headers["Content-Type"] = "application/json"
    xsrf = session.get("XSRF-TOKEN")
    if xsrf:
        headers["X-XSRF-TOKEN"] = xsrf
    return headers


def _authed(method, url, session, json_body=None, endpoint="migros API"):
    """One authed API call. Returns parsed JSON (dict) or {}."""
    headers = _cart_headers(session, with_body=json_body is not None)
    resp = _raw_request(method, url, headers, json_body)
    return _handle_response(resp, endpoint)


def _unwrap_envelope(data, endpoint: str):
    """Return the `data` field of a BFF envelope (or the payload
    itself when it carries no envelope)."""
    if isinstance(data, dict) and "data" in data:
        inner = data.get("data")
        return inner if inner is not None else {}
    return data if data is not None else {}


# ---------------------------------------------------------------- validation

def _validate_quantity(quantity) -> int:
    if (
        not isinstance(quantity, int)
        or isinstance(quantity, bool)
        or not 1 <= quantity <= 99
    ):
        raise ValueError("quantity must be an integer between 1 and 99")
    return quantity


def _validate_product_id(product_id) -> int:
    if (
        not isinstance(product_id, int)
        or isinstance(product_id, bool)
        or product_id <= 0
    ):
        raise ValueError(
            "product_id must be a positive integer (from migros_search_products)"
        )
    return product_id


def _validate_store_id(store_id) -> int:
    if (
        not isinstance(store_id, int)
        or isinstance(store_id, bool)
        or store_id <= 0
    ):
        raise ValueError("store_id must be a positive integer")
    return store_id


# ---------------------------------------------------------------- defensive parsers

def _tl(kurus) -> float | None:
    """Kuruş (1/100 TRY) -> TRY, or None when not a number."""
    if kurus is None:
        return None
    try:
        return round(float(kurus) / 100.0, 2)
    except (TypeError, ValueError):
        return None


def parse_cart(data) -> dict:
    """Defensive parse of the cart BFF's cartInfo (shape unverified
    without a live account — field names come from the storefront JS:
    itemInfos[].{item.{id, productId, storeId, unit, amount},
    product.{name}, totalPrice, totalRegularPrice, revenue},
    totalProductPrice / totalPrice / shownDeliveryFee in kuruş).
    Never fabricates items: an unrecognized shape returns an explicit
    note with the top-level keys."""
    cart = _unwrap_envelope(data, "view cart")
    if not isinstance(cart, dict):
        return {
            "items": [],
            "note": "unexpected response shape",
            "response_keys": [],
        }
    raw_items = cart.get("itemInfos")
    if not isinstance(raw_items, list):
        return {
            "items": [],
            "note": "unexpected response shape",
            "response_keys": sorted(cart.keys()),
        }
    items: list[dict] = []
    for info in raw_items:
        if not isinstance(info, dict):
            continue
        item = info.get("item") if isinstance(info.get("item"), dict) else {}
        product = (
            info.get("product") if isinstance(info.get("product"), dict) else {}
        )
        row: dict = {}
        if item.get("id") is not None:
            row["cart_item_id"] = str(item["id"])
        pid = item.get("productId")
        if pid is None:
            pid = product.get("id")
        if pid is not None:
            try:
                row["product_id"] = int(pid)
            except (TypeError, ValueError):
                pass
        name = product.get("name")
        if name:
            row["name"] = str(name)
        qty = item.get("amount")
        if qty is not None:
            try:
                row["quantity"] = int(qty)
            except (TypeError, ValueError):
                pass
        if item.get("unit"):
            row["unit"] = str(item["unit"])
        total = _tl(info.get("totalPrice"))
        if total is not None:
            row["total_price_try"] = total
        unit_price = _tl(product.get("shownPrice"))
        if unit_price is not None:
            row["unit_price_try"] = unit_price
        items.append(row)
    out: dict = {
        "items": items,
        "total_item_count": sum(i.get("quantity", 0) for i in items),
    }
    total_product = _tl(cart.get("totalProductPrice"))
    if total_product is not None:
        out["total_product_price_try"] = total_product
    total = _tl(cart.get("totalPrice"))
    if total is not None:
        out["total_price_try"] = total
    delivery = _tl(cart.get("shownDeliveryFee"))
    if delivery is not None:
        out["delivery_fee_try"] = delivery
    return out


# ---------------------------------------------------------------- product resolution

def resolve_product(product_id: int) -> dict:
    """Public product detail -> the fields a cart mutation needs.

    Uses the no-auth product-bff API (same as migros_get_product).
    Raises AccountError when the product is not saleable or lacks the
    store/unit the cart API requires.
    """
    payload = _http.get_product(product_id)
    if not payload.get("successful", True):
        raise AccountError(
            f"Migros product lookup failed: "
            f"{payload.get('errorDetail') or payload}"
        )
    data = payload.get("data") or {}
    if not data.get("saleable", True):
        raise AccountError(
            f"product {product_id} is not saleable right now"
        )
    store_id = data.get("storeId")
    unit = data.get("unit")
    if not store_id or not unit:
        raise AccountError(
            f"product {product_id} has no store/unit info — cannot add "
            "it to the cart"
        )
    return {
        "product_id": int(data.get("id") or product_id),
        "name": (data.get("name") or "").strip(),
        "store_id": int(store_id),
        "unit": str(unit),
        "max_amount": data.get("maxAmount"),
    }


# ---------------------------------------------------------------- operations

def view_cart() -> dict:
    session = get_session()
    data = _authed(
        "GET", f"{CART_BFF}/carts?isCartPage=true", session,
        endpoint="view cart",
    )
    result = parse_cart(data)
    result["cart_url"] = CART_URL
    return result


def _replace_items(session: Session, items: list[dict]) -> dict:
    """PUT /carts/items — the storefront's single cart mutation.

    `items` are {productId, storeId, unit, amount} rows (amount 0
    removes). The apply* flags are false exactly as the storefront
    sends them. Returns the parsed updated cart."""
    body = {
        "items": items,
        "applyCrmDiscounts": False,
        "applySpecialDiscounts": False,
        "applyDeepDiscounts": False,
        "includeDeliveryFee": False,
        "applyFoodProductDiscounts": False,
    }
    data = _authed(
        "PUT", f"{CART_BFF}/carts/items", session, json_body=body,
        endpoint="update cart",
    )
    return parse_cart(data)


def _mutation_item(product_id: int, quantity: int,
                   store_id: int | None, unit: str | None) -> dict:
    """Build one replace row, resolving store/unit from the public
    product API when not supplied. Also enforces the product's
    maxAmount when known."""
    _validate_product_id(product_id)
    if store_id is not None:
        _validate_store_id(store_id)
    if unit is not None and not str(unit).strip():
        raise ValueError("unit must not be empty")
    if store_id is None or unit is None:
        info = resolve_product(product_id)
        store_id = store_id if store_id is not None else info["store_id"]
        unit = unit if unit is not None else info["unit"]
        max_amount = info.get("max_amount")
        if (
            isinstance(max_amount, int)
            and quantity > max_amount
        ):
            raise ValueError(
                f"quantity {quantity} exceeds this product's limit of "
                f"{max_amount}"
            )
    return {
        "productId": product_id,
        "storeId": store_id,
        "unit": unit,
        "amount": quantity,
    }


def add_to_cart(product_id: int, quantity: int = 1,
                store_id: int | None = None,
                unit: str | None = None) -> dict:
    """Set a product's cart quantity (replace semantics: the item's
    amount BECOMES `quantity`, it is not added on top — that is how
    the storefront's replace call works)."""
    _validate_quantity(quantity)
    session = get_session()
    row = _mutation_item(product_id, quantity, store_id, unit)
    cart = _replace_items(session, [row])
    out: dict = {
        "added": True,
        "product_id": product_id,
        "quantity": quantity,
        "cart_url": CART_URL,
    }
    if "total_item_count" in cart:
        out["total_item_count"] = cart["total_item_count"]
    if "total_price_try" in cart:
        out["total_price_try"] = cart["total_price_try"]
    return out


def remove_from_cart(product_id: int,
                     store_id: int | None = None,
                     unit: str | None = None) -> dict:
    """Remove a product from the cart (replace with amount 0 — the
    storefront's own deleteItem flow)."""
    session = get_session()
    row = _mutation_item(product_id, 0, store_id, unit)
    cart = _replace_items(session, [row])
    out: dict = {
        "removed": True,
        "product_id": product_id,
        "cart_url": CART_URL,
    }
    if "total_item_count" in cart:
        out["total_item_count"] = cart["total_item_count"]
    return out


def update_cart_quantity(product_id: int, quantity: int,
                         store_id: int | None = None,
                         unit: str | None = None) -> dict:
    """Set a cart item's quantity (replace semantics)."""
    _validate_quantity(quantity)
    session = get_session()
    row = _mutation_item(product_id, quantity, store_id, unit)
    cart = _replace_items(session, [row])
    out: dict = {
        "updated": True,
        "product_id": product_id,
        "quantity": quantity,
        "cart_url": CART_URL,
    }
    if "total_item_count" in cart:
        out["total_item_count"] = cart["total_item_count"]
    if "total_price_try" in cart:
        out["total_price_try"] = cart["total_price_try"]
    return out


def start_checkout() -> dict:
    """Start checkout: verify the cart is non-empty, then return the
    checkout (ödeme) link. This does NOT place an order and never
    touches payment — address, delivery slot and payment are
    completed by the user in the browser."""
    cart = view_cart()
    if not cart.get("items"):
        raise AccountError(
            "your cart is empty — add products before checkout"
        )
    return {
        "checkout_url": CHECKOUT_URL,
        "cart_url": CART_URL,
        "total_item_count": cart.get("total_item_count", 0),
        **(
            {"total_price_try": cart["total_price_try"]}
            if "total_price_try" in cart else {}
        ),
        "note": (
            "Complete address, delivery slot and payment in the "
            "browser — this tool never places an order or pays."
        ),
    }
