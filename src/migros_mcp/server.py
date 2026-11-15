"""MCP server: unofficial access to Migros Sanal Market (migros.com.tr).

Read-only tools (search, details, categories, promos, price stats)
need no login. Account tools (cart, start-checkout) use the user's own
browser session from the MIGROS_SESSION env var — local only, never
logged or persisted — and every cart mutation needs confirm=true.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
import sys

from mcp.server.fastmcp import FastMCP

from . import account as _A
from . import http as _http
from . import products as _p

mcp = FastMCP("migros-mcp")

INSTRUCTIONS = """\
Unofficial MCP server for Migros Sanal Market (migros.com.tr), \
Türkiye's largest supermarket chain — live catalogue search, product \
detail, categories, Money-discount promotions and price stats from \
Migros's public product-bff JSON API. Read-only tools need no login \
and no API key. Account tools (cart, start-checkout) use the user's \
own browser session from the MIGROS_SESSION env var — local only, \
never logged or persisted — and every cart mutation needs \
confirm=true. Cart quantities use replace semantics: setting a \
product's quantity makes it that amount, it is not added on top. \
migros_create_order only returns the checkout link — it never places \
an order or touches payment. Prices are in Turkish Lira (TRY); the \
API reports kuruş (1/100 TRY). ``money_discount_pct`` is the \
Money-loyalty discount percentage, not a strikethrough — the shelf \
price is what a guest pays. Store lookup and delivery slots need an \
authenticated session, so this server does not offer them. Built by \
Mohammad Abbasi (github.com/mohammad-abbasi-sh/migros-mcp).\
Built by Mohammad Abbasi (mohammad-abbasi-sh) — https://almanibama.ir · https://mabbasi.ir
"""


_SOURCE = "migros.com.tr"
_DISCLAIMER = "Unofficial read-only data from migros.com.tr; verify on the site before acting on it."


def _envelope() -> dict:
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": _SOURCE,
        "disclaimer": _DISCLAIMER,
    }


def _ok(payload: dict) -> str:
    return json.dumps({**_envelope(), **payload}, ensure_ascii=False)


def _err(e: Exception) -> str:
    return _ok({"error": str(e)})


@mcp.tool()
def migros_search_products(query: str, page: int = 0, sort: str = "relevance") -> str:
    """Search Migros products by keyword (Turkish, e.g. "süt", "ekmek"). \
sort: relevance | best_seller | discount | discount_amount | price_asc | price_desc. \
Returns up to 36 products per page with prices in TRY."""
    key = sort.strip().lower()
    if key not in _p.SORTS:
        return _ok({"error": f"unknown sort {sort!r}", "known_sorts": sorted(_p.SORTS)})
    try:
        return _ok(_p.parse_search(_http.search_products(query, page, _p.SORTS[key]), query, page))
    except (_http.MigrosError, ValueError) as e:
        return _err(e)


@mcp.tool()
def migros_get_product(product_id: int) -> str:
    """Full detail for one Migros product by numeric id (from search results)."""
    try:
        return _ok(_p.parse_product_detail(_http.get_product(product_id)))
    except (_http.MigrosError, ValueError) as e:
        return _err(e)


@mcp.tool()
def migros_list_categories() -> str:
    """Top-level Migros store categories (id, name, link slug)."""
    try:
        cats = _p.parse_categories(_http.list_categories())
        return _ok({"count": len(cats), "categories": cats})
    except (_http.MigrosError, ValueError) as e:
        return _err(e)


@mcp.tool()
def migros_list_promotions(query: str, limit: int = 10) -> str:
    """Discounted (Money-indirimli) products for a keyword, best discount first. \
query: e.g. "süt", "çay", "deterjan". money_discount_pct is the Money-loyalty \
discount, not a price cut — see the server instructions."""
    try:
        res = _p.parse_search(_http.search_discounted(query), query)
    except (_http.MigrosError, ValueError) as e:
        return _err(e)
    discounted = [p for p in res["products"] if (p.get("money_discount_pct") or 0) > 0]
    discounted.sort(key=lambda p: p["money_discount_pct"], reverse=True)
    return _ok({
            "query": query,
            "hit_count": res["hit_count"],
            "count": min(len(discounted), max(limit, 0)),
            "products": discounted[: max(limit, 0)],
        })


@mcp.tool()
def migros_price_stats(query: str) -> str:
    """Price statistics (min/median/max/mean, cheapest & priciest) for a \
keyword's first page of Migros search results (up to 36 products)."""
    try:
        res = _p.parse_search(_http.search_products(query, 0, "akilli-siralama"), query)
    except (_http.MigrosError, ValueError) as e:
        return _err(e)
    stats = _p.price_stats(res["products"])
    return _ok({"query": query, "hit_count": res["hit_count"], **stats})


@mcp.tool()
def migros_health() -> str:
    """Check whether migros.com.tr is reachable right now.

    Returns status ok (HTTP 200), blocked (HTTP 403/429 — bot wall or
    rate limit) or error, plus the HTTP status and the probed URL.
    One polite request; it does not fetch any listings."""
    return _ok(_http.health_check())


# ---------------------------------------------------------------- account actions
# Local-session tools: they need MIGROS_SESSION (the user's browser
# cookie, set in the MCP client config — never leaves their machine).
# Every cart mutation needs confirm=true or it does nothing.

def _confirmation_required(action: str) -> str:
    return _ok({
        "error": "confirmation_required",
        "message": f"Set confirm=true to {action}.",
    })


@mcp.tool()
def migros_view_cart() -> str:
    """View your Migros cart: items (cart item id, product id, name,
    quantity, unit, total price in TRY), total item count, total
    product price and delivery fee, plus a cart URL to review in the
    browser. Requires MIGROS_SESSION (see README 'Account actions')."""
    try:
        result = _A.view_cart()
    except _A.AccountError as e:
        return _err(e)
    return _ok(result)


@mcp.tool()
def migros_add_to_cart(product_id: int, quantity: int = 1,
                       store_id: int | None = None,
                       unit: str | None = None,
                       confirm: bool = False) -> str:
    """Add a product to your Migros cart. product_id: numeric id from
    migros_search_products / migros_get_product. quantity 1..99 —
    REPLACE semantics: the item's amount becomes this value, it is
    not added on top of what is already in the cart. store_id / unit
    are resolved from the public product detail automatically; pass
    them only to skip that lookup (e.g. from migros_view_cart).
    Requires MIGROS_SESSION and confirm=true."""
    if not confirm:
        return _confirmation_required("add this product to your Migros cart")
    try:
        result = _A.add_to_cart(
            product_id, quantity, store_id=store_id, unit=unit
        )
    except (ValueError, _A.AccountError, _http.MigrosError) as e:
        return _err(e)
    return _ok(result)


@mcp.tool()
def migros_remove_from_cart(product_id: int,
                            store_id: int | None = None,
                            unit: str | None = None,
                            confirm: bool = False) -> str:
    """Remove a product from your Migros cart. product_id: numeric id
    (see migros_view_cart). store_id / unit are resolved from the
    public product detail automatically; pass them only to skip that
    lookup. Requires MIGROS_SESSION and confirm=true."""
    if not confirm:
        return _confirmation_required("remove this product from your Migros cart")
    try:
        result = _A.remove_from_cart(
            product_id, store_id=store_id, unit=unit
        )
    except (ValueError, _A.AccountError, _http.MigrosError) as e:
        return _err(e)
    return _ok(result)


@mcp.tool()
def migros_update_cart_quantity(product_id: int, quantity: int,
                                store_id: int | None = None,
                                unit: str | None = None,
                                confirm: bool = False) -> str:
    """Change the quantity of a product in your Migros cart.
    product_id: numeric id (see migros_view_cart). quantity 1..99 —
    REPLACE semantics: the item's amount becomes this value (use
    migros_remove_from_cart to remove an item — quantity 0 is not
    supported here). store_id / unit are resolved from the public
    product detail automatically. Requires MIGROS_SESSION and
    confirm=true."""
    if not confirm:
        return _confirmation_required("change this cart item's quantity")
    try:
        result = _A.update_cart_quantity(
            product_id, quantity, store_id=store_id, unit=unit
        )
    except (ValueError, _A.AccountError, _http.MigrosError) as e:
        return _err(e)
    return _ok(result)


@mcp.tool()
def migros_create_order() -> str:
    """Start checkout for your Migros cart: verifies the cart is
    non-empty and returns the checkout (ödeme) link plus a cart
    summary. This does NOT place an order and never touches payment —
    address, delivery slot and payment are completed by you in the
    browser. Requires MIGROS_SESSION (see README 'Account actions')."""
    try:
        result = _A.start_checkout()
    except _A.AccountError as e:
        return _err(e)
    return _ok(result)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    sys.exit(main())
