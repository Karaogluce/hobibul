# 🎯 Hobi Bul — Affiliate Hobi Rehberi Sitesi

`hobibul.com.tr` için kapsamlı bir affiliate & içerik sitesi. Tüm hobi kategorilerini
kapsayan SEO uyumlu statik site + trafik/affiliate tıklama analitiği paneli.

## Özellikler

- **Geniş kategori ağacı:** 7 ana kategori, 28 alt kategori (35 kategori sayfası).
- **Her kategori/alt kategori için "En İyi 5" ürün rehberi:** 175 ürün, artı/eksi listeleri ve satın alma bağlantıları.
- **SEO:** her sayfa için özgün meta title/description, kanonik URL, breadcrumb, JSON-LD, `sitemap.xml`, `robots.txt`.
- **Çoklu affiliate ağı desteği:** Amazon (aktif), Amazon TR / Trendyol / Hepsiburada (ID eklemeye hazır).
- **Analitik paneli:** `/dashboard/` — makale görüntülenme, affiliate tıklama ve CTR (Supabase ile).
- **3 detaylı başlangıç makalesi** (1200+ kelime, H2/H3, gömülü affiliate linkleri).
- **Footer'da yasal affiliate açıklaması.**

## Dizin yapısı

```
content/            # VERİ (düzenlenecek kaynak)
  site.json         #   site adı, domain, analitik yapılandırması
  links.json        #   affiliate ağları ve tag'ler
  categories.json   #   kategori ağacı + SEO meta
  products.json     #   ürün verisi (Top 5 listeleri)
  articles/*.md     #   makaleler (markdown + frontmatter)
templates/          # Jinja2 şablonları
static/             # CSS + JS (stil, izleme, dashboard)
build.py            # statik site üretici
analytics/          # Supabase SQL şeması
docs/               # ÜRETİLEN site (GitHub Pages bunu yayınlar — commit'lenir)
```

## Yerelde çalıştırma

```bash
# 1) Siteyi üret (docs/ klasörüne)
python build.py

# 2) Önizleme
cd docs
python -m http.server 8000
# → http://localhost:8000
```

Gereksinim: Python 3 + Jinja2 (`pip install jinja2`).

## Affiliate link yöneticisi

Tüm ürün linkleri `content/products.json` içindeki `query` alanından otomatik üretilir ve
`content/links.json` içindeki ağ yapılandırmasıyla birleştirilir. Amazon ID şu anda
`hobibulsite67-20` (Amazon.com). Diğer ağları aktifleştirmek için `content/links.json`'da
ilgili ağın `tag`/`base_url` alanını doldurup `"active": true` yapın, sonra `python build.py`
ile yeniden üretin.

> Amazon.com.tr, Trendyol ve Hepsiburada affiliate programlarına katıldığınızda ilgili
> ID/link şablonunu aynı dosyaya ekleyin — yapı buna hazır.

Yeni ürün/kategori eklemek: `content/products.json` ve/veya `content/categories.json`'ı
düzenleyin, `python build.py` çalıştırın. Her şey otomatik üretilir.

## GitHub Pages ile yayınlama

1. GitHub'da **hobibul** (veya istediğiniz ad) adında bir repo oluşturun.
2. Bu klasörün tamamını repoya push'layın:
   ```bash
   git init
   git add .
   git commit -m "Hobi Bul — ilk sürüm"
   git branch -M main
   git remote add origin https://github.com/KULLANICI_ADI/hobibul.git
   git push -u origin main
   ```
3. Repo ayarları → **Pages** → *Build and deployment* bölümünde:
   - Source: **Deploy from a branch**
   - Branch: **main**, klasör: **/docs**
   - Kaydet.
4. Birkaç dakika içinde site `https://KULLANICI_ADI.github.io/hobibul/` adresinde yayınlanır.

## Özel alan adı (hobibul.com.tr)

1. `.com.tr` alan adını kayıt operatöründen satın alın (`.com.tr` tescilinde genellikle
   kimlik/firma bilgisi ve bazı durumlarda belge istenir).
2. DNS yönetiminde **CNAME** kaydı ekleyin:
   - Host: `www`  →  Değer: `KULLANICI_ADI.github.io`
   - (Apex `hobibul.com.tr` için kayıt operatörünüz destekliyorsa GitHub Pages'in IP
     adreslerine A kaydı ekleyin — GitHub'ın güncel IP'lerini GitHub Docs'tan kontrol edin.)
3. GitHub repo ayarları → **Pages** → **Custom domain** alanına `hobibul.com.tr` yazın.
   (Bu, `docs/CNAME` dosyasına da yazılır — build.py zaten `docs/CNAME` üretir.)
4. "Enforce HTTPS" seçeneğini açın (sertifika otomatik oluşturulur).

## Analitik paneli kurulumu (Supabase — ücretsiz)

1. [supabase.com](https://supabase.com)'da ücretsiz proje oluşturun.
2. **SQL Editor**'a gidin ve `analytics/supabase-schema.sql` içeriğini yapıştırıp çalıştırın.
3. **Project Settings → API** bölümünden şunları kopyalayın:
   - `Project URL`
   - `anon` / `public` anahtarı
4. `content/site.json` içindeki `analytics` bölümüne yapıştırın:
   ```json
   "analytics": {
     "supabase_url": "https://xxxx.supabase.co",
     "supabase_anon_key": "eyJ..."
   }
   ```
5. `python build.py` ile yeniden üretin ve GitHub'a push'layın.
6. `/dashboard/` sayfasını açın — canlı görüntülenme ve tıklama verileri gelecek.

> Not: anon anahtar herkese açık olduğundan teknik olarak isteyen sahte olay yazabilir.
> Küçük bir site için önemsizdir; ciddi ölçeğe ulaştığınızda yazmayı bir sunucuya taşıyın.

## Amazon bölgesi notu

`hobibulsite67-20` bir Amazon.com (ABD) Associates tag'idir. Türk ziyaretçilerinize
Amazon.com.tr üzerinden satın alma önermek isterseniz Amazon.com.tr Associates programına
katılıp tag'inizi `content/links.json` → `amazon_tr` bölümüne ekleyin ve ürünlerin
`network` alanını `amazon_tr` yapın.

## Yasal

Footer'da yer alan affiliate açıklaması, FTC/uluslararası affiliate düzenlemeleri
gereği tüm sayfalarda gösterilir. Satış/vergi/veri yükümlülükleriniz için bir hukuk
danışmanına başvurmanız önerilir.


## Yeni makale ekleme (otomatik)

```
pip install jinja2
copy .env.example .env        # içine GEMINI_API_KEY yaz (aistudio.google.com)
python yeni_makale.py --liste outdoor
python yeni_makale.py --kategori outdoor --alt kampcilik --baslik "Başlık" --urunler id1,id2 --build
python yeni_makale.py ... --build --push      # build + git push (yayın)
```

Not: `docs/` her `python build.py` çalıştırmasında sıfırdan üretilir. `docs/` içindeki dosyaları elle
düzenleme; değişiklikleri `templates/`, `static/` ve `content/` altında yap. Amazon TR tag'i:
`content/links.json` → `amazon_tr.tag`.

## Günlük otomatik makale (GitHub Actions)

`.github/workflows/gunluk-makale.yml` her gün 08:00'de (TR) `otomatik.py` ile 2 makale üretir, siteyi
yeniden oluşturur ve commit eder.

Kurulum (bir kerelik): GitHub → Settings → Secrets and variables → Actions
- **Secrets:** `GEMINI_API_KEY`, `UNSPLASH_ACCESS_KEY` (unsplash.com/developers → New Application → Access Key)
- **Variables:** `TASLAK_MODU` = `true` (ilk 2 hafta öneri) → makaleler `draft: "true"` ile yazılır, yayınlanmaz.
  Beğendiğin makalenin `content/articles/…md` dosyasında `draft: "true"` → `"false"` yapıp kaydedince site otomatik güncellenir.
  Güvendiğinde `TASLAK_MODU` = `false` yap, makaleler doğrudan yayınlanır.
- Opsiyonel `GEMINI_MODEL`: model adı eskirse AI Studio'dan güncel adı yaz.
- Opsiyonel `GEMINI_MODEL_YEDEK` (variable): ana model 503/429 verdiğinde sırayla denenecek yedek
  model(ler), virgülle. Örn. `gemini-flash-lite-latest`. Günlük kota (429 per-day) algılanırsa
  beklenmeden doğrudan yedek modele geçilir; kota her gece Pasifik saatiyle 00:00'da sıfırlanır.

Kalite kapıları (geçemeyen makale yayınlanmaz, `content/uretim_log.json` → `atlanan`): minimum kelime,
H2 sayısı, SSS bölümü, tüm ürünlerin linki, fiyat/abartı yasağı, mevcut makalelerle benzerlik kontrolü.
Sıradaki konuları görmek için: `python otomatik.py --konu-listesi`

- Yazım kuralları ve yasaklı kalıplar: `content/yazim_rehberi.md` (düzenlenebilir). Çalışma planı: `PLAN.md`.

## GA4 analitik paneli

`fetch_analytics.py` + `.github/workflows/analytics.yml`, GA4'ten günlük veriyi **sunucu
tarafında** (GitHub Actions) çekip `content/analytics_ga4.json`'a yazar; panel bu dosyayı okur.
Servis hesabı anahtarı hiçbir zaman tarayıcıya/koda konmaz. Kurulum adımları aşağıda —
`/dashboard/` sayfasındaki "GA4 kurulumu" notuna da bakabilirsin.

Secrets (GitHub → Settings → Secrets and variables → Actions):
- `GA4_PROPERTY_ID` — GA4 mülk numarası (örn. 123456789)
- `GA4_SERVICE_ACCOUNT_JSON` — servis hesabı JSON anahtarının tüm içeriği

`content/site.json` → `ga4_id` alanına gerçek `G-XXXXXXXXXX` ölçüm kodunu yaz (ziyaretçi
takibini [gtag.js] başlatır; panel verisiyle aynı şey değildir, ikisi de gerekli).
