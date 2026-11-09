#!/usr/bin/env python3
"""Haftalık Amazon.com.tr çok satanlar listesi ve kısa tanıtım yazıları.

  python cok_satan.py --dry-run     # listeyi çek, yazı yazma
  python cok_satan.py --yaz         # bu haftanın en fazla 4 yazısını üret

Captcha veya 503 olursa çıkış kodu 0'dır; content/cok_satan/hata.json güncellenir.
Ürün adı ve ASIN yalnızca çekilen sayfadan gelir.
"""
import argparse
import json
import os
import re
import sys
from datetime import date, datetime

import amazon_tr
import otomatik

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(BASE, "content")
CIKTI = os.path.join(CONTENT, "cok_satan")
ARTICLES = os.path.join(CONTENT, "articles")

# Site kategorisine karşılık gelen Amazon.com.tr çok satanlar yolları.
LISTELER = (
    {
        "id": "kitap",
        "yol": "/gp/bestsellers/books",
        "ad": "Kitap",
        "cat": "yazi-edebiyat",
        "sub": "okuma",
        "zorunlu": True,
    },
    {
        "id": "oyuncak",
        "yol": "/gp/bestsellers/toys",
        "ad": "Oyuncak",
        "cat": "koleksiyon",
        "sub": "masaustu-oyun",
    },
    {
        "id": "muzik",
        "yol": "/gp/bestsellers/musical-instruments",
        "ad": "Müzik aletleri",
        "cat": "muzik",
        "sub": "gitar",
    },
    {
        "id": "bahce",
        "yol": "/gp/bestsellers/garden",
        "ad": "Bahçe",
        "cat": "bahce-bitki",
        "sub": "bahcecilik",
    },
    {
        "id": "evcil",
        "yol": "/gp/bestsellers/pet-supplies",
        "ad": "Evcil hayvan",
        "cat": "evcil-hayvan",
        "sub": "kedi-bakimi",
    },
    {
        "id": "elektronik",
        "yol": "/gp/bestsellers/electronics",
        "ad": "Elektronik",
        "cat": "teknoloji",
        "sub": "",
    },
    {
        "id": "mutfak",
        "yol": "/gp/bestsellers/kitchen",
        "ad": "Mutfak",
        "cat": "yemek-mutfak",
        "sub": "yemek-pisirme",
    },
)

HAFTA_TAVAN = 4


def hafta_kimligi(gun=None):
    gun = gun or date.today()
    iso = gun.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def liste_cek(oturum, tanim, limit=3):
    url = amazon_tr.HOST + tanim["yol"]
    html, _final = oturum.getir(url)
    urunler = amazon_tr.cok_satanlari_ayikla(html, limit=limit)
    if len(urunler) < 1:
        raise amazon_tr.AmazonEngel(url, "liste bos")
    return urunler


def _secilecek(listeler, log, bugun, tavan=HAFTA_TAVAN):
    """Kitap her hafta durur. Kalan yer, son 7 günde az yazılan kategorilere gider."""
    gecmis = otomatik.kategori_sayaclari(log, bugun)
    kitap = [l for l in listeler if l.get("zorunlu")]
    diger = [l for l in listeler if not l.get("zorunlu") and l.get("urunler")]
    diger.sort(key=lambda l: (int(gecmis.get(l["cat"], 0) or 0), l["id"]))
    sec, kullanilan = [], set()
    for liste in kitap + diger:
        if liste["cat"] in kullanilan:
            continue
        if not liste.get("urunler"):
            continue
        sec.append(liste)
        kullanilan.add(liste["cat"])
        if len(sec) >= tavan:
            break
    return sec


def _slug(metin):
    return otomatik.ym.slugify(metin)


def yazi_metni(liste, hafta):
    """Yalnızca listedeki ad, sıra ve yazarı kullanır. Ölçü ve fiyat yazılmaz."""
    ad = liste["ad"]
    urunler = liste["urunler"][:3]
    if liste["id"] == "kitap":
        giris = (
            f"Amazon.com.tr kitap çok satanlar listesinin {hafta} haftası çekiminde "
            f"ilk üç sıra şöyle duruyor. Sıra haftalık değişir. Burada yalnızca bu çekimde "
            f"görünen ad, yazar satırı ve ürün bağlantısı var."
        )
    else:
        giris = (
            f"Amazon.com.tr {ad.lower()} çok satanlar listesinin {hafta} haftası çekiminde "
            f"ilk üç ürünün adı aşağıda. Sıra, o sayfanın bu çekimdeki hali."
        )
    bloklar = [giris, ""]
    for u in urunler:
        sira = u["sira"]
        ad_u = u["ad"]
        yazar = u.get("yazar") or ""
        link = f"[{ad_u}]({u['url']})"
        if yazar:
            cumle = f"{sira}. sırada {ad_u} var. Yazar satırı {yazar}. Ürün sayfası {link}."
        else:
            cumle = f"{sira}. sırada {ad_u} var. Ürün sayfası {link}."
        bloklar.append(cumle)
        bloklar.append("")
    bloklar.append(
        "Liste, Amazon.com.tr çok satanlar sayfasının o anki sırasıdır. "
        "Ertesi hafta aynı adlar durmayabilir."
    )
    return "\n".join(bloklar).strip() + "\n"


def yazi_yaz(liste, hafta, bugun):
    urunler = liste["urunler"][:3]
    if liste["id"] == "kitap":
        baslik = f"Bu Haftanın En Çok Satan 3 Kitabı ({hafta})"
        slug = _slug(f"bu-haftanin-en-cok-satan-kitaplari-{hafta}")
        odak = "en çok satan kitaplar"
    else:
        baslik = f"Bu Haftanın En Çok Satan 3 {liste['ad']} Ürünü ({hafta})"
        slug = _slug(f"en-cok-satan-{liste['id']}-{hafta}")
        odak = f"en çok satan {liste['ad'].lower()}"
    ozet_ad = ", ".join(u["ad"] for u in urunler[:3])
    aciklama = f"{hafta} Amazon.com.tr {liste['ad'].lower()} çok satanlar: {ozet_ad}."
    if len(aciklama) > 160:
        aciklama = aciklama[:157].rsplit(" ", 1)[0] + "."
    yol = os.path.join(ARTICLES, slug + ".md")
    if os.path.exists(yol):
        return slug, False
    fm = [
        "---",
        f'title: "{baslik}"',
        f'slug: "{slug}"',
        f'category: "{liste["cat"]}"',
    ]
    if liste.get("sub"):
        fm.append(f'subcategory: "{liste["sub"]}"')
    fm += [
        f'date: "{bugun}"',
        f'updated: "{bugun}"',
        f'meta_title: "{baslik} | Hobi Bul"',
        f'meta_description: "{aciklama}"',
        f'excerpt: "{aciklama}"',
        f'focus_keyword: "{odak}"',
        'image: "/img/og-default.png"',
        f'image_alt: "{liste["ad"]} çok satanlar listesinden bir ürün"',
        'hide_plan: "true"',
        'draft: "false"',
        "---",
        "",
    ]
    os.makedirs(ARTICLES, exist_ok=True)
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(fm) + yazi_metni(liste, hafta))
    return slug, True


def calistir(yaz=False, bugun=None, oturum=None):
    bugun = bugun or date.today().isoformat()
    hafta = hafta_kimligi(datetime.strptime(bugun, "%Y-%m-%d").date())
    oturum = oturum or amazon_tr.Oturum()
    os.makedirs(CIKTI, exist_ok=True)
    kayit = {"hafta": hafta, "tarih": bugun, "listeler": [], "hatalar": []}
    for tanim in LISTELER:
        try:
            urunler = liste_cek(oturum, tanim, limit=3)
        except amazon_tr.AmazonEngel as e:
            kayit["hatalar"].append({"id": tanim["id"], "neden": e.neden, "url": e.url})
            print(f"! {tanim['id']} alınamadı ({e.neden})")
            continue
        satir = dict(tanim)
        satir["urunler"] = urunler
        adlar = " ".join(u["ad"] for u in urunler).lower()
        if satir["cat"] == "evcil-hayvan":
            if "köpek" in adlar or "kopek" in adlar:
                satir["sub"] = "kopek-bakimi"
            elif "kedi" in adlar:
                satir["sub"] = "kedi-bakimi"
            else:
                satir["sub"] = ""
        if satir["id"] == "elektronik" and "drone" not in adlar:
            satir["sub"] = ""
        kayit["listeler"].append({k: satir[k] for k in ("id", "ad", "cat", "sub", "yol", "urunler")})
        print(f"✓ {tanim['id']}: " + " | ".join(f"#{u['sira']} {u['ad']}" for u in urunler))
    yol = os.path.join(CIKTI, hafta + ".json")
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        json.dump(kayit, f, ensure_ascii=False, indent=1)
        f.write("\n")
    if kayit["hatalar"] and not kayit["listeler"]:
        with open(os.path.join(CIKTI, "hata.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump({"hafta": hafta, "tarih": bugun, "hatalar": kayit["hatalar"]}, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print("Amazon engelledi veya liste boş. Yazı üretilmedi.")
        return kayit
    log = otomatik.load_log()
    sec = _secilecek(kayit["listeler"], log, bugun)
    yazilan = []
    if yaz:
        for liste in sec:
            slug, yeni = yazi_yaz(liste, hafta, bugun)
            yazilan.append({"slug": slug, "yeni": yeni, "cat": liste["cat"]})
            print(("✓ yazıldı " if yeni else "· vardı ") + slug)
    kayit["secilen"] = [{"id": l["id"], "cat": l["cat"]} for l in sec]
    kayit["yazilan"] = yazilan
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        json.dump(kayit, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return kayit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yaz", action="store_true")
    a = ap.parse_args()
    try:
        calistir(yaz=a.yaz and not a.dry_run)
    except amazon_tr.AmazonEngel as e:
        os.makedirs(CIKTI, exist_ok=True)
        with open(os.path.join(CIKTI, "hata.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump({"neden": e.neden, "url": e.url, "tarih": date.today().isoformat()}, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(f"Amazon engeli, yumuşak çıkış: {e.neden}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
