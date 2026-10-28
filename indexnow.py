#!/usr/bin/env python3
"""Hobi Bul — IndexNow bildirimi (Bing, Yandex, Seznam, Naver).

Yeni veya değişen sayfaları arama motorlarına anında bildirir; sitemap'in
taranmasını beklemez. Doğrulama dosyası (docs/<anahtar>.txt) build.py
tarafından üretilir, anahtar content/site.json → indexnow_key'de tutulur.

Kullanım:
  python indexnow.py                      # sitemap'teki tüm URL'ler
  python indexnow.py --degisen liste.txt  # yalnızca listedeki dosyaların URL'leri
  python indexnow.py --kuru               # gönderme yok, sadece listele
"""
import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(BASE, "docs")
SITEMAP = os.path.join(SITE, "sitemap.xml")
ENDPOINT = "https://api.indexnow.org/indexnow"
PARCALAR = 500          # IndexNow tek istekte en fazla 10.000 URL kabul eder
YAYIN_BEKLEME = 240     # GitHub Pages yayını için azami bekleme (sn)


def site_config():
    with open(os.path.join(BASE, "content", "site.json"), encoding="utf-8") as f:
        return json.load(f)


def sitemap_urls():
    if not os.path.exists(SITEMAP):
        sys.exit("! docs/sitemap.xml yok; önce python build.py çalıştır.")
    kok = ET.parse(SITEMAP).getroot()
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [u.findtext("s:loc", namespaces=ns) for u in kok.findall("s:url", ns)]


def dosyadan_url(yol, base_url, bilinen, anahtar):
    """docs/... dosya yolunu sitemap'teki URL'ye çevir; bilinmiyorsa None."""
    yol = yol.strip().replace("\\", "/")
    if not yol.startswith("docs/"):
        return None
    # sitemap veya anahtar dosyası değiştiyse yapı değişmiş demektir: tümünü bildir
    if yol in ("docs/sitemap.xml", f"docs/{anahtar}.txt"):
        return "__tumu__"
    if not yol.endswith("index.html"):
        return None
    rel = yol[len("docs"):-len("index.html")] or "/"
    url = base_url + rel
    return url if url in bilinen else None


def yayinda_mi(key_url, azami=YAYIN_BEKLEME):
    bitis = time.time() + azami
    while True:
        try:
            with urllib.request.urlopen(key_url, timeout=15) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        if time.time() >= bitis:
            return False
        time.sleep(10)


def gonder(host, key, key_url, urls, deneme=3):
    veri = json.dumps({"host": host, "key": key, "keyLocation": key_url,
                       "urlList": urls}).encode("utf-8")
    son = ""
    for n in range(1, deneme + 1):
        req = urllib.request.Request(ENDPOINT, data=veri, method="POST",
                                     headers={"Content-Type": "application/json; charset=utf-8"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, ""
        except urllib.error.HTTPError as e:
            govde = e.read().decode("utf-8", "replace")[:200]
            if e.code in (400, 403, 422, 429):
                return e.code, govde
            son = f"HTTP {e.code}: {govde}"
        except (urllib.error.URLError, socket.timeout) as e:
            son = str(getattr(e, "reason", e))
        if n < deneme:
            time.sleep(5 * n)
    return None, son


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--degisen", help="git diff --name-only çıktısı (dosya yolları)")
    ap.add_argument("--kuru", action="store_true", help="gönderme yok, sadece listele")
    a = ap.parse_args()

    cfg = site_config()
    host = cfg["domain"].strip()
    base_url = cfg["base_url"].rstrip("/")
    key = (cfg.get("indexnow_key") or "").strip()
    if not key:
        sys.exit("! content/site.json → indexnow_key boş.")
    key_url = f"{base_url}/{key}.txt"
    if not os.path.exists(os.path.join(SITE, key + ".txt")):
        sys.exit(f"! docs/{key}.txt üretilmemiş; önce python build.py çalıştır.")

    tumu = sitemap_urls()
    bilinen = set(tumu)

    if a.degisen:
        if not os.path.exists(a.degisen):
            print(f"· {a.degisen} yok (değişiklik yok), bildirim atlandı.")
            return 0
        with open(a.degisen, encoding="utf-8") as f:
            satirlar = f.read().splitlines()
        urls = []
        for s in satirlar:
            u = dosyadan_url(s, base_url, bilinen, key)
            if u == "__tumu__":
                urls = list(tumu)
                break
            if u:
                urls.append(u)
        urls = list(dict.fromkeys(urls))
        if not urls:
            print("· Değişen sayfa yok, bildirim atlandı.")
            return 0
    else:
        urls = tumu

    print(f"→ {len(urls)} URL IndexNow'a bildirilecek: {host}")
    if a.kuru:
        for u in urls:
            print("  " + u)
        return 0

    print(f"… anahtar dosyası yayında mı: {key_url}")
    if not yayinda_mi(key_url):
        print(f"! Anahtar dosyası {YAYIN_BEKLEME} sn içinde yayına girmedi; "
              "bildirim yine denenecek (403 dönerse yarınki çalıştırma düzeltir).")

    hata = 0
    for i in range(0, len(urls), PARCALAR):
        parca = urls[i:i + PARCALAR]
        kod, govde = gonder(host, key, key_url, parca)
        if kod in (200, 202):
            print(f"✓ {len(parca)} URL bildirildi (HTTP {kod})")
        elif kod is None:
            print(f"! IndexNow'a ulaşılamadı: {govde}")
            print("  (içerik yayınlandı; sonraki çalıştırma tekrar dener)")
        elif kod == 429:
            print("! IndexNow istek sınırı aşıldı (HTTP 429); yarın tekrar denenecek.")
        elif kod == 403:
            print(f"! Anahtar doğrulanamadı (HTTP 403). {key_url} erişilebilir mi? {govde}")
            hata += 1
        elif kod == 422:
            print(f"! URL'ler host/anahtar ile eşleşmiyor (HTTP 422): {govde}")
            hata += 1
        elif kod == 400:
            print(f"! İstek biçimi reddedildi (HTTP 400): {govde}")
            hata += 1
        else:
            print(f"! IndexNow hatası (HTTP {kod}): {govde}")
            hata += 1
    return 1 if hata else 0


if __name__ == "__main__":
    sys.exit(main())
