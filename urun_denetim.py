#!/usr/bin/env python3
"""Ürün verisi doğrulama ve tekilleştirme.

content/products.json kategori → alt kategori → ürün listesi biçimindedir. Aynı
ürün birden fazla listede görünebilir (kategori ve alt kategori bağlantıları).
Bu araç aynı kimlikli kayıtları tek bir tutarlı içeriğe indirger, bağlantıları
korur ve çelişkileri sessizce yutmak yerine raporlar.

  python urun_denetim.py             # doğrula, raporla (dosya yazmaz)
  python urun_denetim.py --duzelt    # çelişkili kopyaları birleştir, sonra doğrula
  python urun_denetim.py --json      # raporu JSON olarak bas

Çıkış kodu: hata varsa 1, yalnızca uyarı varsa 0.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(BASE, "content")
PRODUCTS_PATH = os.path.join(CONTENT, "products.json")
CATEGORIES_PATH = os.path.join(CONTENT, "categories.json")
ARTICLES = os.path.join(CONTENT, "articles")

ZORUNLU = ("id", "name", "desc", "query", "network")
LISTE_ALANLARI = ("pros", "cons", "images")
ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")
URL_RE = re.compile(r"^https?://[^\s]+$")
DOGRULAMA_DURUMLARI = {"dogrulanmis", "incelenecek", "devre_disi"}
TARIH_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
AMAZON_DP_RE = re.compile(
    r"^https://(?:www\.)?amazon\.com(?:\.tr)?(?:/[^\s]*)?/dp/([A-Z0-9]{10})(?:[/?#]|$)",
    re.I,
)
# _ek, categories.json'da olmayan ama ürüne `alt` alanıyla bağlanan ek listedir.
EK_LISTE = "_ek"
BUCKET_ALANLARI = {"alt"}


class UrunVerisiHatasi(Exception):
    """Ürün verisi yayın için güvenli değil."""


def yukle(yol=PRODUCTS_PATH):
    with open(yol, encoding="utf-8") as f:
        return json.load(f)


def kaydet(products, yol=PRODUCTS_PATH):
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
        f.write("\n")


def iter_kayitlar(products):
    """(kategori, alt kategori, ürün) üçlüleri; bucket sırası korunur."""
    for cat_id, subs in (products or {}).items():
        for sub_id, items in subs.items():
            for rec in items or []:
                if isinstance(rec, dict):
                    yield cat_id, sub_id, rec


def grupla(products):
    """id -> [(kategori, alt kategori, kayıt), ...]"""
    out = defaultdict(list)
    for cat, sub, rec in iter_kayitlar(products):
        rid = str(rec.get("id") or "").strip()
        if rid:
            out[rid].append((cat, sub, rec))
    return out


def _bos(deger):
    if deger is None:
        return True
    if isinstance(deger, str):
        return not deger.strip()
    if isinstance(deger, (list, dict)):
        return not deger
    return False


def _govde(rec):
    """Bucket'a özgü alanları (alt) çıkarılmış kayıt; karşılaştırma için."""
    return {k: v for k, v in rec.items() if k not in BUCKET_ALANLARI}


def _kanonik_anahtar(rec):
    """En zengin kaydı deterministik seç: ASIN, dolu alan, açıklama uzunluğu."""
    dolu = sum(1 for k, v in rec.items() if not _bos(v))
    return (
        0 if not _bos(rec.get("asin")) else -1,
        -dolu,
        -len(str(rec.get("desc") or "")),
        -len(str(rec.get("name") or "")),
        json.dumps(_govde(rec), ensure_ascii=False, sort_keys=True),
    )


def gecerli_mi(rec):
    """Kayıt zorunlu alanları ve biçimleriyle birlikte kullanılabilir mi."""
    if not isinstance(rec, dict):
        return False
    for alan in ZORUNLU:
        if _bos(rec.get(alan)):
            return False
    for alan in LISTE_ALANLARI:
        if alan in rec and not isinstance(rec[alan], list):
            return False
    asin = re.sub(r"[^A-Za-z0-9]", "", str(rec.get("asin") or "")).upper()
    if asin and not ASIN_RE.match(asin):
        return False
    for alan in ("url", "amazon_url", "image"):
        deger = str(rec.get(alan) or "").strip()
        if deger and not deger.startswith("data:image/") and not URL_RE.match(deger):
            return False
    return True


def dogrulama_durumu(rec):
    """Kanıt alanı yoksa ürün gerçek kabul edilmez; incelemede kalır."""
    dogrulama = rec.get("dogrulama") if isinstance(rec, dict) else None
    if not isinstance(dogrulama, dict):
        return "incelenecek"
    durum = str(dogrulama.get("durum") or "").strip()
    return durum if durum in DOGRULAMA_DURUMLARI else "incelenecek"


def dogrulanmis_mi(rec):
    """Gerçek ürün kanıtı: ASIN tek başına veya arama URL'si yeterli değildir."""
    if not gecerli_mi(rec) or dogrulama_durumu(rec) != "dogrulanmis":
        return False
    d = rec["dogrulama"]
    tarih = str(d.get("tarih") or "").strip()
    kaynak = str(d.get("kaynak_url") or "").strip()
    yontem = str(d.get("yontem") or "").strip()
    if not TARIH_RE.match(tarih) or not URL_RE.match(kaynak) or not yontem:
        return False
    try:
        date.fromisoformat(tarih)
    except ValueError:
        return False
    net = rec.get("network", "amazon_tr")
    if net in ("amazon_tr", "amazon"):
        asin = re.sub(r"[^A-Za-z0-9]", "", str(rec.get("asin") or "")).upper()
        m = AMAZON_DP_RE.match(kaynak)
        if not ASIN_RE.match(asin) or not m or m.group(1).upper() != asin:
            return False
        if net == "amazon_tr" and "amazon.com.tr/" not in kaynak:
            return False
    return True


def dogrulama_isaretle(products, rid, asin, kaynak_url, tarih, yontem="manuel"):
    """İnsan tarafından bulunan gerçek ürün sayfasını bütün kopyalara işle."""
    rows = grupla(products).get(rid) or []
    if not rows:
        raise UrunVerisiHatasi(f"Ürün kimliği bulunamadı: {rid}")
    asin = re.sub(r"[^A-Za-z0-9]", "", str(asin or "")).upper()
    dogrulama = {"durum": "dogrulanmis", "tarih": tarih,
                 "kaynak_url": kaynak_url.strip(), "yontem": yontem.strip()}
    aday = dict(rows[0][2], asin=asin, amazon_url=kaynak_url.strip(), dogrulama=dogrulama)
    if not dogrulanmis_mi(aday):
        raise UrunVerisiHatasi("Geçerli ASIN, aynı ASIN'li doğrudan Amazon /dp/ URL'si, ISO tarih ve yöntem gerekli")
    for _, _, rec in rows:
        rec["asin"] = asin
        rec["amazon_url"] = kaynak_url.strip()
        rec["dogrulama"] = dict(dogrulama)
    return len(rows)


def devre_disi_isaretle(products, rid, neden="ürün doğrulanamadı"):
    """Kaydı silmeden yeni üretimden çıkar."""
    rows = grupla(products).get(rid) or []
    if not rows:
        raise UrunVerisiHatasi(f"Ürün kimliği bulunamadı: {rid}")
    for _, _, rec in rows:
        rec["dogrulama"] = {"durum": "devre_disi", "neden": neden}
    return len(rows)


def birlestir(kayitlar):
    """Aynı id'nin kopyalarını tek kayda indir; çelişen değerleri ayrıca döndür.

    Boş alan hiçbir zaman dolu alanın üstüne yazılmaz. Skaler ve liste
    alanlarında en zengin kayıt kazanır; kaybedilen alternatifler raporlanır.
    """
    if not kayitlar:
        return {}, {}
    temel = sorted(kayitlar, key=_kanonik_anahtar)[0]
    birlesik = {k: v for k, v in temel.items() if k not in BUCKET_ALANLARI}
    celiskiler = defaultdict(list)
    for rec in kayitlar:
        if rec is temel:
            continue
        for alan, deger in rec.items():
            if alan in BUCKET_ALANLARI or _bos(deger):
                continue
            if _bos(birlesik.get(alan)):
                birlesik[alan] = deger
            elif deger != birlesik[alan]:
                if deger not in celiskiler[alan]:
                    celiskiler[alan].append(deger)
    return birlesik, dict(celiskiler)


def _ayni(recs):
    return len({json.dumps(_govde(r), ensure_ascii=False, sort_keys=True) for r in recs}) == 1


def urun_haritasi(products):
    """id -> tek kayıt. Çelişkili kopya varsa sessizce seçmez, hata verir.

    Build ve üretim hatları bu haritayı kullanır; böylece "ilk kayıt kazanır"
    davranışı yayına sızamaz.
    """
    harita, sorunlar = {}, []
    for rid, rows in grupla(products).items():
        recs = [r for _, _, r in rows]
        if _ayni(recs):
            harita[rid] = _govde(recs[0])
            continue
        birlesik, celiskiler = birlestir(recs)
        harita[rid] = birlesik
        alanlar = ", ".join(sorted(celiskiler))
        sorunlar.append(f"{rid} ({alanlar})")
    if sorunlar:
        raise UrunVerisiHatasi(
            f"{len(sorunlar)} ürün kimliğinde çelişkili kopya var: "
            + "; ".join(sorunlar[:8])
            + (" …" if len(sorunlar) > 8 else "")
            + ". `python urun_denetim.py --duzelt` ile birleştir.")
    return harita


def gecerli_urunler(products, cat=None, sub=None):
    """Doğrulanmış, tekilleştirilmiş ürün listesi. Üç ürün kuralı bunu sayar."""
    if cat is not None and sub is not None:
        return alt_kategori_urunleri(products, cat, sub)
    if cat is not None:
        subs = products.get(cat, {}) or {}
    else:
        subs = products or {}
    gorulen, out = set(), []
    for sub_id, items in subs.items():
        for rec in items or []:
            rid = str(rec.get("id") or "").strip()
            if not rid or rid in gorulen:
                continue
            row = rec if sub_id != EK_LISTE else {**rec, "alt": rec.get("alt") or sub}
            if dogrulanmis_mi(row):
                gorulen.add(rid)
                out.append(row)
    return out


def alt_kategori_urunleri(products, cat, sub):
    """Bir alt kategorinin gerçek ürünleri: kendi listesi + `alt` eşleşen _ek kayıtları."""
    kat = products.get(cat, {}) or {}
    havuz = list(kat.get(sub, []) or []) + [
        rec for rec in (kat.get(EK_LISTE) or []) if rec.get("alt") == sub
    ]
    gorulen, out = set(), []
    for rec in havuz:
        rid = str(rec.get("id") or "").strip()
        if not rid or rid in gorulen or not dogrulanmis_mi(rec):
            continue
        gorulen.add(rid)
        out.append(rec)
    return out


def makale_verileri(articles_dir=ARTICLES):
    """Makale frontmatter'ından kategori/alt kategori/aff id'leri."""
    out = []
    if not os.path.isdir(articles_dir):
        return out
    for fn in sorted(os.listdir(articles_dir)):
        if not fn.endswith(".md"):
            continue
        with open(os.path.join(articles_dir, fn), encoding="utf-8") as f:
            text = f.read()
        meta = {}
        if text.startswith("---"):
            head = text.split("---", 2)[1]
            for line in head.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip('"').strip("'")
        out.append({
            "dosya": fn,
            "slug": fn[:-3],
            "baslik": meta.get("title", ""),
            "odak": meta.get("focus_keyword", ""),
            "kategori": meta.get("category", ""),
            "alt": meta.get("subcategory", ""),
            "starter": meta.get("starter_product", ""),
            "aff": set(re.findall(r"aff://([A-Za-z0-9_-]+)", text)),
        })
    return out


def dogrula(products, categories, articles_dir=ARTICLES):
    """Yapısal doğrulama raporu. `hatalar` boşsa veri yayın için güvenli."""
    hatalar, uyarilar, rapor = [], [], {}
    recs = list(iter_kayitlar(products))
    gruplar = grupla(products)
    rapor["toplam_kayit"] = len(recs)
    rapor["benzersiz_id"] = len(gruplar)

    tam_ayni, celiskili = [], []
    for rid, rows in gruplar.items():
        if len(rows) < 2:
            continue
        liste = [r for _, _, r in rows]
        (tam_ayni if _ayni(liste) else celiskili).append(rid)
    rapor["mukerrer"] = {
        "ayni": sorted(tam_ayni),
        "celiskili": sorted(celiskili),
        "detay": {},
    }
    for rid in sorted(celiskili):
        _, celiskiler = birlestir([r for _, _, r in gruplar[rid]])
        rapor["mukerrer"]["detay"][rid] = sorted(celiskiler)
    if celiskili:
        hatalar.append(f"{len(celiskili)} kimlikte çelişkili kopya: {', '.join(sorted(celiskili)[:6])}")

    eksik = [(c, s, r.get("id")) for c, s, r in recs
             if any(_bos(r.get(a)) for a in ZORUNLU)]
    rapor["zorunlu_eksik"] = eksik
    if eksik:
        hatalar.append(f"{len(eksik)} kayıtta zorunlu alan eksik")
    marksiz = sorted({r.get("id") for _, _, r in recs if _bos(r.get("brand"))})
    rapor["brandsiz"] = marksiz
    if marksiz:
        uyarilar.append(f"{len(marksiz)} üründe marka alanı boş (uydurulmadı, arama linki kullanılır)")

    asin_var, asin_gecersiz, asin_haritasi = 0, [], defaultdict(set)
    url_gecersiz, url_sayisi = [], 0
    for c, s, r in recs:
        ham = str(r.get("asin") or "").strip()
        if ham:
            asin_var += 1
            norm = re.sub(r"[^A-Za-z0-9]", "", ham).upper()
            if ASIN_RE.match(norm):
                asin_haritasi[norm].add(r.get("id"))
            else:
                asin_gecersiz.append((r.get("id"), ham))
        for alan in ("url", "amazon_url"):
            deger = str(r.get(alan) or "").strip()
            if not deger:
                continue
            url_sayisi += 1
            if not URL_RE.match(deger):
                url_gecersiz.append((r.get("id"), alan, deger))
    rapor["asin"] = {"var": asin_var, "yok": len(recs) - asin_var, "gecersiz": asin_gecersiz}
    rapor["url"] = {"sayi": url_sayisi, "gecersiz": url_gecersiz}
    rapor["ayni_asin_farkli_id"] = {a: sorted(v) for a, v in asin_haritasi.items() if len(v) > 1}
    if asin_gecersiz:
        hatalar.append(f"{len(asin_gecersiz)} geçersiz ASIN")
    if url_gecersiz:
        hatalar.append(f"{len(url_gecersiz)} geçersiz URL")
    if rapor["ayni_asin_farkli_id"]:
        uyarilar.append(f"{len(rapor['ayni_asin_farkli_id'])} ASIN farklı kimliklerle kullanılıyor")

    cat_by_id = {c["id"]: c for c in categories}
    sub_by_cat = {c["id"]: {s["id"] for s in c.get("subcategories", [])} for c in categories}
    bilinmeyen_kat, bilinmeyen_alt = [], []
    for cat, sub, rec in iter_kayitlar(products):
        if cat not in cat_by_id:
            bilinmeyen_kat.append(cat)
            continue
        if sub == "_main":
            continue
        if sub == EK_LISTE:
            if rec.get("alt") not in sub_by_cat[cat]:
                bilinmeyen_alt.append((cat, sub, rec.get("id"), "geçersiz alt"))
        elif sub not in sub_by_cat[cat]:
            bilinmeyen_alt.append((cat, sub, rec.get("id"), ""))
    rapor["kategori_hata"] = sorted(set(bilinmeyen_kat))
    rapor["alt_kategori_hata"] = bilinmeyen_alt
    if bilinmeyen_kat:
        hatalar.append(f"Bilinmeyen kategori: {', '.join(sorted(set(bilinmeyen_kat)))}")
    if bilinmeyen_alt:
        hatalar.append(f"{len(bilinmeyen_alt)} kayıt bilinmeyen alt kategoriye bağlı")

    ids = set(gruplar)
    makaleler = makale_verileri(articles_dir)
    kullanilan, cozulmeyen = set(), []
    for m in makaleler:
        for pid in m["aff"] | ({m["starter"]} if m["starter"] else set()):
            kullanilan.add(pid)
            if pid not in ids:
                cozulmeyen.append((m["dosya"], pid))
    rapor["aff"] = {"kullanilan": len(kullanilan), "cozulemeyen": cozulmeyen}
    if cozulmeyen:
        hatalar.append(f"{len(cozulmeyen)} aff:// kimliği ürün verisinde yok")

    durumlar = Counter()
    hatali_kanit = []
    for rid, rows in gruplar.items():
        rec = rows[0][2]
        durum = dogrulama_durumu(rec)
        durumlar[durum] += 1
        if durum == "dogrulanmis" and not dogrulanmis_mi(rec):
            hatali_kanit.append(rid)
    rapor["dogrulama"] = {k: durumlar[k] for k in ("dogrulanmis", "incelenecek", "devre_disi")}
    rapor["hatali_kanit"] = sorted(hatali_kanit)
    if hatali_kanit:
        uyarilar.append(f"{len(hatali_kanit)} üründe doğrulama kanıtı geçersiz")

    riskli_makaleler = []
    for m in makaleler:
        dogrulanmayan = sorted(
            pid for pid in m["aff"] | ({m["starter"]} if m["starter"] else set())
            if pid in gruplar and not dogrulanmis_mi(gruplar[pid][0][2])
        )
        if dogrulanmayan:
            riskli_makaleler.append({"dosya": m["dosya"], "urunler": dogrulanmayan})
    rapor["makale_dogrulama"] = {"riskli": riskli_makaleler, "riskli_sayi": len(riskli_makaleler)}

    rapor["gecerli_urun"] = {
        f"{c}/{s}": len(gecerli_urunler(products, c, s))
        for c, s in {(c, s) for c, s, _ in recs}
        if s != EK_LISTE
    }
    rapor["hatalar"] = hatalar
    rapor["uyarilar"] = uyarilar
    return rapor


def duzelt(products):
    """Çelişkili kopyaları tek tutarlı içeriğe indir; liste bağlantılarını koru."""
    degisim = {"gruplar": 0, "kayit": 0, "kaldirilan": 0, "celiskiler": {}}
    for rid, rows in grupla(products).items():
        recs = [r for _, _, r in rows]
        if _ayni(recs):
            continue
        birlesik, celiskiler = birlestir(recs)
        degisim["gruplar"] += 1
        degisim["celiskiler"][rid] = sorted(celiskiler)
        for _, sub, rec in rows:
            yeni = dict(birlesik)
            if sub == EK_LISTE or rec.get("alt"):
                yeni["alt"] = rec.get("alt") or sub
            if yeni != rec:
                degerler = [k for k in set(rec) | set(yeni) if rec.get(k) != yeni.get(k)]
                _yerine_koy(rec, yeni)
                degisim["kayit"] += 1
                degisim.setdefault("alanlar", Counter()).update(degerler)
    for subs in products.values():
        for sub_id, items in subs.items():
            if not isinstance(items, list):
                continue
            gorulen, temiz = set(), []
            for rec in items:
                rid = str(rec.get("id") or "").strip()
                if rid and rid in gorulen:
                    degisim["kaldirilan"] += 1
                    continue
                gorulen.add(rid)
                temiz.append(rec)
            subs[sub_id] = temiz
    return products, degisim


def _yerine_koy(hedef, kaynak):
    """Liste nesnesini yerinde güncelle (referanslar korunur)."""
    hedef.clear()
    hedef.update(kaynak)


def _rapor_bas(rapor):
    print("Ürün verisi denetimi")
    print(f"  kayıt: {rapor['toplam_kayit']}  |  benzersiz id: {rapor['benzersiz_id']}")
    m = rapor["mukerrer"]
    print(f"  aynı içerikli kopya grubu: {len(m['ayni'])}"
          f"  |  çelişkili kopya grubu: {len(m['celiskili'])}")
    for rid, alanlar in list(m["detay"].items())[:10]:
        print(f"    ! {rid}: çelişen alanlar {', '.join(alanlar)}")
    a = rapor["asin"]
    print(f"  ASIN: {a['var']} dolu, {a['yok']} yok (arama linkine düşer), {len(a['gecersiz'])} geçersiz")
    if rapor["ayni_asin_farkli_id"]:
        print(f"  ! aynı ASIN farklı id: {len(rapor['ayni_asin_farkli_id'])}")
    print(f"  URL: {rapor['url']['sayi']} alan, {len(rapor['url']['gecersiz'])} geçersiz")
    print(f"  zorunlu alan eksiği: {len(rapor['zorunlu_eksik'])}  |  markasız: {len(rapor['brandsiz'])}")
    print(f"  bilinmeyen kategori: {len(rapor['kategori_hata'])}  |  "
          f"bilinmeyen alt kategori: {len(rapor['alt_kategori_hata'])}")
    print(f"  makalelerde aff:// kimliği: {rapor['aff']['kullanilan']}  |  "
          f"çözülemeyen: {len(rapor['aff']['cozulemeyen'])}")
    d = rapor["dogrulama"]
    print(f"  gerçek ürün doğrulaması: {d['dogrulanmis']} doğrulanmış | "
          f"{d['incelenecek']} incelemede | {d['devre_disi']} devre dışı")
    print(f"  doğrulanmamış ürün içeren mevcut makale: {rapor['makale_dogrulama']['riskli_sayi']}")
    for h in rapor["hatalar"]:
        print(f"  HATA: {h}")
    for u in rapor["uyarilar"]:
        print(f"  uyarı: {u}")


def main():
    ap = argparse.ArgumentParser(description="Ürün verisi doğrulama / tekilleştirme")
    ap.add_argument("--duzelt", action="store_true", help="çelişkili kopyaları birleştirip dosyayı yaz")
    ap.add_argument("--json", action="store_true", help="raporu JSON bas")
    ap.add_argument("--dogrula-urun", metavar="URUN_ID", help="gerçek ürün sayfası kontrol edilen kimlik")
    ap.add_argument("--asin", help="ürünün doğrulanmış ASIN'i")
    ap.add_argument("--urun-url", help="aynı ASIN'li doğrudan Amazon /dp/ adresi")
    ap.add_argument("--tarih", default=date.today().isoformat(), help="doğrulama tarihi (YYYY-MM-DD)")
    ap.add_argument("--yontem", default="manuel", help="doğrulama yöntemi")
    ap.add_argument("--devre-disi", metavar="URUN_ID", help="ürünü silmeden yeni üretimden çıkar")
    ap.add_argument("--neden", default="ürün doğrulanamadı", help="devre dışı bırakma nedeni")
    a = ap.parse_args()
    if a.dogrula_urun and a.devre_disi:
        ap.error("--dogrula-urun ve --devre-disi birlikte kullanılamaz")
    if a.dogrula_urun and not (a.asin and a.urun_url):
        ap.error("--dogrula-urun için --asin ve --urun-url zorunlu")

    products = yukle()
    categories = yukle(CATEGORIES_PATH)

    try:
        if a.dogrula_urun:
            n = dogrulama_isaretle(products, a.dogrula_urun, a.asin, a.urun_url, a.tarih, a.yontem)
            kaydet(products)
            print(f"Doğrulama işlendi: {a.dogrula_urun} ({n} kopya)")
        if a.devre_disi:
            n = devre_disi_isaretle(products, a.devre_disi, a.neden)
            kaydet(products)
            print(f"Devre dışı bırakıldı: {a.devre_disi} ({n} kopya)")
    except UrunVerisiHatasi as e:
        ap.error(str(e))

    if a.duzelt:
        products, degisim = duzelt(products)
        kaydet(products)
        print(f"Birleştirilen grup: {degisim['gruplar']}  |  güncellenen kayıt: {degisim['kayit']}"
              f"  |  kaldırılan mükerrer: {degisim['kaldirilan']}")
        if degisim.get("alanlar"):
            print("  değişen alanlar: " + ", ".join(f"{k}={v}" for k, v in degisim["alanlar"].most_common()))
        for rid, alanlar in list(degisim["celiskiler"].items())[:10]:
            print(f"    {rid}: {', '.join(alanlar)} (en zengin kayıt korundu)")

    rapor = dogrula(products, categories)
    if a.json:
        print(json.dumps(rapor, ensure_ascii=False, indent=1))
    else:
        _rapor_bas(rapor)
    return 1 if rapor["hatalar"] else 0


if __name__ == "__main__":
    sys.exit(main())
