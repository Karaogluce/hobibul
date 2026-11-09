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

# Hobi karşılığı sabit. Mutfak, mama ve genel elektronik bu akışa girmez.
# Yollar Amazon.com.tr çok satanlar menüsündeki alt kategorilerdir.
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
        "id": "kutu-oyun",
        "yol": "/gp/bestsellers/toys/12923340031",
        "ad": "Kutu Oyunu",
        "cat": "koleksiyon",
        "sub": "masaustu-oyun",
        "ipucu": [["oyun"], ["kutu"], ["monopoly"], ["tabu"]],
    },
    {
        "id": "puzzle",
        "yol": "/gp/bestsellers/toys/12923346031",
        "ad": "Puzzle",
        "cat": "koleksiyon",
        "sub": "puzzle",
        "ipucu": [["yapboz"], ["jigsaw"], ["puzzle"]],
        "red": ["yapıştırıcı", "çerçeve", "poster"],
    },
    {
        "id": "lego",
        "yol": "/gp/bestsellers/toys/12923347031",
        "ad": "LEGO ve model",
        "cat": "koleksiyon",
        "sub": "lego-model",
        "ipucu": [["lego"], ["yapı"], ["blok"], ["model"]],
    },
    {
        "id": "el-isi",
        "yol": "/gp/bestsellers/toys/12923343031",
        "ad": "Sanat ve El İşi",
        "cat": "el-sanatlari",
        "sub": "resim-boyama",
        "ipucu": [["boya"], ["fırça"], ["kalem"], ["tuval"], ["hobi"], ["el işi"]],
    },
    {
        "id": "muzik",
        "yol": "/gp/bestsellers/musical-instruments/21428844031",
        "ad": "Müzik aleti",
        "cat": "muzik",
        "sub": "gitar",
        "ipucu": [["gitar"], ["tel"], ["amfi"], ["pena"], ["akort"]],
    },
    {
        "id": "bahce-alet",
        "yol": "/gp/bestsellers/garden/21440344031",
        "ad": "Bahçe Aleti",
        "cat": "bahce-bitki",
        "sub": "bahcecilik",
        "ipucu": [["makas"], ["hortum"], ["budama"], ["kürek"], ["testere"], ["tırpan"], ["sulama"], ["bel"]],
    },
    {
        "id": "kamp",
        "yol": "/gp/bestsellers/sporting-goods/13484282031",
        "ad": "Kamp ve outdoor",
        "cat": "outdoor",
        "sub": "kampcilik",
        "ipucu": [["çadır"], ["uyku tulumu"], ["uyku mat"], ["yürüyüş baton"]],
        "red": ["anahtarlık", "tornavida", "şişe açacağı"],
    },
    {
        "id": "foto",
        "yol": "/gp/bestsellers/electronics/13709883031",
        "ad": "Fotoğraf",
        "cat": "sanat",
        "sub": "fotografcilik",
        "ipucu": [["fotoğraf makinesi"], ["aynasız"], ["drone"], ["eos"], ["alpha"]],
        "red": ["güvenlik", "temizlik", "microsd", "kulaklık", "kılıf"],
    },
)

HAFTA_TAVAN = 4


def hafta_kimligi(gun=None):
    gun = gun or date.today()
    iso = gun.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def liste_cek(oturum, tanim, limit=3):
    """Alt kategoriden ilk ürünler. İpucu uymayan ad (termos, mama) yazıya girmez."""
    url = amazon_tr.HOST + tanim["yol"]
    html, _final = oturum.getir(url)
    ham = amazon_tr.cok_satanlari_ayikla(html, limit=15)
    ipucu = tanim.get("ipucu") or []
    red = tuple(amazon_tr.fold(x) for x in (tanim.get("red") or ()))
    if ipucu:
        urunler = []
        for u in ham:
            if not amazon_tr.tip_uyuyor(u["ad"], ipucu):
                continue
            if any(k in amazon_tr.fold(u["ad"]) for k in red):
                continue
            urunler.append(u)
    else:
        urunler = list(ham)
    urunler = urunler[:limit]
    if len(urunler) < (1 if tanim.get("zorunlu") else 2):
        raise amazon_tr.AmazonEngel(url, "kategori uyumsuz" if ipucu else "liste bos")
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


_AY = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
       "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def tarih_yaz(iso):
    yil, ay, gun = (int(x) for x in str(iso).split("-"))
    return f"{gun} {_AY[ay]} {yil}"


def yazi_metni(liste, hafta, gun_yazi):
    """Yalnızca listedeki ad, sıra ve yazarı kullanır. Ölçü ve fiyat yazılmaz."""
    ad = liste["ad"]
    urunler = liste["urunler"][:3]
    if liste["id"] == "kitap":
        giris = (
            f"Amazon.com.tr kitap çok satanlar listesinin {gun_yazi} haftası çekiminde "
            f"ilk üç sıra şöyle duruyor. Sıra haftalık değişir. Burada yalnızca bu çekimde "
            f"görünen ad, yazar satırı ve ürün bağlantısı var."
        )
    else:
        giris = (
            f"Amazon.com.tr {ad.lower()} çok satanlar sayfasının {gun_yazi} çekiminde, "
            f"adı bu kategoriye uyan ilk üç kayıt aşağıda. Sayı, sayfadaki sıradır."
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
    gun_yazi = tarih_yaz(bugun)
    if liste["id"] == "kitap":
        baslik = f"Bu Haftanın En Çok Satan 3 Kitabı ({gun_yazi})"
        slug = _slug(f"bu-haftanin-en-cok-satan-kitaplari-{hafta}")
        odak = "en çok satan kitaplar"
    else:
        baslik = f"Bu Haftanın En Çok Satan 3 {liste['ad']} Ürünü ({gun_yazi})"
        slug = _slug(f"en-cok-satan-{liste['id']}-{hafta}")
        odak = f"en çok satan {liste['ad'].lower()}"
    ozet_ad = ", ".join(u["ad"] for u in urunler[:3])
    aciklama = f"{gun_yazi} Amazon.com.tr {liste['ad'].lower()} çok satanlar: {ozet_ad}."
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
        f.write("\n".join(fm) + yazi_metni(liste, hafta, gun_yazi))
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
        if satir["id"] == "foto" and "drone" in adlar and "foto" not in adlar and "kamera" not in adlar:
            satir["cat"] = "teknoloji"
            satir["sub"] = "drone"
            satir["ad"] = "Drone"
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
