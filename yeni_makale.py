#!/usr/bin/env python3
"""Hobi Bul — otomatik makale üretici (Gemini ücretsiz katmanı).

Kullanım örnekleri (Windows / Python 3.11, ek paket gerekmez):

  python yeni_makale.py --kategori outdoor --alt kampcilik --baslik "Kamp İçin Uyku Matı Nasıl Seçilir?"
  python yeni_makale.py --kategori muzik --alt gitar --baslik "..." --urunler yamaha-f310,boss-katana-50
  python yeni_makale.py ... --build            # makaleyi yazınca build.py'yi de çalıştırır
  python yeni_makale.py ... --build --push     # + git add/commit/push (siteyi yayınlar)
  python yeni_makale.py --liste outdoor        # o kategorideki ürün id'lerini listeler

Kurulum: aynı klasöre .env dosyası oluştur ve içine şunu yaz:
  GEMINI_API_KEY=anahtarin
  GEMINI_MODEL=gemini-flash-latest      (isteğe bağlı; model adı değişirse AI Studio'dan kopyala)

Mantık: Ürünleri SEN seçersin (content/products.json). Model yalnızca bu ürün
verilerini (ad, açıklama, artı/eksi) kullanarak metni yazar; ürün, fiyat veya
teknik özellik uydurması yasaklanır. Linkler aff://ürün-id olarak yazılır ve
build.py bunları Amazon TR linkine (hobibulsite-21 tag'i) çevirir.
"""
import argparse
import http.client
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date

class GeminiError(Exception):
    pass


BASE = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(BASE, "content")
ARTICLES = os.path.join(CONTENT, "articles")


def load_env():
    path = os.path.join(BASE, ".env")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load(name):
    with open(os.path.join(CONTENT, name), encoding="utf-8") as f:
        return json.load(f)


TR = str.maketrans("çğıöşüÇĞİÖŞÜâîû", "cgiosuCGIOSUaiu")


def slugify(text):
    t = text.translate(TR).lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:80].rstrip("-")


def pick_products(products, cat, sub, ids):
    pool = products.get(cat, {}).get(sub or "_main", [])
    if not ids:
        return pool
    by_id = {p["id"]: p for p in pool}
    # alt kategori dışından da id verilebilsin
    for subs in products.values():
        for items in subs.values():
            for p in items:
                by_id.setdefault(p["id"], p)
    missing = [i for i in ids if i not in by_id]
    if missing:
        sys.exit(f"Bilinmeyen ürün id: {', '.join(missing)}  (--liste ile bak)")
    return [by_id[i] for i in ids]


def build_prompt(title, cat_name, prods, words):
    plist = []
    for p in prods:
        plist.append(
            f"- id: {p['id']}\n  ad: {p['name']}\n  marka: {p.get('brand','')}\n"
            f"  açıklama: {p.get('desc','')}\n"
            f"  artılar: {'; '.join(p.get('pros', []))}\n"
            f"  eksiler: {'; '.join(p.get('cons', []))}"
        )
    return f"""Sen Türkiye'deki hobi meraklıları için yazan bir blog editörüsün.
Aşağıdaki başlıkla, Türkçe, özgün ve yardımsever bir rehber makalesi yaz.

BAŞLIK: {title}
KATEGORİ: {cat_name}
HEDEF UZUNLUK: yaklaşık {words} kelime

KULLANABİLECEĞİN ÜRÜNLER (SADECE bunlar; başka ürün/marka/model ekleme):
{chr(10).join(plist)}

KESİN KURALLAR:
1. Yukarıdaki ürün verilerinde olmayan teknik özellik, ağırlık, ölçü, fiyat, puan veya test sonucu UYDURMA. Emin olmadığın şeyi yazma.
2. Fiyat yazma. Gerekirse "güncel fiyatı Amazon'da kontrol et" de.
3. Her ürün için ayrı bir ### başlık aç; açıklamayı, artıları ve eksileri kullan, sonunda tam olarak şu biçimde link ver:
   [Satın Al: ÜRÜN ADI](aff://ÜRÜN_ID)
4. Biçim: yalnızca Markdown. En üstte H1 kullanma (başlık ayrı basılacak). ## ve ### başlıkları, madde listeleri ve kısa paragraflar kullan.
5. Yapı: kısa giriş, "Nelere dikkat etmeli?" bölümü, ürün önerileri, "Hangisini seçmeli?" özeti, SSS (3 soru), sonuç.
6. Doğal ve samimi Türkçe kullan, klişe ve abartıdan kaçın ("mükemmel", "piyasa lideri" gibi kanıtsız iddialar yok).
7. Çıktıda sadece makale metni olsun; açıklama, kod bloğu veya ön söz ekleme.
"""


def call_gemini(prompt, key, model):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.6, "maxOutputTokens": 8192},
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json", "x-goog-api-key": key})
    kopma = 0
    for attempt in range(7):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read().decode("utf-8"))
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts).strip()
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 503) and attempt < 3:
                wait = 20 * (attempt + 1)
                print(f"  API {e.code}, {wait} sn bekleniyor…")
                time.sleep(wait)
                continue
            raise GeminiError(f"Gemini hatası {e.code}: {msg} (Model adı eskimiş olabilir: GEMINI_MODEL değerini AI Studio'dan kontrol et.)")
        except (http.client.RemoteDisconnected, urllib.error.URLError) as e:
            # urllib bazı sürümlerde bağlantı kopmasını URLError içine sarar
            if not (isinstance(e, http.client.RemoteDisconnected)
                    or isinstance(getattr(e, "reason", None), http.client.RemoteDisconnected)):
                raise
            kopma += 1
            if kopma > 3:
                raise GeminiError("Gemini bağlantıyı 3 kez üst üste kesti; tekrar deneyin.")
            print(f"  Bağlantı koptu, 30 sn bekleniyor… ({kopma}/3)")
            time.sleep(30)
    raise GeminiError("Gemini yanıt vermedi.")


def validate(body, prods):
    """Üretilen metni denetle; sorun varsa uyarı ver, uydurma linkleri temizle."""
    allowed = {p["id"] for p in prods}
    used = set(re.findall(r"aff://([A-Za-z0-9_-]+)", body))
    bad = used - allowed
    if bad:
        print(f"  ! İzin verilmeyen ürün id'leri kaldırıldı: {', '.join(sorted(bad))}")
        for b in bad:
            body = re.sub(r"\[[^\]]*\]\(aff://%s\)" % re.escape(b), "", body)
    unused = allowed - used
    if unused:
        print(f"  ! Metinde linki olmayan ürünler: {', '.join(sorted(unused))}")
    body = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", body.strip())
    body = re.sub(r"^# .*\n+", "", body)  # olası H1'i at
    if re.search(r"\d+\s*(?:₺|TL)\b", body):
        print("  ! Metinde fiyat geçiyor; yayından önce kontrol et.")
    return body.strip()


def first_paragraph(body, n=220):
    for para in body.split("\n\n"):
        p = para.strip()
        if p and not p.startswith(("#", "-", "*", "[")):
            p = re.sub(r"[*_`]", "", p)
            return (p[: n - 1].rsplit(" ", 1)[0] + "…") if len(p) > n else p
    return ""


def main():
    ap = argparse.ArgumentParser(description="Hobi Bul makale üretici")
    ap.add_argument("--kategori")
    ap.add_argument("--alt", default="", help="alt kategori id (boşsa ana kategori listesi)")
    ap.add_argument("--baslik")
    ap.add_argument("--urunler", default="", help="virgülle ürün id'leri (boşsa alt kategorinin tüm ürünleri)")
    ap.add_argument("--kelime", type=int, default=1100)
    ap.add_argument("--slug", default="")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--liste", metavar="KATEGORI", help="bu kategorideki ürün id'lerini listele")
    a = ap.parse_args()

    load_env()
    products = load("products.json")
    cats = {c["id"]: c for c in load("categories.json")}

    if a.liste:
        for sub, items in products.get(a.liste, {}).items():
            print(f"[{sub}]")
            for p in items:
                print(f"   {p['id']}  —  {p['name']}")
        return
    if not (a.kategori and a.baslik):
        ap.error("--kategori ve --baslik gerekli")
    if a.kategori not in cats:
        sys.exit(f"Kategori yok. Geçerli olanlar: {', '.join(cats)}")

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("GEMINI_API_KEY yok. .env dosyasına ekle (aistudio.google.com).")
    model = os.environ.get("GEMINI_MODEL") or "gemini-flash-latest"

    ids = [x.strip() for x in a.urunler.split(",") if x.strip()]
    prods = pick_products(products, a.kategori, a.alt, ids)
    if not prods:
        sys.exit("Bu kategoride ürün bulunamadı; products.json'a ürün ekle.")

    slug = a.slug or slugify(a.baslik)
    path = os.path.join(ARTICLES, slug + ".md")
    if os.path.exists(path):
        sys.exit(f"Zaten var: {path} (--slug ile farklı ad ver)")

    cat_name = cats[a.kategori]["name"]
    print(f"→ {len(prods)} ürünle makale üretiliyor ({model})…")
    try:
        raw = call_gemini(build_prompt(a.baslik, cat_name, prods, a.kelime), key, model)
    except GeminiError as e:
        sys.exit(str(e))
    body = validate(raw, prods)
    if len(body.split()) < 400:
        sys.exit("Çıktı çok kısa geldi, yazılmadı. Tekrar dene.")

    excerpt = first_paragraph(body)
    year = date.today().year
    meta_title = f"{a.baslik} | Hobi Bul"
    fm = "\n".join([
        "---",
        f'title: "{a.baslik}"',
        f'slug: "{slug}"',
        f'category: "{a.kategori}"',
        f'date: "{date.today().isoformat()}"',
        f'meta_title: "{meta_title[:70]}"',
        f'meta_description: "{excerpt[:155].replace(chr(34), chr(39))}"',
        f'excerpt: "{excerpt.replace(chr(34), chr(39))}"',
        "---", ""])
    os.makedirs(ARTICLES, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(fm + "\n" + body + "\n")
    print(f"✓ Yazıldı: content/articles/{slug}.md  ({len(body.split())} kelime)")
    print("  Yayından önce metni bir kez oku ve gerekirse düzelt.")

    if a.build or a.push:
        subprocess.run([sys.executable, os.path.join(BASE, "build.py")], check=True)
    if a.push:
        subprocess.run(["git", "add", "-A"], cwd=BASE, check=True)
        subprocess.run(["git", "commit", "-m", f"Yeni makale: {a.baslik}"], cwd=BASE, check=True)
        subprocess.run(["git", "push"], cwd=BASE, check=True)
        print("✓ Yayınlandı (GitHub Pages birkaç dakikada günceller).")


if __name__ == "__main__":
    main()
