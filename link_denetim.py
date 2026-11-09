#!/usr/bin/env python3
"""Satın alma linklerini Amazon.com.tr ürün sayfasıyla denetler.

  python link_denetim.py            # content/link_denetim.json yazar
  python link_denetim.py --uygula   # doğrulanan ASIN'i işler, Neo Troy'u kaldırır

Arama linki ve adı taşımayan sayfa bozuk sayılır. Engel (503/captcha) linki silmez.
"""
import argparse
import json
import os
import re
import sys

import amazon_tr
import build

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(BASE, "content")
ARTICLES = os.path.join(CONTENT, "articles")
RAPOR = os.path.join(CONTENT, "link_denetim.json")
OYUN = os.path.join(CONTENT, "kutu_oyunlari_tr.json")

_AFF = re.compile(r"\[([^\]]+)\]\(aff://([a-z0-9\-]+)\)")
_HTTP = re.compile(r"https?://[^\s)>\"]+")


def _yukle(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _yaz(path, data):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")


def _urunler():
    ham = _yukle(os.path.join(CONTENT, "products.json"))
    out = {}
    for _cat, subs in ham.items():
        if not isinstance(subs, dict):
            continue
        for _sub, items in subs.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict) and item.get("id"):
                    out[item["id"]] = item
    return ham, out


def _makale_aff():
    kullanilan = {}
    for fn in sorted(os.listdir(ARTICLES)):
        if not fn.endswith(".md"):
            continue
        text = open(os.path.join(ARTICLES, fn), encoding="utf-8").read()
        for _etiket, pid in _AFF.findall(text):
            kullanilan.setdefault(pid, []).append(fn[:-3])
    return kullanilan


def _sinif(url):
    u = str(url or "")
    if "neotroygames.com" in u:
        return "neo_troy"
    if "/dp/" in u and "amazon." in u:
        return "amazon_dp"
    if "amazon." in u and ("/s?" in u or "/s/" in u or "k=" in u):
        return "arama"
    if any(h in u for h in ("trendyol.com", "hepsiburada.com", "aliexpress.", "geekbuying.")):
        return "arama"
    if u.startswith("http"):
        return "diger"
    return "bos"


def denetle(oturum=None, limit=0):
    oturum = oturum or amazon_tr.Oturum(bekle=0.3)
    _ham, urunler = _urunler()
    kullanan = _makale_aff()
    kimlikler = [i for i in kullanan if i in urunler]
    if limit:
        kimlikler = kimlikler[:limit]
    rapor = {
        "tarih": __import__("datetime").date.today().isoformat(),
        "ozet": {},
        "kayitlar": [],
    }
    say = {"denetlenen": 0, "dogrulandi": 0, "bozuk": 0, "engel": 0, "neo_troy": 0}
    for n, pid in enumerate(kimlikler, 1):
        urun = urunler[pid]
        try:
            url = build.affiliate_url(urun)
        except Exception:
            url = urun.get("url") or ""
        sinif = _sinif(url)
        kayit = {
            "id": pid,
            "ad": urun.get("name") or "",
            "marka": urun.get("brand") or "",
            "url": url,
            "sinif": sinif,
            "makaleler": kullanan.get(pid) or [],
            "durum": "",
            "asin": "",
            "baslik": "",
        }
        say["denetlenen"] += 1
        if sinif == "neo_troy":
            say["neo_troy"] += 1
        if sinif == "amazon_dp":
            asin = re.search(r"/dp/([A-Z0-9]{10})", url)
            if asin:
                try:
                    baslik, _dp = amazon_tr.urun_basligi(oturum, asin.group(1))
                except amazon_tr.AmazonEngel as e:
                    kayit["durum"] = "engel"
                    kayit["neden"] = e.neden
                    say["engel"] += 1
                    rapor["kayitlar"].append(kayit)
                    continue
                kayit["baslik"] = baslik
                kayit["asin"] = asin.group(1)
                if amazon_tr.baslik_uyuyor(baslik, kayit["ad"], kayit["marka"]):
                    kayit["durum"] = "dogrulandi"
                    say["dogrulandi"] += 1
                else:
                    kayit["durum"] = "yanlis_urun"
                    say["bozuk"] += 1
                rapor["kayitlar"].append(kayit)
                continue
        try:
            bulunan = amazon_tr.urun_bul(oturum, kayit["ad"], "")
        except amazon_tr.AmazonEngel as e:
            kayit["durum"] = "engel"
            kayit["neden"] = e.neden
            say["engel"] += 1
            rapor["kayitlar"].append(kayit)
            print(f"  ! {n} {pid} engel")
            continue
        if bulunan:
            kayit["durum"] = "dogrulandi"
            kayit["asin"] = bulunan["asin"]
            kayit["baslik"] = bulunan["baslik"]
            kayit["yeni_url"] = bulunan["url"]
            say["dogrulandi"] += 1
            print(f"  ✓ {n} {pid} {bulunan['asin']}")
        else:
            kayit["durum"] = "bulunamadi" if sinif != "neo_troy" else "neo_troy_yok"
            say["bozuk"] += 1
            print(f"  – {n} {pid} yok")
        rapor["kayitlar"].append(kayit)
        if n % 15 == 0:
            rapor["ozet"] = say
            _yaz(RAPOR, rapor)
    rapor["ozet"] = say
    _yaz(RAPOR, rapor)
    print("özet", say)
    return rapor


def _neo_troy_metin(text):
    text = text.replace("[Neo Troy Games](https://neotroygames.com/)", "Türkiye vitrinindeki kayıt")
    text = re.sub(r"Neo Troy Games sitesinde", "kayıttaki ürün sayfasında", text)
    text = re.sub(r"Neo Troy'un ", "", text)
    text = re.sub(r"Neo Troy'a ", "", text)
    text = re.sub(r"Neo Troy'da ", "", text)
    text = re.sub(r"Neo Troy kaydı ", "Kayıt ", text)
    text = re.sub(r"Neo Troy sayfası ", "Ürün sayfası ", text)
    text = re.sub(r"Neo Troy, ", "", text)
    text = re.sub(r"Neo Troy ", "", text)
    text = re.sub(r"  +", " ", text)
    return text


def tekrar_bulunamayan(rapor=None):
    """Marka adı sayfa başlığında olmayan oyunları adsız sorguyla bir kez daha dener.

    Gevşek eşleşip kitap sayfasına düşen kayıtlar önce bozulur, sonra yeniden aranır.
    """
    rapor = rapor or _yukle(RAPOR)
    for kayit in rapor.get("kayitlar") or []:
        if kayit.get("durum") != "dogrulandi":
            continue
        if amazon_tr.baslik_uyuyor(kayit.get("baslik") or "", kayit.get("ad") or "", ""):
            continue
        kayit["durum"] = "bulunamadi"
        kayit["asin"] = ""
        kayit["yeni_url"] = ""
        kayit["not"] = "baslik urun adiyla uyusmadi"
    oturum = amazon_tr.Oturum(bekle=0.3)
    say = rapor.setdefault("ozet", {})
    for kayit in rapor.get("kayitlar") or []:
        if kayit.get("durum") not in ("bulunamadi", "neo_troy_yok"):
            continue
        try:
            bulunan = amazon_tr.urun_bul(oturum, kayit.get("ad") or "", "")
        except amazon_tr.AmazonEngel as e:
            kayit["durum"] = "engel"
            kayit["neden"] = e.neden
            say["engel"] = int(say.get("engel") or 0) + 1
            say["bozuk"] = max(0, int(say.get("bozuk") or 0) - 1)
            continue
        if not bulunan:
            continue
        kayit["durum"] = "dogrulandi"
        kayit["asin"] = bulunan["asin"]
        kayit["baslik"] = bulunan["baslik"]
        kayit["yeni_url"] = bulunan["url"]
        say["dogrulandi"] = int(say.get("dogrulandi") or 0) + 1
        say["bozuk"] = max(0, int(say.get("bozuk") or 0) - 1)
        print(f"  ✓ tekrar {kayit['id']} {bulunan['asin']}")
    _yaz(RAPOR, rapor)
    return rapor


def uygula(rapor=None):
    rapor = rapor or _yukle(RAPOR)
    _ham, _urun = _urunler()
    dogru = {k["id"]: k for k in rapor.get("kayitlar") or [] if k.get("durum") == "dogrulandi" and k.get("asin")}
    bozuk = {k["id"] for k in rapor.get("kayitlar") or [] if k.get("durum") in ("bulunamadi", "neo_troy_yok", "yanlis_urun")}
    degisen_urun = 0
    for _cat, subs in _ham.items():
        if not isinstance(subs, dict):
            continue
        for _sub, items in subs.items():
            if not isinstance(items, list):
                continue
            for item in items:
                pid = item.get("id")
                if pid in dogru:
                    item["asin"] = dogru[pid]["asin"]
                    item["amazon_url"] = dogru[pid].get("yeni_url") or amazon_tr.dp_url(dogru[pid]["asin"])
                    item["network"] = "amazon_tr"
                    if "neotroygames.com" in str(item.get("url") or ""):
                        item.pop("url", None)
                    desc = item.get("desc") or ""
                    item["desc"] = _neo_troy_metin(desc)
                    degisen_urun += 1
                elif pid in bozuk and "neotroygames.com" in str(item.get("url") or ""):
                    item.pop("url", None)
    _yaz(os.path.join(CONTENT, "products.json"), _ham)

    silinen_link = 0
    neo_cumle = 0
    for fn in sorted(os.listdir(ARTICLES)):
        if not fn.endswith(".md"):
            continue
        path = os.path.join(ARTICLES, fn)
        text = open(path, encoding="utf-8").read()
        yeni = text
        if "Neo Troy" in yeni or "neotroygames.com" in yeni:
            yeni = _neo_troy_metin(yeni)
            neo_cumle += 1

        def _sil(m):
            nonlocal silinen_link
            if m.group(2) in bozuk:
                silinen_link += 1
                return ""
            return m.group(0)

        yeni = _AFF.sub(_sil, yeni)
        yeni = re.sub(r"  +", " ", yeni)
        yeni = re.sub(r" +([.,])", r"\1", yeni)
        if yeni != text:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(yeni)
    oyun_yolu = OYUN
    if os.path.exists(oyun_yolu):
        data = _yukle(oyun_yolu)
        kalan = []
        for oyun in data.get("oyunlar") or []:
            pid = oyun.get("id")
            if pid in dogru:
                oyun["url"] = dogru[pid].get("yeni_url") or amazon_tr.dp_url(dogru[pid]["asin"])
                oyun["asin"] = dogru[pid]["asin"]
                oyun["ozet"] = _neo_troy_metin(oyun.get("ozet") or "")
                kalan.append(oyun)
            elif pid in bozuk:
                continue
            else:
                if "neotroygames.com" in str(oyun.get("url") or ""):
                    oyun["url"] = ""
                oyun["ozet"] = _neo_troy_metin(oyun.get("ozet") or "")
                kalan.append(oyun)
        data["oyunlar"] = kalan
        data["kaynak"] = "Amazon.com.tr ürün sayfası. Başlık oyun adını taşıyor. Kişi, süre ve yaş önceki kayıttan; yeni sayı uydurulmadı."
        data["not"] = "Amazon.com.tr başlığında adı bulunamayan oyun listeden çıkarıldı."
        _yaz(oyun_yolu, data)
    ozet = {
        "dogrulanan_urun": degisen_urun,
        "kaldirilan_satinal_link": silinen_link,
        "neo_troy_metin_dosyasi": neo_cumle,
        "listeden_cikan_oyun": sum(1 for k in rapor.get("kayitlar") or [] if k.get("durum") in ("neo_troy_yok", "bulunamadi") and k["id"] in _oyun_idler()),
    }
    rapor["uygulama"] = ozet
    _yaz(RAPOR, rapor)
    print("uygulama", ozet)
    return ozet


def _oyun_idler():
    if not os.path.exists(OYUN):
        return set()
    data = _yukle(OYUN)
    return {o.get("id") for o in data.get("oyunlar") or []}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uygula", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    if a.uygula and os.path.exists(RAPOR) and not a.limit:
        uygula()
        return
    rapor = denetle(limit=a.limit)
    if a.uygula:
        uygula(rapor)


if __name__ == "__main__":
    main()
