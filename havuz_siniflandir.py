#!/usr/bin/env python3
"""Konu havuzundaki tip_onerisi=None kayıtlarını ön elemeden geçirip sınıflandırır.

  python havuz_siniflandir.py            # kuru çalışma; rapor basar, dosya yazmaz
  python havuz_siniflandir.py --yaz      # siniflandirma alanlarını havuza yazar
  python havuz_siniflandir.py --json     # özeti JSON basar

Yeni Autocomplete isteği yapılmaz, makale üretilmez. Ham `sorgu`, `kategori`,
`alt` alanları korunur. Her kayda geriye uyumlu bir `siniflandirma` nesnesi
eklenir; `tip_onerisi` yalnızca kesin atamada güncellenir. Böylece eski havuz
tüketicileri alanı yok saymaya devam eder, yeni kuyruk ise elenenleri atlar.

Durumlar:
  uygun        tip atandı, ürün eşiği tutuyor, makale/kuyrukla yinelenmiyor
  yinelenen    mevcut makale, tamamlanmış sorgu veya yakın niyetle çakışıyor
  incelenecek  tip sinyali yok ya da ürün sayısı eşiğin altında
  elendi       bozuk, alakasız veya istenmeyen niyet
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

import urun_denetim

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(BASE, "content")
POOL_PATH = os.path.join(CONTENT, "konu_havuzu.json")
CATEGORIES_PATH = os.path.join(CONTENT, "categories.json")
PRODUCTS_PATH = os.path.join(CONTENT, "products.json")
LOG_PATH = os.path.join(CONTENT, "uretim_log.json")
ARTICLES = os.path.join(CONTENT, "articles")

TIPLER = ("ticari", "rehber", "yeni_baslayan", "hatalar", "sss", "kontrol_listesi", "nasil_yapilir")
URUN_ODAKLI = ("ticari", "rehber", "yeni_baslayan")

TR_LOWER = str.maketrans("ÇĞİÖŞÜI", "çğiöşüı")
SADE = str.maketrans("çğıöşüâîû", "cgiosuaiu")

FIYAT = re.compile(r"\bfiyat|ucuz|indirim|kampanya|kupon|\btl\b|\btry\b|₺", re.I)
MAGAZA = re.compile(
    r"\b(?:a101|bim|şok|n11|trendyol|hepsiburada|amazon|sahibinden|aliexpress|geekbuying)\w*", re.I)
YIL = re.compile(r"\b(?:201[5-9]|202[0-5])\b")
ISTENMEYEN = re.compile(
    r"\bpdf\b|\bindir\b|\bizle\b|\bonline\b|\bikinci\s+el|\bkiral|\bsatın\s+al|\bsatin\s+al"
    r"|\bkul[üu]b|\bderne[ğg]|\bbelgesi\b", re.I)
KAMP_BELGE = re.compile(r"kamp[çc]ılık\s+belgesi", re.I)
TANIM = re.compile(
    r"\bnedir\b|\bne demek\b|\bne anlama gelir\b|\bnasıl yazılır\b|\bnasil yazilir\b"
    r"|\bnasıl okunur\b|\bnasil okunur\b|\bnereden alınır\b|\bnereden alinir\b"
    r"|\bnasıl alınır\b|\bnasil alinir\b", re.I)
# Açıkça başka bir bağlama ait sorgular; silinmez, incelemeye bırakılır.
BASKA_BAGLAM = re.compile(
    r"\bmetin2\b|\bhecelerine\b|\bheceleme\b|\bnasıl çizilir\b|\bnasil cizilir\b|\bçizim\b|\bcizim\b"
    r"|\bnasıl sürülür\b|\bnasil surulur\b|\bnasıl basılır\b|\bnasil basilir\b"
    r"|\bantrenör\b|\bantrenor\b|\behliyet\b|\bsertifika\b|\bmaaş\b|\bmaas\b|\bmeslek\b"
    r"|\bnasıl olunur\b|\bnasil olunur\b", re.I)
GENEL_YORUM = re.compile(
    r"\bgelecekte\b|\bgelecek mi\b|\binsan hayatını\b|\binsan hayatini\b"
    r"|\bpara kazandırır\b|\bpara kazandirir\b|\bpara kazan\b|\bkazandırır\b|\bkazandirir\b"
    r"|\bkazanç\b|\bkazanc\b|\bgelir elde\b|\bmeslek olarak\b", re.I)


def _kucuk(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().translate(TR_LOWER).lower()


def _sade(s):
    return _kucuk(s).translate(SADE)


def _kelimeler(s):
    return set(re.findall(r"[a-z0-9]+", _sade(s)))


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", _sade(s)).strip("-")[:80].rstrip("-")


def _jaccard(a, b):
    return len(a & b) / len(a | b) if a | b else 0.0


def _kapsar(q, t):
    """Sorgunun kelimelerinin en az %80'i hedef metinde geçiyor mu."""
    return bool(q and t and len(q & t) / len(q) >= 0.8)


def _kok_eslesir(a, b):
    """Türkçe ek farkını yut: en az dört harflik ortak kök yeter."""
    if a == b:
        return True
    kisa = min(len(a), len(b))
    return kisa >= 4 and (a.startswith(b) or b.startswith(a))


def _ortak(a, b):
    """İki kelime kümesi kök düzeyinde kesişiyor mu."""
    return any(_kok_eslesir(x, y) for x in a for y in b)


def elenme_nedeni(sorgu):
    """Sorgu üretime hiç alınmamalı mı; alınacaksa None."""
    if len(str(sorgu).split()) < 3:
        return "çok kısa/bozuk"
    if KAMP_BELGE.search(sorgu):
        return "belge/kariyer sorgusu"
    if TANIM.search(sorgu):
        return "tanım/sözlük sorgusu"
    if ISTENMEYEN.search(sorgu):
        return "kiralama/satın alma/belge/kulüp"
    if FIYAT.search(sorgu):
        return "fiyat/indirim niyeti"
    if MAGAZA.search(sorgu):
        return "mağaza/marka sorgusu"
    if YIL.search(sorgu):
        return "eski yıl etiketi"
    return None


def tip_belirle(sorgu):
    """Sorguya en uygun makale tipi; sinyal yoksa None."""
    s = _sade(sorgu)
    if re.search(
        r"nasil yapilir|yapimi\b|adim adim|uygulama|nasil cekilir|nasil kurulur|kurulum"
        r"|nasil sikilir|nasil takilir|nasil sokulur|nasil temizlenir|nasil ayarlanir"
        r"|nasil tamir|nasil dikilir|nasil orulur|nasil pisirilir|nasil boyanir|nasil yikanir", s):
        return "nasil_yapilir"
    if re.search(r"kontrol listesi|checklist|listesi|malzemeleri|ihtiyac listesi", s):
        return "kontrol_listesi"
    if re.search(r"\bhata|yanlis|kacin|dikkat edilmesi", s):
        return "hatalar"
    if re.search(r"yeni baslayan|sifirdan|ilk kez|ilk defa|nasil baslanir|nasil baslarim|nereden baslamali", s):
        return "yeni_baslayan"
    if re.search(r"\bseti\b", s):
        return "ticari"
    if re.search(r"en iyi|hangi|secimi|secilir|alirken|butce|marka|\bmodel\b|oneri|karsilastirma|satin", s):
        return "ticari"
    if re.search(r"\?$|\b(mi|mu|neden|nicin|nasil|ne kadar|ne zaman|hangisi)\b", s):
        return "sss"
    if re.search(r"rehber|ogren|ipucu|tavsiye|bakim|kullanim|basla", s):
        return "rehber"
    if re.search(r"\bbaslangic\b", s):
        return "yeni_baslayan"
    return None


def gerekli_urun(tip):
    return 3 if tip in URUN_ODAKLI else 2


def makale_indeksi(articles_dir=ARTICLES):
    rows = []
    for m in urun_denetim.makale_verileri(articles_dir):
        metin = " ".join([m.get("baslik", ""), m.get("odak", ""), str(m.get("slug", "")).replace("-", " ")])
        rows.append((m.get("dosya", ""), m.get("slug", ""), _kelimeler(metin)))
    return rows


def kuyruk_indeksi(pool, log):
    """Mevcut tipli havuz kayıtları + tamamlanmış sorgu kimlikleri."""
    rows, sluglar = [], set()
    for e in pool:
        # Bu aracın kendi atadığı tipler kuyruk sayılmaz; yeniden değerlendirilir.
        if e.get("tip_onerisi") and not e.get("siniflandirma"):
            rows.append((str(e.get("sorgu") or ""), _kelimeler(e.get("sorgu"))))
    for item in (log or {}).get("done") or []:
        if isinstance(item, str):
            parca = item.split(":")
            if len(parca) >= 4 and parca[-1]:
                sluglar.add(parca[-1])
        elif isinstance(item, dict):
            anahtar = str(item.get("anahtar") or "")
            parca = anahtar.split(":")
            if len(parca) >= 4 and parca[-1]:
                sluglar.add(parca[-1])
            elif item.get("slug"):
                sluglar.add(str(item["slug"]))
    for m in (log or {}).get("makaleler") or []:
        if isinstance(m, dict) and m.get("slug"):
            sluglar.add(str(m["slug"]))
    return rows, sluglar


def urun_sayilari(products, categories):
    out = {}
    for c in categories:
        for s in c.get("subcategories", []):
            out[(c["id"], s["id"])] = len(
                urun_denetim.alt_kategori_urunleri(products, c["id"], s["id"]))
    return out


def _makale_eslesmesi(sorgu, slug, makaleler):
    for dosya, mslug, kelimeler in makaleler:
        if slug and slug == mslug:
            return dosya
        if _kapsar(_kelimeler(sorgu), kelimeler):
            return dosya
    return ""


def _kuyruk_eslesmesi(sorgu, slug, kuyruk, kuyruk_sluglar):
    if slug and slug in kuyruk_sluglar:
        return "tamamlanmış kayıt"
    q = _kelimeler(sorgu)
    for k_sorgu, k_kelimeler in kuyruk:
        if _kapsar(q, k_kelimeler):
            return k_sorgu
    return ""


def siniflandir(pool, categories, products, articles_dir=ARTICLES, log=None):
    """Havuzu yerinde sınıflandırır; özet rapor döndürür. Dosya yazmaz."""
    cat_by_id = {c["id"]: c for c in categories}
    sub_adi = {
        (c["id"], s["id"]): s["name"]
        for c in categories for s in c.get("subcategories", [])
    }
    makaleler = makale_indeksi(articles_dir)
    kuyruk, kuyruk_sluglar = kuyruk_indeksi(pool, log)
    urun = urun_sayilari(products, categories)
    rapor = {
        "toplam": len(pool),
        "islenen": 0,
        "dokunulmayan": 0,
        "durum": Counter(),
        "tip": Counter(),
        "elendi": Counter(),
        "incelenecek": Counter(),
        "yinelenen": Counter(),
        "ornek": [],
    }
    kabul_edilen = defaultdict(list)  # (kategori, alt) -> kabul edilen sorgular

    # Kendi katmanımızı baştan değerlendir: ham tipi geri yükle. Böylece aynı
    # havuz üzerinde ikinci çalıştırma aynı sonucu verir.
    for e in pool:
        s = e.get("siniflandirma")
        if isinstance(s, dict):
            if "ham_tip_onerisi" not in s:
                s["ham_tip_onerisi"] = None  # ilk sürüm yalnızca None kayıtları işledi
            e["tip_onerisi"] = s["ham_tip_onerisi"]

    for e in pool:
        if e.get("tip_onerisi") and not e.get("siniflandirma"):
            rapor["dokunulmayan"] += 1
            continue
        rapor["islenen"] += 1
        ham_tip = e.get("tip_onerisi")
        sorgu = re.sub(r"\s+", " ", str(e.get("sorgu") or "")).strip()
        cat, sub = str(e.get("kategori") or "").strip(), str(e.get("alt") or "").strip()
        durum, tip, neden, eslesen, urun_sayisi = "uygun", None, "", "", 0
        slug = _slug(sorgu)

        if not sorgu or not cat or not sub:
            durum, neden = "elendi", "eksik alan"
        elif cat not in cat_by_id or (cat, sub) not in sub_adi:
            durum, neden = "elendi", "bilinmeyen kategori/alt kategori"
        else:
            neden = elenme_nedeni(sorgu)
            if neden:
                durum = "elendi"
            elif BASKA_BAGLAM.search(sorgu):
                durum, neden = "incelenecek", "başka bağlam (inceleme)"
            elif GENEL_YORUM.search(sorgu):
                durum, neden = "incelenecek", "genel yorum/gelir sorusu"
            elif not _ortak(_kelimeler(sorgu), _kelimeler(cat_by_id[cat]["name"] + " " + sub_adi[(cat, sub)])):
                durum, neden = "elendi", "kategori/alt kategoriyle ilgisiz"
            else:
                eslesen = _makale_eslesmesi(sorgu, slug, makaleler)
                if eslesen:
                    durum, neden = "yinelenen", "mevcut makale"
                else:
                    eslesen = _kuyruk_eslesmesi(sorgu, slug, kuyruk, kuyruk_sluglar)
                    if eslesen:
                        durum, neden = "yinelenen", "mevcut kuyruk"
                if durum == "uygun":
                    tip = tip_belirle(sorgu)
                    urun_sayisi = urun.get((cat, sub), 0)
                    if not tip:
                        durum, neden = "incelenecek", "tip sinyali yok"
                    else:
                        gerekli = gerekli_urun(tip)
                        if urun_sayisi < gerekli:
                            durum = "incelenecek"
                            neden = f"ürün eşiği ({urun_sayisi}/{gerekli})"
                        else:
                            q = _kelimeler(sorgu)
                            for onceki in kabul_edilen[(cat, sub)]:
                                if _jaccard(q, onceki) >= 0.7:
                                    durum, neden = "yinelenen", "yakın niyet"
                                    eslesen = "yakın niyet"
                                    break

        sinif = {
            "durum": durum, "tip": tip, "neden": neden, "urun": urun_sayisi,
            "ham_tip_onerisi": ham_tip,
        }
        if eslesen:
            sinif["eslesen"] = str(eslesen)
        e["siniflandirma"] = sinif
        if durum == "uygun":
            e["tip_onerisi"] = tip
            kabul_edilen[(cat, sub)].append(_kelimeler(sorgu))

        rapor["durum"][durum] += 1
        if tip:
            rapor["tip"][tip] += 1
        if durum == "elendi":
            rapor["elendi"][neden] += 1
        elif durum == "incelenecek":
            rapor["incelenecek"][neden] += 1
        elif durum == "yinelenen":
            rapor["yinelenen"][neden] += 1
        if durum == "uygun" and len(rapor["ornek"]) < 15:
            rapor["ornek"].append((tip, sorgu, cat, sub, urun_sayisi))
    return rapor


def _yaz(pool, path=POOL_PATH):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(pool, f, ensure_ascii=False, indent=1)


def rapor_bas(rapor, yazildi=False):
    print("Havuz sınıflandırma" + (" (yazıldı)" if yazildi else " (kuru çalışma)"))
    print(f"  toplam: {rapor['toplam']}  |  işlenen: {rapor['islenen']}"
          f"  |  dokunulmayan (zaten tipli): {rapor['dokunulmayan']}")
    for durum in ("uygun", "yinelenen", "incelenecek", "elendi"):
        print(f"  {durum}: {rapor['durum'].get(durum, 0)}")
    print("  tipler: " + ", ".join(f"{k}={v}" for k, v in rapor["tip"].most_common()))
    for ad, anahtar in (("elendi", "elendi"), ("incelenecek", "incelenecek"), ("yinelenen", "yinelenen")):
        if rapor[anahtar]:
            print(f"  {ad} nedenleri: " + ", ".join(f"{k}={v}" for k, v in rapor[anahtar].most_common()))
    if rapor["ornek"]:
        print("  ilk uygun konular:")
        for tip, sorgu, cat, sub, urun in rapor["ornek"]:
            print(f"    [{tip}] {sorgu}  ({cat}/{sub}, ürün {urun})")


def main():
    ap = argparse.ArgumentParser(description="Konu havuzu ön eleme ve sınıflandırma")
    ap.add_argument("--yaz", action="store_true", help="siniflandirma alanlarını konu_havuzu.json'a yaz")
    ap.add_argument("--json", action="store_true", help="özet raporu JSON bas")
    a = ap.parse_args()

    with open(POOL_PATH, encoding="utf-8") as f:
        pool = json.load(f)
    with open(CATEGORIES_PATH, encoding="utf-8") as f:
        categories = json.load(f)
    products = urun_denetim.yukle(PRODUCTS_PATH)
    log = {}
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, encoding="utf-8") as f:
            log = json.load(f)

    rapor = siniflandir(pool, categories, products, ARTICLES, log)
    if a.yaz:
        _yaz(pool)
    if a.json:
        print(json.dumps({
            "toplam": rapor["toplam"], "islenen": rapor["islenen"],
            "dokunulmayan": rapor["dokunulmayan"], "durum": dict(rapor["durum"]),
            "tip": dict(rapor["tip"]), "elendi": dict(rapor["elendi"]),
            "incelenecek": dict(rapor["incelenecek"]), "yinelenen": dict(rapor["yinelenen"]),
            "ornek": rapor["ornek"],
        }, ensure_ascii=False, indent=1))
    else:
        rapor_bas(rapor, a.yaz)


if __name__ == "__main__":
    main()
