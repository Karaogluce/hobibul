#!/usr/bin/env python3
"""Hobi Bul — günlük otomatik makale hattı.

  python otomatik.py --adet 2            # sıradaki 2 konuyu üret (varsayılan: TASLAK modu)
  python otomatik.py --adet 2 --yayinla  # taslak değil, doğrudan yayına hazır yaz
  python otomatik.py --konu-listesi      # sıradaki konuları göster (API çağırmaz)

Akış: konu seç → Google Autocomplete'ten gerçek Türkçe sorguları çek → Gemini ile yaz
(yalnızca products.json verisiyle) → kalite kapıları → Unsplash'tan görsel → .md yaz.
Kapıdan geçemeyen makale YAYINLANMAZ, content/uretim_log.json'a işlenir.

Ortam değişkenleri: GEMINI_API_KEY, UNSPLASH_ACCESS_KEY, GEMINI_MODEL (ops.), TASLAK_MODU (true/false)
"""
import argparse
import json
import os
import re
import statistics
import sys
from collections import Counter
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

import yeni_makale as ym

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CONTENT, ARTICLES = ym.CONTENT, ym.ARTICLES
LOG_PATH = os.path.join(CONTENT, "uretim_log.json")
POOL_PATH = os.path.join(CONTENT, "konu_havuzu.json")
YEAR = date.today().year
UA = {"User-Agent": "Mozilla/5.0 (HobiBul-bot)"}

CAT_EN = {
    "outdoor": "camping outdoor nature", "el-sanatlari": "handmade crafts", "muzik": "music instruments",
    "teknoloji": "technology gadgets", "koleksiyon": "collectibles hobby", "spor-fitness": "fitness workout",
    "sanat": "art painting studio", "yemek-mutfak": "cooking kitchen", "bahce-bitki": "gardening plants",
    "evcil-hayvan": "pets", "bilim-astronomi": "astronomy telescope", "seyahat-gezi": "travel adventure",
    "yazilim-kodlama": "coding laptop", "yazi-edebiyat": "writing books",
}

TIPLER = {
    "rehber": dict(
        min=800, hepsi=True,
        baslik=lambda s: f"En İyi {s} Ekipmanları ({YEAR}): Alım Rehberi",
        yapi="Kısa giriş (odak anahtar kelime ilk paragrafta geçsin) → '## Satın Almadan Önce Nelere Bakmalı?' (genel, "
             "doğrulanabilir bilgiler; sayı/ölçü uydurma) → '## En İyi Seçenekler' altında her ürün için ### başlık → "
             "'## Hangisini Seçmeli?' (kullanım senaryosuna göre kısa eşleştirme) → '## Sık Sorulan Sorular' (3-4 soru) → kapanış: tek cümlelik net tavsiye ('Sonuç' başlığı kullanma).",
    ),
    "yeni_baslayan": dict(
        min=750, hepsi=True,
        baslik=lambda s: f"{s} İçin Yeni Başlayanlar Rehberi: İlk Alınacak Ekipmanlar",
        yapi="Giriş (başlangıç kaygıları) → '## Başlamadan Önce Bilmen Gerekenler' → '## İlk Alışverişte Öncelik Sırası' altında "
             "ürünleri neden bu sırayla alınacağıyla ### başlıklar halinde anlat → '## Yeni Başlayanların Sık Yaptığı Hatalar' → "
             "'## Sık Sorulan Sorular' (3-4 soru) → kapanış: tek cümlelik net tavsiye ('Sonuç' başlığı kullanma).",
    ),
    "hatalar": dict(
        min=700, hepsi=False,
        baslik=lambda s: f"{s} Ekipmanı Alırken Yapılan 7 Hata ve Nasıl Kaçınılır",
        yapi="Giriş → 7 numaralı hata, her biri ### başlık + 'neden sorun' + 'ne yapmalı' → hataların 2-3'üne uygun ürünlerden "
             "doğal biçimde link ver → '## Sık Sorulan Sorular' (3 soru) → kapanış: tek cümlelik net tavsiye ('Sonuç' başlığı kullanma).",
    ),
    "sss": dict(
        min=700, hepsi=False,
        baslik=lambda s: f"{s} Hakkında Sık Sorulan Sorular: Cevaplarıyla Kısa Rehber",
        yapi="Kısa giriş → 8-10 soru, her biri ### başlık olarak (aşağıdaki gerçek arama sorgularından seç) ve 2-4 cümlelik net cevap → "
             "uygun cevaplarda 2-3 üründen doğal biçimde link ver → '## Sık Sorulan Sorular' başlığını da kullan (ör. 'Hâlâ Aklında Soru Var mı?') → kapanış: tek cümlelik net tavsiye ('Sonuç' başlığı kullanma).",
    ),
    "kontrol_listesi": dict(
        min=700, hepsi=False,
        baslik=lambda s: f"{s} Kontrol Listesi: Eksiksiz Hazırlık",
        yapi="Kısa giriş (hedef sorguya ilk paragrafta cevap) → '## Neye İhtiyacın Var?' (hangi durumda hangi ekipman, "
             "ürün verisine dayalı genel gerekçeler) → '## Kontrol Listesi' altında madde madde liste; her maddede o şeyin neden "
             "gerektiğini tek cümleyle açıkla → '## Listeyi Kendine Göre Uyarlama' (kısa/uzun hazırlık, mevsim, deneyim farkı) → "
             "'## Sık Sorulan Sorular' (3-4 soru) → kapanış: tek cümlelik net tavsiye ('Sonuç' başlığı kullanma). Listede geçen en az 2 üründen doğal biçimde link ver.",
    ),
    "nasil_yapilir": dict(
        min=750, hepsi=False,
        baslik=lambda s: f"{s} Nasıl Yapılır? Adım Adım Rehber",
        yapi="Kısa giriş (hedef sorguya ilk iki cümlede cevap) → '## Gerekli Malzemeler ve Hazırlık' (kısa liste) → "
             "'## Adım Adım Uygulama' altında her adımı ### başlık yaparak sırayla anlat → '## Yeni Başlayanların Sık Yaptığı Hatalar' → "
             "'## Sık Sorulan Sorular' (3-4 soru) → kapanış: tek cümlelik net tavsiye ('Sonuç' başlığı kullanma). Uygun adımlarda en az 2 üründen doğal biçimde link ver.",
    ),
}
ESKI_TIPLER = ("rehber", "yeni_baslayan", "hatalar", "sss")
YENI_TIPLER = ("kontrol_listesi", "nasil_yapilir")
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


def yeni_tip_konulari(products, c, pool, used):
    items = []
    subs = {s["id"]: s["name"] for s in c["subcategories"]}
    for e in pool:
        tip, sub = e.get("tip_onerisi"), e.get("alt")
        sorgu = re.sub(r"\s+", " ", str(e.get("sorgu", ""))).strip()
        plist = products.get(c["id"], {}).get(sub, [])
        if tip not in YENI_TIPLER or e.get("kategori") != c["id"] or sub not in subs or not sorgu:
            continue
        if len(plist) < 3:
            continue
        sslug = ym.slugify(sorgu)
        if not sslug or sslug in used:
            continue
        used.add(sslug)
        items.append(dict(
            key=f"{tip}:{c['id']}:{sub}:{sslug}", tip=tip, cat=c["id"], cat_name=c["name"],
            sub=sub, sub_name=subs[sub], ids=[p["id"] for p in plist],
            title=dogal_baslik(sorgu), sorgu=sorgu, sorgu_slug=sslug))
    return items


def topic_queue(products, cats):
    """Kategoriler arası dönüşümlü: önce mevcut tipler eski sırayla, sonra konu havuzundan yeni tipler."""
    pool, used = load_pool(), set()
    per_cat = []
    for c in cats:
        items = []
        subs = [("_main", c["name"])] + [(s["id"], s["name"]) for s in c["subcategories"]]
        for tip in ESKI_TIPLER:
            for sid, sname in subs:
                plist = products.get(c["id"], {}).get(sid, [])
                if len(plist) < 3:
                    continue
                items.append(dict(
                    key=f"{tip}:{c['id']}:{sid}", tip=tip, cat=c["id"], cat_name=c["name"],
                    sub=sid, sub_name=sname, ids=[p["id"] for p in plist],
                    title=TIPLER[tip]["baslik"](sname)))
        items += yeni_tip_konulari(products, c, pool, used)
        per_cat.append(items)
    out, i = [], 0
    while any(per_cat):
        for items in per_cat:
            if i < len(items):
                out.append(items[i])
        i += 1
        if i > 400:
            break
    return out


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
                if s not in out and len(s) > len(base) + 3 and not re.search(r"\d+\s*(tl|₺)|fiyat|ucuz|indirim", s):
                    out.append(s)
        except Exception:
            continue
    return out[:14]


# ------------------------------------------------------------------ prompt / parse
def build_prompt(t, prods, sugg, guide=""):
    cfg = TIPLER[t["tip"]]
    plist = "\n".join(
        f"- id: {p['id']}\n  ad: {p['name']}\n  marka: {p.get('brand','')}\n  açıklama: {p.get('desc','')}\n"
        f"  artılar: {'; '.join(p.get('pros', []))}\n  eksiler: {'; '.join(p.get('cons', []))}"
        + (f"\n  yazarın notu: {p['not']}" if p.get('not') else "") for p in prods)
    sq = "\n".join(f"- {s}" for s in sugg) or "- (sorgu bulunamadı; konuyla ilgili doğal sorular kullan)"
    zorunlu = ("HER ÜRÜN için en az bir kez" if cfg["hepsi"] else "en az 2 ürün için")
    return f"""Sen Türkiye'deki hobi meraklıları için yazan deneyimli bir blog editörüsün. Aşağıdaki konuda özgün, işe yarar, Türkçe bir makale yaz.

BAŞLIK: {t['title']}
KATEGORİ: {t['cat_name']} › {t['sub_name']}
MAKALE TİPİ: {t['tip']}
BEKLENEN YAPI: {cfg['yapi']}
HEDEF UZUNLUK: en az {cfg['min']} kelime

İNSANLARIN GERÇEKTEN ARADIĞI SORGULAR (uygun olanları başlıklara ve SSS bölümüne doğal biçimde yedir; zorlama ya da tekrar yapma):
{sq}

KULLANABİLECEĞİN ÜRÜNLER (başka ürün, marka veya model ekleme):
{plist}

KESİN KURALLAR:
1. Ürün verilerinde olmayan teknik özellik, ağırlık, ölçü, fiyat, puan, test sonucu veya "denedik" iddiası UYDURMA. Emin olmadığın bilgiyi yazma.
2. Fiyat yazma. Gerekirse "güncel fiyatı Amazon'da kontrol et" de.
3. Ürün linkini şu biçimde ver ({zorunlu}): [Satın Al: ÜRÜN ADI](aff://ÜRÜN_ID)
4. Yalnızca Markdown. En üstte H1 yok. Tablo kullanma. ## ve ### başlıkları, kısa paragraflar, madde listeleri kullan.
5. Doğal, samimi, abartısız Türkçe. "Mükemmel", "piyasa lideri", "kesinlikle", "garanti" gibi kanıtsız iddialar yok. Her paragraf bilgi taşısın, dolgu cümle yazma.
6. Başka sitelerden metin alma; kalıp cümleleri tekrarlama.

YAZIM REHBERİ (bunu sıkı uygula; okuyucuya bir insanın yazdığı gibi gelmeli, ama kimseyi yanıltma):
{guide}

ÇIKTI BİÇİMİ (tam olarak böyle):
GORSEL: <Unsplash'ta aratılacak 2-4 kelimelik İNGİLİZCE sorgu; marka/ürün adı yok; konuyu görsel olarak anlatsın>
ANAHTAR: <odak anahtar kelime, Türkçe, 2-4 kelime>
ACIKLAMA: <140-155 karakterlik Türkçe meta açıklama, odak anahtar kelimeyi içersin>
---
<makale metni>
"""


def edit_prompt(body, prods, guide):
    veri = "\n".join(f"- {p['id']}: {p['name']} | {p.get('desc','')} | artı: {'; '.join(p.get('pros', []))} | eksi: {'; '.join(p.get('cons', []))}" for p in prods)
    return f"""Sen titiz bir Türkçe blog editörüsün. Aşağıdaki taslağı, YAZIM REHBERİ'ne göre elden geçir.

YAPILACAKLAR:
1. Yasaklı kalıpları, klişe girişleri ve dolgu cümleleri kaldır ya da somut ifadeyle değiştir.
2. Cümle ritmini çeşitlendir: kısa ve orta cümleleri karıştır, 28 kelimeyi geçen cümleyi böl, art arda aynı kelimeyle başlayan cümleleri değiştir.
3. Ürün verisinde bulunmayan her bilgiyi (ölçü, ağırlık, süre, puan, fiyat, "denedik/kullandım" iddiası) sil.
4. Tüm aff:// linklerini aynen koru. ## ve ### başlık sayısını koru (başlık metinlerini doğallaştırabilirsin).
5. Kelime sayısını %10'dan fazla azaltma. Yeni bilgi ekleme.
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
    lines = [l for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    text = re.sub(r"[*_>`]|^\s*[-\d.]+\s+", "", "\n".join(lines), flags=re.M)
    sents = [x for x in re.split(r"(?<=[.!?])\s+", text) if len(x.split()) >= 2]
    if len(sents) < 20:
        return "çok az cümle"
    lens = [len(x.split()) for x in sents]
    if statistics.pstdev(lens) < 5:
        return "cümle ritmi monoton"
    if sum(1 for n in lens if n > 28) / len(lens) > 0.2:
        return "çok uzun cümle fazla"
    if sum(1 for n in lens if n <= 7) / len(lens) < 0.1:
        return "kısa cümle yok"
    top = Counter(x.split()[0].lower() for x in sents).most_common(1)[0][1] / len(sents)
    if top > 0.18:
        return "aynı kelimeyle başlayan cümle çok"
    return None


def gate(body, tip, prods, others, banned=()):
    cfg = TIPLER[tip]
    words = len(body.split())
    if words < cfg["min"]:
        return f"kısa ({words} kelime)"
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
        for ph in res:
            if ph["id"] in used:
                continue
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


def write_article(t, meta, body, img, draft):
    slug = ym.slugify(t["title"])
    title = t["title"]
    mt = title if len(title) > 58 else f"{title} | Hobi Bul"
    lines = ["---", f'title: "{q(title)}"', f'slug: "{slug}"', f'category: "{t["cat"]}"',
             f'date: "{date.today().isoformat()}"', f'meta_title: "{q(mt)}"',
             f'meta_description: "{q(meta["ACIKLAMA"])[:158]}"', f'excerpt: "{q(meta["ACIKLAMA"])}"',
             f'focus_keyword: "{q(meta["ANAHTAR"])}"']
    if img:
        lines += [f'image: "{img["url"]}"', f'image_alt: "{q(img["alt"])}"',
                  f'image_credit: "{q(img["credit"])}"', f'image_credit_url: "{img["credit_url"]}"']
    lines += [f'draft: "{"true" if draft else "false"}"', "---", ""]
    path = os.path.join(ARTICLES, slug + ".md")
    os.makedirs(ARTICLES, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n" + body.strip() + "\n")
    return slug, len(body.split())


def uret(t, products, key, model, ukey, log, draft):
    pool = {p["id"]: p for s in products.values() for items in s.values() for p in items}
    prods = [pool[i] for i in t["ids"]]
    sugg = suggestions(t["sub_name"])
    if t.get("sorgu"):
        sugg = [t["sorgu"]] + [s for s in sugg if s.lower() != t["sorgu"].lower()]
    others = existing_shingles()
    guide, banned = load_guide()
    why = "bilinmiyor"
    for attempt in range(2):
        raw = ym.call_gemini(build_prompt(t, prods, sugg, guide), key, model)
        parsed = parse(raw)
        if not parsed:
            why = "çıktı biçimi bozuk"
            continue
        meta, body = parsed
        body = ym.validate(body, prods)
        edited = ym.validate(re.sub(r"^```(?:markdown)?\s*|\s*```$", "", ym.call_gemini(edit_prompt(body, prods, guide), key, model).strip()), prods)
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
    if img:
        log["photos"].append(img["id"])
    elif ukey:
        print("  ! Görsel bulunamadı; kategori görseli kullanılacak.")
    slug, n = write_article(t, meta, body, img, draft)
    return (slug, n, bool(img)), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adet", type=int, default=2)
    ap.add_argument("--yayinla", action="store_true", help="taslak yerine yayına hazır yaz")
    ap.add_argument("--taslak", action="store_true")
    ap.add_argument("--konu-listesi", action="store_true")
    a = ap.parse_args()

    ym.load_env()
    products, cats = ym.load("products.json"), ym.load("categories.json")
    log = load_log()
    have = {fn[:-3] for fn in os.listdir(ARTICLES)} if os.path.isdir(ARTICLES) else set()
    fails = {}
    for x in log["atlanan"]:
        fails[x["anahtar"]] = fails.get(x["anahtar"], 0) + 1
    done_sorgu = {k.rsplit(":", 1)[-1] for k in log["done"] if k.split(":", 1)[0] in YENI_TIPLER}
    queue = [t for t in topic_queue(products, cats)
             if t["key"] not in log["done"] and ym.slugify(t["title"]) not in have
             and t.get("sorgu_slug") not in done_sorgu and fails.get(t["key"], 0) < 2]

    if a.konu_listesi:
        print(f"Kuyrukta {len(queue)} konu. Sıradakiler:")
        for t in queue[:12]:
            print(f"  [{t['tip']}] {t['title']}")
        return

    draft_env = os.environ.get("TASLAK_MODU", "true").strip().lower() not in ("false", "0", "hayir", "hayır")
    draft = False if a.yayinla else (True if a.taslak else draft_env)
    key, ukey = os.environ.get("GEMINI_API_KEY"), os.environ.get("UNSPLASH_ACCESS_KEY")
    if not key:
        sys.exit("GEMINI_API_KEY yok.")
    if not ukey:
        print("! UNSPLASH_ACCESS_KEY yok: makaleler kategori görseliyle çıkacak.")
    model = os.environ.get("GEMINI_MODEL") or "gemini-flash-latest"

    made, tried = 0, 0
    for t in queue:
        if made >= a.adet or tried >= a.adet * 3:
            break
        tried += 1
        print(f"→ {t['title']}")
        try:
            res, why = uret(t, products, key, model, ukey, log, draft)
        except ym.GeminiError as e:
            save_log(log)
            sys.exit(f"API hatası, durduruldu: {e}")
        if res:
            slug, n, has_img = res
            log["done"].append(t["key"])
            made += 1
            print(f"  ✓ {slug}  ({n} kelime, {'taslak' if draft else 'yayın'}, görsel: {'Unsplash' if has_img else 'kategori'})")
        else:
            log["atlanan"].append({"anahtar": t["key"], "neden": why, "tarih": date.today().isoformat()})
            print(f"  ✗ atlandı: {why}")
    save_log(log)
    print(f"Bitti: {made} makale ({'TASLAK — onay bekliyor' if draft else 'yayına hazır'}).")


if __name__ == "__main__":
    main()
