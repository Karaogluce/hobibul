#!/usr/bin/env python3
"""Hobi Bul — günlük otomatik makale hattı.

  python otomatik.py                  # bugünün kalanını üret (hedef 3, Europe/Istanbul)
  python otomatik.py --adet 2         # en fazla 2; günlük kalan daha azsa o kadar
  python otomatik.py --adet 2 --yayinla
  python otomatik.py --konu-listesi   # sıradaki konuları göster (API çağırmaz)

Akış: konu seç → Google Autocomplete'ten gerçek Türkçe sorguları çek → Gemini ile yaz
(yalnızca products.json verisiyle) → kısa veya MAX_TOKENS ile kesik taslakta eksik
bölümleri tamamlayan devam çağrısı → kalite kapıları → Unsplash görselini yerel webp'ye indir → .md yaz.
Kapıdan geçemeyen makale YAYINLANMAZ, content/uretim_log.json'a işlenir.

Günlük hedef: İstanbul takvim gününde 3 makale. Sayı logdaki tarih kayıtlarından gelir.
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
STATIC = os.path.join(ym.BASE, "static")
LOG_PATH = os.path.join(CONTENT, "uretim_log.json")
POOL_PATH = os.path.join(CONTENT, "konu_havuzu.json")
GUNLUK_HEDEF = 3
TAMAM_MESAJI = "Bugünün 3 makalesi tamam"
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
    "talep": dict(
        hedef=1500, hepsi=False, taban=1500,
        baslik=lambda s: s,
        yapi="Giriş (aranan sorguyu ilk iki cümlede doğal Türkçeyle cevapla) → '## Ne Arıyor, Ne İşe Yarar?' → "
             "'## Seçerken Nelere Bakmalı?' → '## Ürün Ürün Karşılaştırma' altında her ürün için ### başlık, artı, eksi ve kime uymaz → "
             "'## Sık Yapılan Hatalar' → '## Sık Sorulan Sorular' (en az 4 soru, ### başlık) → kapanışta tek cümlelik net tavsiye "
             "('Sonuç' başlığı kullanma). Kategori sayfasına bir iç link ve en az 2 aff:// ürün linki ver.",
    ),
}
ESKI_TIPLER = ("rehber", "yeni_baslayan", "hatalar", "sss")
TICARI_TIP = "ticari"

# Aynı alt kategoride başlık düzeyinde yakın konu eşiği. Makale gövdesi
# shingle kontrolünden ayrıdır; konu üretilmeden önce eler.
# Kısa başlıklarda kelime Jaccard. Uzun şablonlar alt kategori adını
# paylaştığı için birbirine bu eşikle kıyaslanmaz; onların çakışması
# ilk üç kelimenin aynı olmasıyla yakalanır.
BENZER_BASLIK_ESIK = 0.35
BENZER_KISA_BASLIK = 6
BENZER_KISA_KARSIT = 8
TR_KUCUK = str.maketrans("ÇĞİÖŞÜI", "çğiöşüı")
_ASCII = str.maketrans("çğıöşüı", "cgiosui")
# Jaccard'da gürültü. "nasıl" ve "seti" durur; yoksa yakın nasıl soruları kaçardı.
_JACCARD_STOP = {
    "en", "iyi", "yeni", "ilk", "icin", "ile", "ve", "bir", "bu",
    "rehber", "rehberi", "hakkinda", "baslayanlar", "alinacaklar",
    "olan", "olarak", "daha", "cok", "gibi", "kadar",
}
# Otomatik tamamlamadan kalan bozuk başlıklar: sonda/ortada "adı", tek başına "ai".
_BOZUK_ARTEFAKT = re.compile(r"(?:^|\s)(?:ai|ad[ıi]|ismi)(?:\s|$)", re.I)

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
        # Arama-talebi makaleleri günlük 3'lük tavana yazılmaz; kendi kotası vardır.
        if not anahtar or anahtar.startswith("talep:") or anahtar in seen:
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


def _baslik_kelimeleri(text):
    """Sıralı kelime listesi. Türkçe karakterler ve slug ASCII'si aynı gövdeye iner."""
    low = str(text or "").translate(TR_KUCUK).lower().translate(_ASCII)
    return [w for w in re.findall(r"[a-z0-9]+", low) if len(w) > 1]


def _kelime_jaccard(a, b):
    def sade(words):
        return {w for w in words if w not in _JACCARD_STOP} or set(words)
    sa, sb = sade(a), sade(b)
    return len(sa & sb) / len(sa | sb) if sa | sb else 0.0


def baslik_bozuk(title):
    """Yayınlanmayacak başlık. Uygunsa None, değilse kısa neden.

    Havuz sorgusu küçük harfle gelir; bu kontrol `dogal_baslik` sonrası
    üretilmiş başlığa uygulanır. Küçük harfle başlayan, çok kısa ya da
    otomatik tamamlama artığı ('ai', 'adı') başlıklar elenir.
    """
    s = re.sub(r"\s+", " ", str(title or "")).strip().strip("\"'")
    if not s:
        return "bos"
    ilk = s[0]
    if ilk.isalpha() and ilk == ilk.lower():
        return "kucuk-harf"
    if _BOZUK_ARTEFAKT.search(s.translate(TR_KUCUK).lower()):
        return "artefakt"
    kelimeler = re.findall(r"[A-Za-z0-9çğıöşüÇĞİÖŞÜâîûÂÎÛ]+", s)
    if len(kelimeler) < 3 or len(s) < 12:
        return "kisa"
    return None


def _baslik_cakisiyor(aday, mevcutlar):
    """Aday başlık, yayındaki veya bu turda kabul edilmiş bir konuyla örtüşüyor mu?"""
    if not aday:
        return False
    for diger in mevcutlar:
        if not diger:
            continue
        if len(aday) >= 3 and len(diger) >= 3 and aday[:3] == list(diger)[:3]:
            return True
        # Kısa sorular (nasıl kurulur / nasıl sökülür). Uzun şablonlar
        # alt kategori adını paylaştığı için bu kıyasa girmez.
        if (len(aday) <= BENZER_KISA_BASLIK and len(diger) <= BENZER_KISA_KARSIT
                and _kelime_jaccard(aday, diger) >= BENZER_BASLIK_ESIK):
            return True
    return False


def _kuyruk_basligi_uygun(title, mevcutlar, rapor=None, etiket=""):
    """Başlık kuyruğa girebilir mi? Giremezse rapora yazar ve False döner."""
    neden = baslik_bozuk(title)
    if neden:
        if rapor is not None:
            rapor["bozuk_baslik"] = rapor.get("bozuk_baslik", 0) + 1
            ornek = rapor.setdefault("bozuk_ornek", [])
            if len(ornek) < 20:
                ornek.append(f"{etiket} ({neden})" if etiket else f"{title} ({neden})")
        return False
    kelimeler = _baslik_kelimeleri(title)
    if _baslik_cakisiyor(kelimeler, mevcutlar):
        if rapor is not None:
            rapor["benzer"] = rapor.get("benzer", 0) + 1
            ornek = rapor.setdefault("ornek", [])
            if len(ornek) < 20:
                ornek.append(etiket or title)
        return False
    return True


def _makale_baslik_kumeleri(articles_dir=None):
    """(kategori, alt kategori) -> yayınlanmış başlık ve slug kelime listeleri."""
    out = {}
    for m in urun_denetim.makale_verileri(articles_dir or ARTICLES):
        cat = str(m.get("kategori") or "").strip()
        sub = str(m.get("alt") or "").strip() or "_main"
        if not cat:
            continue
        for kaynak in (m.get("baslik"), str(m.get("slug") or "").replace("-", " ")):
            kume = _baslik_kelimeleri(kaynak)
            if kume:
                out.setdefault((cat, sub), []).append(kume)
    return out


def _urun_haritasi(products):
    try:
        return urun_denetim.urun_haritasi(products)
    except urun_denetim.UrunVerisiHatasi as e:
        sys.exit(f"Ürün verisi hatası: {e}")


BRIEFS_PATH = os.path.join(CONTENT, "briefs", "kuyruk.json")
_BRIEF_CACHE = None


def load_brief_index():
    """Slug -> yazar brifi. Dosya yoksa boş döner; üretim brifsiz de çalışır."""
    global _BRIEF_CACHE
    if _BRIEF_CACHE is not None:
        return _BRIEF_CACHE
    idx = {}
    if os.path.exists(BRIEFS_PATH):
        try:
            with open(BRIEFS_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = []
        if isinstance(data, list):
            for b in data:
                if isinstance(b, dict) and b.get("slug"):
                    idx[str(b["slug"])] = b
    _BRIEF_CACHE = idx
    return idx


def _brief_kaydi(e):
    """Havuz kaydının üstüne content/briefs/kuyruk.json alanlarını yazar."""
    if not isinstance(e, dict):
        return e or {}
    key = str(e.get("brief") or e.get("slug") or "").strip()
    b = load_brief_index().get(key) if key else None
    if not b:
        return e
    out = dict(e)
    for alan in (
        "h1", "slug", "meta_title", "meta_description", "oncelik", "yasak",
        "zorunlu_linkler", "terimler", "brief_dosya", "brief_baslik", "focus_keyword",
    ):
        if b.get(alan) not in (None, "", []):
            out[alan] = b[alan]
    if not out.get("brief"):
        out["brief"] = b.get("slug")
    if b.get("urunler") and not out.get("urunler"):
        out["urunler"] = b["urunler"]
    return out


def _konu_ekleri(kayit, e):
    if isinstance(e.get("oncelik"), int):
        kayit["oncelik"] = e["oncelik"]
    if e.get("brief"):
        kayit["brief"] = e["brief"]
    slug = str(e.get("slug") or "").strip()
    if slug:
        kayit["slug"] = slug
    for alan in ("meta_title", "meta_description", "yasak", "zorunlu_linkler", "terimler", "focus_keyword"):
        if e.get(alan):
            kayit[alan] = e[alan]
    return kayit


def _brief_metni(b):
    dosya = str((b or {}).get("brief_dosya") or "").strip()
    if not dosya:
        return ""
    path = dosya if os.path.isabs(dosya) else os.path.join(CONTENT, "briefs", dosya)
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    bas = str(b.get("brief_baslik") or "").strip()
    if not bas:
        return text.strip()
    i = text.find(bas)
    if i < 0:
        return ""
    rest = text[i:]
    nxt = rest.find("\n# Brief #", 8)
    return (rest if nxt < 0 else rest[:nxt]).strip()


def _brief_prompt(t):
    key = str(t.get("brief") or "").strip()
    b = load_brief_index().get(key) if key else None
    if not b and not key:
        return ""
    b = b or {}
    terimler = t.get("terimler") or b.get("terimler") or []
    yasak = t.get("yasak") or b.get("yasak") or []
    linkler = t.get("zorunlu_linkler") or b.get("zorunlu_linkler") or []
    if isinstance(terimler, str):
        terimler = [terimler]
    if isinstance(yasak, str):
        yasak = [yasak]
    if isinstance(linkler, str):
        linkler = [linkler]
    ham = _brief_metni(b)
    satirlar = [
        "YAZAR BRİFİ (bu konu için bağlayıcıdır; tip şablonuyla çelişirse brif kazanır):",
        f"- H1 olarak şu başlık kullanılacak, gövdede H1 yazma: {t.get('title') or b.get('h1') or ''}",
        f"- Slug sabit: {t.get('slug') or b.get('slug') or ''}. Başlıktan başka slug üretme. URL'ye yıl ekleme.",
        f"- Meta title: {t.get('meta_title') or b.get('meta_title') or ''}",
        f"- Meta description: {t.get('meta_description') or b.get('meta_description') or ''}",
        "- Hedef terimler: " + "; ".join(str(x) for x in terimler),
        "- Yasak: " + ("; ".join(str(x) for x in yasak) if yasak else "(yok)"),
        "- Zorunlu iç linkler (doğal cümlede, tam yol): " + (", ".join(str(x) for x in linkler) if linkler else "(yok)"),
        "- Her ana bölümün hemen altında, soruya 40-60 kelimelik doğrudan cevabı `> ` ile başlayan tek satır olarak yaz.",
        "- SSS başlığı birebir `## Sıkça Sorulan Sorular` olsun. Tip şablonundaki 'Sık Sorulan Sorular' ifadesini bununla değiştir.",
        "- Her SSS sorusu `**soru**` biçiminde olsun; altında cevap paragrafı gelsin. Soruyu ### başlık yapma.",
        "- Brifteki H2/H3 planını izle. Brifteki AEO kısa cevaplarını kendi cümlelerinle yaz; rakip metin kopyalama.",
        "- Brif ham metninde fiyat, puan, stok veya uydurma ölçü geçse bile yazma.",
    ]
    if ham:
        satirlar.append("HAM BRİF:\n" + ham)
    liste = _oyun_listesi_satiri(b)
    if liste:
        satirlar.append(liste)
    return "\n".join(satirlar) + "\n\n"


def _oyun_listesi_satiri(brief):
    """Kutu oyunu brifleri yalnızca doğrulanmış Türkiye listesini kullanır."""
    rel = str((brief or {}).get("oyun_listesi") or "").strip()
    if not rel:
        return ""
    path = rel if os.path.isabs(rel) else os.path.join(CONTENT, rel)
    if not os.path.exists(path):
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return ""
    grup = str(brief.get("oyun_grup") or "").strip()
    satirlar = [
        "TÜRKİYE KUTU OYUNU LİSTESİ (bağlayıcı): yalnızca bu oyunlar. Kişi, süre ve yaş bu kayıttan. Listede olmayan oyunu yazma. Kesik cümle ve 'fiyat yok' tekrarı yok.",
    ]
    for g in data.get("oyunlar") or []:
        if grup and grup not in (g.get("grup") or []):
            continue
        satirlar.append(
            f"- {g.get('ad')} | kişi {g.get('oyuncu')} | süre {g.get('sure')} | yaş {g.get('yas')} | "
            f"satın al: [Satın Al: {g.get('ad')}]({g.get('url')}) | {g.get('ozet')}"
        )
    satirlar.append(
        "Satın alma linki yukarıdaki Neo Troy ürün sayfası olsun. aff:// ve Amazon arama linki yazma. "
        "rel elle yazma; build nofollow ekler."
    )
    return "\n".join(satirlar)


def havuz_konulari(products, c, pool, used, basliklar=None, rapor=None):
    """Havuzdaki ticari olmayan konular. Ürün eşiği doğrulanmış ürünlerle sayılır.

    `basliklar` aynı alt kategoride kuyrukta/yayında olan başlık kelime listelerini
    taşır. Yakın veya bozuk başlık kuyruğa girmez; üretim başka konuya kalır.
    """
    items = []
    basliklar = basliklar if basliklar is not None else {}
    subs = {s["id"]: s["name"] for s in c["subcategories"]}
    for e in pool:
        if not _havuz_uygun(e):
            continue
        e = _brief_kaydi(e)
        tip, sub = e.get("tip_onerisi"), e.get("alt")
        if tip not in TIPLER or tip == TICARI_TIP or e.get("kategori") != c["id"] or sub not in subs:
            continue
        sorgu = re.sub(r"\s+", " ", str(e.get("sorgu", ""))).strip()
        gevsek = isinstance(e.get("oncelik"), int) or bool(e.get("brief"))
        if not sorgu or (not gevsek and cop_mu(sorgu)):
            continue
        title = str(e.get("h1") or "").strip() or dogal_baslik(sorgu)
        plist = _plist_for_entry(products, c["id"], sub, e, tip)
        if len(plist) < _gerekli_urun(tip):
            continue
        sslug = str(e.get("slug") or "").strip() or ym.slugify(sorgu)
        if not sslug or sslug in used:
            continue
        # Ticari olmayan her tip aynı elekten geçer. Yakın konu kuyruğa
        # girmez; tur, başka alt kategorideki veya başka tipten konuya kalır.
        if not _kuyruk_basligi_uygun(title, basliklar.get(sub, ()), rapor, f"{c['id']}/{sub}: {sorgu}"):
            continue
        used.add(sslug)
        sorgu_slug = ym.slugify(sorgu)
        if sorgu_slug:
            used.add(sorgu_slug)
        kayit = dict(
            key=f"{tip}:{c['id']}:{sub}:{sslug}", tip=tip, cat=c["id"], cat_name=c["name"],
            sub=sub, sub_name=subs[sub], ids=[p["id"] for p in plist],
            title=title, sorgu=sorgu, sorgu_slug=sorgu_slug or sslug, kaynak="havuz")
        _konu_ekleri(kayit, e)
        items.append(kayit)
        basliklar.setdefault(sub, []).append(_baslik_kelimeleri(title))
    return items


def _gecerli_urunler(products, ids):
    """Öncelikli konuda ASIN'i olmayan ama arama linki kurulabilen ürünler."""
    try:
        harita = _urun_haritasi(products)
    except SystemExit:
        return []
    gorulen, out = set(), []
    for rid in ids:
        rid = str(rid).strip()
        if not rid or rid in gorulen:
            continue
        rec = harita.get(rid)
        if rec is not None and urun_denetim.gecerli_mi(rec):
            gorulen.add(rid)
            out.append(rec)
    return out


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


def _plist_for_entry(products, cat_id, sub, e, tip):
    """Brifli konuda listelenen ürünler; ASIN yoksa arama linki kurulabilen kayıt yeter."""
    wanted = [str(x).strip() for x in (e.get("urunler") or []) if str(x).strip()]
    gevsek = isinstance(e.get("oncelik"), int) or bool(e.get("brief"))
    if wanted:
        plist = _urun_bul(products, wanted)
        if gevsek and len(plist) < _gerekli_urun(tip):
            plist = _gecerli_urunler(products, wanted)
        return plist
    return urun_denetim.alt_kategori_urunleri(products, cat_id, sub)


def ticari_konulari(products, c, pool, used):
    """Havuzdaki ticari niyetli konular, sonra her alt kategori için başlangıç seti."""
    items = []
    subs = {s["id"]: s["name"] for s in c["subcategories"]}

    def ekle(tip_key, sub, sub_name, plist, title, sorgu, kaynak, e=None):
        e = e or {}
        gevsek = isinstance(e.get("oncelik"), int) or bool(e.get("brief"))
        if not gevsek and cop_mu(sorgu or title):
            return
        sslug = str(e.get("slug") or "").strip() or ym.slugify(sorgu or title)
        if not sslug or sslug in used:
            return
        if len(plist) < _gerekli_urun(TICARI_TIP):
            return
        used.add(sslug)
        sorgu_slug = ym.slugify(sorgu or title)
        if sorgu_slug:
            used.add(sorgu_slug)
        kayit = dict(
            key=tip_key, tip=TICARI_TIP, cat=c["id"], cat_name=c["name"],
            sub=sub, sub_name=sub_name, ids=[p["id"] for p in plist],
            title=title, sorgu=sorgu, sorgu_slug=sorgu_slug or sslug, kaynak=kaynak)
        _konu_ekleri(kayit, e)
        items.append(kayit)

    for ham in pool:
        if not _havuz_uygun(ham):
            continue
        e = _brief_kaydi(ham)
        if e.get("tip_onerisi") != TICARI_TIP or e.get("kategori") != c["id"]:
            continue
        sub = e.get("alt")
        if sub not in subs:
            continue
        sorgu = re.sub(r"\s+", " ", str(e.get("sorgu", ""))).strip()
        if not sorgu:
            continue
        title = str(e.get("h1") or "").strip() or dogal_baslik(sorgu)
        plist = _plist_for_entry(products, c["id"], sub, e, TICARI_TIP)
        ekle(f"ticari:{c['id']}:{sub}:{str(e.get('slug') or '').strip() or ym.slugify(sorgu)}",
             sub, subs[sub], plist, title, sorgu, "havuz", e)
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


def topic_queue(products, cats, log=None, articles_dir=None, rapor=None):
    """Kategori/alt kategori grupları arasında adil, deterministik üretim sırası.

    Önce ticari niyet, sonra havuzun diğer tipleri ve başlangıç setleri. Konusu
    olmayan alt kategori kuyruğa girmez; her grup tur başına bir konu verir.
    """
    pool, used = load_pool(), set()
    makale_sayisi = _makale_gruplari(articles_dir)
    yayin_basliklari = _makale_baslik_kumeleri(articles_dir)
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
        basliklar = {sid: list(yayin_basliklari.get((c["id"], sid), ()))
                     for sid, _ in subs}
        uygun = []
        for t in items:
            sub = t.get("sub")
            etiket = f"{c['id']}/{sub}: {t.get('title')}"
            if not _kuyruk_basligi_uygun(t.get("title"), basliklar.get(sub, ()), rapor, etiket):
                continue
            basliklar.setdefault(sub, []).append(_baslik_kelimeleri(t.get("title")))
            uygun.append(t)
        items = uygun + havuz_konulari(products, c, pool, used, basliklar=basliklar, rapor=rapor)
        yerliler = {}
        for t in sorted(items, key=lambda x: 0 if x.get("kaynak") == "havuz" else 1):
            yerliler.setdefault(t["sub"], []).append(t)
        for sub, konular in yerliler.items():
            gruplar.append(dict(cat=c["id"], sub=sub, konular=konular))
    sira = _adil_sira(gruplar, makale_sayisi, son_uretim)
    # oncelik alanı olan havuz kayıtları adil sıranın önüne alınır.
    # Yılbaşı gibi tarihli konular küçük sayıyla en öne yazılır.
    oncelikli = [t for t in sira if isinstance(t.get("oncelik"), int)]
    diger = [t for t in sira if not isinstance(t.get("oncelik"), int)]
    oncelikli.sort(key=lambda t: (t["oncelik"], t.get("key") or ""))
    return oncelikli + diger


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


def _yayin_tabani(tip):
    """Kapı alt sınırı. Arama-talebi dışında güvenlik tabanı değişmez."""
    return int(TIPLER.get(tip, {}).get("taban") or GUVENLIK_TABANI)


def _urun_bloku(prods):
    return "\n".join(
        f"- id: {p['id']}\n  ad: {p['name']}\n  marka: {p.get('brand','')}\n  açıklama: {p.get('desc','')}\n"
        f"  artılar: {'; '.join(p.get('pros', []))}\n  eksiler: {'; '.join(p.get('cons', []))}"
        + (f"\n  yazarın notu: {p['not']}" if p.get('not') else "") for p in prods)


def _wondershare_kural(t):
    """Eşleşen konuda model, Filmora adresini yazmasın; düğme build'de gelir."""
    sub = t.get("sub") if t.get("sub") not in (None, "", "_main") else ""
    try:
        blok = deeplink.shop_ctas_for(t.get("cat"), sub)
    except Exception:
        return ""
    offers = blok.get("offers") or []
    if not offers:
        return ""
    adlar = ", ".join(o["label"] for o in offers)
    return (
        f"9. Bu konuya build sırasında şu düğme eklenir: {adlar}. "
        "wondershare.com, Admitad veya kjuzv.com adresi yazma. "
        "Filmora video düzenleme aracıdır; drone, fotoğraf makinesi veya DJ kontrol cihazının yerine koyma.\n"
    )


def build_prompt(t, prods, sugg, guide=""):
    cfg = TIPLER[t["tip"]]
    plist = _urun_bloku(prods)
    hedef = t.get("hedef") or kelime_hedef(t["tip"])
    sq = "\n".join(f"- {s}" for s in sugg) or "- (sorgu bulunamadı; konuyla ilgili doğal sorular kullan)"
    zorunlu = ("HER ÜRÜN için en az bir kez" if cfg["hepsi"] else "en az 2 ürün için")
    tablo_kurali = "Paket bölümündeki markdown tablo serbest; başka tablo yok." if t["tip"] == TICARI_TIP else "Tablo kullanma."
    alt_yol = f"/kategori/{t['cat']}/{t['sub']}/" if t.get("sub") and t["sub"] != "_main" else f"/kategori/{t['cat']}/"
    if t["tip"] == "talep":
        uzunluk = (
            f"- En az {hedef} kelime yaz. Sorguyu ilk paragrafta doğal Türkçeyle cevapla; kelimeyi doldurmak için aynı öğüdü tekrarlama.\n"
            "- En az 6 adet \"## \" bölümü yaz. Her ## bölümünde en az iki paragraf olsun.\n"
            "- '## Sık Sorulan Sorular' altında en az 4 soru olsun; her soru ### başlık.\n"
            f"- Kategoriye bir iç link ver: [{t['sub_name']}]({alt_yol})\n"
            "- Başka bir rehber doğal düşüyorsa /makale/... iç linki de kullan.\n"
            "- Her bölüm yeni bir ayrım taşısın: kime uyar, kime uymaz, hangi durumda hangi parça."
        )
    else:
        uzunluk = (
            f"- Yaklaşık {hedef} kelime yeterli. Konu tamamlandığında sırf kelime sayısını artırmak için uzatma; gereksiz genel bilgi, tekrar ve dolgu cümle yazma.\n"
            "- En az 4 adet \"## \" bölümü yaz; her ## bölümünde en az iki paragraf olsun.\n"
            "- Her bölümü somut bir durumdan aç. Gerekçeyi ürün verisine bağla. Aynı öğüdü yeni başlık altında tekrarlama."
        )
    ws_kural = _wondershare_kural(t)
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
{uzunluk}

İNSANLARIN GERÇEKTEN ARADIĞI SORGULAR (uygun olanları başlıklara ve SSS bölümüne doğal biçimde yedir; zorlama ya da tekrar yapma):
{sq}

KULLANABİLECEĞİN ÜRÜNLER (başka ürün, marka veya model ekleme):
{plist}

KESİN KURALLAR:
1. Ürün verilerinde olmayan teknik özellik, ağırlık, ölçü, fiyat, puan, test sonucu veya "denedik" iddiası UYDURMA. Emin olmadığın bilgiyi yazma.
2. Fiyat yazma. Gerekirse "güncel fiyatı Amazon'da kontrol et" de.
3. Ürün linkini şu biçimde ver ({zorunlu}): [Satın Al: ÜRÜN ADI](aff://ÜRÜN_ID)
4. Yalnızca Markdown. En üstte H1 yok. {tablo_kurali} ## ve ### başlıkları, nefes alan paragraflar ve gerektiğinde madde listesi kullan.
5. Doğal, samimi, abartısız Türkçe. Konuşur gibi yaz: cümleler birbirine bağlansın, uzunlukları değişsin. Art arda tek yargı dizme. Aynı öğüdü yeni başlıkta tekrarlama. "Fiyat yok", "puan yok", "kapakta yazıyor", "bu yazı uzamaz" gibi meta cümle kurma; bilmediğin sayıyı yazma ve konuya dön. "Mükemmel", "piyasa lideri", "kesinlikle", "garanti" gibi kanıtsız iddialar yok.
6. Başka sitelerden metin alma; kalıp cümleleri tekrarlama.
7. Yabancı dilde paragraf yazma. İl adı, "nedir" tanımı veya "nasıl yazılır" konusu açma.
8. AliExpress, Geekbuying, Wondershare, Trendyol veya Hepsiburada adresi yazma. Bu mağaza düğmeleri, kategori eşleşirse sayfaya build sırasında eklenir. Ürün linki yalnızca aff:// biçiminde olsun.
{ws_kural}{ticari_ek}
YAZIM REHBERİ (bunu uygula; okuyucuya bir insanın konuşur gibi yazdığı gelsin, ama kimseyi yanıltma):
{guide}

{_brief_prompt(t)}ÇIKTI BİÇİMİ (tam olarak böyle):
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
    taban = _yayin_tabani(tip)
    if words < taban:
        return f"kısa ({words} kelime, güvenlik tabanı {taban})"
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


def gorsel_indir(url, slug):
    """Unsplash görselini 1600 px webp olarak static/img/makale/<slug>.webp'ye indir."""
    if not url or not slug:
        return None
    hedef = os.path.join(STATIC, "img", "makale", slug + ".webp")
    ayrac = "&" if "?" in url else "?"
    indirme = url + ayrac + urllib.parse.urlencode(
        {"fm": "webp", "w": 1600, "q": 80, "fit": "max"})
    try:
        with urllib.request.urlopen(
                urllib.request.Request(indirme, headers=UA), timeout=30) as r:
            veri = r.read()
        if len(veri) < 2048 or veri[:4] != b"RIFF" or veri[8:12] != b"WEBP":
            raise ValueError("geçerli webp değil")
        os.makedirs(os.path.dirname(hedef), exist_ok=True)
        gecici = hedef + ".tmp"
        with open(gecici, "wb") as f:
            f.write(veri)
        os.replace(gecici, hedef)
        return "/img/makale/" + slug + ".webp"
    except Exception as e:
        print(f"  ! görsel indirilemedi ({slug}): {e}")
        return None


def unsplash(query, fallback, used, key, slug):
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
                id=ph["id"], url=gorsel_indir(ph["urls"]["raw"], slug),
                alt=(ph.get("alt_description") or q).replace('"', "'"),
                credit=u["name"], credit_url=u["links"]["html"] + "?utm_source=hobibul&utm_medium=referral")
    return None


# ------------------------------------------------------------------ yazma
def q(s):
    return str(s).replace('"', "'").replace("\n", " ").strip()


def write_article(t, meta, body, img, draft, tarih=None):
    slug = str(t.get("slug") or "").strip() or ym.slugify(t["title"])
    title = t["title"]
    raw_desc = q(t.get("meta_description") or meta.get("ACIKLAMA") or "")
    raw_mt = str(t.get("meta_title") or "").strip()
    if raw_mt:
        mt = fit_title(raw_mt if raw_mt.endswith("Hobi Bul") else f"{raw_mt} | Hobi Bul")
    else:
        mt = fit_title(title if title.endswith("Hobi Bul") else f"{title} | Hobi Bul")
    md = fit_description(raw_desc, extra=f"{q(meta.get('ANAHTAR') or title)} rehberi, yeni başlayan için ürün notlarıyla")
    tarih = tarih or istanbul_bugun().isoformat()
    lines = ["---", f'title: "{q(title)}"', f'slug: "{slug}"', f'category: "{t["cat"]}"',
             f'date: "{tarih}"', f'updated: "{tarih}"', f'meta_title: "{q(mt)}"',
             f'meta_description: "{q(md)}"', f'excerpt: "{raw_desc or q(md)}"',
             f'focus_keyword: "{q(t.get("focus_keyword") or meta.get("ANAHTAR") or title)}"']
    if img and img.get("url"):
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
    return len((body or "").split()) < _yayin_tabani(tip)


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
        print(f"  {etiket} ({once} kelime, güvenlik tabanı {_yayin_tabani(t['tip'])}); eksik bölümler tamamlanıyor")
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
    gevsek = isinstance(t.get("oncelik"), int) or bool(t.get("brief"))
    if gevsek:
        gecersiz = [p["id"] for p in prods if not urun_denetim.gecerli_mi(p)]
        if gecersiz:
            return None, f"geçersiz ürün: {', '.join(gecersiz)}"
    else:
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
        hak = 4 if t.get("tip") == "talep" else DEVAM_HAKKI
        body = uzat_taslak(body, t, prods, guide, key, models, model_idx, reason, hak=hak)
        if t.get("tip") == "talep":
            body = _talep_ic_link(body, t)
        if len(body.split()) < alt_sinir:
            why = gate(body, t["tip"], prods, others, banned)
            continue
        edited_raw = _gemini(edit_prompt(body, prods, guide, _yayin_tabani(t["tip"])), key, models, model_idx)
        edited = ym.validate(re.sub(r"^```(?:markdown)?\s*|\s*```$", "", edited_raw.strip()), prods)
        if t.get("tip") == "talep":
            edited = _talep_ic_link(edited, t)
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
    slug = str(t.get("slug") or "").strip() or ym.slugify(t["title"])
    img = unsplash(meta["GORSEL"], CAT_EN.get(t["cat"], "hobby"), set(log["photos"]), ukey, slug)
    if not img:
        return None, "konuyla eşleşen Unsplash görseli bulunamadı"
    if img.get("url"):
        log["photos"].append(img["id"])
    slug, n, tarih = write_article(t, meta, body, img, draft, tarih)
    # Makale diske yazıldığı anda log da yazılır; sonraki madde düşse de bu kayıt kalır.
    makale_kaydi_ekle(log, t["key"], slug, tarih)
    save_log(log)
    return (slug, n, bool(img.get("url")), tarih), None


# ------------------------------------------------------------------ arama talebi
GSC_PATH = os.path.join(CONTENT, "analytics_gsc.json")
GSC_SEED_PATH = os.path.join(CONTENT, "gsc_seed_queries.json")
TALEP_HEDEF_VARSAYILAN = 2
_TALEP_ARA_STOP = _JACCARD_STOP | {"hangi", "icin"}
_NIYET_ON_EK = ("mark", "sec", "olc", "ideal", "alin", "malz", "gerek", "alet")
_KOK_YAKIN = {
    "cadir": {"kamp", "kampc"},
    "kamp": {"cadir"},
    "kampc": {"cadir"},
    "spor": {"fitne"},
    "fitne": {"spor"},
    "robot": {"kodla"},
    "kodla": {"robot"},
    "yoga": {"pilat"},
    "pilat": {"yoga"},
}


def gsc_hedef():
    """Günlük arama-talebi kotası. GSC_HEDEF yoksa 2. Bozuk değerde varsayılan."""
    raw = (os.environ.get("GSC_HEDEF") or "").strip()
    if not raw:
        return TALEP_HEDEF_VARSAYILAN
    try:
        return max(0, int(raw))
    except ValueError:
        return TALEP_HEDEF_VARSAYILAN


def _kok5(word):
    return word[:5] if len(word) >= 5 else word


def _talep_govde(text):
    out = []
    for w in _baslik_kelimeleri(text):
        if w in _TALEP_ARA_STOP:
            continue
        out.append(_kok5(w))
    return out


def _govde_kume(stems):
    out = set(stems)
    for s in list(out):
        out |= _KOK_YAKIN.get(s, set())
    return out


def sorgular_yakin(a, b):
    """İki arama sorgusu aynı yazıya gider mi? Yazım farkı ve ortak başlangıç dahil."""
    ta, tb = _baslik_kelimeleri(a), _baslik_kelimeleri(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    if _baslik_cakisiyor(ta, [tb]) or _baslik_cakisiyor(tb, [ta]):
        return True
    ga, gb = _talep_govde(a), _talep_govde(b)
    if ga and ga == gb:
        return True
    if len(ga) >= 2 and len(gb) >= 2 and ga[:2] == gb[:2]:
        return True
    sa, sb = set(ga), set(gb)
    if sa and sb and len(sa & sb) / len(sa | sb) >= 0.45:
        return True
    return False


def makale_sorguyu_karsilar(sorgu, baslik, slug=""):
    """Yayındaki başlık bu sorguyu zaten cevaplıyorsa yeni yazı açma."""
    if sorgular_yakin(sorgu, baslik):
        return True
    if slug and sorgular_yakin(sorgu, slug.replace("-", " ")):
        return True
    q = _talep_govde(sorgu)
    b = _talep_govde(f"{baslik} {slug.replace('-', ' ')}")
    if not q or not b:
        return False
    bset = set(b)

    def niyet(w):
        return any(w.startswith(p) for p in _NIYET_ON_EK)

    konu = [w for w in q if not niyet(w)]
    if not konu:
        konu = q
    eslesen = [w for w in konu if w in bset]
    kalan = [w for w in konu if w not in bset]
    if len(eslesen) >= 2:
        return True
    return bool(eslesen) and not kalan


def _tr_kelime(word):
    if not word:
        return word
    ilk = {"i": "İ", "ı": "I"}.get(word[0], word[0].upper())
    return ilk + word[1:]


def talep_basligi(sorgu):
    """Sorgunun doğal Türkçe H1'i. Kısa kalan sorguya seçim eki eklenir."""
    s = re.sub(r"\s+", " ", str(sorgu or "")).strip().strip("?.!")
    if not s:
        return ""
    baslik = " ".join(_tr_kelime(w) for w in s.split())
    if re.search(r"\b(nasıl|nedir|hangi|nereden)\b", baslik, re.I) and not baslik.endswith("?"):
        baslik += "?"
    if baslik_bozuk(baslik):
        ek = baslik.rstrip("?")
        baslik = f"{ek}: Seçim Rehberi"
    if baslik_bozuk(baslik):
        return ""
    return baslik


def _json_oku(path):
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def talep_ham_sorgular(gsc_path=None, seed_path=None):
    """GSC varsa gösterim, sonra tıklama. Yoksa tohum listesinin sırası."""
    gsc_path = gsc_path if gsc_path is not None else GSC_PATH
    seed_path = seed_path if seed_path is not None else GSC_SEED_PATH
    data = _json_oku(gsc_path)
    rows = []
    if isinstance(data, dict) and data.get("ok") and data.get("queries"):
        for i, row in enumerate(data["queries"]):
            if not isinstance(row, dict):
                continue
            q = re.sub(r"\s+", " ", str(row.get("query") or "")).strip()
            if not q:
                continue
            rows.append({
                "query": q,
                "impressions": int(row.get("impressions") or 0),
                "clicks": int(row.get("clicks") or 0),
                "sira": i,
            })
    if rows:
        rows.sort(key=lambda r: (-r["impressions"], -r["clicks"], r["sira"]))
        return rows, "gsc"
    seed = _json_oku(seed_path) or {}
    queries = seed.get("queries") if isinstance(seed, dict) else seed
    out = []
    for i, q in enumerate(queries or []):
        text = q.get("query") if isinstance(q, dict) else q
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        if text:
            out.append({"query": text, "impressions": 0, "clicks": 0, "sira": i})
    return out, "seed"


def talep_kumeleri(rows):
    """Yakın sorguları tek hedefte birleştir. Temsilci en yüksek taleplidir."""
    kumeler = []
    for row in rows:
        hedef = None
        for kume in kumeler:
            if any(sorgular_yakin(row["query"], u) for u in kume["uyeler"]):
                hedef = kume
                break
        if hedef:
            hedef["uyeler"].append(row["query"])
            hedef["impressions"] += row["impressions"]
            hedef["clicks"] += row["clicks"]
            if row["sira"] < hedef["sira"]:
                hedef["sira"] = row["sira"]
        else:
            kumeler.append({
                "sorgu": row["query"],
                "uyeler": [row["query"]],
                "impressions": row["impressions"],
                "clicks": row["clicks"],
                "sira": row["sira"],
            })
    kumeler.sort(key=lambda k: (-k["impressions"], -k["clicks"], k["sira"]))
    return kumeler


def _talep_anahtar(sorgu):
    slug = ym.slugify(sorgu) or "sorgu"
    return "talep:" + slug


def _talep_kullanilan(log):
    kullanilan = []
    for item in log.get("talep") or []:
        if not isinstance(item, dict):
            continue
        if item.get("durum") not in ("yazildi", "guclendir"):
            continue
        q = str(item.get("sorgu") or "").strip()
        if q:
            kullanilan.append(q)
    for anahtar in done_anahtarlari(log):
        if anahtar.startswith("talep:"):
            kullanilan.append(anahtar.split(":", 1)[1].replace("-", " "))
    return kullanilan


def bugun_talep_say(log, bugun):
    if not isinstance(bugun, str):
        bugun = bugun.isoformat()
    seen = set()
    n = 0
    for item in _tarihli_kayitlar(log):
        if str(item.get("tarih") or "").strip() != bugun:
            continue
        anahtar = str(item.get("anahtar") or "").strip()
        if not anahtar.startswith("talep:") or anahtar in seen:
            continue
        seen.add(anahtar)
        n += 1
    return n


def talep_sec(rows, log, makaleler, adet):
    """Bugün yazılacak kümeler ve 'mevcut makaleyi güçlendir' diye ayrılanlar."""
    if adet <= 0:
        return [], []
    kullanilan = _talep_kullanilan(log)
    basliklar = []
    for m in makaleler or []:
        for kaynak in (m.get("baslik"), str(m.get("slug") or "").replace("-", " ")):
            kelime = _baslik_kelimeleri(kaynak)
            if kelime:
                basliklar.append(kelime)
    secilen, guclendir = [], []
    for kume in talep_kumeleri(rows):
        if any(sorgular_yakin(kume["sorgu"], eski) for eski in kullanilan):
            continue
        if any(makale_sorguyu_karsilar(kume["sorgu"], m.get("baslik") or "", m.get("slug") or "")
               for m in makaleler or []):
            guclendir.append(kume["sorgu"])
            kullanilan.append(kume["sorgu"])
            continue
        baslik = talep_basligi(kume["sorgu"])
        if not baslik or not _kuyruk_basligi_uygun(baslik, basliklar):
            if baslik:
                guclendir.append(kume["sorgu"])
                kullanilan.append(kume["sorgu"])
            continue
        kume = dict(kume)
        kume["baslik"] = baslik
        kume["anahtar"] = _talep_anahtar(kume["sorgu"])
        secilen.append(kume)
        kullanilan.append(kume["sorgu"])
        basliklar.append(_baslik_kelimeleri(baslik))
        if len(secilen) >= adet:
            break
    return secilen, guclendir


def kategori_eslestir(sorgu, cats, products=None):
    """Sorguya en yakın kategori / alt kategori. Ürün verilirse en az 2 doğrulanmış ürün şart."""
    q = _govde_kume(_talep_govde(sorgu))
    if not q:
        return None
    adaylar = []
    for c in cats or []:
        secenek = [("_main", c.get("name") or c.get("id") or "")]
        for s in c.get("subcategories") or []:
            secenek.append((s.get("id") or "", s.get("name") or ""))
        for sid, name in secenek:
            if not sid:
                continue
            blob = _govde_kume(_talep_govde(f"{name} {str(sid).replace('-', ' ')} {c.get('name') or ''}"))
            skor = len(q & blob)
            if skor < 1:
                continue
            ozel = 0 if sid == "_main" else 1
            adaylar.append((skor, ozel, c.get("id"), sid, name or sid))
    adaylar.sort(key=lambda x: (x[0], x[1]), reverse=True)
    for skor, _ozel, cat, sid, name in adaylar:
        if products is not None:
            plist = urun_denetim.alt_kategori_urunleri(products, cat, sid)
            if len(plist) < 2:
                continue
        return cat, sid, name, skor
    return None


def _talep_ic_link(body, t):
    if "/kategori/" in body or "/makale/" in body:
        return body
    if t.get("sub") and t["sub"] != "_main":
        yol = f"/kategori/{t['cat']}/{t['sub']}/"
    else:
        yol = f"/kategori/{t['cat']}/"
    ad = t.get("sub_name") or t.get("cat_name") or "kategori"
    return body.rstrip() + f"\n\nSeçimi [{ad}]({yol}) sayfasındaki diğer rehberlerle birlikte düşün.\n"


def _talep_kaydet(log, sorgu, durum, tarih, slug="", anahtar=""):
    kayitlar = log.setdefault("talep", [])
    anahtar = anahtar or _talep_anahtar(sorgu)
    for item in kayitlar:
        if isinstance(item, dict) and item.get("anahtar") == anahtar and item.get("durum") == durum:
            return
    kayitlar.append({
        "sorgu": sorgu,
        "anahtar": anahtar,
        "durum": durum,
        "tarih": tarih,
        "slug": slug,
    })


# Brif sorgularında her rehberde geçen gövdeler. Bunlar tek başına
# kannibalizasyon sayılmaz; ayırıcı kökler (yılbaşı, kadın, strateji) kalır.
_BRIF_GENEL_KOK = (
    "basla", "set", "nasil", "yapil", "kutu", "oyun", "hobi",
    "evde", "yeni", "ilk", "rehbe", "secim", "fikir", "malze",
)
# "Yeni başlayanlar için …" birçok rehberin ortak ön eki. İlk üç kelime
# yalnız bu kalıptan oluşuyorsa başlık çakışması sayılmaz.
_BRIF_BASLIK_GENEL = {
    "yeni", "baslayanlar", "baslangic", "icin", "en", "iyi",
    "rehber", "rehberi", "seti", "nasil", "nedir",
}


def _brif_genel_kok(word):
    return any(
        word == g or word.startswith(g) or (len(word) >= 4 and g.startswith(word))
        for g in _BRIF_GENEL_KOK
    )


def _brif_ozel_kok(text):
    """Çoğul eki kökü uzatır: oyunları → oyunl, setleri → setle. Genel kök elenir."""
    return [w for w in _talep_govde(text) if not _brif_genel_kok(w)]


def _brif_ayri_sluglar(brief):
    """Brifin iç link verdiği makaleler aynı konu değildir."""
    ayri = set()
    for yol in (brief or {}).get("zorunlu_linkler") or []:
        parca = [p for p in str(yol).strip("/").split("/") if p]
        if len(parca) >= 2 and parca[0] == "makale":
            ayri.add(parca[1])
    return ayri


def brif_makaleyle_cakisir(brief, makale):
    """SEO brifini, yayındaki yazıyla aynı sorguya düşüyorsa ele.

    Ortak 'kutu oyunu' / 'başlangıç seti' gövdesi yetmez. Ayırıcı köklerin
    hepsi yayındaki başlıkta varsa, ya da başlığın ilk üç kelimesi aynıysa
    yeni yazı açılmaz. Brifin kendi iç linkleri bu eleğe girmez.
    """
    slug = str((makale or {}).get("slug") or "")
    if slug and slug == str((brief or {}).get("slug") or ""):
        return True
    if slug in _brif_ayri_sluglar(brief):
        return False
    baslik = str((makale or {}).get("baslik") or "")
    sorgu = str((brief or {}).get("sorgu") or "")
    h1 = str((brief or {}).get("h1") or "")
    ilk = _baslik_kelimeleri(h1)[:3]
    if (h1 and baslik and any(w not in _BRIF_BASLIK_GENEL for w in ilk)
            and _baslik_cakisiyor(_baslik_kelimeleri(h1), [_baslik_kelimeleri(baslik)])):
        return True
    ozel = _brif_ozel_kok(sorgu)
    hedef = set(_talep_govde(f"{baslik} {slug.replace('-', ' ')}"))
    # Ayırıcı köklerin hepsi yayındaki başlıkta olmalı. Tek başına
    # "kutu oyunu" veya "başlangıç seti" yeni brifi düşürmez.
    if ozel and hedef and all(w in hedef for w in ozel):
        return True
    return False


def talep_brif_listesi():
    """SEO brifleri, küçük oncelik önce. Yılbaşı 1'dir."""
    return sorted(
        load_brief_index().values(),
        key=lambda b: (int(b.get("oncelik") or 9999), str(b.get("slug") or "")),
    )


def talep_brif_sec(briefs, log, makaleler, adet):
    """Bugünkü arama-talebi kotasının brif kısmı. Düzenli havuzdan okumaz."""
    if adet <= 0:
        return [], []
    kullanilan = _talep_kullanilan(log)
    yayin = {str(m.get("slug") or "") for m in makaleler or []}
    secilen, guclendir = [], []
    sirali = sorted(briefs or [], key=lambda b: (int(b.get("oncelik") or 9999), str(b.get("slug") or "")))
    for b in sirali:
        slug = str(b.get("slug") or "").strip()
        sorgu = re.sub(r"\s+", " ", str(b.get("sorgu") or "")).strip()
        if not slug or not sorgu:
            continue
        if slug in yayin:
            continue
        if any(sorgular_yakin(sorgu, eski) for eski in kullanilan):
            continue
        if any(brif_makaleyle_cakisir(b, m) for m in makaleler or []):
            guclendir.append(sorgu)
            kullanilan.append(sorgu)
            continue
        if any(sorgular_yakin(sorgu, s.get("sorgu") or "") for s in secilen):
            continue
        secilen.append(b)
        kullanilan.append(sorgu)
        if len(secilen) >= adet:
            break
    return secilen, guclendir


def _brif_konusu(brief, cats, products):
    """Brifi talep konusu yap. Ürünler brifteki kimliklerdir."""
    cat = str(brief.get("kategori") or "").strip()
    sub = str(brief.get("alt") or "").strip()
    cat_rec = next((c for c in cats or [] if c.get("id") == cat), None)
    if not cat_rec:
        return None
    sub_rec = next((s for s in cat_rec.get("subcategories") or [] if s.get("id") == sub), None)
    if not sub_rec:
        return None
    plist = _gecerli_urunler(products, brief.get("urunler") or [])
    if len(plist) < _gerekli_urun("talep"):
        return None
    slug = str(brief.get("slug") or "").strip()
    return {
        "key": "talep:" + slug,
        "tip": "talep",
        "cat": cat,
        "cat_name": cat_rec.get("name") or cat,
        "sub": sub,
        "sub_name": sub_rec.get("name") or sub,
        "ids": [p["id"] for p in plist],
        "title": str(brief.get("h1") or "").strip() or talep_basligi(brief.get("sorgu")),
        "slug": slug,
        "sorgu": brief.get("sorgu"),
        "hedef": 1500,
        "kaynak": "talep-brif",
        "brief": slug,
        "oncelik": brief.get("oncelik"),
        "meta_title": brief.get("meta_title") or "",
        "meta_description": brief.get("meta_description") or "",
        "focus_keyword": brief.get("focus_keyword") or brief.get("sorgu") or "",
        "yasak": brief.get("yasak") or [],
        "zorunlu_linkler": brief.get("zorunlu_linkler") or [],
        "terimler": brief.get("terimler") or [],
    }


def _talep_yaz(konular, log, products, key, models, model_idx, ukey, draft, tarih, yedek_acik, kalan, kaynak):
    """Hazır talep konularını yazar. Kota veya geçici hatada (adet, True) döner."""
    fails = {}
    for x in log.get("atlanan") or []:
        if isinstance(x, dict):
            fails[x.get("anahtar")] = fails.get(x.get("anahtar"), 0) + 1
    made = 0
    for konu in konular:
        if made >= kalan:
            break
        if fails.get(konu.get("key"), 0) >= 2:
            continue
        print(f"→ [talep/{kaynak}] {konu['title']}")
        try:
            res, why = uret(konu, products, key, models, model_idx, ukey, log, draft, tarih)
        except ym.GeminiError as e:
            save_log(log)
            if isinstance(e, ym.GeminiQuotaError) or gecici_api_hatasi(e):
                if isinstance(e, ym.GeminiQuotaError):
                    _kota_mesaji(e, yedek_acik, made)
                else:
                    _gecici_mesaji(e, made)
                print("Arama talebi kota/geçici hatada durdu. Düzenli makaleler diskte.")
                return made, True
            raise
        if res:
            slug, n, _has_img, gun = res
            _talep_kaydet(log, konu["sorgu"], "yazildi", gun, slug=slug, anahtar=konu["key"])
            for uye in konu.get("uyeler") or []:
                if uye == konu["sorgu"]:
                    continue
                _talep_kaydet(log, uye, "yazildi", gun, slug=slug, anahtar=_talep_anahtar(uye))
            save_log(log)
            made += 1
            print(f"  ✓ {slug}  ({n} kelime, talep)")
        else:
            log.setdefault("atlanan", []).append({"anahtar": konu["key"], "neden": why, "tarih": tarih})
            save_log(log)
            print(f"  ✗ atlandı: {why}")
    return made, False


def talep_uret(log, products, cats, articles_dir, key, models, model_idx, ukey, draft, tarih, yedek_acik):
    """Düzenli 3'ten sonra en fazla GSC_HEDEF yazı.

    Önce SEO brif kuyruğu (yılbaşı en önde, brifle yazılır). Brif kalmayınca
    Search Console / tohum sorgusuna düşer. Brifler düzenli konu havuzundan okunmaz.
    """
    hedef = gsc_hedef()
    kalan = hedef - bugun_talep_say(log, tarih)
    if kalan <= 0 or hedef <= 0:
        print(f"Arama talebi: bugünün {hedef} yazısı tamam.")
        return 0
    makaleler = urun_denetim.makale_verileri(articles_dir)
    brifler, brif_guclendir = talep_brif_sec(talep_brif_listesi(), log, makaleler, kalan)
    for sorgu in brif_guclendir:
        anahtar = "talep:" + (ym.slugify(sorgu) or "sorgu")
        for b in talep_brif_listesi():
            if b.get("sorgu") == sorgu and b.get("slug"):
                anahtar = "talep:" + b["slug"]
                break
        _talep_kaydet(log, sorgu, "guclendir", tarih, anahtar=anahtar)
        print(f"! mevcut makaleyi güçlendir: {sorgu}")
    if brif_guclendir:
        save_log(log)
    made = 0
    if brifler:
        print(f"Arama talebi (brif): {len(brifler)} konu denenecek.")
        brif_konu = []
        for b in brifler:
            konu = _brif_konusu(b, cats, products)
            if not konu:
                print(f"  ! brif yazılamadı (kategori veya ürün): {b.get('slug')}")
                continue
            brif_konu.append(konu)
        n, dur = _talep_yaz(
            brif_konu, log, products, key, models, model_idx, ukey, draft, tarih,
            yedek_acik, kalan, kaynak="brif")
        made += n
        if dur:
            return made
    kalan_gsc = kalan - made
    if kalan_gsc <= 0:
        print(f"Arama talebi bitti: {made} makale.")
        return made
    rows, kaynak = talep_ham_sorgular()
    secilen, guclendir = talep_sec(rows, log, makaleler, kalan_gsc)
    for sorgu in guclendir:
        _talep_kaydet(log, sorgu, "guclendir", tarih)
        print(f"! mevcut makaleyi güçlendir: {sorgu}")
    if guclendir:
        save_log(log)
    if not secilen:
        print(f"Arama talebi ({kaynak}): yazılacak yeni sorgu kalmadı.")
        print(f"Arama talebi bitti: {made} makale.")
        return made
    print(f"Arama talebi ({kaynak}): {len(secilen)} sorgu denenecek.")
    gsc_konu = []
    for kume in secilen:
        eslesen = kategori_eslestir(kume["sorgu"], cats, products)
        if not eslesen:
            print(f"  ! kategori yok, sonraki sorgu: {kume['sorgu']}")
            continue
        cat, sub, sub_name, _skor = eslesen
        cat_name = next((c.get("name") for c in cats if c.get("id") == cat), cat)
        plist = urun_denetim.alt_kategori_urunleri(products, cat, sub if sub != "_main" else "_main")
        if len(plist) < 2:
            print(f"  ! yeterli ürün yok, sonraki sorgu: {kume['sorgu']}")
            continue
        gsc_konu.append({
            "key": kume["anahtar"],
            "tip": "talep",
            "cat": cat,
            "cat_name": cat_name,
            "sub": sub,
            "sub_name": sub_name,
            "ids": [p["id"] for p in plist[:6]],
            "title": kume["baslik"],
            "sorgu": kume["sorgu"],
            "hedef": 1500,
            "kaynak": "talep",
            "uyeler": kume.get("uyeler") or [],
        })
    n, dur = _talep_yaz(
        gsc_konu, log, products, key, models, model_idx, ukey, draft, tarih,
        yedek_acik, kalan_gsc, kaynak=kaynak)
    made += n
    if not dur:
        print(f"Arama talebi bitti: {made} makale.")
    return made


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
    else:
        a.adet = 0

    products, cats = ym.load("products.json"), ym.load("categories.json")
    have = {fn[:-3] for fn in os.listdir(ARTICLES)} if os.path.isdir(ARTICLES) else set()
    fails = {}
    for x in log["atlanan"]:
        fails[x["anahtar"]] = fails.get(x["anahtar"], 0) + 1
    done_keys = set(done_anahtarlari(log))
    done_sorgu = {k.rsplit(":", 1)[-1] for k in done_keys if k.count(":") >= 3}
    rapor = {}
    queue = [t for t in topic_queue(products, cats, log=log, rapor=rapor)
             if t["key"] not in done_keys and ym.slugify(t["title"]) not in have
             and t.get("sorgu_slug") not in done_sorgu and fails.get(t["key"], 0) < 2]
    if rapor.get("benzer"):
        print(f"! benzer başlık: {rapor['benzer']} konu kuyruğa alınmadı; sıra başka konuya geçti")
    if rapor.get("bozuk_baslik"):
        print(f"! bozuk başlık: {rapor['bozuk_baslik']} konu kuyruğa alınmadı")

    talep_rows, talep_kaynak = talep_ham_sorgular()
    talep_kalan = max(0, gsc_hedef() - bugun_talep_say(log, bugun))
    talep_onizleme, talep_guclendir = talep_sec(
        talep_rows, log, urun_denetim.makale_verileri(ARTICLES), talep_kalan)

    if a.konu_listesi:
        print(f"Kuyrukta {len(queue)} konu. Sıradakiler:")
        for t in queue[:12]:
            print(f"  [{t['tip']}] {t['title']}")
        print(f"Arama talebi ({talep_kaynak}), bugün en fazla {talep_kalan}:")
        for kume in talep_onizleme:
            print(f"  [talep] {kume['baslik']}  ← {kume['sorgu']}")
        for sorgu in talep_guclendir:
            print(f"  ! mevcut makaleyi güçlendir: {sorgu}")
        return

    if a.adet <= 0 and talep_kalan <= 0:
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

    made, kota = 0, False
    # Kalite kapısı eleyen taslakları atlayıp günlük hedefi tutturmak için konu payı.
    if a.adet > 0:
        made, kota = _duzenli_uret(
            queue, a.adet, products, key, models, model_idx, ukey, log, draft, bugun, yedek_acik)
    if talep_kalan > 0 and not kota:
        talep_uret(
            log, products, cats, ARTICLES, key, models, model_idx, ukey, draft, bugun, yedek_acik)
    save_log(log)
    print(f"Bitti: {made} düzenli makale ({'TASLAK — onay bekliyor' if draft else 'yayına hazır'}).")


def _duzenli_uret(queue, adet, products, key, models, model_idx, ukey, log, draft, bugun, yedek_acik):
    made, tried = 0, 0
    for t in queue:
        if made >= adet or tried >= max(GUNLUK_HEDEF, adet * 4):
            break
        tried += 1
        print(f"→ {t['title']}")
        try:
            res, why = uret(t, products, key, models, model_idx, ukey, log, draft, bugun)
        except ym.GeminiError as e:
            save_log(log)
            if isinstance(e, ym.GeminiQuotaError):
                _kota_mesaji(e, yedek_acik, made)
                return made, True
            if gecici_api_hatasi(e):
                _gecici_mesaji(e, made)
                return made, True
            sys.exit(f"API hatası, durduruldu: {e}")
        if res:
            slug, n, has_img, tarih = res
            makale_kaydi_ekle(log, t["key"], slug, tarih)
            made += 1
            save_log(log)
            print(f"  ✓ {slug}  ({n} kelime, {'taslak' if draft else 'yayın'}, görsel: {'Unsplash' if has_img else 'kategori'})")
            sub = "" if t.get("sub") in (None, "", "_main") else t["sub"]
            ctas = deeplink.shop_ctas_for(t["cat"], sub)
            dugmeler = list(ctas["links"]) + list(ctas.get("offers") or [])
            if dugmeler:
                print("  ✓ mağaza CTA: " + ", ".join(c["label"] for c in dugmeler))
        else:
            log["atlanan"].append({"anahtar": t["key"], "neden": why, "tarih": bugun})
            save_log(log)
            print(f"  ✗ atlandı: {why}")
    save_log(log)
    return made, False


if __name__ == "__main__":
    main()
