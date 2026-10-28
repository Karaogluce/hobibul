# 🎯 Hobi Bul — Affiliate Hobi Rehberi Sitesi

`hobibul.com.tr` için kapsamlı bir affiliate & içerik sitesi. Tüm hobi kategorilerini
kapsayan SEO uyumlu statik site + trafik/affiliate tıklama analitiği paneli.

## Özellikler

- **Geniş kategori ağacı:** 7 ana kategori, 28 alt kategori (35 kategori sayfası).
- **Her kategori/alt kategori için "En İyi 5" ürün rehberi:** 175 ürün, artı/eksi listeleri ve satın alma bağlantıları.
- **SEO:** her sayfa için özgün meta title/description, kanonik URL, breadcrumb, JSON-LD, `sitemap.xml`, `robots.txt`.
- **IndexNow:** yeni/değişen sayfalar Bing, Yandex, Seznam ve Naver'a sitemap beklemeden anında bildirilir.
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
4. **Enforce HTTPS** kutusunu işaretleyin. Sertifika onaylı olsa bile kutu kapalıysa
   `https://karaogluce.github.io/hobibul/` ziyaretçiyi `http://hobibul.com.tr/` adresine yollar.
   Kutu açıkken aynı adres `https://hobibul.com.tr/` adresine gider ve düz HTTP de oraya döner.

### HTTPS zinciri (28 Ekim 2026 ölçümü)

Repo bunu tek başına çeviremez. `docs/CNAME` zaten `hobibul.com.tr`. Kanonik adres `https://hobibul.com.tr`.
GitHub, `*.github.io` isteğine 301'i dosyalara bakmadan kendisi yazar. Bu çalıştırmada Pages API şunu döndü:

- `https_enforced`: **false**
- `html_url`: `http://hobibul.com.tr/`
- sertifika: **approved**, yalnızca `hobibul.com.tr` (www yok), bitiş 2027-01-23
- `https://karaogluce.github.io/hobibul/` → `301 Location: http://hobibul.com.tr/`
- `https://hobibul.com.tr/` → 200
- `http://hobibul.com.tr/` bu ortamda 200 (site şifresiz açılıyor). 500 görürsen sebep aynı anahtar:
  Enforce HTTPS kapalıyken HTTP kenarı kararsız kalabiliyor. Anahtar açılınca HTTP, 301 ile HTTPS'e döner.
- `https://www.hobibul.com.tr/` sertifika hatası: sunucu `*.github.io` sertifikası veriyor, www adıda yok.
  DNS'te `www`, `hobibul.com.tr` adresine CNAME. GitHub'ın istediği hedef `karaogluce.github.io`.

Ayar değiştirme denemesi `403 Resource not accessible by integration` ile durdu. Kutuyu Emre açar:

1. Aç: `https://github.com/Karaogluce/hobibul/settings/pages`
2. **Build and deployment** → Source: Deploy from a branch, Branch: `main`, Folder: `/docs`.
3. **Custom domain** kutusunda `hobibul.com.tr` yazsın. Değilse yaz, **Save**.
4. "DNS check successful" görününce **Enforce HTTPS** kutusunu işaretle.
5. Kutu griyse: domain'i sil, Save, bir dakika bekle, `hobibul.com.tr` yaz, Save, sertifika "approved" olunca kutuyu işaretle.
6. Kontrol:
   - `curl -sI https://karaogluce.github.io/hobibul/` → `location: https://hobibul.com.tr/`
   - `curl -sI http://hobibul.com.tr/` → `301` ve `location: https://hobibul.com.tr/`

DNS (Turkticaret, NS: `ns1/ns2/ns3.turkticaret.net`). Apex A kayıtları doğru, silme:

- `185.199.108.153`
- `185.199.109.153`
- `185.199.110.153`
- `185.199.111.153`

`www` kaydını değiştir: tür CNAME, hedef `karaogluce.github.io` (şu an `hobibul.com.tr`).
Panelde ayrı bir "HTTP yönlendir / 301" kuralı varsa kapat; o kural `http://` üretirse zinciri bozar.
İsteğe bağlı AAAA (GitHub'ın yayımladığı adresler): `2606:50c0:8000::153`, `2606:50c0:8001::153`, `2606:50c0:8002::153`, `2606:50c0:8003::153`.

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

`.github/workflows/gunluk-makale.yml` her gün 11:00'de (TR) `otomatik.py` ile **tam 2** makale üretir, siteyi
yeniden oluşturur ve commit eder. (Saat, Gemini günlük kotasının Pasifik gece yarısı sıfırlanmasına göre seçildi.)
Elle tetikte de sayı 2'nin üstüne çıkmaz.

Sıra ticari niyettedir: önce `content/konu_havuzu.json` içinde `tip_onerisi: "ticari"` olan konular, sonra her alt
kategori için bir başlangıç seti. `nedir`, `nasıl yazılır`, il adı ve yabancı dil sorguları havuzdan ve Google
önerilerinden elenir. Kapıdan geçen metin en az yaklaşık 1500 kelimedir (ticari konularda 1550); hedef 1650–2000.

Kurulum (bir kerelik): GitHub → Settings → Secrets and variables → Actions
- **Secrets (zorunlu):** `GEMINI_API_KEY` — [Google AI Studio](https://aistudio.google.com) anahtarı. Yoksa iş makale üretmeden durur.
- **Secrets (görsel için):** `UNSPLASH_ACCESS_KEY` — unsplash.com/developers → New Application → Access Key. Yoksa makale kategori görseliyle çıkar, iş durmaz.
- **Variables:** `TASLAK_MODU` — varsayılan `false`: makaleler doğrudan yayınlanır. `true` yaparsan makaleler
  `draft: "true"` ile taslak yazılır; beğendiğin makalenin `content/articles/…md` dosyasında `draft: "true"` → `"false"`
  yapıp kaydedince site otomatik güncellenir. (Değişkeni hiç tanımlamazsan da yayın modu geçerli.)
- Opsiyonel `GEMINI_MODEL`: model adı eskirse AI Studio'dan güncel adı yaz. Tanımsızsa `gemini-flash-latest`.
- Opsiyonel `GEMINI_MODEL_YEDEK` (variable): ana model 503/429 verdiğinde sırayla denenecek yedek
  model(ler), virgülle. Örn. `gemini-flash-lite-latest`. Günlük kota (429 per-day) algılanırsa
  beklenmeden doğrudan yedek modele geçilir; kota her gece Pasifik saatiyle 00:00'da sıfırlanır.

Kalite kapıları (geçemeyen makale yayınlanmaz, `content/uretim_log.json` → `atlanan`): minimum kelime,
H2 sayısı, SSS bölümü, ürün linki, ticari konuda paket tablosu, fiyat/abartı yasağı, yazım ritmi,
mevcut makalelerle benzerlik kontrolü.
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

## IndexNow (Bing / Yandex anında bildirim)

`indexnow.py`, sitemap'in taranmasını beklemeden yeni ve değişen sayfaları IndexNow
API'sine bildirir. Google bu protokolü kullanmaz; Google tarafı Search Console +
sitemap ile yürür. Bing, Yandex, Seznam ve Naver kullanır.

Kurulum gerekmez, hazır:
- `content/site.json` → `indexnow_key` anahtarı tutar (gizli değildir, protokol gereği
  sitenin kökünde herkese açık yayınlanır).
- `build.py` bu anahtarı `docs/<anahtar>.txt` olarak üretir; doğrulama bu dosya üzerinden yapılır.
- `.github/workflows/gunluk-makale.yml` son adımda yalnızca **o çalıştırmada değişen**
  sayfaları bildirir (`docs/sitemap.xml` veya anahtar dosyası değiştiyse tüm siteyi).

Elle kullanım:
```bash
python build.py
python indexnow.py                 # sitemap'teki tüm URL'ler
python indexnow.py --kuru          # göndermeden listele
python indexnow.py --degisen liste.txt
```

Anahtarı değiştirmek istersen `content/site.json` → `indexnow_key` alanına yeni bir
8–128 karakterlik hex değer yaz, `build.py` yeni doğrulama dosyasını üretir (eskisini sil).
