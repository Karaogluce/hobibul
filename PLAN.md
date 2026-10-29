# Hobi Bul — Çalışma Planı

Hedef: kategorilere uygun, aranan konulara cevap veren, okuyucuya doğal gelen makalelerle organik trafik çekmek ve Amazon TR affiliate geliri elde etmek.

## Faz 0 — Altyapı ✅
- [x] Üretici (`build.py`) şablonlara taşındı, makale sayfası site düzeniyle açılıyor
- [x] `otomatik.py` + GitHub Actions: İstanbul gününde 8 makale; her 30 dk eksik kalanı tamamlar
- [x] Unsplash görselleri ve fotoğrafçı kredisi

## Faz 1 — Yazım kalitesi ✅ (bu sürüm)
- [x] `content/yazim_rehberi.md`: ses, yapı, ritim, dürüstlük kuralları, yasaklı kalıplar (dosyayı sen düzenleyebilirsin)
- [x] İki geçiş: taslak yaz → editör geçişi (klişe temizleme, ritim, uydurma bilgi silme)
- [x] Stil kapıları: yasaklı kalıp, cümle ritmi, uzun cümle oranı, aynı kelimeyle başlama
- [x] Uydurma deneyim yasağı; gerçek deneyim için `products.json` ürünlerine `"not": "..."` alanı

## Faz 2 — Konu keşfi (sıradaki)
- [ ] Google Autocomplete'i alfabe/soru ekleriyle genişletip `konu_havuzu.json` oluştur (gerçek aramalar → trafik)
- [ ] Yeni tipler: kontrol listesi, "nasıl yapılır", mevsimsel, sadece gerçekten kıyaslanabilir ürünlerde "X mi Y mi"
- [ ] Konuları önceliklendir (uzun kuyruk, düşük rekabet) ve kümelere ayır

## Faz 3 — Teknik SEO
- [ ] Makale içine otomatik iç link (aynı kategori/alt kategori makaleleri)
- [ ] Pillar sayfa (alt kategori sayfası) ↔ makale çift yönlü bağlantı
- [ ] Sitemap `lastmod`, içindekiler listesi, görsel boyutu/`alt` denetimi
- [ ] Search Console + Bing Webmaster kayıtları, sitemap gönderimi

## Faz 4 — Ürün havuzu
- [ ] Türkiye'de Amazon TR'de gerçekten satılan ürünleri `products.json`'a ekle; arama linki yerine `/dp/ASIN` linki
- [ ] Her kategoride en az 10 ürün (tekrar riskini azaltır)
- [ ] Mümkünse gerçek notlar (`"not"`) ve kendi fotoğrafların

## Faz 5 — Ölçüm ve bakım (her hafta)
- [ ] Search Console: gösterim/tıklama, indekslenmeyen sayfalar
- [ ] Düşük performanslı makaleyi güncelle ya da `noindex` yap; trafik getiren konuda derinleş
- [ ] `content/uretim_log.json` → `atlanan` nedenlerini oku, yazım rehberini buna göre ayarla
- [ ] Amazon Associates satış sayısını takip et

## Kurallar
- Fiyat, ölçü, puan, test iddiası uydurma yok. Taslak modunda ilk 2 hafta elle onay.
- Günde 8 yayın (Europe/Istanbul). Eksikse Actions yarım saatte bir yeniden dener. Geçici Gemini hataları işi düşürmez; biten makale hemen diske yazılır.
- Gizli anahtarlar yalnızca GitHub Secrets'ta.
