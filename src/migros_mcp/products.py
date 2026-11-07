"""Domain logic: parse Migros Sanal Market product-bff JSON into compact dicts (stdlib only).

Prices in the API are integer kuruş (1/100 TRY): 18900 -> 189.00 TRY.
``discount_rate`` is the Money-loyalty discount percentage (the "Money
İndirimli" aggregation); the shelf price (sale_price) already reflects
the price a guest pays — the discount is a Money-card benefit, not a
strikethrough. We surface it as ``money_discount_pct`` so nobody mistakes
it for a price cut.
"""
from __future__ import annotations

import html
import re
import statistics

PRODUCT_URL = "https://www.migros.com.tr/urun/{}"

SORTS = {
    "relevance": "akilli-siralama",
    "best_seller": "cok-satanlar",
    "discount": "indirim-yuzdesine-gore",
    "discount_amount": "indirim-miktarina-gore",
    "price_asc": "once-en-dusuk-fiyat",
    "price_desc": "once-en-yuksek-fiyat",
}


def _tl(kurus: int | float | None) -> float | None:
    if kurus is None:
        return None
    try:
        return round(float(kurus) / 100.0, 2)
    except (TypeError, ValueError):
        return None


def _strip_html(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _image(p: dict) -> str | None:
    for img in p.get("images") or []:
        urls = img.get("urls") or {}
        for key in ("PRODUCT_DETAIL", "PRODUCT_LIST", "PRODUCT_HD"):
            if urls.get(key):
                return urls[key]
    return None


def parse_product(p: dict) -> dict:
    """One storeProductInfo / product-detail record -> compact dict."""
    price = _tl(p.get("salePrice"))
    regular = _tl(p.get("regularPrice"))
    asc = p.get("categoryAscendants") or []
    return {
        "id": p.get("id"),
        "sku": p.get("sku"),
        "name": (p.get("name") or "").strip(),
        "brand": ((p.get("brand") or {}).get("name") or "").strip(),
        "category": ((p.get("category") or {}).get("name") or "").strip(),
        "category_path": [a.get("name") for a in asc if a.get("name")],
        "price_tl": price,
        "regular_price_tl": regular,
        "money_discount_pct": p.get("discountRate") or 0,
        "unit": p.get("unit"),
        "saleable": bool(p.get("saleable", True)),
        "image_url": _image(p),
        "url": PRODUCT_URL.format(p["prettyName"]) if p.get("prettyName") else None,
    }


def parse_search(payload: dict, query: str, page: int = 0) -> dict:
    """Parse a /products/search response."""
    if not payload.get("successful", True):
        raise ValueError(f"Migros search failed: {payload.get('errorDetail') or payload}")
    data = payload.get("data") or {}
    products = [parse_product(p) for p in data.get("storeProductInfos") or []]
    return {
        "query": query,
        "page": page,
        "hit_count": data.get("hitCount", len(products)),
        "page_count": data.get("pageCount", 0),
        "count": len(products),
        "products": products,
    }


def parse_product_detail(payload: dict) -> dict:
    """Parse a /products/{id} response."""
    if not payload.get("successful", True):
        raise ValueError(f"Migros product lookup failed: {payload.get('errorDetail') or payload}")
    data = payload.get("data") or {}
    d = parse_product(data)
    d["description"] = _strip_html(data.get("description"))[:2000]
    d["short_description"] = _strip_html(data.get("shortDescription"))[:500]
    return d


def parse_categories(payload: dict) -> list[dict]:
    """Parse a /categories response (top-level categories)."""
    if not payload.get("successful", True):
        raise ValueError(f"Migros categories failed: {payload.get('errorDetail') or payload}")
    out = []
    for item in payload.get("data") or []:
        c = item.get("data") or {}
        img = None
        for im in c.get("images") or []:
            urls = im.get("urls") or {}
            img = urls.get("x1") or urls.get("x3")
            if img:
                break
        out.append(
            {
                "id": c.get("id"),
                "name": c.get("name"),
                "pretty_name": c.get("prettyName"),
                "image_url": img,
            }
        )
    return out


def price_stats(products: list[dict]) -> dict:
    """Min/median/max/mean over a list of parsed products with prices."""
    prices = [p["price_tl"] for p in products if p.get("price_tl") is not None]
    if not prices:
        return {"count": 0, "error": "no priced products in this result set"}
    cheapest = min(products, key=lambda p: p["price_tl"] if p.get("price_tl") is not None else float("inf"))
    priciest = max(products, key=lambda p: p["price_tl"] if p.get("price_tl") is not None else float("-inf"))
    return {
        "count": len(prices),
        "min_tl": min(prices),
        "median_tl": round(statistics.median(prices), 2),
        "max_tl": max(prices),
        "mean_tl": round(statistics.mean(prices), 2),
        "cheapest": {"name": cheapest["name"], "price_tl": cheapest["price_tl"]},
        "priciest": {"name": priciest["name"], "price_tl": priciest["price_tl"]},
    }
