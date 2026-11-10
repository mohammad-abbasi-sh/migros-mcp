# migros-mcp 🇹🇷

**Migros Sanal Market** (migros.com.tr) için gayriresmî, **salt-okunur** MCP sunucusu — canlı ürün arama, fiyatlar, Money indirimleri, kategoriler ve fiyat istatistikleri.

> "Türkiye MCP fabrikası" parçasıdır. Migros ile bağlantısı yoktur. Bu, **Türkiye** Migros'udur (migros.com.tr) — İsviçre Migros'unun npm'deki ilgisiz `migros-mcp` paketiyle karıştırılmamalıdır.

## Yapay zekâ ajanları için

MCP istemcinize ekleyin (stdio):

```json
{
  "mcpServers": {
    "migros": {
      "command": "uvx",
      "args": ["migros-mcp==0.1.1"]
    }
  }
}
```

## Araçlar

| Araç | Açıklama |
|------|----------|
| `migros_search_products` | Ürün arama — `query` ("süt", "ekmek"…), `page`, `sort`: relevance / best_seller / discount / discount_amount / price_asc / price_desc |
| `migros_get_product` | Tek ürünün detayı — `product_id` (arama sonuçlarından) |
| `migros_list_categories` | Üst düzey mağaza kategorileri (11) |
| `migros_list_promotions` | Bir anahtar kelime için Money indirimli ürünler, en yüksek indirim önce |
| `migros_price_stats` | Bir anahtar kelime için fiyat istatistikleri (min/medyan/maks/ortalama, en ucuz ve en pahalı) |

Notlar:
- Fiyatlar Türk Lirası (TRY); API kuruş (1/100 TRY) döndürür.
- `money_discount_pct`, Money sadakat indirim yüzdesidir — etiket indirimi değildir; raf fiyatı misafirin ödediği fiyattır.
- Aramanın ilk sonucu genelde sponsorlu/sabitlenmiş üründür; geri kalanlar istenen sıralamayı izler.
- Veri: Migros'un herkese açık `product-bff` JSON API'si — anahtar yok, giriş yok, salt-okunur.
- Mağaza bulma ve teslimat saatleri oturum gerektirdiği için bu sunucuda yoktur.

## Kurallar

Gayriresmî ve salt-okunur — giriş yok, API anahtarı yok, yazma yok. Testler: çevrimdışı fixture + canlı testler (15/15 yeşil).

---

Built by [Mohammad Abbasi](https://github.com/mohammad-abbasi-sh) — [Almanibama](https://almanibama.ir) · [mabbasi.ir](https://mabbasi.ir)
