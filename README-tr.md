# migros-mcp 🇹🇷

**Migros Sanal Market** (migros.com.tr) için gayriresmî MCP sunucusu — canlı ürün arama, fiyatlar, Money indirimleri, kategoriler ve fiyat istatistikleri. Salt-okunur araçlar giriş gerektirmez. İsteğe bağlı **hesap işlemleri** (sepet + ödeme başlatma) kendi tarayıcı oturumunuzu kullanır, yalnızca MCP yapılandırmanızda saklanır — bkz. [Hesap işlemleri](#hesap-i̇şlemleri).

> "Türkiye MCP fabrikası" parçasıdır. Migros ile bağlantısı yoktur. Bu, **Türkiye** Migros'udur (migros.com.tr) — İsviçre Migros'unun npm'deki ilgisiz `migros-mcp` paketiyle karıştırılmamalıdır.

## Yapay zekâ ajanları için

MCP istemcinize ekleyin (stdio):

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

Hesap işlemleri (sepet + ödeme başlatma) için tarayıcı oturum çerezinizi
yapılandırmaya ekleyin — bkz. [Hesap işlemleri](#hesap-i̇şlemleri):

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

## Araçlar

| Araç | Açıklama |
|------|----------|
| `migros_search_products` | Ürün arama — `query` ("süt", "ekmek"…), `page`, `sort`: relevance / best_seller / discount / discount_amount / price_asc / price_desc |
| `migros_get_product` | Tek ürünün detayı — `product_id` (arama sonuçlarından) |
| `migros_list_categories` | Üst düzey mağaza kategorileri (11) |
| `migros_list_promotions` | Bir anahtar kelime için Money indirimli ürünler, en yüksek indirim önce |
| `migros_price_stats` | Bir anahtar kelime için fiyat istatistikleri (min/medyan/maks/ortalama, en ucuz ve en pahalı) |
| `migros_view_cart` | Sepetiniz: ürünler (sepet öğe id, ürün id, ad, adet, birim, toplam fiyat TRY), toplamlar, sepet URL'si — `MIGROS_SESSION` gerekir |
| `migros_add_to_cart` | Sepete ürün ekleme (`product_id`, `quantity` 1..99, değiştirme mantığı) — oturum + `confirm=true` gerekir |
| `migros_remove_from_cart` | Sepetten ürün çıkarma (`product_id`) — oturum + `confirm=true` gerekir |
| `migros_update_cart_quantity` | Sepetteki ürünün adedini değiştirme (`product_id`, `quantity` 1..99) — oturum + `confirm=true` gerekir |
| `migros_create_order` | Ödemeyi başlatma: sepeti doğrular, ödeme (ödeme) bağlantısını döndürür — sipariş OLUŞTURMAZ, ödeme yapmaz — `MIGROS_SESSION` gerekir |

Notlar:
- Fiyatlar Türk Lirası (TRY); API kuruş (1/100 TRY) döndürür.
- `money_discount_pct`, Money sadakat indirim yüzdesidir — etiket indirimi değildir; raf fiyatı misafirin ödediği fiyattır.
- Aramanın ilk sonucu genelde sponsorlu/sabitlenmiş üründür; geri kalanlar istenen sıralamayı izler.
- Veri: Migros'un herkese açık `product-bff` JSON API'si — anahtar yok, giriş yok, salt-okunur.
- Sepet adetleri **değiştirme mantığıyla** çalışır: bir ürünün adedini ayarlamak o değeri yapar — sepetteki miktarın üstüne eklenmez. Her ürünün ayrıca bir üst adet sınırı vardır; sunucu bunun üstündeki adetleri reddeder.
- Mağaza bulma ve teslimat saatleri oturum gerektirdiği için bu sunucuda yoktur.

## Hesap işlemleri

Sepet araçları **kendi tarayıcı oturumunuzla** çalışır — şifre yok, API
anahtarı yok, hiçbir yerde hesap oluşturulmaz. Oturum yalnızca kendi
makinenizdeki MCP istemci yapılandırmanızda bulunur ve yalnızca
migros.com.tr'ye gönderilir. Sunucu onu asla kaydetmez, yazdırmaz veya
saklamaz; hiçbir araç çıktısında görünmez. Her sepet değişikliği
(ekleme / çıkarma / adet değiştirme) ayrıca `confirm=true` gerektirir;
aksi halde hiçbir işlem yapılmaz.

### Kurulum (bir kez)

1. Tarayıcınızda (Chrome / Edge / Firefox)
   [migros.com.tr](https://www.migros.com.tr)'ye giriş yapın.
2. Geliştirici Araçları'nı açın (F12) → **Network** sekmesi → sayfayı
   yenileyin.
3. `migros.com.tr` adresine yapılan herhangi bir isteğe tıklayın →
   **Headers** → **Cookie** istek başlığını bulun → değerinin tamamını
   kopyalayın.
   (Alternatif: Geliştirici Araçları → **Application** → **Cookies** →
   `https://www.migros.com.tr` — ancak Network sekmesindeki Cookie
   başlığı tam değerdir; onu kopyalayın.)
4. Değeri MCP istemci yapılandırmanıza `MIGROS_SESSION` olarak
   yapıştırın (yukarıdaki örneğe bakın) ve MCP sunucusunu yeniden
   başlatın.
5. `migros_view_cart` aracını deneyin — gerçek sepetiniz
   görünmelidir.

### Notlar

- Oturumun süresi dolar: bir araç "session expired" derse, taze
  çerezler için 2–4. adımları tekrarlayın. migros.com.tr'den çıkış
  yapmak oturumu hemen geçersiz kılar.
- **Çerez değerini asla paylaşmayın** — elinde bulunduran herkes
  Migros hesabınıza tam erişim kazanır (sepet, siparişler).
  Sohbetlere, issue'lara veya ekran görüntülerine yapıştırmayın.
- Hesap işlemleri bilinçli olarak dardır: sepet (görüntüleme / ekleme /
  çıkarma / adet değiştirme) ve ödeme başlatma (yalnızca ödeme
  bağlantısını döndürür). Sipariş oluşturma, ödeme, kupon veya toplu
  işlem yoktur. `migros_create_order` asla sipariş oluşturmaz —
  adres, teslimat saati ve ödemeyi tarayıcıda siz tamamlarsınız.
- `store_id` / `unit`, herkese açık ürün detayından otomatik çözülür;
  yalnızca bu aramayı atlamak için verin.
- Sepet uç noktaları Migros'un herkese açık mağaza kodundan tersine
  mühendislikle çıkarıldı ve hesapsız olarak mümkün olduğunca canlı
  doğrulandı (sepet API'si çerezsiz isteklere çıplak HTTP 400,
  sipariş API'si HTTP 401 döndürür). Yanıt şekilleri savunmacı
  ayrıştırılır — beklenmeyen bir şekil açık bir not döndürür, asla
  uydurma veri üretmez.

## Kurallar

Gayriresmî — salt-okunur araçlar giriş gerektirmez, API anahtarı gerekmez. Sepet araçları yalnızca sizin oturumunuzla çalışır, ödeme yapmaz. Testler: çevrimdışı fixture + canlı testler.

---

[Mohammad Abbasi](https://github.com/mohammad-abbasi-sh) tarafından yapıldı — [Almanibama](https://almanibama.ir) · [mabbasi.ir](https://mabbasi.ir)
