#!/usr/bin/env python3
"""Faz 2 — Google Autocomplete ile konu keşfi.

Her alt kategori için "<ad> a" … "<ad> z" ve soru eklerini Autocomplete'e sorar,
sonuçları süzer, benzer sorguları kümelere indirger ve content/konu_havuzu.json yazar.
Mağaza/marka adlarını, 2015-2025 yıllarını, kiralama/satın alma ve kulüp/dernek/belge
gibi istenmeyen kelimeleri eler; alt kategori başına en fazla 15 sorgu tutar
(nasıl/nedir/listesi/malzemeleri/için en iyi öne alınır).

Bileşik adlarda Google boş dönebiliyor; bu yüzden KOK tablosundaki alt kategoriler için
kısa köklerle ("vlog içerik üretimi" yerine "vlog çekimi", "vlog kamerası") yeniden taranır.

  python konu_kesfet.py     # ilk çalıştırma ~25 dk; sonrasında önbellekten anında döner

Önbellek: content/.autocomplete_cache.json (git'e girmez). Hatalı istekler önbelleğe
yazılmaz; bir sonraki çalıştırmada yalnızca onlar yeniden sorulur.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(BASE, "content")
CATEGORIES = os.path.join(CONTENT, "categories.json")
CACHE_PATH = os.path.join(CONTENT, ".autocomplete_cache.json")
POOL_PATH = os.path.join(CONTENT, "konu_havuzu.json")

DELAY = 0.5
TIMEOUT = 15
UA = {"User-Agent": "Mozilla/5.0 (HobiBul-konu-kesfet)"}
SUFFIXES = list("abcdefghijklmnopqrstuvwxyz") + ["nasıl", "nedir", "hangi", "için en iyi"]

BAD = re.compile(r"fiyat|ucuz|indirim|₺|\btl\b|\btry\b", re.I)
BAD_BRANDS = re.compile(
    r"\b(?:a101|bim|şok|n11)\b|\b(?:trendyol|hepsiburada|amazon|sahibinden)\w*", re.I)
BAD_YEARS = re.compile(r"\b(?:201[5-9]|202[0-5])\b")
BAD_WORDS = re.compile(
    r"\bpdf\b|\bindir|\bizle|\bonline\b|\bikinci\s+el|\bkiral|\bsatın\s+al|\bkupon|\bkampanya"
    r"|\btoptan\b|\bkul[üu]b|\bderne[ğg]", re.I)
BELGE = re.compile(r"belgesi\b", re.I)
KAMP_BELGE = re.compile(r"kamp[çc]ılık\s+belgesi", re.I)
PRIORITY = re.compile(r"nasıl|nedir|listesi|malzemeleri|için en iyi", re.I)
MAX_PER_SUB = 15
NASIL = re.compile(r"nasıl\s+(?:yapılır|kurulur|yapılıyor)")
LISTE = re.compile(r"listesi|malzemeleri|ihtiyaç")
TR_LOWER = str.maketrans("ÇĞİÖŞÜI", "çğiöşüı")

# Google'ın bileşik alt kategori adlarına boş döndüğü ya da filtrelerden sonra
# 5'ten az konu kaldığı yerlerde kullanılacak kısa kökler.
KOK = {
    "outdoor/dagcilik-trekking": ["dağcılık", "trekking", "doğa yürüyüşü"],
    "el-sanatlari/mum-sabun": ["mum yapımı", "sabun yapımı"],
    "muzik/davul-perkusyon": ["davul", "perküsyon"],
    "muzik/keman-yayli": ["keman", "yaylı çalgılar"],
    "muzik/dj-produksiyon": ["müzik prodüksiyonu", "dj seti"],
    "teknoloji/oyun-pc-modlama": ["oyun modlama", "modlama"],
    "koleksiyon/masaustu-oyun": ["masa oyunu", "minyatür oyun"],
    "sanat/heykel": ["heykel yapımı", "heykel"],
    "sanat/kaligrafi-cizim": ["kaligrafi", "çizim"],
    "seyahat-gezi/backpacking": ["sırt çantası", "backpacking"],
    "seyahat-gezi/seyahat-fotograf": ["seyahat fotoğraf", "gezi fotoğraf", "seyahat fotoğraf makinesi"],
    "seyahat-gezi/karavan": ["karavan", "karavan yaşam"],
    "seyahat-gezi/vlog": ["vlog çekimi", "vlog kamerası", "içerik üretimi"],
    "yazi-edebiyat/okuma": ["kitap okuma", "okuma alışkanlığı"],
}


def elenir(q):
    if BELGE.search(q) and not KAMP_BELGE.search(q):
        return True
    return bool(BAD.search(q) or BAD_BRANDS.search(q) or BAD_YEARS.search(q) or BAD_WORDS.search(q))


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def fetch(query, cache, stats):
    if query in cache:
        stats["onbellek"] += 1
        return cache[query]
    url = "https://suggestqueries.google.com/complete/search?" + urllib.parse.urlencode(
        {"client": "firefox", "hl": "tr", "gl": "tr", "q": query})
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        rows = [str(x).strip() for x in data[1] if str(x).strip()]
        cache[query] = rows
        stats["istek"] += 1
        return rows
    except Exception as e:
        stats["hata"] += 1
        print(f"  ! atlandı ({query}): {type(e).__name__}")
        return []
    finally:
        time.sleep(DELAY)


def base_name(sub):
    return re.sub(r"\s+", " ", sub["name"].lower().translate(TR_LOWER).replace("&", " ")).strip()


def normal(q):
    return re.sub(r"\s+", " ", q.strip().translate(TR_LOWER)).strip()


def words(q):
    return set(re.findall(r"[a-zçğıöşü0-9]+", q))


def jaccard(a, b):
    return len(a & b) / len(a | b) if a | b else 0.0


def tip_onerisi(q):
    low = q.lower()
    if NASIL.search(low):
        return "nasil_yapilir"
    if LISTE.search(low):
        return "kontrol_listesi"
    return None


def cluster(queries):
    """Kelime kümesi Jaccard >= 0.6 olanları aynı kümeye al; en kısa/en doğal sorgu temsilci."""
    groups = []
    for q in queries:
        w = words(q)
        target = None
        for g in groups:
            if jaccard(w, g["kelimeler"]) >= 0.6:
                target = g
                break
        if target:
            target["uyeler"].append(q)
            if (len(q.split()), len(q)) < (len(target["temsilci"].split()), len(target["temsilci"])):
                target["temsilci"] = q
                target["kelimeler"] = w
        else:
            groups.append(dict(temsilci=q, kelimeler=w, uyeler=[q]))
    return groups


def topla(base, cache, stats, seen, raw):
    for suf in SUFFIXES:
        for q in fetch(f"{base} {suf}", cache, stats):
            n = normal(q)
            if n in seen:
                continue
            seen.add(n)
            raw.append(n)


def build_pool(cats):
    cache = load_json(CACHE_PATH, {})
    stats = {"istek": 0, "onbellek": 0, "hata": 0, "ham": 0, "suzulen": 0, "kume": 0, "konu": 0}
    pool = []
    try:
        for c in cats:
            for s in c["subcategories"]:
                base = base_name(s)
                seen, raw = set(), []
                topla(base, cache, stats, seen, raw)
                kept = [q for q in raw if len(q.split()) >= 3 and not elenir(q)]

                kok = KOK.get(f"{c['id']}/{s['id']}")
                if len(kept) < 5 and kok:
                    for r in kok:
                        topla(r, cache, stats, seen, raw)
                    kept = [q for q in raw if len(q.split()) >= 3 and not elenir(q)]
                    print(f"  ↳ kısa kök denendi: {', '.join(kok)}")

                stats["ham"] += len(raw)
                groups = cluster(kept)
                groups.sort(key=lambda g: 0 if PRIORITY.search(g["temsilci"]) else 1)
                reps = [g["temsilci"] for g in groups[:MAX_PER_SUB]]
                stats["suzulen"] += len(kept)
                stats["kume"] += len(groups)
                stats["konu"] += len(reps)
                for q in reps:
                    pool.append({"sorgu": q, "kategori": c["id"], "alt": s["id"], "tip_onerisi": tip_onerisi(q)})
                print(f"  {c['id']}/{s['id']}: {len(raw)} ham → {len(kept)} süzülen → {len(groups)} küme → {len(reps)} konu")
                save_json(CACHE_PATH, cache)
    except KeyboardInterrupt:
        print("\nKesildi; önbellek kaydediliyor…")
    finally:
        save_json(CACHE_PATH, cache)

    save_json(POOL_PATH, pool)
    tipler = {}
    for e in pool:
        tipler[e["tip_onerisi"]] = tipler.get(e["tip_onerisi"], 0) + 1
    print(f"\n{stats['istek']} istek, {stats['onbellek']} önbellek, {stats['hata']} hata")
    print(f"{stats['ham']} ham → {stats['suzulen']} süzülen → {stats['kume']} küme → "
          f"{stats['konu']} konu (alt kategori başına en fazla {MAX_PER_SUB})")
    print("Tipler: " + ", ".join(f"{k or 'yok'}={v}" for k, v in sorted(tipler.items(), key=lambda x: str(x[0]))))
    return pool


def main():
    cats = load_json(CATEGORIES, [])
    if not cats:
        sys.exit("content/categories.json okunamadı.")
    build_pool(cats)


if __name__ == "__main__":
    main()
