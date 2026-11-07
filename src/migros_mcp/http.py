"""HTTP layer for migros_mcp.

Migros Sanal Market (migros.com.tr) exposes a public, no-auth JSON REST
API under /rest/product-bff — the same endpoints its Angular storefront
calls (base URLs are published in the storefront's own env.js). Verified
live 2026-11-07: product search, product detail and categories all return
200 JSON with a plain browser UA (curl-cffi chrome120). No login, no API
key, no session cookies. Requests are kept gentle (one at a time,
~0.8s apart) and read-only.

Known limits (verified 2026-11-07, do not retry): the delivery-bff
endpoints (store lookup, delivery slots) return 403 Forbidden without an
authenticated session, so this server has no store/slot tools; the
category-products endpoint hangs — promotions come from the search API
instead (sort by discount percentage + Money-discount filter).
"""
from __future__ import annotations

import time
from urllib.parse import quote

from curl_cffi import requests as _r

BASE = "https://www.migros.com.tr/rest/product-bff"
TIMEOUT = 30.0
MIN_INTERVAL = 0.8  # seconds between requests — be polite

_HEADERS = {
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Accept": "application/json",
    "X-Requested-With": "XMLHttpRequest",
}

_last_fetch = 0.0


class MigrosError(RuntimeError):
    pass


def _get(url: str) -> dict:
    global _last_fetch
    wait = MIN_INTERVAL - (time.monotonic() - _last_fetch)
    if wait > 0:
        time.sleep(wait)
    try:
        resp = _r.get(url, impersonate="chrome120", headers=_HEADERS, timeout=TIMEOUT)
    except Exception as e:
        raise MigrosError(f"network error fetching {url}: {e}") from e
    finally:
        _last_fetch = time.monotonic()
    if resp.status_code == 404:
        raise MigrosError(f"Migros returned HTTP 404 for {url}")
    if resp.status_code != 200:
        raise MigrosError(f"Migros returned HTTP {resp.status_code} for {url}")
    try:
        return resp.json()
    except ValueError as e:
        raise MigrosError(f"Migros returned non-JSON for {url}") from e


def search_products(query: str, page: int = 0, sort: str = "akilli-siralama") -> dict:
    """Search the Migros catalogue. sort: requestParam slug, e.g.
    akilli-siralama, cok-satanlar, indirim-yuzdesine-gore,
    indirim-miktarina-gore, once-en-dusuk-fiyat, once-en-yuksek-fiyat.
    Note: the first result is often a sponsored/pinned product; the rest
    follow the requested sort."""
    q = quote(query.strip())
    return _get(f"{BASE}/products/search?q={q}&page={page}&sort={sort}")


def search_discounted(query: str, page: int = 0) -> dict:
    """Search with the Money-discount aggregation filter applied."""
    q = quote(query.strip())
    return _get(
        f"{BASE}/products/search?q={q}&page={page}"
        f"&sort=indirim-yuzdesine-gore&indirim=MCC"
    )


def get_product(product_id: int) -> dict:
    """One product's full detail by numeric id."""
    return _get(f"{BASE}/products/{int(product_id)}")


def list_categories() -> dict:
    """Top-level store categories."""
    return _get(f"{BASE}/categories")
