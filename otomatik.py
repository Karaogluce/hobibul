#!/usr/bin/env python3
"""Hobi Bul — günlük otomatik makale hattı.

  python otomatik.py                  # bugünün kalanını üret (hedef 5, Europe/Istanbul)
  python otomatik.py --adet 2         # en fazla 2; günlük kalan daha azsa o kadar
  python otomatik.py --adet 2 --yayinla
  python otomatik.py --konu-listesi   # sıradaki konuları göster (API çağırmaz)

Akış: konu seç → Google Autocomplete'ten gerçek Türkçe sorguları çek → Gemini ile yaz
(yalnızca products.json verisiyle) → kısa veya MAX_TOKENS ile kesik taslakta eksik
bölümleri tamamlayan devam çağrısı → kalite kapıları → Unsplash'tan görsel → .md yaz.
Kapıdan geçemeyen makale YAYINLANMAZ, content/uretim_log.json'a işlenir.

Günlük hedef: İstanbul takvim gününde 5 makale. Sayı logdaki tarih kayıtlarından gelir.
Hedef doluysa Gemini çağrılmaz. 503/UNAVAILABLE, zaman aşımı, bağlantı hatası ve 429
kotasında biten makaleler diskte kalır, çıkış kodu 0 olur; sonraki çalışma kalanı dener.

Ortam değişkenleri: GEMINI_API_KEY, UNSPLASH_ACCESS_KEY, GEMINI_MODEL (ops.), GEMINI_MODEL_YEDEK (ops.), TASLAK_MODU (true/false)
"""
import argparse
import json
import os
import re
import statistics
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
import urllib.error
import urllib.parse
import urllib.request

import deeplink
import urun_denetim
import yeni_makale as ym
from seo import fit_description, fit_title

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CONTENT, ARTICLES = ym.CONTENT, ym.ARTICLES
LOG_PATH = os.path.join(CONTENT, "uretim_log.json")
POOL_PATH = os.path.join(CONTENT, "konu_havuzu.json")
GUNLUK_HEDEF = 5
TAMAM_MESAJI = "Bugünün 5 makalesi tamam"
UA = {"User-Agent": "Mozilla/5.0 (HobiBul-bot)"}


def _istanbul_tz():
    """Europe/Istanbul. Yaz saati 2016'da kalktı; tz verisi yoksa UTC+3."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Europe/Istanbul")
    except Exception:
        return timezone(timedelta(hours=3))


def istanbul_bugun(an=None):
    """Europe/Istanbul takvim günü. an verilirse o an (test için)."""
    if an is None:
        an = datetime.now(timezone.utc)
    elif an.tzinfo is None:
        an = an.replace(tzinfo=timezone.utc)
    return an.astimezone(_istanbul_tz()).date()


YEAR = istanbul_bugun().year

CAT_EN = {
    "outdoor": "camping outdoor nature", "el-sanatlari": "handmade crafts", "muzik": "music instruments",
    "teknoloji": "technology gadgets", "koleksiyon": "collectibles hobby", "spor-fitness": "fitness workout",
    "sanat": "art painting studio", "yemek-mutfak": "cooking kitchen", "bahce-bitki": "gardening plants",
    "evcil-hayvan": "pets", "bilim-astronomi": "astronomy telescope", "seyahat-gezi": "travel adventure",
    "yazilim-kodlama": "coding laptop", "yazi-edebiyat": "writing books",
}

# Kelime sayısı yalnızca güvenlik kontrolüdür: açıkça yarım, bozuk veya konuyu
# cevaplamayan çıktı bu tabanın altında reddedilir. Uzunluk arama niyetine bırakılır.
GUVENLIK_TABANI = 600

TIPLER = {
    "ticari": dict(
        hedef=1200, hepsi=False,
        baslik=lambda s: f"{s} Başlangıç Seti: İlk Alınacaklar ({YEAR})",
        yapi="İlk iki cümlede alım sorusuna cevap ver. Hemen ardından bir başlangıç ürününe aff:// linki koy. "
             "Sonra '## Satın Almadan Önce Nelere Bakmalı?' → '## Ürün Ürün Set' altında her önerilen ürün için ### başlık "
             "ve 'kime uymaz' cümlesi → '## Bütçe, Orta ve Üst Paket' altında fiyat yazmadan üç satırlık markdown tablo "
             "(Paket | İçinde ne var | Kime uyar) → '## Sık Sorulan Sorular' (3-4 soru) → kapanış: tek cümlelik net tavsiye "
             "('Sonuç' başlığı kullanma).",
    ),
    "rehber": dict(
        hedef=1000, hepsi=True,
        baslik=lambda s: f"En İyi {s} Ekipmanları ({YEAR}): Alım Rehberi",
        yapi="Giriş (odak anahtar kelime ilk paragrafta geçsin) → '## Satın Almadan Önce Nelere Bakmalı?' (genel, "
             "doğrulanabilir bilgiler; sayı/ölçü uydurma) → '## En İyi Seçenekler' altında her ürün için ### başlık → "
             "'## Hangisini Seçmeli?' (kullanım senaryosuna göre kısa eşleştirme) → '## Sık Sorulan Sorular' (3-4 soru) → kapanış: tek cümlelik net tavsiye ('Sonuç' başlığı kullanma).",
    ),
    "yeni_baslayan": dict(
        hedef=1000, hepsi=True,
        baslik=lambda s: f"{s} İçin Yeni Başlayanlar Rehberi: İlk Alınacak Ekipmanlar",
        yapi="Giriş (başlangıç kaygıları) → '## Başlamadan Önce Bilmen Gerekenler' → '## İlk Alışverişte Öncelik Sırası' altında "
             "ürünleri neden bu sırayla alınacağıyla ### başlıklar halinde anlat → '## Yeni Başlayanların Sık Yaptığı Hatalar' → "
             "'## Sık Sorulan Sorular' (3-4 soru) → kapanış: tek cümlelik net tavsiye ('Sonuç' başlığı kullanma).",
    ),
    "hatalar": dict(
        hedef=1000, hepsi=False,
        baslik=lambda s: f"{s} Ekipmanı Alırken Yapılan 7 Hata ve Nasıl Kaçınılır",
        yapi="Giriş → 7 numaralı hata, her biri ### başlık + 'neden sorun' + 'ne yapmalı' → hataların 2-3'üne uygun ürünlerden "
             "doğal biçimde link ver → '## Sık Sorulan Sorular' (3 soru) → kapanış: tek cümlelik net tavsiye ('Sonuç' başlığı kullanma).",
    ),
    "sss": dict(
        hedef=1000, hepsi=False,
        baslik=lambda s: f"{s} Hakkında Sık Sorulan Sorular: Cevaplarıyla Kısa Rehber",
        yapi="Giriş → 8-10 soru, her biri ### başlık olarak (aşağıdaki gerçek arama sorgularından seç) ve 2-4 cümlelik net cevap → "
             "uygun cevaplarda 2-3 üründen doğal biçimde link ver → '## Sık Sorulan Sorular' başlığını da kullan (ör. 'Hâlâ Aklında Soru Var mı?') → kapanış: tek cümlelik net tavsiye ('Sonuç' başlığı kullanma).",
    ),
    "kontrol_listesi": dict(
        hedef=1000, hepsi=False,
        baslik=lambda s: f"{s} Kontrol Listesi: Eksiksiz Hazırlık",
        yapi="Giriş (hedef sorguya ilk paragrafta cevap) → '## Neye İhtiyacın Var?' (hangi durumda hangi ekipman, "
             "ürün verisine dayalı genel gerekçeler) → '## Kontrol Listesi' altında madde madde liste; her maddede o şeyin neden "
             "gerektiğini tek cümleyle açıkla → '## Listeyi Kendine Göre Uyarlama' (kısa/uzun hazırlık, mevsim, deneyim farkı) → "
             "'## Sık Sorulan Sorular' (3-4 soru) → kapanış: tek cümlelik net tavsiye ('Sonuç' başlığı kullanma). Listede geçen en az 2 üründen doğal biçimde link ver.",
    ),
    "nasil_yapilir": dict(
        hedef=1000, hepsi=False,
        baslik=lambda s: f"{s} Nasıl Yapılır? Adım Adım Rehber",
        yapi="Giriş (hedef sorguya ilk iki cümlede cevap) → '## Gerekli Malzemeler ve Hazırlık' (kısa liste) → "
             "'## Adım Adım Uygulama' altında her adımı ### başlık yaparak sırayla anlat → '## Yeni Başlayanların Sık Yaptığı Hatalar' → "
             "'## Sık Sorulan Sorular' (3-4 soru) → kapanış: tek cümlelik net tavsiye ('Sonuç' başlığı kullanma). Uygun adımlarda en az 2 üründen doğal biçimde link ver.",
    ),
}
ESKI_TIPLER = ("rehber", "yeni_baslayan", "hatalar", "sss")
YENI_TIPLER = ("kontrol_listesi", "nasil_yapilir")
TICARI_TIP = "ticari"

# Havuzdan ve otomatik tamamlama önerilerinden elenen sorgular.
_JUNK_RE = re.compile(
    r"(nasıl\s+yazılır|nasil\s+yazilir|\bnedir\b|\bne demek\b|\bne anlama gelir\b|\bnasıl okunur\b|\bnasil okunur\b)",
    re.I,
)
_CITIES = (
    "istanbul ankara izmir adana bursa antalya konya gaziantep mersin diyarbakir diyarbakır "
    "kayseri eskisehir eskişehir samsun denizli urfa malatya erzurum van batman elazig elazığ "
    "sivas manisa balikesir balıkesir trabzon sakarya kocaeli aydin aydın mugla muğla hatay "
    "tekirdag tekirdağ ordu rize canakkale çanakkale edirne bolu zonguldak afyon isparta "
    "nigde niğde nevsehir nevşehir kirsehir kırşehir kirikkale kırıkkale osmaniye sirnak şırnak "
    "hakkari igdir iğdır agri ağrı mus muş bitlis siirt sanliurfa şanlıurfa kahramanmaras "
    "kahramanmaraş yalova duzce düzce karabuk karabük bartin bartın kastamonu amasya tokat "
    "corum çorum gumushane gümüşhane giresun artvin bingol bingöl tunceli kilis karaman "
    "usak uşak kutahya kütahya bilecik burdur sariçam sarıçam"
).split()
_TR_HINTS = {
    "ve", "ile", "icin", "için", "nasil", "nasıl", "en", "iyi", "bir", "bu", "su", "şu", "ne",
    "mi", "mı", "mu", "mü", "rehber", "secim", "seçim", "secimi", "seçimi", "baslangic",
    "başlangıç", "seti", "set", "alirken", "alırken", "evde", "yapilir", "yapılır", "hangi",
    "kadar", "neler", "nelere", "uygun", "malzeme", "malzemeleri", "ekipman", "kamp", "cadir",
    "çadır", "bot", "gitar", "kahve", "icin", "ilk", "alınacaklar", "alinacaklar", "karsilastirma",
    "karşılaştırma", "paket",
}
_EN_STOP = {
    "the", "how", "what", "why", "best", "for", "with", "your", "guide", "review", "versus",
    "buy", "tutorial", "beginner", "beginners",
}


def cop_mu(sorgu):
    """nedir / nasıl yazılır, il adı ve yabancı dil sorgularını ele."""
    s = re.sub(r"\s+", " ", str(sorgu or "")).strip()
    if not s or _JUNK_RE.search(s):
        return True
    if re.search(r"[\u0400-\u04FF\u0600-\u06FF\u4E00-\u9FFF\u3040-\u30FF]", s):
        return True
    low = s.lower()
    for city in _CITIES:
        if re.search(rf"(^|[\s,./]){re.escape(city)}($|[\s,./])", low):
            return True
    # Alfabe dökümü: "lego model a" gibi sonda tek harf kalan otomatik tamamlama.
    if re.search(r"(?:^|\s)[a-zçğıöşü]$", low):
        return True
    words = re.findall(r"[A-Za-zçğıöşüÇĞİÖŞÜâîûÂÎÛ]+", low)
    if not words:
        return True
    if any(ch in s for ch in "çğıöşüÇĞİÖŞÜ"):
        return False
    tr_hits = sum(1 for w in words if w in _TR_HINTS)
    en_hits = sum(1 for w in words if w in _EN_STOP)
    if tr_hits == 0 and en_hits >= 1:
        return True
    return False
HYPE = ["mükemmel", "piyasa lideri", "kesinlikle", "garanti", "%100", "en iyisi budur", "rakipsiz", "kusursuz"]


GUIDE_PATH = os.path.join(CONTENT, "yazim_rehberi.md")


def load_guide():
    txt = ""
    if os.path.exists(GUIDE_PATH):
        with open(GUIDE_PATH, encoding="utf-8") as f:
            txt = f.read()
    banned = []
    m = re.search(r"YASAKLI KALIPLAR[^\n]*\n(.*?)(?:\n## |\Z)", txt, re.S)
    if m:
        banned = [l[2:].strip().lower() for l in m.group(1).splitlines() if l.startswith("- ")]
    return txt, banned


# ------------------------------------------------------------------ durum
def load_log():
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"done": [], "photos": [], "atlanan": []}


def save_log(log):
    with open(LOG_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(log, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())


def done_anahtarlari(log):
    """Kuyruktan düşülecek konu anahtarları. done hem düz metin hem kayıt tutabilir."""
    out = []
    for item in log.get("done") or []:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            anahtar = str(item.get("anahtar") or "").strip()
            if anahtar:
                out.append(anahtar)
    return out


def _tarihli_kayitlar(log):
    """Üretilen makalenin tarihli kaydı. Tarih yoksa bugüne sayılmaz."""
    kayitlar = []
    for kaynak in (log.get("makaleler"), log.get("done")):
        for item in kaynak or []:
            if isinstance(item, dict):
                kayitlar.append(item)
    return kayitlar


def bugun_uretilen_say(log, bugun):
    """İstanbul gününde üretilmiş makale sayısı. Aynı anahtar bir kez sayılır."""
    if not isinstance(bugun, str):
        bugun = bugun.isoformat()
    seen = set()
    n = 0
    for item in _tarihli_kayitlar(log):
        tarih = str(item.get("tarih") or "").strip()
        if tarih != bugun:
            continue
        anahtar = str(item.get("anahtar") or item.get("slug") or "").strip()
        if not anahtar or anahtar in seen:
            continue
        seen.add(anahtar)
        n += 1
    return n


def makale_kaydi_ekle(log, anahtar, slug, tarih):
    """Makaleyi done listesine ve tarihli kayda yazar. Tarih yoksa ekler, olanı değiştirmez."""
    done = log.setdefault("done", [])
    if anahtar not in set(done_anahtarlari(log)):
        done.append(anahtar)
    kayitlar = log.setdefault("makaleler", [])
    for item in kayitlar:
        if isinstance(item, dict) and item.get("anahtar") == anahtar:
            if not item.get("tarih"):
                item["tarih"] = tarih
            if slug and not item.get("slug"):
                item["slug"] = slug
            return item
    item = {"anahtar": anahtar, "tarih": tarih, "slug": slug}
    kayitlar.append(item)
    return item


def kosu_plani(adet, log, bugun, hedef=GUNLUK_HEDEF):
    """Bu çalışmada üretilecek adet ve log satırları. 0 ise günün hedefi dolu."""
    mesajlar = []
    if adet > hedef:
        mesajlar.append(f"Günlük sınır {hedef} makale; adet {hedef}'e çekildi.")
        adet = hedef
    elif adet < 1:
        adet = hedef
    yapilan = bugun_uretilen_say(log, bugun)
    kalan = hedef - yapilan
    if kalan <= 0:
        mesajlar.append(TAMAM_MESAJI)
        return 0, mesajlar
    if adet > kalan:
        mesajlar.append(f"Bugün {yapilan} makale yazılmış; {kalan} makale daha üretilecek.")
        return kalan, mesajlar
    mesajlar.append(f"Bugün {yapilan}/{hedef} makale var; bu çalışmada {adet} üretilecek.")
    return adet, mesajlar


# ------------------------------------------------------------------ konu kuyruğu
def load_pool():
    if not os.path.exists(POOL_PATH):
        return []
    try:
        with open(POOL_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def dogal_baslik(sorgu):
    s = re.sub(r"\s+", " ", str(sorgu)).strip().strip("?.!").strip()
    if not s:
        return ""
    s = {"i": "İ", "ı": "I"}.get(s[0], s[0].upper()) + s[1:]
    s = re.sub(r"\b(nedir)\s+(nasıl)\b", r"\1, \2", s, flags=re.I)
    if re.search(r"\b(nasıl|nedir|hangi|mi|mı|mu|mü)\b", s, re.I) and not s.endswith("?"):
        s += "?"
    return s


# Ürün listesini tam kapsaması gereken tipler. Bu tiplerde alt kategori için
# en az üç doğrulanmış ürün şartı aranır; diğer tipler iki linkle çalışabilir.
URUN_ODAKLI_TIPLER = ("ticari", "rehber", "yeni_baslayan")


def _gerekli_urun(tip):
    return 3 if tip in URUN_ODAKLI_TIPLER else 2


def _havuz_uygun(e):
    """Sınıflandırma sonucu elenen/incelenecek kayıtlar üretime alınmaz.

    `siniflandirma` alanı olmayan eski havuz kayıtları eskisi gibi davranır.
    """
    s = e.get("siniflandirma")
    if isinstance(s, dict):
        durum = s.get("durum")
        if durum and durum != "uygun":
            return False
    return True


def _urun_haritasi(products):
    try:
        return urun_denetim.urun_haritasi(products)
    except urun_denetim.UrunVerisiHatasi as e:
        sys.exit(f"Ürün verisi hatası: {e}")


def havuz_konulari(products, c, pool, used):
    """Havuzdaki ticari olmayan konular. Ürün eşiği doğrulanmış ürünlerle sayılır."""
    items = []
    subs = {s["id"]: s["name"] for s in c["subcategories"]}
    for e in pool:
        if not _havuz_uygun(e):
            continue
        tip, sub = e.get("tip_onerisi"), e.get("alt")
        if tip not in TIPLER or tip == TICARI_TIP or e.get("kategori") != c["id"] or sub not in subs:
            continue
        sorgu = re.sub(r"\s+", " ", str(e.get("sorgu", ""))).strip()
        if not sorgu or cop_mu(sorgu):
            continue
        plist = urun_denetim.alt_kategori_urunleri(products, c["id"], sub)
        if len(plist) < _gerekli_urun(tip):
            continue
        sslug = ym.slugify(sorgu)
        if not sslug or sslug in used:
            continue
        used.add(sslug)
        items.append(dict(
            key=f"{tip}:{c['id']}:{sub}:{sslug}", tip=tip, cat=c["id"], cat_name=c["name"],
            sub=sub, sub_name=subs[sub], ids=[p["id"] for p in plist],
            title=dogal_baslik(sorgu), sorgu=sorgu, sorgu_slug=sslug, kaynak="havuz"))
    return items


def _urun_bul(products, ids):
    """İstenen kimlikleri doğrulanmış ürün haritasından çöz; geçersizleri atla."""
    harita = _urun_haritasi(products)
    gorulen, out = set(), []
    for rid in ids:
        rid = str(rid).strip()
        if not rid or rid in gorulen:
            continue
        gorulen.add(rid)
        rec = harita.get(rid)
        if rec is not None and urun_denetim.dogrulanmis_mi(rec):
            out.append(rec)
    return out


def ticari_konulari(products, c, pool, used):
    """Havuzdaki ticari niyetli konular, sonra her alt kategori için başlangıç seti."""
    items = []
    subs = {s["id"]: s["name"] for s in c["subcategories"]}

    def ekle(tip_key, sub, sub_name, plist, title, sorgu, kaynak):
        sslug = ym.slugify(sorgu or title)
        if not sslug or sslug in used or cop_mu(sorgu or title):
            return
        if len(plist) < _gerekli_urun(TICARI_TIP):
            return
        used.add(sslug)
        items.append(dict(
            key=tip_key, tip=TICARI_TIP, cat=c["id"], cat_name=c["name"],
            sub=sub, sub_name=sub_name, ids=[p["id"] for p in plist],
            title=title, sorgu=sorgu, sorgu_slug=sslug, kaynak=kaynak))

    for e in pool:
        if not _havuz_uygun(e) or e.get("tip_onerisi") != TICARI_TIP or e.get("kategori") != c["id"]:
            continue
        sub = e.get("alt")
        if sub not in subs:
            continue
        sorgu = re.sub(r"\s+", " ", str(e.get("sorgu", ""))).strip()
        if not sorgu:
            continue
        wanted = [str(x).strip() for x in (e.get("urunler") or []) if str(x).strip()]
        if wanted:
            plist = _urun_bul(products, wanted)
        else:
            plist = urun_denetim.alt_kategori_urunleri(products, c["id"], sub)
        ekle(f"ticari:{c['id']}:{sub}:{ym.slugify(sorgu)}", sub, subs[sub], plist,
             dogal_baslik(sorgu), sorgu, "havuz")
    for s in c["subcategories"]:
        plist = urun_denetim.alt_kategori_urunleri(products, c["id"], s["id"])
        title = TIPLER[TICARI_TIP]["baslik"](s["name"])
        ekle(f"ticari:{c['id']}:{s['id']}:baslangic", s["id"], s["name"], plist, title, title, "sablon")
    return items


def _makale_gruplari(articles_dir=None):
    """(kategori, alt kategori) -> makale sayısı. Makalesiz gruba öncelik için."""
    counts = Counter()
    for m in urun_denetim.makale_verileri(articles_dir or ARTICLES):
        cat = str(m.get("kategori") or "").strip()
        if not cat:
            continue
        sub = str(m.get("alt") or "").strip() or "_main"
        counts[(cat, sub)] += 1
    return counts


def _son_uretim_gunu(log):
    """(kategori, alt kategori) -> en son üretim tarihi. Hiç üretilmemiş grup yoktur."""
    out = {}
    for item in _tarihli_kayitlar(log or {}):
        parca = str(item.get("anahtar") or "").split(":")
        if len(parca) < 3:
            continue
        anahtar = (parca[1], parca[2])
        tarih = str(item.get("tarih") or "").strip()
        if not tarih:
            continue
        if anahtar not in out or tarih > out[anahtar]:
            out[anahtar] = tarih
    return out


def _grup_anahtari(g, makale_sayisi, son_uretim):
    """Makalesiz alt kategori önce, sonra en uzun süredir üretim yapılmayan.

    Kategori düzeyi (_main) konuları gerçek alt kategorilerin önüne geçmez;
    böylece ilk günlerde tüm kategorilerin jenerik rehberi kuyruğu doldurmaz.
    """
    cat, sub = g["cat"], g["sub"]
    if sub == "_main":
        oncelik = 2
    elif makale_sayisi.get((cat, sub), 0) == 0:
        oncelik = 0
    else:
        oncelik = 1
    return (oncelik, son_uretim.get((cat, sub), ""), cat, sub)


def _adil_sira(gruplar, makale_sayisi, son_uretim):
    """Gruplar arasında round-robin; aynı ana kategori art arda gelmez.

    Sıra deterministiktir: rastgelelik ve analytics ağırlığı yoktur. Gruplar
    tükenene kadar her turda her gruptan en fazla bir konu alınır.
    """
    sirali = sorted(gruplar, key=lambda g: _grup_anahtari(g, makale_sayisi, son_uretim))
    kuyruk = [list(g["konular"]) for g in sirali]
    out, son_kat = [], None
    while any(kuyruk):
        ilerleme = False
        for i, g in enumerate(sirali):
            if not kuyruk[i] or g["cat"] == son_kat:
                continue
            out.append(kuyruk[i].pop(0))
            son_kat = g["cat"]
            ilerleme = True
        if not ilerleme:
            # Kalan tüm gruplar son kategoriyle aynıysa kilit çözülür.
            for i, g in enumerate(sirali):
                if kuyruk[i]:
                    out.append(kuyruk[i].pop(0))
                    son_kat = g["cat"]
                    ilerleme = True
                    break
            if not ilerleme:
                break
    return out


def topic_queue(products, cats, log=None, articles_dir=None):
    """Kategori/alt kategori grupları arasında adil, deterministik üretim sırası.

    Önce ticari niyet, sonra havuzun diğer tipleri ve başlangıç setleri. Konusu
    olmayan alt kategori kuyruğa girmez; her grup tur başına bir konu verir.
    """
    pool, used = load_pool(), set()
    makale_sayisi = _makale_gruplari(articles_dir)
    son_uretim = _son_uretim_gunu(load_log() if log is None else log)
    gruplar = []
    for c in cats:
        items = ticari_konulari(products, c, pool, used)
        subs = [("_main", c["name"])] + [(s["id"], s["name"]) for s in c["subcategories"]]
        for tip in ESKI_TIPLER:
            for sid, sname in subs:
                plist = urun_denetim.alt_kategori_urunleri(products, c["id"], sid)
                if len(plist) < _gerekli_urun(tip):
                    continue
                items.append(dict(
                    key=f"{tip}:{c['id']}:{sid}", tip=tip, cat=c["id"], cat_name=c["name"],
                    sub=sid, sub_name=sname, ids=[p["id"] for p in plist],
                    title=TIPLER[tip]["baslik"](sname), kaynak="sablon"))
        items += havuz_konulari(products, c, pool, used)
        yerliler = {}
        for t in sorted(items, key=lambda x: 0 if x.get("kaynak") == "havuz" else 1):
            yerliler.setdefault(t["sub"], []).append(t)
        for sub, konular in yerliler.items():
            gruplar.append(dict(cat=c["id"], sub=sub, konular=konular))
    return _adil_sira(gruplar, makale_sayisi, son_uretim)


# ------------------------------------------------------------------ arama sorguları
def suggestions(sub_name):
    base = sub_name.lower().split(" & ")[0]
    seeds = [base, f"{base} nasıl seçilir", f"{base} için en iyi", f"{base} yeni başlayanlar"]
    out = []
    for q in seeds:
        url = "https://suggestqueries.google.com/complete/search?client=firefox&hl=tr&gl=tr&q=" + urllib.parse.quote(q)
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=50) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            for s in data[1]:
                if s not in out and len(s) > len(base) + 3 and not re.search(r"\d+\s*(tl|₺)|fiyat|ucuz|indirim", s) and not cop_mu(s):
                    out.append(s)
        except Exception:
            continue
    return out[:14]


# ------------------------------------------------------------------ prompt / parse
def kelime_hedef(tip):
    """Yumuşak hedef. Zorunlu alt sınır değil; konu bittiyse uzatma gerekmez."""
    return TIPLER[tip]["hedef"]


def _urun_bloku(prods):
    return "\n".join(
        f"- id: {p['id']}\n  ad: {p['name']}\n  marka: {p.get('brand','')}\n  açıklama: {p.get('desc','')}\n"
        f"  artılar: {'; '.join(p.get('pros', []))}\n  eksiler: {'; '.join(p.get('cons', []))}"
        + (f"\n  yazarın notu: {p['not']}" if p.get('not') else "") for p in prods)


def build_prompt(t, prods, sugg, guide=""):
    cfg = TIPLER[t["tip"]]
    plist = _urun_bloku(prods)
    hedef = kelime_hedef(t["tip"])
    sq = "\n".join(f"- {s}" for s in sugg) or "- (sorgu bulunamadı; konuyla ilgili doğal sorular kullan)"
    zorunlu = ("HER ÜRÜN için en az bir kez" if cfg["hepsi"] else "en az 2 ürün için")
    tablo_kurali = "Paket bölümündeki markdown tablo serbest; başka tablo yok." if t["tip"] == TICARI_TIP else "Tablo kullanma."
    alt_yol = f"/kategori/{t['cat']}/{t['sub']}/" if t.get("sub") and t["sub"] != "_main" else f"/kategori/{t['cat']}/"
    ticari_ek = ""
    if t["tip"] == TICARI_TIP:
        ticari_ek = f"""
TİCARİ NİYET (bu kurallar da kesin):
- İlk 80 kelimede alım sorusuna cevap ver ve bir başlangıç ürününe aff:// linki koy.
- Her ürün bölümünde ürünün kime uymadığını yaz. Eksiyi saklama.
- '## Bütçe, Orta ve Üst Paket' bölümünde şu markdown tabloyu doldur. Fiyat, TL veya ₺ yazma.
  | Paket | İçinde ne var | Kime uyar |
  | --- | --- | --- |
- Tabloda bütçe, orta ve üst satırı olsun. Hücrelerde ürün varsa aff:// linki kullan.
- Metinde bir kez şu iç linki doğal bir cümlede kullan: [{t['sub_name']}]({alt_yol})
- Ansiklopedi maddesi yazma. Okuyucu ne alacağına karar versin.
"""
    return f"""Sen Türkiye'deki hobi meraklıları için yazan deneyimli bir blog editörüsün. Aşağıdaki konuda özgün, işe yarar, Türkçe bir makale yaz.

BAŞLIK: {t['title']}
KATEGORİ: {t['cat_name']} › {t['sub_name']}
MAKALE TİPİ: {t['tip']}
BEKLENEN YAPI: {cfg['yapi']}
UZUNLUK VE YAPI (arama niyetine göre doğal yaz):
- Yaklaşık {hedef} kelime yeterli. Konu tamamlandığında sırf kelime sayısını artırmak için uzatma; gereksiz genel bilgi, tekrar ve dolgu cümle yazma.
- En az 4 adet "## " bölümü yaz; her ## bölümünde en az iki paragraf olsun.
- Her bölümü somut bir durumdan aç. Gerekçeyi ürün verisine bağla. Aynı öğüdü yeni başlık altında tekrarlama.

İNSANLARIN GERÇEKTEN ARADIĞI SORGULAR (uygun olanları başlıklara ve SSS bölümüne doğal biçimde yedir; zorlama ya da tekrar yapma):
{sq}

KULLANABİLECEĞİN ÜRÜNLER (başka ürün, marka veya model ekleme):
{plist}

KESİN KURALLAR:
1. Ürün verilerinde olmayan teknik özellik, ağırlık, ölçü, fiyat, puan, test sonucu veya "denedik" iddiası UYDURMA. Emin olmadığın bilgiyi yazma.
2. Fiyat yazma. Gerekirse "güncel fiyatı Amazon'da kontrol et" de.
3. Ürün linkini şu biçimde ver ({zorunlu}): [Satın Al: ÜRÜN ADI](aff://ÜRÜN_ID)
4. Yalnızca Markdown. En üstte H1 yok. {tablo_kurali} ## ve ### başlıkları, nefes alan paragraflar ve gerektiğinde madde listesi kullan.
5. Doğal, samimi, abartısız Türkçe. Konuşur gibi yaz: cümleler birbirine bağlansın. Cümleyi yapay biçimde kısaltma; 3-7 kelime zorunluluğu yok. "Mükemmel", "piyasa lideri", "kesinlikle", "garanti" gibi kanıtsız iddialar yok. Her paragraf bilgi taşısın, dolgu cümle yazma.
6. Başka sitelerden metin alma; kalıp cümleleri tekrarlama.
7. Yabancı dilde paragraf yazma. İl adı, "nedir" tanımı veya "nasıl yazılır" konusu açma.
8. AliExpress, Geekbuying, Trendyol veya Hepsiburada adresi yazma. Bu mağaza düğmeleri, kategori eşleşirse sayfaya build sırasında eklenir. Ürün linki yalnızca aff:// biçiminde olsun.
{ticari_ek}
YAZIM REHBERİ (bunu uygula; okuyucuya bir insanın konuşur gibi yazdığı gelsin, ama kimseyi yanıltma):
{guide}

ÇIKTI BİÇİMİ (tam olarak böyle):
GORSEL: <Unsplash'ta aratılacak 2-4 kelimelik İNGİLİZCE sorgu; marka/ürün adı yok; konuyu görsel olarak anlatsın>
ANAHTAR: <odak anahtar kelime, Türkçe, 2-4 kelime>
ACIKLAMA: <120-160 karakterlik Türkçe meta açıklama, odak anahtar kelimeyi içersin. Başlık artı " | Hobi Bul" en fazla 60 karakter olsun.>
---
<makale metni>
"""


def edit_prompt(body, prods, guide, alt_sinir=GUVENLIK_TABANI):
    veri = "\n".join(f"- {p['id']}: {p['name']} | {p.get('desc','')} | artı: {'; '.join(p.get('pros', []))} | eksi: {'; '.join(p.get('cons', []))}" for p in prods)
    return f"""Sen titiz bir Türkçe blog editörüsün. Aşağıdaki taslağı, YAZIM REHBERİ'ne göre elden geçir.

YAPILACAKLAR:
1. Yasaklı kalıpları, klişe girişleri ve dolgu cümleleri kaldır ya da somut ifadeyle değiştir.
2. Cümleleri doğal konuşma Türkçesine çek. Kesik kesik, telegram gibi dizilmiş yargıları birleştir. Cümleyi salt kısa olsun diye bölme; 3-7 kelime zorunluluğu yok. Art arda aynı kelimeyle başlayan cümleleri değiştir. İç içe geçmiş, nefes aldırmayan cümleleri sadeleştir.
3. Ürün verisinde bulunmayan her bilgiyi (ölçü, ağırlık, süre, puan, fiyat, "denedik/kullandım" iddiası) sil.
4. Tüm aff:// linklerini aynen koru. ## ve ### başlık sayısını koru (başlık metinlerini doğallaştırabilirsin).
5. Bilgi kaybı yaratma; metni {alt_sinir} kelimenin altına düşürme. Sırf uzatmak için yeni paragraf ekleme, dolgu yazma. Markdown tablo satırlarını silme.
Sadece düzeltilmiş Markdown metnini döndür; açıklama yazma.

ÜRÜN VERİSİ:
{veri}

YAZIM REHBERİ:
{guide}

<<<TASLAK
{body}
TASLAK>>>
"""


def parse(raw):
    raw = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", raw.strip())
    head, sep, body = raw.partition("\n---")
    if not sep:
        return None
    meta = {}
    for line in head.splitlines():
        m = re.match(r"\s*(GORSEL|ANAHTAR|ACIKLAMA)\s*:\s*(.+)", line)
        if m:
            meta[m.group(1)] = m.group(2).strip()
    if len(meta) < 3:
        return None
    return meta, body.lstrip("-").strip()


# ------------------------------------------------------------------ kalite kapıları
def shingles(text, n=5):
    w = re.findall(r"\w+", text.lower())
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def existing_shingles():
    out = []
    if os.path.isdir(ARTICLES):
        for fn in os.listdir(ARTICLES):
            if fn.endswith(".md"):
                with open(os.path.join(ARTICLES, fn), encoding="utf-8") as f:
                    out.append((fn, shingles(f.read())))
    return out


def stil_kontrol(body, banned):
    low = body.lower()
    hits = [b for b in banned if b in low]
    if sum(low.count(b) for b in banned) > 1:
        return f"yapay kalıplar: {', '.join(hits[:4])}"
    text = re.sub(r"\[Satın Al:[^\]]*\]\([^)]*\)", " ", body)
    lines = [l for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#") and not l.strip().startswith("|")]
    text = re.sub(r"[*_>`]|^\s*[-\d.]+\s+", "", "\n".join(lines), flags=re.M)
    sents = [x for x in re.split(r"(?<=[.!?])\s+", text) if len(x.split()) >= 2]
    if len(sents) < 20:
        return "çok az cümle"
    lens = [len(x.split()) for x in sents]
    if statistics.pstdev(lens) < 3.5:
        return "cümle ritmi monoton"
    # Telegram üslubu: cümlelerin çoğu tek yargı.
    if sum(1 for n in lens if n <= 6) / len(lens) > 0.45:
        return "cümleler aşırı kesik"
    # İç içe geçmiş cümle. Orta uzunluk serbest; 28 kelime sınırı yok.
    if sum(1 for n in lens if n > 45) / len(lens) > 0.12:
        return "cümleler çok uzun"
    top = Counter(x.split()[0].lower() for x in sents).most_common(1)[0][1] / len(sents)
    if top > 0.18:
        return "aynı kelimeyle başlayan cümle çok"
    return None


def gate(body, tip, prods, others, banned=()):
    cfg = TIPLER[tip]
    words = len(body.split())
    if words < GUVENLIK_TABANI:
        return f"kısa ({words} kelime, güvenlik tabanı {GUVENLIK_TABANI})"
    if len(re.findall(r"^## ", body, re.M)) < 4:
        return "yetersiz H2 bölümü"
    if not re.search(r"sık sorulan|sorular|\bsss\b", body, re.I):
        return "SSS bölümü yok"
    used = set(re.findall(r"aff://([A-Za-z0-9_-]+)", body))
    ids = {p["id"] for p in prods}
    if cfg["hepsi"] and ids - used:
        return f"linksiz ürün: {', '.join(sorted(ids - used))}"
    if not cfg["hepsi"] and len(used & ids) < 2:
        return "en az 2 ürün linki yok"
    if tip == TICARI_TIP and not re.search(r"^\|.*\|$", body, re.M):
        return "paket tablosu yok"
    if re.search(r"\d[\d.,]*\s*(?:₺|TL)\b", body):
        return "metinde fiyat var"
    if sum(body.lower().count(h) for h in HYPE) > 2:
        return "abartılı/kanıtsız ifade çok"
    why = stil_kontrol(body, banned)
    if why:
        return why
    sh = shingles(body)
    for fn, osh in others:
        if sh and osh and len(sh & osh) / len(sh | osh) > 0.22:
            return f"{fn} ile fazla benzer"
    return None


# ------------------------------------------------------------------ Unsplash
_GORSEL_GENEL = {
    "a", "an", "and", "the", "of", "on", "in", "with", "for", "to", "at",
    "photo", "image", "picture", "person", "man", "woman", "white", "black",
    "hobby", "tools", "equipment", "outdoor", "home", "new", "best",
}


def _gorsel_kelimeleri(text):
    return {
        w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(w) > 2 and w not in _GORSEL_GENEL
    }


def gorsel_puani(photo, query):
    """Alt/açıklama metni arama konusuyla en az bir belirgin kelime paylaşmalı."""
    metin = " ".join(str(photo.get(k) or "") for k in ("alt_description", "description"))
    return len(_gorsel_kelimeleri(query) & _gorsel_kelimeleri(metin))


def unsplash(query, fallback, used, key):
    if not key:
        return None
    for q in (query, fallback):
        url = "https://api.unsplash.com/search/photos?" + urllib.parse.urlencode(
            {"query": q, "orientation": "landscape", "per_page": 12, "content_filter": "high"})
        h = {"Authorization": f"Client-ID {key}", "Accept-Version": "v1", **UA}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=20) as r:
                res = json.loads(r.read().decode("utf-8"))["results"]
        except Exception as e:
            print(f"  ! Unsplash hatası: {e}")
            return None
        adaylar = [ph for ph in res if ph["id"] not in used and gorsel_puani(ph, q) > 0]
        adaylar.sort(key=lambda ph: gorsel_puani(ph, q), reverse=True)
        for ph in adaylar:
            try:  # Unsplash kuralı: kullanılan fotoğrafın indirme olayını bildir
                urllib.request.urlopen(urllib.request.Request(ph["links"]["download_location"], headers=h), timeout=15).read()
            except Exception:
                pass
            u = ph["user"]
            return dict(
                id=ph["id"], url=ph["urls"]["regular"],
                alt=(ph.get("alt_description") or q).replace('"', "'"),
                credit=u["name"], credit_url=u["links"]["html"] + "?utm_source=hobibul&utm_medium=referral")
    return None


# ------------------------------------------------------------------ yazma
def q(s):
    return str(s).replace('"', "'").replace("\n", " ").strip()


def write_article(t, meta, body, img, draft, tarih=None):
    slug = ym.slugify(t["title"])
    title = t["title"]
    raw_desc = q(meta.get("ACIKLAMA") or "")
    mt = fit_title(title if title.endswith("Hobi Bul") else f"{title} | Hobi Bul")
    md = fit_description(raw_desc, extra=f"{q(meta.get('ANAHTAR') or title)} rehberi, yeni başlayan için ürün notlarıyla")
    tarih = tarih or istanbul_bugun().isoformat()
    lines = ["---", f'title: "{q(title)}"', f'slug: "{slug}"', f'category: "{t["cat"]}"',
             f'date: "{tarih}"', f'updated: "{tarih}"', f'meta_title: "{q(mt)}"',
             f'meta_description: "{q(md)}"', f'excerpt: "{raw_desc or q(md)}"',
             f'focus_keyword: "{q(meta["ANAHTAR"])}"']
    if img:
        lines += [f'image: "{img["url"]}"', f'image_alt: "{q(img["alt"])}"',
                  f'image_credit: "{q(img["credit"])}"', f'image_credit_url: "{img["credit_url"]}"']
    if t.get("sub") and t["sub"] != "_main":
        lines.append(f'subcategory: "{t["sub"]}"')
    # Mağaza düğmesi buraya yazılmaz. category / subcategory, deeplink.shop_ctas_for
    # ile article.html ve category.html içinde Admitad deeplink'ine döner.
    lines += [f'draft: "{"true" if draft else "false"}"', "---", ""]
    path = os.path.join(ARTICLES, slug + ".md")
    os.makedirs(ARTICLES, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n" + body.strip() + "\n")
        f.flush()
        os.fsync(f.fileno())
    return slug, len(body.split()), tarih


# GEMINI_MODEL_YEDEK boşsa günlük kotada denenecek yerleşik yedek.
# AI Studio adı değişirse variable ile ezilir; uydurma ek model eklenmez.
YERLESIK_YEDEK = "gemini-flash-lite-latest"


def _modeller():
    """(model listesi, yedek variable açıkça tanımlı mı)."""
    ana = (os.environ.get("GEMINI_MODEL") or "gemini-flash-latest").strip() or "gemini-flash-latest"
    yedek_raw = (os.environ.get("GEMINI_MODEL_YEDEK") or "").strip()
    yedek = [m.strip() for m in yedek_raw.split(",") if m.strip()]
    acik = bool(yedek)
    if not yedek and YERLESIK_YEDEK != ana:
        yedek = [YERLESIK_YEDEK]
    out = []
    for m in [ana] + yedek:
        if m not in out:
            out.append(m)
    return out, acik


_GECICI_IZ = (
    "unavailable", "timeout", "timed out", "zaman aşımı", "zaman asimi",
    "bağlantı", "baglanti", "connection", "temporarily unavailable",
    "try again", "reset by peer", "name or service not known",
)


def gecici_api_hatasi(exc):
    """503/UNAVAILABLE, zaman aşımı, bağlantı ve 429. Kalıcı 4xx bu sınıfa girmez."""
    if isinstance(exc, ym.GeminiQuotaError):
        return True
    if not isinstance(exc, ym.GeminiError):
        return False
    msg = str(exc)
    low = msg.lower()
    if re.search(r"\b(429|500|502|503|504)\b", msg):
        return True
    return any(s in low for s in _GECICI_IZ)


def _gemini(prompt, key, models, idx):
    """Kotası biten modeli atla. idx, sıradaki kullanılabilir modeli tutar."""
    last = None
    while idx[0] < len(models):
        model = models[idx[0]]
        try:
            return ym.call_gemini(prompt, key, model)
        except ym.GeminiQuotaError as e:
            last = e
            idx[0] += 1
            if idx[0] < len(models):
                print(f"  günlük kota: {model} — yedek modele geçiliyor ({models[idx[0]]})")
            else:
                print(f"  günlük kota: {model} — denenecek model kalmadı")
    raise last or ym.GeminiError("Kullanılabilir Gemini modeli kalmadı.")


DEVAM_HAKKI = 2


def genisletme_gerekli(body, tip, finish_reason):
    """Yalnızca token kesmesi ya da güvenlik tabanının altı devam ister.

    Konu tamamlanmış ve tabanın üstündeyse sırf kelime sayısı için continuation
    çağrılmaz; `tip` yumuşak hedefi okumak için ayrılabilir.
    """
    if (finish_reason or "") == "MAX_TOKENS":
        return True
    return len((body or "").split()) < GUVENLIK_TABANI


def _cumleler(text):
    text = re.sub(r"(?m)^#+\s*", "", text or "")
    return [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if len(p.split()) >= 6]


def birlestir_taslak(eski, yeni):
    """Tam yeniden yazımı olduğu gibi al; yalnızca ek bölüm geldiyse sona ekle."""
    eski = (eski or "").strip()
    yeni = (yeni or "").strip()
    if not yeni:
        return eski
    if not eski or yeni in eski:
        return eski or yeni
    eski_c = set(_cumleler(eski))
    yeni_c = _cumleler(yeni)
    if yeni_c and eski_c:
        tekrar = sum(1 for c in yeni_c if c in eski_c) / len(yeni_c)
        if tekrar >= 0.35:
            return yeni if len(yeni.split()) > len(eski.split()) else eski
    eski_baslik = set(re.findall(r"(?m)^## .+$", eski))
    yeni_baslik = set(re.findall(r"(?m)^## .+$", yeni))
    ortak = eski_baslik & yeni_baslik
    if eski_baslik and len(ortak) >= min(2, len(eski_baslik)):
        return yeni
    ilk = " ".join(eski.split()[:12])
    if len(ilk.split()) >= 8 and ilk in " ".join(yeni.split()):
        return yeni
    return eski + "\n\n" + yeni


def govde_ayikla(raw):
    text = str(raw or "").strip()
    text = re.sub(r"^```(?:markdown|md)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    parsed = parse(text)
    if parsed:
        return parsed[1]
    if "\n---" in text and re.search(r"(?m)^(GORSEL|ANAHTAR|ACIKLAMA)\s*:", text):
        _, _, body = text.partition("\n---")
        return body.lstrip("-").strip()
    return text


def devam_prompt(taslak, t, prods, guide, finish_reason, tam_bicim=False):
    """Kısa veya kesik taslağı dolguya kaçmadan eksik bölümlerle tamamlat."""
    cfg = TIPLER[t["tip"]]
    simdi = len((taslak or "").split())
    if finish_reason == "MAX_TOKENS":
        durum = (
            "Taslak token sınırında kesildi; cümle yarım kalmış olabilir. "
            "Kaldığın yerden tamamla, sonra eksik bölümleri yaz."
        )
    else:
        durum = (
            f"Taslak {simdi} kelime ve güvenlik tabanı {GUVENLIK_TABANI}. Erken durmuş. "
            "Eksik bölümleri ve ince kalan bölümleri işle."
        )
    if tam_bicim:
        cikti = """ÇIKTI BİÇİMİ (tam olarak böyle, kod bloğu yok):
GORSEL: <2-4 kelimelik İngilizce Unsplash sorgusu; marka adı yok>
ANAHTAR: <Türkçe odak kelime, 2-4 kelime>
ACIKLAMA: <120-160 karakter>
---
<baştan sona makale metni>"""
    else:
        cikti = (
            "Çıktı, baştan sona tam makale gövdesi olsun. Yalnızca eklenti döndürme. "
            "GORSEL, ANAHTAR, ACIKLAMA satırı ve kod bloğu yazma."
        )
    return f"""Sen aynı makaleyi tamamlayan Türkçe blog editörüsün. Yalnızca eksik kalan yerleri tamamla. Dolgu yazma.

BAŞLIK: {t['title']}
MAKALE TİPİ: {t['tip']}
BEKLENEN YAPI: {cfg['yapi']}
DURUM: {durum}

UZUNLUK:
- Şu an yaklaşık {simdi} kelime. Yalnızca eksik kalan bölümleri ve yarım cümleleri tamamla; konu tamamsa sırf daha uzun olsun diye yeni paragraf yazma.
- Dolgu cümle, eş anlamlı tekrar, boş övgü ve aynı öğüdün yeni başlık altında yeniden sıralanması yasak. Her eklenen paragraf yeni bir durum, ayrım veya gerekçe taşısın.

YAPILACAKLAR:
1. Beklenen yapıdaki eksik ## ve ### bölümlerini yaz. Her ## bölümünde en az iki paragraf olsun. SSS cevapları kısa kalabilir; uzunluk karar gerekçesinden gelsin.
2. İnce kalan bölümü derinleştir: somut kullanım durumu, kime uyar, kime uymaz, ürün verisindeki artı ve eksi. Veride olmayan ölçü, fiyat, puan, süre veya "denedim" iddiası ekleme.
3. Yarım kalmış cümleyi tamamla. Var olan ## başlık satırlarını koru. Mevcut aff:// linklerini ve ürün id'lerini koru. Eksik ürün linkini [Satın Al: ÜRÜN ADI](aff://ÜRÜN_ID) biçiminde, yalnızca listedeki id ile ekle.
4. Yeni ürün veya marka ekleme. Fiyat, TL veya ₺ yazma.
5. Doğal konuşma Türkçesi. Dolgu cümle yazma.
6. {cikti}

KULLANABİLECEĞİN ÜRÜNLER:
{_urun_bloku(prods)}

YAZIM REHBERİ:
{guide}

<<<TASLAK
{taslak}
TASLAK>>>
"""


def uzat_taslak(body, t, prods, guide, key, models, model_idx, finish_reason, hak=DEVAM_HAKKI):
    """Alt sınırın altında veya MAX_TOKENS ise en fazla hak kadar devam çağrısı."""
    reason = finish_reason or ""
    kalan = hak
    while kalan > 0 and genisletme_gerekli(body, t["tip"], reason):
        kalan -= 1
        once = len((body or "").split())
        etiket = "kesik" if reason == "MAX_TOKENS" else "kısa"
        print(f"  {etiket} ({once} kelime, güvenlik tabanı {GUVENLIK_TABANI}); eksik bölümler tamamlanıyor")
        raw = _gemini(devam_prompt(body, t, prods, guide, reason), key, models, model_idx)
        reason = getattr(raw, "finish_reason", "") or ""
        ek = ym.validate(govde_ayikla(raw), prods)
        birlesik = birlestir_taslak(body, ek)
        if len(birlesik.split()) <= once:
            print("  devam metni uzamadı")
            break
        body = birlesik
        print(
            f"  devam sonrası {len(body.split())} kelime, finish={reason or 'STOP'}"
            f"{ym.dusunce_notu(getattr(raw, 'usage', None))}")
    return body


def uret(t, products, key, models, model_idx, ukey, log, draft, tarih):
    pool = _urun_haritasi(products)
    eksik = [i for i in t["ids"] if i not in pool]
    if eksik:
        return None, f"ürün kimliği bulunamadı: {', '.join(eksik)}"
    prods = [pool[i] for i in t["ids"]]
    dogrulanmayan = [p["id"] for p in prods if not urun_denetim.dogrulanmis_mi(p)]
    if dogrulanmayan:
        return None, f"doğrulanmamış ürün: {', '.join(dogrulanmayan)}"
    if len(prods) < _gerekli_urun(t["tip"]):
        return None, f"yeterli doğrulanmış ürün yok ({len(prods)}/{_gerekli_urun(t['tip'])})"
    sugg = suggestions(t["sub_name"])
    if t.get("sorgu"):
        sugg = [t["sorgu"]] + [s for s in sugg if s.lower() != t["sorgu"].lower()]
    others = existing_shingles()
    guide, banned = load_guide()
    why = "bilinmiyor"
    alt_sinir = GUVENLIK_TABANI
    for attempt in range(2):
        raw = _gemini(build_prompt(t, prods, sugg, guide), key, models, model_idx)
        reason = getattr(raw, "finish_reason", "") or ""
        if not str(raw).strip():
            why = "boş çıktı" + (" (MAX_TOKENS)" if reason == "MAX_TOKENS" else "")
            continue
        parsed = parse(raw)
        if not parsed and reason == "MAX_TOKENS":
            print("  kesik çıktı (MAX_TOKENS); üst bilgiyle birlikte tamamlanıyor")
            raw = _gemini(
                devam_prompt(str(raw), t, prods, guide, reason, tam_bicim=True),
                key, models, model_idx)
            reason = getattr(raw, "finish_reason", "") or ""
            parsed = parse(raw)
        if not parsed:
            why = "çıktı biçimi bozuk" + (" (MAX_TOKENS)" if reason == "MAX_TOKENS" else "")
            continue
        meta, body = parsed
        body = ym.validate(body, prods)
        if reason == "MAX_TOKENS" or len(body.split()) < alt_sinir:
            print(
                f"  taslak {len(body.split())} kelime, finish={reason or 'STOP'}"
                f"{ym.dusunce_notu(getattr(raw, 'usage', None))}")
        body = uzat_taslak(body, t, prods, guide, key, models, model_idx, reason)
        if len(body.split()) < alt_sinir:
            why = gate(body, t["tip"], prods, others, banned)
            continue
        edited_raw = _gemini(edit_prompt(body, prods, guide, alt_sinir), key, models, model_idx)
        edited = ym.validate(re.sub(r"^```(?:markdown)?\s*|\s*```$", "", edited_raw.strip()), prods)
        if len(edited.split()) >= 0.85 * len(body.split()):
            why = gate(edited, t["tip"], prods, others, banned)
            if not why:
                body = edited
                break
        why = gate(body, t["tip"], prods, others, banned) or None
        if not why:
            break
    else:
        return None, why
    img = unsplash(meta["GORSEL"], CAT_EN.get(t["cat"], "hobby"), set(log["photos"]), ukey)
    if not img:
        return None, "konuyla eşleşen Unsplash görseli bulunamadı"
    log["photos"].append(img["id"])
    slug, n, tarih = write_article(t, meta, body, img, draft, tarih)
    # Makale diske yazıldığı anda log da yazılır; sonraki madde düşse de bu kayıt kalır.
    makale_kaydi_ekle(log, t["key"], slug, tarih)
    save_log(log)
    return (slug, n, bool(img), tarih), None


def _kota_mesaji(exc, yedek_acik, made):
    print("Günlük Gemini kotası doldu. Kalan konular bugün yazılmadı.")
    print(exc)
    if not yedek_acik:
        print("GEMINI_MODEL_YEDEK yok. Öneri: gemini-flash-lite-latest veya AI Studio'daki güncel flash.")
    else:
        print("Tanımlı modellerin günlük kotası doldu. Kota Pasifik gece yarısında sıfırlanır.")
    print("Eksik API anahtarı bu yol değildir; anahtar yoksa iş kırmızı biter.")
    print("Schedule kırmızı görünmesin diye çıkış kodu 0.")
    if made:
        print(f"Kota dolmadan {made} makale yazıldı; site üretimi devam edebilir.")


def _gecici_mesaji(exc, made):
    print("Gemini geçici olarak yanıt vermedi (503/UNAVAILABLE, zaman aşımı, bağlantı veya 429).")
    print(exc)
    print("Bitmiş makaleler diskte ve logda. Sonraki zamanlanmış çalışma kalanı dener.")
    print("Geçici API sorunu; çıkış kodu 0.")
    if made:
        print(f"Hata öncesinde {made} makale yazıldı.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adet", type=int, default=GUNLUK_HEDEF)
    ap.add_argument("--yayinla", action="store_true", help="taslak yerine yayına hazır yaz")
    ap.add_argument("--taslak", action="store_true")
    ap.add_argument("--konu-listesi", action="store_true")
    a = ap.parse_args()

    ym.load_env()
    log = load_log()
    bugun = istanbul_bugun().isoformat()
    if not a.konu_listesi:
        a.adet, plan_mesaj = kosu_plani(a.adet, log, bugun)
        for satir in plan_mesaj:
            print(satir)
        if a.adet <= 0:
            return

    products, cats = ym.load("products.json"), ym.load("categories.json")
    have = {fn[:-3] for fn in os.listdir(ARTICLES)} if os.path.isdir(ARTICLES) else set()
    fails = {}
    for x in log["atlanan"]:
        fails[x["anahtar"]] = fails.get(x["anahtar"], 0) + 1
    done_keys = set(done_anahtarlari(log))
    done_sorgu = {k.rsplit(":", 1)[-1] for k in done_keys if k.count(":") >= 3}
    queue = [t for t in topic_queue(products, cats, log=log)
             if t["key"] not in done_keys and ym.slugify(t["title"]) not in have
             and t.get("sorgu_slug") not in done_sorgu and fails.get(t["key"], 0) < 2]

    if a.konu_listesi:
        print(f"Kuyrukta {len(queue)} konu. Sıradakiler:")
        for t in queue[:12]:
            print(f"  [{t['tip']}] {t['title']}")
        return

    draft_env = os.environ.get("TASLAK_MODU", "false").strip().lower() not in ("false", "0", "hayir", "hayır")
    draft = False if a.yayinla else (True if a.taslak else draft_env)
    key, ukey = os.environ.get("GEMINI_API_KEY"), os.environ.get("UNSPLASH_ACCESS_KEY")
    if not key:
        sys.exit("GEMINI_API_KEY yok.")
    if not ukey:
        print("! UNSPLASH_ACCESS_KEY yok: makaleler kategori görseliyle çıkacak.")
    models, yedek_acik = _modeller()
    model_idx = [0]
    if not yedek_acik:
        ekstra = ", ".join(models[1:]) or "yok (ana modelle aynı)"
        print("GEMINI_MODEL_YEDEK tanımlı değil. Günlük kotada yerleşik yedek: " + ekstra)
        print("Kalıcı ayar: GitHub variable GEMINI_MODEL_YEDEK=gemini-flash-lite-latest")
        print("Ana model zaten buysa AI Studio'daki güncel flash adını yedek olarak yaz.")

    made, tried = 0, 0
    # Kalite kapısı eleyen taslakları atlayıp günlük hedefi tutturmak için konu payı.
    for t in queue:
        if made >= a.adet or tried >= max(GUNLUK_HEDEF, a.adet * 4):
            break
        tried += 1
        print(f"→ {t['title']}")
        try:
            res, why = uret(t, products, key, models, model_idx, ukey, log, draft, bugun)
        except ym.GeminiError as e:
            save_log(log)
            if isinstance(e, ym.GeminiQuotaError):
                _kota_mesaji(e, yedek_acik, made)
                return
            if gecici_api_hatasi(e):
                _gecici_mesaji(e, made)
                return
            sys.exit(f"API hatası, durduruldu: {e}")
        if res:
            slug, n, has_img, tarih = res
            makale_kaydi_ekle(log, t["key"], slug, tarih)
            made += 1
            save_log(log)
            print(f"  ✓ {slug}  ({n} kelime, {'taslak' if draft else 'yayın'}, görsel: {'Unsplash' if has_img else 'kategori'})")
            sub = "" if t.get("sub") in (None, "", "_main") else t["sub"]
            ctas = deeplink.shop_ctas_for(t["cat"], sub)
            if ctas["links"]:
                print("  ✓ mağaza CTA: " + ", ".join(c["label"] for c in ctas["links"]))
        else:
            log["atlanan"].append({"anahtar": t["key"], "neden": why, "tarih": bugun})
            save_log(log)
            print(f"  ✗ atlandı: {why}")
    save_log(log)
    print(f"Bitti: {made} makale ({'TASLAK — onay bekliyor' if draft else 'yayına hazır'}).")


if __name__ == "__main__":
    main()
