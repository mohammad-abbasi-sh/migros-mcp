# migros-mcp 🇹🇷

mcp-name: io.github.mohammad-abbasi-sh/migros-mcp

Unofficial MCP server for **Migros Sanal Market** (migros.com.tr), Türkiye's largest supermarket chain — live product search, prices, Money-discount promotions, categories and price stats. Read-only tools need no login. Optional **account actions** (cart + start-checkout) use your own browser session, stored only in your MCP config — see [Account actions](#account-actions).

> Part of the "Turkey MCP factory". Not affiliated with Migros. Note: this is the **Turkish** Migros (migros.com.tr) — not the Swiss Migros, which has its own unrelated `migros-mcp` on npm. Price comparison across chains is covered by `yibudak/marketfiyati_mcp` (marketfiyati.org.tr); this server covers Migros's own catalogue, promos and categories.

## For AI agents

Add to your MCP client config (stdio):

```json
{
  "mcpServers": {
    "migros": {
      "command": "uvx",
      "args": ["migros-mcp==0.2.0"]
    }
  }
}
```

Or run locally: `python -m migros_mcp.server` (needs `mcp<2`, `curl-cffi`).

For account actions (cart + start-checkout), add your browser session cookie
to the config — see [Account actions](#account-actions):

```json
{
  "mcpServers": {
    "migros": {
      "command": "uvx",
      "args": ["migros-mcp==0.2.0"],
      "env": {
        "MIGROS_SESSION": "YOUR_SESSION_COOKIE_HERE"
      }
    }
  }
}
```

## Tools

| Tool | Description |
|------|-------------|
| `migros_search_products` | Search products — `query` (Turkish, e.g. "süt"), `page`, `sort`: relevance / best_seller / discount / discount_amount / price_asc / price_desc |
| `migros_get_product` | Full detail for one product — `product_id` (numeric, from search) |
| `migros_list_categories` | Top-level store categories (11) |
| `migros_list_promotions` | Money-discounted products for a keyword, best discount first |
| `migros_price_stats` | Price stats (min/median/max/mean, cheapest & priciest) for a keyword |
| `migros_view_cart` | Your cart: items (cart item id, product id, name, quantity, unit, total price in TRY), totals, cart URL — needs `MIGROS_SESSION` |
| `migros_add_to_cart` | Add a product to your cart (`product_id`, `quantity` 1..99, replace semantics) — needs session + `confirm=true` |
| `migros_remove_from_cart` | Remove a product from your cart (`product_id`) — needs session + `confirm=true` |
| `migros_update_cart_quantity` | Change a cart item's quantity (`product_id`, `quantity` 1..99) — needs session + `confirm=true` |
| `migros_create_order` | Start checkout: verifies the cart and returns the checkout (ödeme) link — places NO order, never pays — needs `MIGROS_SESSION` |

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
- Cart quantities use **replace semantics**: setting a product's quantity makes it that amount — it is not added on top of what is already in the cart. Each product also has a max amount (e.g. 8); the server rejects quantities above it.
- Store lookup and delivery slots need an authenticated session, so this server does not offer them.

## Account actions

Cart tools work with **your own browser session** — no password, no API
key, no account is created anywhere. The session lives only in your MCP
client config on your own machine and is sent only to migros.com.tr. The
server never logs, prints, or persists it, and it never appears in any
tool output. Every cart mutation (add / remove / change quantity) also
needs `confirm=true`, or it does nothing.

### Setup (one time)

1. Log in to [migros.com.tr](https://www.migros.com.tr) in your browser
   (Chrome / Edge / Firefox).
2. Open DevTools (F12) → **Network** tab → reload the page.
3. Click any request to `migros.com.tr` → **Headers** → find the
   **Cookie** request header → copy its full value.
   (Alternative: DevTools → **Application** → **Cookies** →
   `https://www.migros.com.tr` — but the Network-tab Cookie header is
   the complete value; copy that one.)
4. Paste it as `MIGROS_SESSION` in your MCP client config (see the
   example above) and restart the MCP server.
5. Try `migros_view_cart` — it should show your real cart.

### Notes

- The session expires: when a tool reports "session expired", repeat
  steps 2–4 to copy fresh cookies. Logging out of migros.com.tr
  revokes the session immediately.
- **Never share the cookie value** — anyone holding it has full access
  to your Migros account (cart, orders). Do not paste it into chats,
  issues, or screenshots.
- Account actions are deliberately narrow: cart (view / add / remove /
  change quantity) and start-checkout (returns the checkout link
  only). There is no order placement, payment, coupon, or bulk action.
  `migros_create_order` never places an order — you complete address,
  delivery slot and payment in the browser.
- `store_id` / `unit` are resolved from the public product detail
  automatically; pass them only to skip that lookup.
- The cart endpoints were reverse-engineered from Migros's public
  storefront code and verified live as far as possible without an
  account (the cart API answers cookie-less requests with a bare
  HTTP 400; the order API answers HTTP 401). Response shapes are
  parsed defensively — an unexpected shape returns an explicit note,
  never invented data.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install "mcp<2" curl-cffi pytest
.venv/bin/python -m pytest tests/ -q
```

- `tests/test_products.py` — offline, parses real captured API fixtures
- `tests/test_account.py` — offline, mocked cart API + recorded gate shapes
- `tests/test_live.py` — 4 cautious live requests against migros.com.tr
- `tests/test_live_account.py` — live gate-shape probes (no session) + live product resolver

## License

[PolyForm Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/) — free for personal and non-commercial use; commercial use needs a separate license (see LICENSE).

---

Built by [Mohammad Abbasi](https://github.com/mohammad-abbasi-sh) — [Almanibama](https://almanibama.ir) · [mabbasi.ir](https://mabbasi.ir)
