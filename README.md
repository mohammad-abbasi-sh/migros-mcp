# migros-mcp 🇹🇷

mcp-name: io.github.mohammad-abbasi-sh/migros-mcp

Unofficial **read-only** MCP server for **Migros Sanal Market** (migros.com.tr), Türkiye's largest supermarket chain — live product search, prices, Money-discount promotions, categories and price stats.

> Part of the "Turkey MCP factory". Not affiliated with Migros. Note: this is the **Turkish** Migros (migros.com.tr) — not the Swiss Migros, which has its own unrelated `migros-mcp` on npm. Price comparison across chains is covered by `yibudak/marketfiyati_mcp` (marketfiyati.org.tr); this server covers Migros's own catalogue, promos and categories.

## For AI agents

Add to your MCP client config (stdio):

```json
{
  "mcpServers": {
    "migros": {
      "command": "uvx",
      "args": ["migros-mcp==0.1.0"]
    }
  }
}
```

Or run locally: `python -m migros_mcp.server` (needs `mcp<2`, `curl-cffi`).

## Tools

| Tool | Description |
|------|-------------|
| `migros_search_products` | Search products — `query` (Turkish, e.g. "süt"), `page`, `sort`: relevance / best_seller / discount / discount_amount / price_asc / price_desc |
| `migros_get_product` | Full detail for one product — `product_id` (numeric, from search) |
| `migros_list_categories` | Top-level store categories (11) |
| `migros_list_promotions` | Money-discounted products for a keyword, best discount first |
| `migros_price_stats` | Price stats (min/median/max/mean, cheapest & priciest) for a keyword |

Example output (`migros_search_products` / "süt", price_asc):

```json
{"query": "süt", "hit_count": 371, "page_count": 13, "count": 36,
 "products": [{"id": 20000011010208, "name": "Sütaş Latte 1 L",
 "brand": "Sütaş", "category": "Uzun Ömürlü Süt",
 "price_tl": 189.0, "money_discount_pct": 0, ...}]}
```

Notes:
- Prices are Turkish Lira (TRY); the API reports kuruş (1/100 TRY).
- `money_discount_pct` is the **Money-loyalty discount** percentage, not a strikethrough — the shelf price is what a guest pays.
- The first search result is often a sponsored/pinned product; the rest follow the requested sort.
- Data: Migros's public `product-bff` JSON API (`migros.com.tr/rest/product-bff`) — no key, no login, read-only.
- Store lookup and delivery slots need an authenticated session, so this server does not offer them.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install "mcp<2" curl-cffi pytest
.venv/bin/python -m pytest tests/ -q
```

- `tests/test_products.py` — offline, parses real captured API fixtures
- `tests/test_live.py` — 4 cautious live requests against migros.com.tr

## License

MIT

---

Built by [Mohammad Abbasi](https://github.com/mohammad-abbasi-sh) — [Almanibama](https://almanibama.ir) · [mabbasi.ir](https://mabbasi.ir)
