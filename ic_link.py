#!/usr/bin/env python3
"""Makale gövdesindeki iç linkler, yetim raporu ve yeni makaleye geri link.

Gelen gövde linki, başka bir makalenin metnindeki benzersiz iç bağlantıdır.
Üst menü, altbilgi ve ekmek kırıntısı bu sayıda yoktur; onlar tıklama
derinliği ve site haritası denetiminde izlenir.

Kullanım:
  python ic_link.py            # zayıf sayfalara gövde linki yazar
  python ic_link.py --dry-run  # dosyaya yazmadan planı basar
"""
import json
import os
import re
from collections import defaultdict
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urlsplit

BASE = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(BASE, "content")
ARTICLES = os.path.join(CONTENT, "articles")
GSC_PATH = os.path.join(CONTENT, "analytics_gsc.json")
RAPOR_PATH = os.path.join(CONTENT, "inlink_raporu.json")

# Bir kaynak sayfaya bu turda eklenecek yeni gövde linkinin tavanı.
MAX_YENI = 5
# Yetimden çıkmak için gereken benzersiz gövde linki.
HEDEF_GELEN = 2
# Search Console'da 8-20 arası ortalama pozisyon (vuruş mesafesi) bir fazla link ister.
HEDEF_GSC = 3
# Kaynak başına FAQ öncesine konan yeni paragraf tavanı.
MAX_YENI_PARAGRAF = 2

_YASAK = (
    "sonuç olarak", "günümüzde", "bu makalede", "bu yazıda", "dijital çağda",
    "hiç şüphesiz", "unutmayın ki", "dünyasına", "yolculuk", "keşfedin",
    "adım atın", "göz önünde bulundurulmalıdır", "önem arz", "vazgeçilmez",
    "olmazsa olmaz", "her şeyden önce", "sizlere", "kısacası",
    "ideal bir seçim", "harika bir seçenek", "mükemmel", "piyasa lideri",
    "tam size göre", "hayalinizdeki", "sınırlarını zorla", "bir çok",
)

_STOP = {
    "en", "iyi", "yeni", "baslayan", "baslayanlar", "icin", "baslangic",
    "seti", "set", "rehber", "rehberi", "rehberler", "secim", "secimi",
    "hakkinda", "ile", "ilk", "alinacaklar", "nedir", "nasil", "sik",
    "sikca", "sorulan", "sorular", "soru", "kisa", "ekipman", "ekipmanlari",
    "alirken", "yapilan", "hata", "hatalar", "kacinilir", "model", "modeller",
    "bir", "bu", "su", "olan", "olarak", "daha", "gibi", "kadar", "veya",
    "yada", "yani", "cok", "tum", "hem", "once", "sonra", "burada", "orada",
    "sen", "senin", "sana", "paket", "paketleri", "not", "notu", "notlari",
    "sayfa", "sayfasi", "sayfasinda", "yazi", "yazisi", "mini", "kisa",
    "cevaplariyla", "baslangici", "icin", "ve", "da", "de", "mi", "mu",
    "the", "for", "with", "and", "bakim", "bakimi", "durum", "durumu",
    "hobi", "hobiler", "hobisi", "malzeme", "malzemeler", "setler",
    "setleri", "hangisi", "hangisini", "yapilacak", "evde", "kadinlar",
    "kadin", "yetiskin",
}
_STOP_ONEK = ("basla", "rehbe", "secim", "ekipm", "alinac", "sorul", "hakkin")

_FAQ = re.compile(r"^##\s+.*(sık|sik|merak)", re.IGNORECASE)
_LINK = re.compile(r"\[[^\]]+\]\((/[^)\s]+)\)")

_MAKALE_KALIP = (
    "Aynı {konu} işinin devamı {link} rehberinde.",
    "{konu} için burada kapanan ayrımı {link} ayrıca tutuyor.",
    "Seçimi bitirmeden {link} notuna da bak; aynı {konu} masasının diğer ucu orada.",
    "Bu sayfadaki liste {konu} için burada kalsın. Sıradaki karar {link} içinde.",
    "{link}, {konu} tarafında bu sayfanın değmediği yeri yazıyor.",
)
_KONUSUZ_KALIP = (
    "Bu seçimin devamı {link} rehberinde duruyor.",
    "Aynı masada kalan ayrım {link} içinde.",
    "Sıradaki bakacağın yer {link}.",
    "Burada kesilen ayrıntıyı {link} sürdürüyor.",
    "İstersen konunun diğer ucuna {link} ile geçebilirsin.",
)
_KAT_KALIP = (
    "Bu notların bir arada durduğu yer {link}.",
    "Aynı başlık altındaki diğer rehberler {link} sayfasında.",
    "{link} bu parçanın yanındaki seçimleri topluyor.",
)


def fold(text):
    text = str(text or "").replace("İ", "i").replace("I", "ı").lower()
    return text.translate(str.maketrans("çğıöşüâîû", "cgiosuaiu"))


def kokler(text):
    out = set()
    for word in re.findall(r"[a-z0-9]+", fold(text)):
        if word in _STOP or len(word) < 4 or word.isdigit():
            continue
        if any(word.startswith(p) for p in _STOP_ONEK):
            continue
        out.add(word)
    return out


def _ek_mi(ek):
    """Kısa çekim eki. Türetme ekleri (-sal, -imli, -lu) sayılmaz."""
    return bool(re.fullmatch(r"y?[aeiou]{1,2}|[aeiou]n|n[aeiou]|s[aeiou]", ek or ""))


def ayni_kok(x, y):
    if x == y:
        return len(x) >= 4
    kisa, uzun = (x, y) if len(x) <= len(y) else (y, x)
    if len(kisa) < 4 or not uzun.startswith(kisa):
        return False
    return _ek_mi(uzun[len(kisa):])


def ortusen_kokler(a, b):
    """Örtüşen kök çiftleri. 'gitar/gitara' sayılır; 'deri/derin' sayılmaz."""
    if not a or not b:
        return []
    kullanilan = set()
    cift = []
    for x in a:
        for y in b:
            if y in kullanilan:
                continue
            if ayni_kok(x, y):
                kullanilan.add(y)
                cift.append((x, y))
                break
    return cift


def ortus(a, b):
    return len(ortusen_kokler(a, b))


def norm_yol(url):
    raw = str(url or "").strip()
    if not raw or raw.startswith(("#", "mailto:", "tel:", "javascript:", "aff:")):
        return ""
    if raw.startswith(("http://", "https://")):
        parca = urlsplit(raw)
        raw = parca.path or ""
    raw = raw.split("#", 1)[0].split("?", 1)[0]
    if not raw.startswith("/"):
        return ""
    if raw.endswith("/index.html"):
        raw = raw[: -len("index.html")] or "/"
    if raw != "/" and not raw.endswith("/") and "." not in raw.rsplit("/", 1)[-1]:
        raw += "/"
    return raw or "/"


def yasak_var(text):
    low = fold(text)
    return any(fold(k) in low for k in _YASAK)


def yasak_temizle(text):
    temiz = str(text or "")
    for k in _YASAK:
        temiz = re.sub(re.escape(k), " ", temiz, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", temiz).strip(" -,:;.")


def tr_lower_first(text):
    if not text:
        return text
    ilk = {"I": "ı", "İ": "i"}.get(text[0], text[0].lower())
    return ilk + text[1:]


def konu_adi(name):
    """Alt kategori adının cümle içine girecek hali. Marka büyük harfi korunur."""
    parca = re.split(r"\s*[&/]\s*", str(name or ""))[0].strip()
    if not parca:
        return ""
    if parca.isupper():
        return parca
    if any(ch.isupper() for ch in parca[1:]):
        return parca
    return tr_lower_first(parca)


def _json_oku(path):
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def load_categories(path=None):
    path = path or os.path.join(CONTENT, "categories.json")
    data = _json_oku(path) or []
    return data if isinstance(data, list) else []


def _kategori_index(categories):
    by_id = {}
    for c in categories or []:
        by_id[c.get("id")] = c
    return by_id


def _adlar(categories, cat_id, sub_id):
    cat = _kategori_index(categories).get(cat_id) or {}
    sub_name = ""
    for s in cat.get("subcategories") or []:
        if s.get("id") == sub_id:
            sub_name = s.get("name") or ""
            break
    return cat.get("name") or "", sub_name


def parse_markdown(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    meta, body = {}, text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip('"').strip("'")
            body = parts[2]
    return meta, body, text


def load_articles(articles_dir=None, categories=None):
    """Yayındaki makaleler. Taslaklar rapora ve linke girmez."""
    articles_dir = articles_dir or ARTICLES
    if categories is None:
        root = os.path.dirname(os.path.abspath(articles_dir))
        categories = load_categories(os.path.join(root, "categories.json"))
    rows = []
    if not os.path.isdir(articles_dir):
        return rows
    for fn in sorted(os.listdir(articles_dir)):
        if not fn.endswith(".md"):
            continue
        full = os.path.join(articles_dir, fn)
        meta, body, original = parse_markdown(full)
        if str(meta.get("draft", "")).lower() in ("true", "1", "evet"):
            continue
        slug = meta.get("slug") or fn[:-3]
        cat = meta.get("category") or ""
        sub = meta.get("subcategory") or ""
        cat_name, sub_name = _adlar(categories, cat, sub)
        rows.append({
            "slug": slug,
            "title": meta.get("title") or slug,
            "category": cat,
            "subcategory": sub,
            "category_name": cat_name,
            "subcategory_name": sub_name,
            "focus": meta.get("focus_keyword") or "",
            "date": meta.get("date") or "",
            "yol": f"/makale/{slug}/",
            "body": body,
            "original": original,
            "dosya": full,
        })
    return rows


def govde_yollari(body):
    out = []
    for m in _LINK.finditer(body or ""):
        yol = norm_yol(m.group(1))
        if yol:
            out.append(yol)
    return out


def govde_graf(makaleler):
    """kaynak yol -> hedef yollar, ve hedef -> kaynak yolları."""
    giden = {}
    gelen = defaultdict(set)
    for m in makaleler:
        yollar = []
        for yol in govde_yollari(m["body"]):
            if yol == m["yol"] or yol in yollar:
                continue
            yollar.append(yol)
            gelen[yol].add(m["yol"])
        giden[m["yol"]] = yollar
    return giden, gelen


def gsc_yukle(path_or_data):
    if path_or_data is None:
        return None
    if isinstance(path_or_data, dict):
        return path_or_data
    return _json_oku(path_or_data)


def gsc_hedef_yollar(data, makaleler):
    """Pozisyonu 8-20 olan sorguların denk sayfaları.

    Dosya yoksa, ok değilse veya sorgular boşsa boş liste. Satırda page varsa
    o yol kullanılır. Yoksa sorgu, başlık / odak / slug ile eşlenir. Sayfa
    boyutunda 8-20 pozisyon da aynı listeye girer.
    """
    if not isinstance(data, dict) or not data.get("ok"):
        return []
    makaleler = list(makaleler or [])
    bulunan = []

    def ekle(yol):
        yol = norm_yol(yol)
        if yol and yol not in bulunan:
            bulunan.append(yol)

    def pozisyon(row):
        try:
            return float(row.get("position"))
        except (TypeError, ValueError):
            return None

    def makale_sec(sorgu):
        q = kokler(sorgu)
        if not q:
            return ""
        en_iyi, skor = "", 0
        for m in makaleler:
            blob = kokler(f"{m.get('title') or ''} {m.get('focus') or ''} {(m.get('slug') or '').replace('-', ' ')}")
            s = ortus(q, blob)
            if s > skor or (s == skor and s and en_iyi and len(m["yol"]) < len(en_iyi)):
                en_iyi, skor = m["yol"], s
        if skor >= 2 or (skor >= 1 and len(q) == 1):
            return en_iyi
        return ""

    for row in data.get("queries") or []:
        if not isinstance(row, dict):
            continue
        pos = pozisyon(row)
        if pos is None or not (8 <= pos <= 20):
            continue
        sayfa = row.get("page") or row.get("yol") or ""
        if sayfa:
            ekle(sayfa)
            continue
        ekle(makale_sec(row.get("query") or ""))
    for row in data.get("pages") or []:
        if not isinstance(row, dict):
            continue
        pos = pozisyon(row)
        if pos is None or not (8 <= pos <= 20):
            continue
        ekle(row.get("page") or row.get("yol") or "")
    return bulunan


def kategori_kayitlari(categories, makaleler):
    by_cat = defaultdict(list)
    for m in makaleler:
        by_cat[m.get("category")].append(m)
    rows = []
    for c in categories or []:
        cid = c.get("id") or ""
        slug = c.get("slug") or cid
        uyeler = by_cat.get(cid) or []
        rows.append({
            "yol": f"/kategori/{slug}/",
            "tur": "kategori",
            "baslik": c.get("name") or slug,
            "kategori": cid,
            "alt_kategori": "",
            "makale_sayisi": len(uyeler),
        })
        for s in c.get("subcategories") or []:
            sid = s.get("id") or ""
            sslug = s.get("slug") or sid
            n = len([m for m in uyeler if (m.get("subcategory") or "") == sid])
            rows.append({
                "yol": f"/kategori/{slug}/{sslug}/",
                "tur": "kategori",
                "baslik": s.get("name") or sid,
                "kategori": cid,
                "alt_kategori": sid,
                "makale_sayisi": n,
            })
    return rows


def _hedef_kok(hedef):
    """Eşleşme başlık ve odaktan gelir. Alt kategori adı 'oyun' gibi geniş kök taşır."""
    return kokler(
        f"{hedef.get('title') or ''} {hedef.get('focus') or ''} {hedef.get('baslik') or ''}"
    )


def _paragraf_mi(line):
    s = line.strip()
    if len(s) < 80:
        return False
    if s.startswith(("#", "|", ">", "-", "*", "•", "!")):
        return False
    if re.match(r"^\d+\.\s", s):
        return False
    return True


_KENAR = {"nasil", "icin", "ile", "veya", "ve", "da", "de", "mi", "mu", "bir", "bu"}
_BAGLAC = {"ve", "ile", "veya", "icin", "ya", "da", "de"}
# Kayan parçanın sonunda kalan yarım kelimeler: "Hakkında Sık", "Üstü Set".
_YARIM = {"mod", "sik", "alirken", "hangi", "set", "ustu", "model", "ilk"}


def _buyuk_basla(text):
    if not text:
        return text
    ilk = {"i": "İ", "ı": "I"}.get(text[0], text[0].upper())
    return ilk + text[1:]


def _kelimeler(parca):
    parca = yasak_temizle(re.sub(r"[?]+", "", parca or ""))
    parca = parca.replace("&", " ")
    kelime = [re.sub(r"^[,:;()]+|[,:;()]+$", "", w) for w in parca.split()]
    return [w for w in kelime if w and not re.fullmatch(r"\d+", w)]


def _ifade_ekle(aday, kelime):
    if not (2 <= len(kelime) <= 5):
        return
    if any("'" in w or "’" in w or "&" in w or "(" in w or ")" in w for w in kelime):
        return
    if fold(kelime[0]) in _KENAR or fold(kelime[-1]) in _KENAR:
        return
    if any(fold(w) in _BAGLAC for w in kelime):
        return
    if fold(kelime[-1]) in _YARIM:
        return
    harfli = [len(re.sub(r"[^a-z0-9]", "", fold(w))) for w in kelime]
    if any(n <= 1 for n in harfli):
        return
    if len(kelime) <= 3 and sum(1 for n in harfli if n <= 2) >= 1:
        return
    p = " ".join(kelime)
    if len(p) < 8 or len(p) > 48 or yasak_var(p):
        return
    if all(fold(w) in _STOP or harfli[i] < 4 for i, w in enumerate(kelime)):
        return
    if p.casefold() in {x.casefold() for x in aday}:
        return
    aday.append(p)


def _anchor_adaylari(makale):
    """Başlığın kendi parçalarından kısa çapa. Kayan pencereyle kırık ifade üretilmez."""
    title = re.sub(r"\s*\(20\d\d\)", "", makale.get("title") or "")
    title = re.sub(r"\([^)]*\)", " ", title)
    title = re.sub(r"(?i)^en iyi\s+", "", title).strip()
    parcalar = []
    for yan in re.split(r"\s*[:|—–?]\s*", title):
        for virgul in yan.split(","):
            parcalar.append(virgul.strip())
    focus = (makale.get("focus") or "").strip()
    # Odak, başlıkta geçmiyorsa (kırık sorgu, "dj liğe") çapa olmaz.
    if focus and fold(re.sub(r"\s+", " ", focus)) in fold(re.sub(r"\s+", " ", title)):
        parcalar.append(focus)
    aday = []
    for parca in parcalar:
        kelime = _kelimeler(parca)
        if not kelime:
            continue
        if len(kelime) <= 5:
            _ifade_ekle(aday, kelime)
            if len(kelime) >= 3:
                _ifade_ekle(aday, kelime[-2:])
        else:
            _ifade_ekle(aday, kelime[:4])
            _ifade_ekle(aday, kelime[:3])

    def puan(p):
        n = len(p.split())
        # Üç ila beş kelimelik tam parça, kesik iki kelimeden önce gelsin.
        return (0 if 3 <= n <= 5 else 1, -n, len(p))

    aday.sort(key=puan)
    return aday


def _anchor_sec(adaylar, kullanilan):
    for aday in adaylar:
        if aday.casefold() in kullanilan:
            continue
        return aday
    return ""


def _kat_anchor(baslik, kullanilan):
    adaylar = [baslik, f"{baslik} notları", f"{baslik} rehberi", f"{baslik} ekipmanları"]
    for aday in adaylar:
        aday = yasak_temizle(aday)
        if len(aday) < 4 or yasak_var(aday):
            continue
        if aday.casefold() in kullanilan:
            continue
        return aday
    return ""


def _cumle(hedef, anchor, yol, idx, kategori=False):
    link = f"[{anchor}]({yol})"
    if kategori:
        frames = _KAT_KALIP
        konu = ""
    else:
        konu = konu_adi(hedef.get("subcategory_name") or "")
        frames = _MAKALE_KALIP if konu else _KONUSUZ_KALIP
    for shift in range(len(frames)):
        if konu:
            cumle = frames[(idx + shift) % len(frames)].format(konu=konu, link=link)
        else:
            cumle = frames[(idx + shift) % len(frames)].format(link=link)
        if yasak_var(cumle):
            continue
        if "rehber" in anchor.casefold() and cumle.casefold().count("rehber") > anchor.casefold().count("rehber"):
            continue
        return _buyuk_basla(cumle)
    if konu:
        return _buyuk_basla(frames[idx % len(frames)].format(konu=konu, link=link))
    return _buyuk_basla(frames[idx % len(frames)].format(link=link))


def _sar(line, anchor, yol):
    """Paragrafta hazır duran ifadeyi linkle. Yoksa None."""
    if "rehber" in anchor.casefold() and len(anchor.split()) < 2:
        return None
    parts = re.split(r"(\[[^\]]+\]\([^)]+\))", line)
    desen = re.compile(r"(?<!\w)" + re.escape(anchor) + r"(?!\w)", re.IGNORECASE)
    for i, part in enumerate(parts):
        if part.startswith("["):
            continue
        if part.count("**") % 2:
            continue
        m = desen.search(part)
        if not m:
            continue
        parts[i] = part[:m.start()] + f"[{m.group(0)}]({yol})" + part[m.end():]
        return "".join(parts)
    return None


def _yerlestir(body, sentence, kok_hedef, serbest_paragraf, sar_anchor="", yol="", sona_ekle=False):
    """Cümleyi ilgili paragrafa ekle. Uygun yer yoksa None."""
    lines = body.split("\n")
    faq = None
    en_iyi, en_skor = None, 0
    for i, line in enumerate(lines):
        if _FAQ.match(line.strip()):
            faq = i
            break
        if not _paragraf_mi(line):
            continue
        if yol and yol in line:
            continue
        skor = ortus(kok_hedef, kokler(line))
        if skor > en_skor:
            en_iyi, en_skor = i, skor
    if en_skor > 0 and en_iyi is not None:
        if sar_anchor and yol:
            sarilmis = _sar(lines[en_iyi], sar_anchor, yol)
            if sarilmis:
                lines[en_iyi] = sarilmis
                return "\n".join(lines), "sarma"
        lines[en_iyi] = lines[en_iyi].rstrip() + " " + sentence
        return "\n".join(lines), "cumle"
    if sona_ekle:
        son = None
        limit = faq if faq is not None else len(lines)
        for i in range(limit):
            if _paragraf_mi(lines[i]):
                son = i
        if son is not None and lines[son].count("](/kategori/") < 2 and (not yol or yol not in lines[son]):
            lines[son] = lines[son].rstrip() + " " + sentence
            return "\n".join(lines), "cumle"
    if not serbest_paragraf:
        return None
    if faq is not None:
        # FAQ başlığının hemen öncesine, boş satırla.
        ek = [sentence, ""]
        if faq > 0 and lines[faq - 1].strip():
            ek = ["", sentence, ""]
        lines[faq:faq] = ek
        return "\n".join(lines), "paragraf"
    return body.rstrip() + "\n\n" + sentence + "\n", "paragraf"


def _kaynak_adaylari(hedef, makaleler, gelen, yeni_sayisi, denenen, dolu_esigi=None):
    """İlgili ve hâlâ yeri olan kaynaklar. Önce aynı alt kategori, güçlü olan önde."""
    hedef_kok = _hedef_kok(hedef)
    hedef_yol = hedef["yol"]
    aday = []
    for m in makaleler:
        if m["yol"] == hedef_yol or m["yol"] in denenen:
            continue
        if yeni_sayisi.get(m["yol"], 0) >= MAX_YENI:
            continue
        giden_yollar = govde_yollari(m["body"])
        if hedef_yol in giden_yollar:
            continue
        ayni_alt = bool(hedef.get("alt_kategori") or hedef.get("subcategory")) and (
            m.get("category") == (hedef.get("kategori") or hedef.get("category"))
            and (m.get("subcategory") or "") == (hedef.get("alt_kategori") or hedef.get("subcategory") or "")
        )
        ayni_kat = m.get("category") == (hedef.get("kategori") or hedef.get("category"))
        giden_makale = sum(1 for y in giden_yollar if y.startswith("/makale/"))
        if dolu_esigi and giden_makale >= dolu_esigi and not ayni_alt:
            continue
        govde_kok = kokler(m["body"])
        cift = ortusen_kokler(hedef_kok, govde_kok)
        ortak = len(cift)
        en_uzun = max((max(len(x), len(y)) for x, y in cift), default=0)
        if hedef.get("tur") == "kategori":
            if hedef.get("alt_kategori"):
                if not ayni_alt:
                    continue
            elif not ayni_kat:
                continue
            tier = 0
        elif ayni_alt:
            tier = 0
        elif ayni_kat and ortak >= 2:
            tier = 1
        elif (not ayni_kat) and ortak >= 2 and en_uzun >= 6:
            tier = 2
        else:
            continue
        guc = len(gelen.get(m["yol"], ()))
        aday.append((tier, -guc, yeni_sayisi.get(m["yol"], 0), m.get("date") or "", m))
    aday.sort(key=lambda row: row[:4])
    return [row[-1] for row in aday]


def _kaydet(makale, yeni_body, bugun):
    original = makale["original"]
    if not original.startswith("---"):
        raise ValueError(f"Ön bilgi yok: {makale['dosya']}")
    _pre, fm, _eski = original.split("---", 2)
    if re.search(r"(?m)^updated:", fm):
        fm = re.sub(r"(?m)^updated:.*$", f'updated: "{bugun}"', fm, count=1)
    elif re.search(r"(?m)^date:", fm):
        fm = re.sub(r"(?m)^(date:.*)$", rf'\1\nupdated: "{bugun}"', fm, count=1)
    else:
        fm = fm.rstrip("\n") + f'\nupdated: "{bugun}"\n'
    text = "---" + fm + "---\n" + yeni_body.strip() + "\n"
    with open(makale["dosya"], "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    makale["original"] = text
    makale["body"] = "\n" + yeni_body.strip() + "\n"


def _istatistik(makaleler, categories, gelen):
    kat = kategori_kayitlari(categories, makaleler)
    yetim_makale = []
    yetim_kategori = []
    makalesiz = []
    for m in makaleler:
        n = len(gelen.get(m["yol"], ()))
        if n <= 1:
            yetim_makale.append(m["yol"])
    for k in kat:
        n = len(gelen.get(k["yol"], ()))
        if k["makale_sayisi"] <= 0:
            if n <= 1:
                makalesiz.append(k["yol"])
            continue
        if n <= 1:
            yetim_kategori.append(k["yol"])
    return {
        "makale": len(makaleler),
        "kategori": len(kat),
        "yetim_makale": len(yetim_makale),
        "yetim_kategori": len(yetim_kategori),
        "yetim": len(yetim_makale) + len(yetim_kategori),
        "makalesiz_kategori": len(makalesiz),
        "yetim_makale_yollar": yetim_makale,
        "yetim_kategori_yollar": yetim_kategori,
    }


def guclendir(articles_dir=None, bugun=None, gsc=None, gsc_yolu=None, uygula=True, categories=None):
    """0-1 gövde linkli makale ve dolu kategori sayfalarına bağlamsal link ekle.

    Makalesi olmayan kategoriye link yazılmaz. Dönüş, önce/sonra sayıları ve
    eklenen linklerin listesidir. uygula False ise dosya değişmez.
    """
    articles_dir = articles_dir or ARTICLES
    root = os.path.dirname(os.path.abspath(articles_dir))
    if categories is None:
        categories = load_categories(os.path.join(root, "categories.json"))
    if gsc is None:
        gsc = gsc_yukle(gsc_yolu or os.path.join(root, "analytics_gsc.json"))
    bugun = bugun or date.today().isoformat()
    makaleler = load_articles(articles_dir, categories)
    _giden, gelen = govde_graf(makaleler)
    once = _istatistik(makaleler, categories, gelen)
    gsc_yollar = gsc_hedef_yollar(gsc, makaleler)
    gsc_kume = set(gsc_yollar)
    by_yol = {m["yol"]: m for m in makaleler}
    kategoriler = kategori_kayitlari(categories, makaleler)

    hedefler = []
    for m in makaleler:
        n = len(gelen.get(m["yol"], ()))
        if n >= (HEDEF_GSC if m["yol"] in gsc_kume else HEDEF_GELEN):
            continue
        if n > 1 and m["yol"] not in gsc_kume:
            continue
        hedefler.append({
            "yol": m["yol"],
            "tur": "makale",
            "baslik": m["title"],
            "title": m["title"],
            "focus": m["focus"],
            "kategori": m["category"],
            "alt_kategori": m["subcategory"],
            "category": m["category"],
            "subcategory": m["subcategory"],
            "subcategory_name": m["subcategory_name"],
            "slug": m["slug"],
            "gsc": m["yol"] in gsc_kume,
            "gelen": n,
        })
    for k in kategoriler:
        if k["makale_sayisi"] <= 0:
            continue
        n = len(gelen.get(k["yol"], ()))
        if n >= HEDEF_GELEN:
            continue
        hedefler.append({
            "yol": k["yol"],
            "tur": "kategori",
            "baslik": k["baslik"],
            "title": k["baslik"],
            "focus": "",
            "kategori": k["kategori"],
            "alt_kategori": k["alt_kategori"],
            "category": k["kategori"],
            "subcategory": k["alt_kategori"],
            "subcategory_name": k["baslik"] if k["alt_kategori"] else "",
            "gsc": k["yol"] in gsc_kume,
            "gelen": n,
        })
    hedefler.sort(key=lambda h: (
        0 if h["gsc"] else 1,
        h["gelen"],
        0 if h["tur"] == "makale" else 1,
        h["yol"],
    ))

    kullanilan_anchor = set()
    for m in makaleler:
        for match in re.finditer(r"\[([^\]]+)\]\(/", m["body"]):
            kullanilan_anchor.add(match.group(1).casefold())
    yeni_sayisi = defaultdict(int)
    yeni_paragraf = defaultdict(int)
    kalip_idx = defaultdict(int)
    eklenen = []

    for hedef in hedefler:
        tavan = HEDEF_GSC if hedef["gsc"] else HEDEF_GELEN
        denenen = set()
        while len(gelen.get(hedef["yol"], ())) < tavan:
            adaylar = _kaynak_adaylari(hedef, makaleler, gelen, yeni_sayisi, denenen)
            if not adaylar:
                break
            kaynak = adaylar[0]
            denenen.add(kaynak["yol"])
            if hedef["tur"] == "kategori":
                anchor = _kat_anchor(hedef["baslik"], kullanilan_anchor)
            else:
                kaynak_makale = by_yol.get(hedef["yol"])
                anchor = _anchor_sec(_anchor_adaylari(kaynak_makale or hedef), kullanilan_anchor)
            if not anchor:
                continue
            ayni = (
                hedef["tur"] == "kategori"
                or (
                    kaynak.get("category") == hedef.get("category")
                    and (kaynak.get("subcategory") or "") == (hedef.get("subcategory") or "")
                    and bool(hedef.get("subcategory"))
                )
            )
            serbest = ayni and yeni_paragraf[kaynak["yol"]] < MAX_YENI_PARAGRAF
            cumle = _cumle(
                hedef, anchor, hedef["yol"], kalip_idx[kaynak["yol"]],
                kategori=(hedef["tur"] == "kategori"),
            )
            if yasak_var(cumle):
                continue
            sonuc = _yerlestir(
                kaynak["body"], cumle, _hedef_kok(hedef), serbest,
                sar_anchor=anchor if hedef["tur"] == "makale" else "",
                yol=hedef["yol"],
                sona_ekle=(hedef["tur"] == "kategori"),
            )
            if not sonuc:
                continue
            yeni_body, nasil = sonuc
            if nasil == "paragraf":
                yeni_paragraf[kaynak["yol"]] += 1
            kaynak["body"] = yeni_body if yeni_body.startswith("\n") or yeni_body.startswith("\r") else "\n" + yeni_body.lstrip("\n")
            # load_articles body'i frontmatter sonrası ham metin olarak tutar; başında boş satır olabilir.
            if not kaynak["body"].startswith("\n"):
                kaynak["body"] = "\n" + kaynak["body"]
            gelen[hedef["yol"]].add(kaynak["yol"])
            yeni_sayisi[kaynak["yol"]] += 1
            kalip_idx[kaynak["yol"]] += 1
            kullanilan_anchor.add(anchor.casefold())
            eklenen.append({
                "kaynak": kaynak["yol"],
                "hedef": hedef["yol"],
                "anchor": anchor,
                "nasil": nasil,
                "cumle": cumle if nasil != "sarma" else f"[{anchor}]({hedef['yol']})",
            })
            if uygula:
                _kaydet(kaynak, kaynak["body"], bugun)

    _giden2, gelen2 = govde_graf(makaleler)
    sonra = _istatistik(makaleler, categories, gelen2)
    return {
        "once": once,
        "sonra": sonra,
        "eklenen": eklenen,
        "eklenen_sayisi": len(eklenen),
        "gsc_hedef": gsc_yollar,
        "uygula": uygula,
    }


def yeni_makaleye_geri_link(slug, articles_dir=None, bugun=None, gsc=None, categories=None):
    """Yeni makaleye, aynı konudaki 2-3 eski makaleden birer gövde linki ekle.

    İlgili eski makale yoksa zorlama yapılmaz. Taslak slug için 0 döner.
    Her eski sayfa bu çağrıda tek link alır ve sayfa başına 5 yeni link tavanına uyar.
    """
    articles_dir = articles_dir or ARTICLES
    root = os.path.dirname(os.path.abspath(articles_dir))
    if categories is None:
        categories = load_categories(os.path.join(root, "categories.json"))
    bugun = bugun or date.today().isoformat()
    makaleler = load_articles(articles_dir, categories)
    yeni = next((m for m in makaleler if m["slug"] == slug), None)
    if not yeni:
        return 0
    secilen = _geri_plan(yeni, makaleler)
    if not secilen:
        return 0
    return _geri_uygula(yeni, makaleler, secilen, bugun)


def _geri_plan(yeni, makaleler):
    _giden, gelen = govde_graf(makaleler)
    hedef = {
        "yol": yeni["yol"],
        "tur": "makale",
        "baslik": yeni["title"],
        "title": yeni["title"],
        "focus": yeni["focus"],
        "kategori": yeni["category"],
        "alt_kategori": yeni["subcategory"],
        "category": yeni["category"],
        "subcategory": yeni["subcategory"],
        "subcategory_name": yeni["subcategory_name"],
        "gsc": True,
        "gelen": 0,
    }
    kullanilan = set()
    for m in makaleler:
        for match in re.finditer(r"\[([^\]]+)\]\(/", m["body"]):
            kullanilan.add(match.group(1).casefold())
    yeni_sayisi = defaultdict(int)
    denenen = set()
    secilen = []
    while len(secilen) < 3:
        aday = _kaynak_adaylari(
            hedef, makaleler, gelen, yeni_sayisi, denenen, dolu_esigi=8)
        if not aday:
            break
        kaynak = aday[0]
        denenen.add(kaynak["yol"])
        anchor = _anchor_sec(_anchor_adaylari(yeni), kullanilan)
        if not anchor:
            break
        secilen.append({
            "kaynak": kaynak["yol"],
            "hedef": yeni["yol"],
            "anchor": anchor,
        })
        kullanilan.add(anchor.casefold())
        yeni_sayisi[kaynak["yol"]] += 1
        gelen[yeni["yol"]].add(kaynak["yol"])
    return secilen


def _geri_uygula(yeni, makaleler, secilen, bugun):
    by_yol = {m["yol"]: m for m in makaleler}
    yazilan = 0
    kalip_idx = defaultdict(int)
    yeni_paragraf = defaultdict(int)
    for satir in secilen[:3]:
        kaynak = by_yol.get(satir["kaynak"])
        if not kaynak or satir["hedef"] in govde_yollari(kaynak["body"]):
            continue
        anchor = satir["anchor"]
        ayni = (
            kaynak.get("category") == yeni.get("category")
            and (kaynak.get("subcategory") or "") == (yeni.get("subcategory") or "")
            and bool(yeni.get("subcategory"))
        )
        serbest = ayni and yeni_paragraf[kaynak["yol"]] < MAX_YENI_PARAGRAF
        cumle = _cumle(yeni, anchor, yeni["yol"], kalip_idx[kaynak["yol"]])
        if yasak_var(cumle):
            continue
        sonuc = _yerlestir(
            kaynak["body"], cumle, _hedef_kok(yeni), serbest,
            sar_anchor=anchor, yol=yeni["yol"],
        )
        if not sonuc:
            # İlgili paragraf şartı tutmadıysa ve aynı alt kategorideyse paragraf aç.
            if not ayni:
                continue
            sonuc = _yerlestir(kaynak["body"], cumle, set(), True, sar_anchor="", yol=yeni["yol"])
            if not sonuc:
                continue
        yeni_body, nasil = sonuc
        if nasil == "paragraf":
            yeni_paragraf[kaynak["yol"]] += 1
        _kaydet(kaynak, yeni_body, bugun)
        kalip_idx[kaynak["yol"]] += 1
        yazilan += 1
    return yazilan


class _BaglantiAyikla(HTMLParser):
    """header, footer ve breadcrumb dışındaki linkleri içerik sayar."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self._skip = 0
        self._stack = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cls = (attrs.get("class") or "").split()
        region = None
        if tag in ("header", "footer"):
            region = tag
        elif tag == "nav" and "breadcrumb" in cls:
            region = "nav"
        if region:
            self._skip += 1
            self._stack.append(region)
        href = (attrs.get("href") or "").strip()
        if href:
            self.links.append((href, self._skip == 0))

    def handle_endtag(self, tag):
        if not self._stack:
            return
        beklenen = "nav" if self._stack[-1] == "nav" else self._stack[-1]
        if tag == beklenen:
            self._stack.pop()
            self._skip = max(0, self._skip - 1)


def html_yol(site, path):
    rel = os.path.relpath(path, site).replace(os.sep, "/")
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        return "/" + rel[: -len("index.html")]
    return "/" + rel


def html_graf(site_dir):
    """Sayfa -> (tüm hedefler, içerik hedefleri). Yönlendirme sayfaları ayrı döner."""
    giden = {}
    icerik = {}
    yonlendirme = set()
    for root, _dirs, files in os.walk(site_dir):
        for fn in files:
            if not fn.endswith(".html"):
                continue
            full = os.path.join(root, fn)
            yol = html_yol(site_dir, full)
            try:
                with open(full, encoding="utf-8") as f:
                    text = f.read()
            except OSError:
                continue
            if 'http-equiv="refresh"' in text or "http-equiv='refresh'" in text:
                yonlendirme.add(yol)
            parser = _BaglantiAyikla()
            try:
                parser.feed(text)
            except Exception:
                continue
            tum, ic = set(), set()
            for href, icinde in parser.links:
                hedef = norm_yol(href)
                if not hedef or hedef == yol:
                    continue
                tum.add(hedef)
                if icinde:
                    ic.add(hedef)
            giden[yol] = tum
            icerik[yol] = ic
    return giden, icerik, yonlendirme


def tik_derinligi(giden, bas="/"):
    dist = {bas: 0}
    kuyruk = [bas]
    while kuyruk:
        cur = kuyruk.pop(0)
        for nxt in giden.get(cur, ()):
            if nxt not in dist:
                dist[nxt] = dist[cur] + 1
                kuyruk.append(nxt)
    return dist


def sitemap_yollari(site_dir, base_url):
    path = os.path.join(site_dir, "sitemap.xml")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        text = f.read()
    base = (base_url or "").rstrip("/")
    yollar = []
    for loc in re.findall(r"<loc>([^<]+)</loc>", text):
        yol = norm_yol(loc)
        if not yol and base and loc.startswith(base):
            yol = norm_yol(loc[len(base):])
        if yol:
            yollar.append(yol)
    return yollar


def raporu_yaz(site_dir, content_dir=None, yonlendirmeler=None, gsc_yolu=None):
    """Makale ve kategori sayfalarının gelen iç link raporu.

    Dosya: content/inlink_raporu.json. Site haritasında olup hiçbir sayfadan
    link almayan adresler ve ana sayfadan 3 tıklamadan uza kalanlar ayrıca yazılır.
    Yönlendirme sayfaları bu iki listeden çıkar.
    """
    content_dir = content_dir or CONTENT
    categories = load_categories(os.path.join(content_dir, "categories.json"))
    makaleler = load_articles(os.path.join(content_dir, "articles"), categories)
    _giden_md, gelen = govde_graf(makaleler)
    gsc = gsc_yukle(gsc_yolu or os.path.join(content_dir, "analytics_gsc.json"))
    gsc_yollar = gsc_hedef_yollar(gsc, makaleler)
    gsc_kume = set(gsc_yollar)
    html_giden, html_icerik, html_yon = html_graf(site_dir)
    gelen_tum = defaultdict(set)
    gelen_icerik = defaultdict(set)
    for src, hedefler in html_giden.items():
        if src in html_yon:
            continue
        for hedef in hedefler:
            gelen_tum[hedef].add(src)
    for src, hedefler in html_icerik.items():
        if src in html_yon:
            continue
        for hedef in hedefler:
            gelen_icerik[hedef].add(src)
    derinlik = tik_derinligi(html_giden)
    site_json = _json_oku(os.path.join(content_dir, "site.json")) or {}
    sitemap = sitemap_yollari(site_dir, site_json.get("base_url") or "")
    haric = set(yonlendirmeler or ()) | html_yon
    for yol in list(haric):
        haric.add(norm_yol(yol))

    def sayfa_kaydi(yol, tur, baslik, kategori, alt, makale_sayisi=None):
        govde_kaynak = sorted(gelen.get(yol, ()))
        return {
            "yol": yol,
            "tur": tur,
            "baslik": baslik,
            "kategori": kategori,
            "alt_kategori": alt,
            "govde_gelen": len(govde_kaynak),
            "icerik_gelen": len(gelen_icerik.get(yol, ())),
            "toplam_gelen": len(gelen_tum.get(yol, ())),
            "tik": derinlik.get(yol),
            "gsc_oncelik": yol in gsc_kume,
            "govde_kaynaklar": govde_kaynak,
            "makale_sayisi": makale_sayisi,
        }

    sayfalar = []
    for m in makaleler:
        sayfalar.append(sayfa_kaydi(
            m["yol"], "makale", m["title"], m["category"], m["subcategory"],
        ))
    kategoriler = kategori_kayitlari(categories, makaleler)
    for k in kategoriler:
        sayfalar.append(sayfa_kaydi(
            k["yol"], "kategori", k["baslik"], k["kategori"], k["alt_kategori"], k["makale_sayisi"],
        ))

    yetimler = []
    makalesiz = []
    for s in sayfalar:
        if s["govde_gelen"] > 1:
            continue
        if s["tur"] == "kategori" and (s.get("makale_sayisi") or 0) <= 0:
            makalesiz.append({
                "yol": s["yol"],
                "baslik": s["baslik"],
                "govde_gelen": s["govde_gelen"],
                "toplam_gelen": s["toplam_gelen"],
                "tik": s["tik"],
            })
            continue
        yetimler.append({
            "yol": s["yol"],
            "tur": s["tur"],
            "baslik": s["baslik"],
            "kategori": s["kategori"],
            "alt_kategori": s["alt_kategori"],
            "govde_gelen": s["govde_gelen"],
            "toplam_gelen": s["toplam_gelen"],
            "tik": s["tik"],
            "gsc_oncelik": s["gsc_oncelik"],
            "govde_kaynaklar": s["govde_kaynaklar"],
        })
    yetimler.sort(key=lambda s: (0 if s["gsc_oncelik"] else 1, s["govde_gelen"], s["tur"], s["yol"]))

    linksiz = []
    uzak = []
    for yol in sitemap:
        if yol in haric:
            continue
        if len(gelen_tum.get(yol, ())) == 0 and yol != "/":
            # Ana sayfa grafın köküdür; gelen linki olmasa da başlangıçtır.
            linksiz.append(yol)
        tik = derinlik.get(yol)
        if tik is None or tik > 3:
            uzak.append({"yol": yol, "tik": tik})

    yetim_makale = sum(1 for s in yetimler if s["tur"] == "makale")
    yetim_kategori = sum(1 for s in yetimler if s["tur"] == "kategori")
    rapor = {
        "tanim": (
            "govde_gelen, başka bir makalenin gövdesinden gelen benzersiz iç linktir. "
            "Üst menü, altbilgi ve ekmek kırıntısı bu sayıda yoktur. "
            "yetim: yayındaki makale ya da içinde makalesi olan kategori sayfası, govde_gelen 0 veya 1 ise. "
            "Makalesi olmayan kategori sayfası menüden ulaşılır; alakasız gövde linki eklenmez ve makalesiz listesindedir. "
            "toplam_gelen, üretilmiş HTML içindeki diğer sayfalardan gelen benzersiz linktir. "
            "tik, ana sayfadan tıklama derinliğidir. "
            "gsc_oncelik, analytics_gsc.json içinde ortalama pozisyonu 8-20 olan sorguya denk sayfadır; dosya yoksa veya ok değilse boş kalır."
        ),
        "ozet": {
            "makale": len(makaleler),
            "kategori": len(kategoriler),
            "yetim_makale": yetim_makale,
            "yetim_kategori": yetim_kategori,
            "yetim": len(yetimler),
            "makalesiz_kategori": len(makalesiz),
            "sitemap_linksiz": linksiz,
            "uc_tik_disi": uzak,
            "gsc_dosyasi": bool(gsc),
            "gsc_uygun": bool(gsc_yollar),
            "gsc_hedef": gsc_yollar,
        },
        "yetimler": yetimler,
        "makalesiz": makalesiz,
        "sayfalar": sayfalar,
    }
    os.makedirs(content_dir, exist_ok=True)
    hedef = os.path.join(content_dir, "inlink_raporu.json")
    with open(hedef, "w", encoding="utf-8", newline="\n") as f:
        json.dump(rapor, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return rapor


def erisim_denetle(rapor):
    """Site haritasında linksiz ya da 3 tıklamadan uzak sayfa varsa build durur.

    Yönlendirme sayfaları rapor üretilirken elenmiş olmalıdır.
    """
    ozet = (rapor or {}).get("ozet") or {}
    linksiz = ozet.get("sitemap_linksiz") or []
    uzak = ozet.get("uc_tik_disi") or []
    if not linksiz and not uzak:
        return
    satirlar = []
    for yol in linksiz:
        satirlar.append(f"linksiz: {yol}")
    for row in uzak:
        satirlar.append(f"3 tıklamadan uzak ({row.get('tik')}): {row.get('yol')}")
    raise RuntimeError("İç erişim denetimi başarısız:\n" + "\n".join(satirlar[:30]))


def _main():
    import sys
    dry = "--dry-run" in sys.argv
    sonuc = guclendir(uygula=not dry)
    once, sonra = sonuc["once"], sonuc["sonra"]
    print(f"yetim makale: {once['yetim_makale']} -> {sonra['yetim_makale']}")
    print(f"yetim kategori: {once['yetim_kategori']} -> {sonra['yetim_kategori']}")
    print(f"yetim toplam: {once['yetim']} -> {sonra['yetim']}")
    print(f"makalesiz kategori (link eklenmedi): {sonra['makalesiz_kategori']}")
    print(f"eklenen gövde linki: {sonuc['eklenen_sayisi']}")
    if sonuc["gsc_hedef"]:
        print("GSC hedef:", ", ".join(sonuc["gsc_hedef"]))
    else:
        print("GSC hedef yok (dosya boş veya pozisyon 8-20 eşleşmedi).")
    for e in sonuc["eklenen"]:
        print(f"  {e['kaynak']} -> {e['hedef']} [{e['anchor']}] {e['nasil']}")


if __name__ == "__main__":
    _main()
