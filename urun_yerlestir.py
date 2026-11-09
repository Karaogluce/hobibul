#!/usr/bin/env python3
"""Silinen satın alma linkinin yerine, tipe uyan doğrulanmış Amazon ürünü koyar.

Birebir marka aranmaz. Makale yoga matı diyorsa başlığında yoga ve mat geçen
bir ürün yeter. Her ürün /dp/ASIN, HTTP 200 ve başlık kontrolünden geçer.
Kutu oyunu yazıları ayrıca 6-8 doğrulanmış oyunla yeniden kurulur.
"""
import html
import json
import os
import re
import subprocess
import sys
from collections import Counter

import amazon_tr

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(BASE, "content")
ARTICLES = os.path.join(CONTENT, "articles")
HAVUZ_YOL = os.path.join(CONTENT, "urun_havuzu.json")
OYUN_YOL = os.path.join(CONTENT, "kutu_oyunlari_tr.json")
RAPOR = os.path.join(CONTENT, "link_denetim.json")

KUTU = {
    "en-iyi-kutu-oyunlari-2026",
    "2-kisilik-kutu-oyunlari",
    "aile-kutu-oyunlari",
    "yilbasi-hediyesi-kutu-oyunlari",
}
ATLA = ("bu-haftanin-en-cok-satan", "en-cok-satan-")

# sorgu listesi, başlıkta aranacak kelime grupları, kısa rol, istenmeyen kelimeler
TIPLER = {
    "deri-set": (["deri el aleti seti", "deri işçilik seti"], [["deri", "set"], ["deri", "alet"]], "deri seti", ()),
    "deri-bicak": (["deri kesim bıçağı", "deri bıçağı"], [["deri", "bıçak"], ["deri", "bıcak"], ["deri", "kesim"]], "deri bıçağı", ()),
    "deri-kenar": (["deri kenar bıçağı", "deri oluk açacağı"], [["deri", "kenar"], ["deri", "oluk"]], "deri kenar aleti", ()),
    "deri-boya": (["deri boyası", "deri kenar boyası"], [["deri", "boya"]], "deri boyası", ()),
    "tig": (["örgü tığ seti", "amigurumi tığ"], [["tığ"], ["tig"]], "örgü tığı", ()),
    "ip": (["örgü ipi", "amigurumi ip seti"], [["örgü", "ip"], ["amigurumi"], ["pamuk", "ip"], ["yün"]], "örgü ipi", ()),
    "sis": (["örgü şiş seti", "misinalı şiş"], [["şiş"], ["sis"]], "örgü şişi", ()),
    "kimya": (["kimya deney seti", "Clementoni kimya"], [["kimya"]], "kimya deney seti", ()),
    "bilim": (["bilim deney seti", "bilim ve oyun"], [["bilim", "oyun"], ["deney", "set"], ["bilim", "set"]], "bilim seti", ()),
    "volkan": (["yanardağ deney seti", "volkan deneyi"], [["yanardağ"], ["volkan"]], "yanardağ deneyi", ()),
    "hava": (["dijital hava istasyonu", "ev hava istasyonu"], [["hava", "istasyon"], ["meteoroloji"]], "hava istasyonu", ()),
    "termometre": (["iç dış mekan termometre", "dijital termometre nem"], [["termometre"], ["higrometre"]], "termometre", ("et ",)),
    "nem": (["nem ölçer dijital", "higrometre"], [["nem"], ["higrometre"]], "nem ölçer", ()),
    "tirmalama": (["kedi tırmalama tahtası", "kedi tırmalama"], [["kedi", "tırmalama"], ["kedi", "tirmalama"]], "kedi tırmalama", ()),
    "kedi-firca": (["kedi fırçası", "kedi tarağı"], [["kedi", "fırça"], ["kedi", "firca"], ["kedi", "tarak"]], "kedi fırçası", ()),
    "kedi-oyuncak": (["kedi oyuncağı", "kedi oyuncak"], [["kedi", "oyuncak"]], "kedi oyuncağı", ()),
    "bot": (["trekking bot", "yürüyüş botu su geçirmez"], [["trekking"], ["yürüyüş", "bot"], ["hiking"]], "trekking bot", ()),
    "baton": (["yürüyüş batonu", "trekking baton"], [["baton"], ["pole"]], "yürüyüş batonu", ()),
    "kafa": (["kafa lambası", "şarjlı kafa feneri"], [["kafa", "lamba"], ["kafa", "fener"], ["headlamp"]], "kafa lambası", ()),
    "sirt": (["yürüyüş sırt çantası", "günlük sırt çantası outdoor"], [["sırt", "çanta"], ["sirt", "canta"]], "sırt çantası", ()),
    "cadir": (["kamp çadırı", "otomatik kamp çadırı"], [["çadır"], ["cadir"]], "kamp çadırı", ()),
    "mat": (["uyku matı kamp", "kamp matı"], [["uyku", "mat"], ["kamp", "mat"]], "uyku matı", ()),
    "ocak": (["kamp ocağı", "portatif kamp ocağı"], [["kamp", "ocak"], ["portatif", "ocak"]], "kamp ocağı", ()),
    "fener": (["kamp feneri", "led kamp lambası"], [["kamp", "fener"], ["kamp", "lamba"]], "kamp feneri", ()),
    "bonsai-makas": (["bonsai makası", "budama makası bonsai"], [["bonsai", "makas"], ["budama", "makas"]], "bonsai makası", ()),
    "bonsai-tel": (["bonsai teli", "bonsai alüminyum tel"], [["bonsai", "tel"], ["aluminyum", "tel"]], "bonsai teli", ()),
    "bonsai-toprak": (["bonsai toprağı", "bonsai toprak"], [["bonsai", "toprak"], ["bonsai", "torf"]], "bonsai toprağı", ()),
    "filtre": (["akvaryum dış filtre", "akvaryum filtre"], [["akvaryum", "filtre"]], "akvaryum filtresi", ("yem",)),
    "isitici": (["akvaryum ısıtıcı", "akvaryum isitici"], [["akvaryum", "ısıt"], ["akvaryum", "isit"]], "akvaryum ısıtıcısı", ()),
    "tank": (["akvaryum tank", "akvaryum set"], [["akvaryum"]], "akvaryum", ("yem", "mama")),
    "tasma": (["köpek otomatik tasma", "flexi tasma"], [["tasma"], ["kayış"]], "köpek tasması", ("kedi",)),
    "kopek-oyuncak": (["köpek oyuncağı", "köpek çiğneme"], [["köpek", "oyuncak"], ["kopek", "oyuncak"]], "köpek oyuncağı", ()),
    "kopek-tarak": (["köpek tarağı", "köpek fırçası"], [["köpek", "tarak"], ["köpek", "fırça"], ["kopek", "firca"]], "köpek tarağı", ()),
    "kosum": (["köpek koşum takımı", "köpek göğüs tasması"], [["koşum"], ["kosum"]], "köpek koşumu", ()),
    "kosu-ayakkabi": (["koşu ayakkabısı", "running shoes"], [["koşu", "ayakkabı"], ["kosu", "ayakkabi"], ["running"]], "koşu ayakkabısı", ()),
    "kosu-kemer": (["koşu kemeri", "bel kemeri koşu"], [["koşu", "kemer"], ["running", "belt"]], "koşu kemeri", ()),
    "saat": (["koşu saati gps", "spor saati"], [["koşu", "saat"], ["spor", "saat"], ["gps", "saat"]], "spor saati", ()),
    "yoga-mat": (["yoga matı", "pilates minderi yoga"], [["yoga", "mat"], ["pilates", "minder"]], "yoga matı", ()),
    "yoga-blok": (["yoga bloğu", "yoga block"], [["yoga", "blok"], ["yoga", "block"]], "yoga bloğu", ()),
    "yoga-kayis": (["yoga kayışı", "yoga strap"], [["yoga", "kayış"], ["yoga", "kayis"], ["yoga", "strap"]], "yoga kayışı", ()),
    "dambil": (["ayarlanabilir dambıl", "dambıl set"], [["dambıl"], ["dambil"], ["dumbbell"]], "dambıl", ()),
    "bant": (["direnç bandı set", "resistance band"], [["direnç", "band"], ["direnc", "band"], ["resistance"]], "direnç bandı", ()),
    "minder": (["egzersiz minderi", "pilates minderi"], [["egzersiz", "minder"], ["pilates", "minder"]], "egzersiz minderi", ()),
    "mangal": (["kömürlü mangal", "barbekü mangal"], [["mangal"], ["barbekü"], ["barbeku"]], "mangal", ()),
    "et-termo": (["et termometresi", "mutfak termometresi"], [["termometre"]], "et termometresi", ()),
    "mangal-firca": (["mangal fırçası", "ızgara fırçası"], [["mangal", "fırça"], ["ızgara", "fırça"], ["mangal", "firca"]], "mangal fırçası", ()),
    "bicak": (["şef bıçağı", "mutfak bıçağı"], [["bıçak"], ["bicak"]], "mutfak bıçağı", ("deri",)),
    "tava": (["yapışmaz tava", "tava 24"], [["tava"]], "tava", ()),
    "spatula": (["mutfak spatulası", "silikon spatula"], [["spatula"]], "spatula", ()),
    "ogutucu": (["kahve öğütücü", "coffee grinder"], [["öğütücü"], ["ogutucu"], ["grinder"]], "kahve öğütücü", ()),
    "v60": (["Hario V60", "v60 dripper"], [["v60"], ["dripper"]], "v60", ()),
    "french": (["french press", "french press kahve"], [["french"]], "french press", ()),
    "pizza-firin": (["pizza fırını", "elektrikli pizza fırını"], [["pizza"]], "pizza fırını", ()),
    "tencere": (["döküm tencere", "tencere set"], [["tencere"]], "tencere", ()),
    "mikser": (["mutfak mikseri", "stand mikser"], [["mikser"], ["mixer"]], "mikser", ()),
    "kamera": (["aynasız fotoğraf makinesi", "fotoğraf makinesi"], [["fotoğraf"], ["fotograf"], ["aynasız"], ["kamera"]], "fotoğraf makinesi", ("telefon", "kılıf")),
    "tripod": (["fotoğraf tripodu", "tripod"], [["tripod"], ["üçayak"], ["ucayak"]], "tripod", ()),
    "hafiza": (["sd kart 64", "hafıza kartı"], [["sd"], ["hafıza", "kart"], ["hafiza", "kart"]], "hafıza kartı", ()),
    "gitar": (["elektro gitar", "elektrik gitar başlangıç"], [["gitar"]], "gitar", ("tel", "kılıf", "askı")),
    "amfi": (["gitar amfisi", "gitar ampli"], [["amfi"], ["ampli"], ["katana"]], "gitar amfisi", ()),
    "tel": (["elektro gitar teli", "gitar teli"], [["gitar", "tel"]], "gitar teli", ()),
    "akort": (["gitar akort aleti", "klip akort"], [["akort"], ["tuner"]], "akort aleti", ()),
    "dj": (["dj kontrol cihazı", "dj controller"], [["dj"], ["mixtrack"], ["ddj"]], "dj kontrol", ("kulaklık",)),
    "kulaklik": (["dj kulaklık", "stüdyo kulaklık"], [["kulaklık"], ["kulaklik"], ["headphone"]], "kulaklık", ()),
    "kablo": (["gitar kablosu", "enstrüman kablosu"], [["kablo"]], "enstrüman kablosu", ()),
    "drone": (["kamera drone", "dji mini drone"], [["drone"]], "drone", ("5-8 dakika", "takla")),
    "yazici": (["3d yazıcı", "ender 3d yazıcı"], [["3d", "yazıcı"], ["3d", "yazici"], ["3d", "printer"]], "3d yazıcı", ()),
    "filament": (["pla filament", "3d filament"], [["filament"], ["pla"]], "filament", ()),
    "3d-alet": (["3d yazıcı alet seti", "nozzle set"], [["nozzle"], ["nozul"], ["3d", "alet"]], "3d alet", ()),
    "raspberry": (["raspberry pi 5", "raspberry pi"], [["raspberry"]], "raspberry pi", ()),
    "arduino": (["arduino uno", "arduino başlangıç"], [["arduino"]], "arduino", ()),
    "guc": (["raspberry pi 5 güç adaptörü", "usb-c güç adaptörü 5v"], [["raspberry"], ["usb-c", "adaptör"], ["usb-c", "adaptor"]], "güç adaptörü", ()),
    "boya": (["akrilik boya seti", "resim boya seti"], [["akrilik"], ["boya"]], "boya seti", ("deri",)),
    "pense": (["takı pensesi", "kuyumcu pensesi"], [["pense"]], "pense", ()),
    "firca": (["resim fırçası set", "akrilik fırça set"], [["resim", "fırça"], ["akrilik", "fırça"], ["fırça", "set"]], "resim fırçası", ("kedi", "köpek", "mangal")),
    "diamond": (["diamond painting set", "elmas tablo set"], [["diamond"], ["elmas"]], "diamond painting", ()),
    "sehpa": (["resim sehpası", "masaüstü şövale"], [["sehpa"], ["şövale"], ["sovale"]], "sehpa", ()),
    "klavye": (["oyuncu klavye", "mekanik klavye"], [["klavye"]], "klavye", ()),
    "mouse": (["oyuncu mouse", "gaming mouse"], [["mouse"]], "oyuncu mouse", ()),
}

SUB_TIP = {
    "deri-isleri": ["deri-set", "deri-bicak", "deri-kenar", "deri-boya"],
    "orgu-tig": ["tig", "ip", "sis"],
    "kimya-deney": ["kimya", "bilim", "volkan"],
    "meteoroloji": ["hava", "termometre", "nem"],
    "kedi-bakimi": ["tirmalama", "kedi-firca", "kedi-oyuncak"],
    "dagcilik-trekking": ["bot", "baton", "kafa", "sirt"],
    "kampcilik": ["cadir", "mat", "ocak", "fener", "kafa"],
    "bonsai": ["bonsai-makas", "bonsai-tel", "bonsai-toprak"],
    "akvaryum": ["filtre", "isitici", "tank"],
    "kopek-bakimi": ["tasma", "kopek-oyuncak", "kopek-tarak", "kosum"],
    "kosu": ["kosu-ayakkabi", "kosu-kemer", "saat"],
    "yoga-pilates": ["yoga-mat", "yoga-blok", "yoga-kayis"],
    "evde-fitness": ["dambil", "bant", "minder"],
    "mangal-bbq": ["mangal", "et-termo", "mangal-firca"],
    "yemek-pisirme": ["bicak", "tava", "spatula"],
    "kahve": ["ogutucu", "v60", "french"],
    "ekmek-pasta": ["pizza-firin", "tencere", "mikser"],
    "fotografcilik": ["kamera", "tripod", "hafiza"],
    "gitar": ["gitar", "amfi", "tel", "akort"],
    "dj-produksiyon": ["dj", "kulaklik", "kablo"],
    "drone": ["drone", "hafiza", "tripod"],
    "3d-yazici": ["yazici", "filament", "3d-alet"],
    "raspberry-pi-elektronik": ["raspberry", "arduino", "guc"],
    "diamond-painting": ["diamond", "boya", "firca"],
}

SLUG_TIP = {
    "evde-el-sanatlari-hobileri": ["tig", "boya", "pense", "diamond", "firca", "sehpa"],
    "evde-yapilacak-hobiler": ["tig", "boya", "diamond", "sehpa"],
    "kadinlar-icin-evde-yapilacak-hobiler": ["tig", "ip", "sis", "boya"],
    "yetiskin-hobi-setleri": ["boya", "sehpa", "diamond", "lego-yok"],
    "en-iyi-teknoloji-ekipmanlari-2026-alim-rehberi": ["arduino", "raspberry", "drone"],
    "teknoloji-ekipmani-alirken-yapilan-7-hata-ve-nasil-kacinilir": ["arduino", "klavye", "mouse"],
    "teknoloji-hakkinda-sik-sorulan-sorular-cevaplariyla-kisa-rehber": ["arduino", "raspberry", "drone"],
    "teknoloji-icin-yeni-baslayanlar-rehberi-ilk-alinacak-ekipmanlar": ["arduino", "raspberry", "guc"],
    "drone-secimi-yeni-baslayanlar-icin": ["drone", "hafiza", "tripod"],
    "drone-nasil-kullanilir": ["drone", "hafiza"],
    "drone-hakkinda-sik-sorulan-sorular-cevaplariyla-kisa-rehber": ["drone", "tripod"],
}

ADLI_OYUN = (
    ("Catan", ["catan"], ["Catan kutu oyunu", "Catan Türkçe", "Kolonistler Catan", "Catan"]),
    ("Codenames", ["codenames"], ["Codenames Türkçe", "Codenames kutu oyunu", "Kod Adları"]),
    ("Splendor", ["splendor"], ["Splendor kutu oyunu", "Splendor"]),
    ("Carcassonne", ["carcassonne"], ["Carcassonne kutu oyunu", "Carcassonne Türkçe"]),
    ("Dixit", ["dixit"], ["Dixit kutu oyunu", "Dixit"]),
    ("Ticket to Ride Europe", ["ticket", "ride"], ["Ticket to Ride Europe", "Ticket to Ride"]),
    ("Pandemic", ["pandemic"], ["Pandemic kutu oyunu", "Pandemik kutu oyunu"]),
    ("Pandemik", ["pandemik"], ["Pandemik kutu oyunu"]),
    ("Azul", ["azul"], ["Azul kutu oyunu", "Azul"]),
    ("Wingspan", ["wingspan"], ["Wingspan kutu oyunu"]),
    ("7 Wonders", ["7 wonders"], ["7 Wonders kutu oyunu", "7 Wonders"]),
    ("Sky Team", ["sky", "team"], ["Sky Team kutu oyunu"]),
    ("Risk", ["risk"], ["Risk kutu oyunu"]),
    ("Monopoly", ["monopoly"], ["Monopoly Türkiye", "Monopoly kutu oyunu"]),
    ("Cluedo", ["cluedo"], ["Cluedo kutu oyunu"]),
    ("Tabu", ["tabu"], ["Tabu XL kutu oyunu", "Tabu kutu oyunu"]),
    ("Bomb Busters", ["bomb", "busters"], ["Bomb Busters kutu oyunu"]),
)


def _kisa(ad):
    ad = html.unescape(ad or "")
    ad = re.sub(r"\s+", " ", ad).strip()
    ad = re.split(r"\s+[|–—]\s+", ad)[0].strip()
    if len(ad) > 88:
        ad = ad[:88].rsplit(" ", 1)[0]
    return ad


def _fm(text):
    if not text.startswith("---"):
        return {}, text
    _, fm, body = text.split("---", 2)
    meta = {}
    for key in ("category", "subcategory", "slug", "title"):
        m = re.search(rf'{key}:\s*"([^"]*)"', fm)
        if m:
            meta[key] = m.group(1)
    return meta, body


def _mevcut_asin(text):
    asins = set(re.findall(r"/dp/([A-Z0-9]{10})", text))
    return asins


def _silinen():
    diff = subprocess.check_output(
        ["git", "diff", "-U0", "origin/main", "--", "content/articles"],
        text=True, errors="replace",
    )
    cur = None
    out = {}
    for line in diff.splitlines():
        if line.startswith("diff --git"):
            m = re.search(r"b/content/articles/(.+)\.md", line)
            cur = m.group(1) if m else None
        elif line.startswith("-") and "aff://" in line and cur:
            for pid in re.findall(r"aff://([a-z0-9\-]+)", line):
                out.setdefault(cur, set()).add(pid)
    return out


def _dogrulanan_aff():
    try:
        rapor = json.load(open(RAPOR, encoding="utf-8"))
    except OSError:
        return set()
    return {k["id"] for k in rapor.get("kayitlar") or [] if k.get("durum") == "dogrulandi"}


def ihtiyac_haritasi():
    silinen = _silinen()
    dogru = _dogrulanan_aff()
    plan = {}
    for fn in sorted(os.listdir(ARTICLES)):
        if not fn.endswith(".md"):
            continue
        slug = fn[:-3]
        if slug in KUTU or slug.startswith(ATLA):
            continue
        text = open(os.path.join(ARTICLES, fn), encoding="utf-8").read()
        meta, _body = _fm(text)
        aff = set(re.findall(r"aff://([a-z0-9\-]+)", text))
        veri = sum(1 for i in aff if i in dogru) + len(_mevcut_asin(text))
        rem = len(silinen.get(slug, ()))
        need = max(rem, max(0, 3 - veri))
        if need <= 0:
            continue
        tips = SLUG_TIP.get(slug) or SUB_TIP.get(meta.get("subcategory") or "", [])
        tips = [t for t in tips if t in TIPLER]
        if not tips:
            tips = ["boya", "tig", "diamond"]
        plan[slug] = {"need": need, "tips": tips, "cat": meta.get("category"), "sub": meta.get("subcategory")}
    return plan


def havuz_cek(oturum, plan):
    lazim = []
    for bilgi in plan.values():
        for tip in bilgi["tips"]:
            if tip not in lazim:
                lazim.append(tip)
    havuz = {}
    if os.path.exists(HAVUZ_YOL):
        try:
            havuz = json.load(open(HAVUZ_YOL, encoding="utf-8"))
        except json.JSONDecodeError:
            havuz = {}
    for tip in lazim:
        if havuz.get(tip):
            print(f"· havuz {tip} ({len(havuz[tip])})")
            continue
        sorgular, gruplar, _rol, red = TIPLER[tip]
        print(f"… {tip}")
        try:
            bulunan = amazon_tr.tip_bul(
                oturum, sorgular, gruplar, limit=4, ekstra_red=red,
            )
        except amazon_tr.AmazonEngel as e:
            print(f"! {tip} {e.neden}")
            bulunan = []
        for u in bulunan:
            u["ad"] = _kisa(u["ad"])
        havuz[tip] = bulunan
        print(f"  {len(bulunan)} " + " | ".join(u["ad"][:40] for u in bulunan))
        _yaz(HAVUZ_YOL, havuz)
    return havuz


def _yaz(path, data):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")


def _sec(tips, need, havuz, dolu):
    secilen = []
    indeks = {t: 0 for t in tips}
    for _ in range(need * 6):
        if len(secilen) >= need:
            break
        ilerleme = False
        for tip in tips:
            urunler = havuz.get(tip) or []
            while indeks[tip] < len(urunler):
                u = urunler[indeks[tip]]
                indeks[tip] += 1
                if u["asin"] in dolu:
                    continue
                dolu.add(u["asin"])
                secilen.append((tip, u))
                ilerleme = True
                break
            if len(secilen) >= need:
                break
        if not ilerleme:
            break
    return secilen


def _bolum(ciftler):
    satir = [
        "<!-- urun-havuzu -->",
        "## Sayfada duran ürünler",
        "",
        "Aşağıdaki bağlantılar Amazon.com.tr ürün sayfası. Başlık, bu yazının konusuna uyuyor.",
        "",
    ]
    for i, (tip, u) in enumerate(ciftler):
        rol = TIPLER[tip][2]
        rol = rol[:1].upper() + rol[1:]
        link = f"[{u['ad']}]({u['url']})"
        if i % 3 == 1:
            satir.append(f"Aynı işe bakan bir diğeri {link}.")
        elif i % 3 == 2:
            satir.append(f"Listenin devamında {link} var.")
        else:
            satir.append(f"{rol} için Amazon.com.tr sayfasında {link} duruyor.")
        satir.append("")
    satir.append("<!-- /urun-havuzu -->")
    return "\n".join(satir).strip() + "\n"


def _temiz(text):
    return re.sub(
        r"<!-- urun-havuzu -->.*?<!-- /urun-havuzu -->\n?",
        "",
        text,
        flags=re.S,
    )


def _yerlestir(text, bolum):
    text = _temiz(text)
    m = re.search(r"\n## Sık(?:ça)? Sorulan Sorular\b", text)
    if m:
        return text[:m.start()].rstrip() + "\n\n" + bolum + "\n" + text[m.start():]
    return text.rstrip() + "\n\n" + bolum


def makalelere_yaz(plan, havuz):
    ozet = {}
    for slug, bilgi in plan.items():
        yol = os.path.join(ARTICLES, slug + ".md")
        text = _temiz(open(yol, encoding="utf-8").read())
        dolu = _mevcut_asin(text)
        cift = _sec(bilgi["tips"], bilgi["need"], havuz, dolu)
        if not cift:
            print(f"! ürün yok {slug}")
            ozet[slug] = 0
            continue
        yeni = _yerlestir(text, _bolum(cift))
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            f.write(yeni)
        ozet[slug] = len(cift)
        print(f"✓ {slug} +{len(cift)}")
    return ozet


_OYUN_RED = (
    "kilif", "kılıf", "sleeve", "kollari", "kılıfı", "aksesuar",
    "expansion", "genisleme", "genişleme", "dodatek", "kitap", "prime video",
    "fincan", "kahve", "vazo", "seramik", "porselen",
)


def _oyun_kabul(baslik, parcalar):
    h = amazon_tr.fold(baslik)
    if not h or h.startswith("prime video"):
        return False
    if any(k in h for k in _OYUN_RED):
        return False
    if not all(p in h for p in parcalar):
        return False
    return any(k in h for k in ("kutu", "oyun", "oyuncak", "board", "card game"))


def _oyun_kaydi(aday, baslik):
    url = amazon_tr.dp_url(aday["asin"])
    oyuncu = ""
    m = re.search(r"(\d+\s*[-–]\s*\d+|\d+)\s*oyuncu", baslik, re.I)
    if m:
        oyuncu = re.sub(r"\s+", "", m.group(1))
    yas = ""
    y = re.search(r"(\d+)\s*\+", baslik)
    if not y:
        y = re.search(r"(\d+)\s*yaş", baslik, re.I)
    if y:
        yas = y.group(1) + "+"
    return {
        "asin": aday["asin"],
        "ad": _kisa(aday["ad"]),
        "baslik": baslik,
        "url": url,
        "oyuncu": oyuncu,
        "yas": yas,
        "turkce": "türkçe" in amazon_tr.fold(baslik) or "turkce" in amazon_tr.fold(baslik),
    }


def oyunlari_cek(oturum):
    bulunan = []
    gorulen = set()

    def ekle(aday, baslik):
        if aday["asin"] in gorulen:
            return
        gorulen.add(aday["asin"])
        bulunan.append(_oyun_kaydi(aday, baslik))

    for ad, parcalar, sorgular in ADLI_OYUN:
        if any(_oyun_kabul(x["baslik"], parcalar) for x in bulunan):
            continue
        for sorgu in sorgular:
            try:
                adaylar = amazon_tr.ara(oturum, sorgu, limit=8)
            except amazon_tr.AmazonEngel as e:
                print(f"! oyun {sorgu} {e.neden}")
                continue
            for aday in adaylar:
                if not _oyun_kabul(aday["ad"], parcalar):
                    continue
                try:
                    baslik, _dp = amazon_tr.urun_basligi(oturum, aday["asin"])
                except amazon_tr.AmazonEngel:
                    continue
                if _oyun_kabul(baslik, parcalar):
                    ekle(aday, baslik)
                    print(f"✓ oyun {ad}: {bulunan[-1]['ad'][:50]}")
                    break
            if bulunan and _oyun_kabul(bulunan[-1]["baslik"], parcalar):
                break
    if len(bulunan) < 8:
        try:
            pop = amazon_tr.tip_bul(
                oturum,
                ["kutu oyunu", "masa oyunu aile"],
                [["kutu", "oyun"], ["masa", "oyun"]],
                limit=10,
            )
        except amazon_tr.AmazonEngel as e:
            print("! popüler oyun", e.neden)
            pop = []
        for u in pop:
            if u["asin"] in gorulen:
                continue
            ekle({"asin": u["asin"], "ad": u["ad"]}, u["baslik"])
            print(f"✓ popüler {bulunan[-1]['ad'][:50]}")
            if len(bulunan) >= 10:
                break
    return bulunan


def _liste_sec(oyunlar, n=8):
    if len(oyunlar) <= n:
        return list(oyunlar)
    return oyunlar[:n]


def _iki_kisi(oyunlar):
    uygun = [o for o in oyunlar if re.search(r"\b2\b", o.get("oyuncu") or o["baslik"])]
    diger = [o for o in oyunlar if o not in uygun]
    sec = (uygun + diger)[:8]
    return sec if len(sec) >= 6 else oyunlar[:8]


def _aile(oyunlar):
    def puan(o):
        h = amazon_tr.fold(o["baslik"] + " " + o["ad"])
        return sum(k in h for k in ("aile", "monopoly", "tabu", "cluedo", "dixit", "8 yaş", "8+"))
    sirali = sorted(oyunlar, key=puan, reverse=True)
    return sirali[:8]


def _oyun_metin(oyun):
    link = f"[{oyun['ad']}]({oyun['url']})"
    ek = []
    if oyun.get("oyuncu"):
        ek.append(f"başlık {oyun['oyuncu']} oyuncu diyor")
    if oyun.get("yas"):
        ek.append(f"yaş satırı {oyun['yas']}")
    if oyun.get("turkce"):
        ek.append("başlıkta Türkçe geçiyor")
    if ek:
        return f"{link} Amazon.com.tr üzerinde duruyor; {', '.join(ek)}."
    return f"{link} Amazon.com.tr üzerinde duruyor."


def _kutu_govde(slug, oyunlar):
    if slug == "2-kisilik-kutu-oyunlari":
        liste = _iki_kisi(oyunlar)
        giris = (
            "İki sandalyelik bir akşamda kutu, sayfa başlığında kaç kişi yazdığına göre seçilir. "
            "Aşağıdaki oyunların her biri Amazon.com.tr'de açılıyor. "
            "Başlık oyuncu aralığı veriyorsa o sayı burada da duruyor. "
            "Daha geniş masa için [en iyi kutu oyunları](/makale/en-iyi-kutu-oyunlari-2026/) "
            "ve [aile listesi](/makale/aile-kutu-oyunlari/) var."
        )
    elif slug == "aile-kutu-oyunlari":
        liste = _aile(oyunlar)
        giris = (
            "Aile masasında kutu, yaş ve kişi sayısı başlıkta yazıyorsa ona göre durur. "
            "Bu listedekiler Amazon.com.tr ürün sayfası. "
            "Kalabalık strateji gecesi için [en iyi kutu oyunları](/makale/en-iyi-kutu-oyunlari-2026/), "
            "yalnız iki kişi için [2 kişilik liste](/makale/2-kisilik-kutu-oyunlari/)."
        )
    elif slug == "yilbasi-hediyesi-kutu-oyunlari":
        liste = list(reversed(oyunlar[:8])) if len(oyunlar) >= 8 else list(oyunlar)
        giris = (
            "Yılbaşı hediyesi için kutu, masaya ilk kez oturacak birine anlatması kolay olandan seçilir. "
            "Buradaki her bağlantı Amazon.com.tr ürün sayfası ve başlık oyun adını taşıyor. "
            "Kime ne gider, [aile listesinde](/makale/aile-kutu-oyunlari/) ve "
            "[genel listede](/makale/en-iyi-kutu-oyunlari-2026/) de duruyor."
        )
    else:
        liste = _liste_sec(oyunlar, 8)
        giris = (
            "Bu listedeki her kutu Amazon.com.tr'de açılıyor ve sayfa başlığı oyunun adını taşıyor. "
            "Dar listeler ayrı: [2 kişilik](/makale/2-kisilik-kutu-oyunlari/) ve "
            "[aile](/makale/aile-kutu-oyunlari/). Hepsi [masaüstü oyunlar](/kategori/koleksiyon/masaustu-oyun/) kategorisinde."
        )
    if len(liste) > 8:
        liste = liste[:8]
    blok = [giris, "", "## Kutular", ""]
    for oyun in liste:
        blok.append(f"### {oyun['ad']}")
        blok.append("")
        blok.append(_oyun_metin(oyun))
        blok.append("")
    blok.append("## Sıkça Sorulan Sorular")
    blok.append("")
    blok.append("**Satın alma linki nereye gider?**")
    blok.append("Amazon.com.tr üzerinde, başlığında oyun adı duran ürün sayfasına.")
    blok.append("")
    return "\n".join(blok).strip() + "\n", liste


def kutu_yaz(oyunlar):
    if len(oyunlar) < 6:
        print(f"! kutu oyunu az: {len(oyunlar)}")
    kayit = []
    for i, oyun in enumerate(oyunlar):
        kayit.append({
            "id": re.sub(r"[^a-z0-9]+", "-", amazon_tr.fold(oyun["ad"])).strip("-")[:48] or f"oyun-{i}",
            "ad": oyun["ad"],
            "url": oyun["url"],
            "asin": oyun["asin"],
            "oyuncu": oyun.get("oyuncu") or "",
            "yas": oyun.get("yas") or "",
            "turkce": bool(oyun.get("turkce")),
            "baslik": oyun["baslik"],
        })
    _yaz(OYUN_YOL, {
        "tarih": "2026-11-09",
        "kaynak": "Amazon.com.tr. Başlık oyun adını veya kutu oyunu ibaresini taşıyor. Kişi ve yaş yalnız başlıktaysa yazıldı.",
        "oyunlar": kayit,
    })
    sayilar = {}
    for slug in sorted(KUTU):
        yol = os.path.join(ARTICLES, slug + ".md")
        text = open(yol, encoding="utf-8").read()
        meta_blok = text.split("---", 2)
        bas = "---" + meta_blok[1] + "---\n"
        govde, liste = _kutu_govde(slug, oyunlar)
        ozet_ad = ", ".join(o["ad"] for o in liste[:3])
        aciklama = f"Amazon.com.tr başlığı tutan kutu oyunları: {ozet_ad}."
        if len(aciklama) > 155:
            aciklama = aciklama[:152].rsplit(" ", 1)[0] + "."
        bas = re.sub(r'meta_description: ".*"', f'meta_description: "{aciklama}"', bas, count=1)
        bas = re.sub(r'excerpt: ".*"', f'excerpt: "{aciklama}"', bas, count=1)
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            f.write(bas + govde)
        sayilar[slug] = len(liste)
        print(f"✓ kutu {slug} {len(liste)}")
    return sayilar


def tekrar_bulunamayan(oturum):
    """85 'bulunamadı' kaydını yavaş aramayla ayır: engel, aday, yok."""
    try:
        rapor = json.load(open(RAPOR, encoding="utf-8"))
    except OSError:
        return {}
    say = Counter()
    ornek = []
    for kayit in rapor.get("kayitlar") or []:
        if kayit.get("durum") != "bulunamadi":
            continue
        ad = (kayit.get("ad") or "").strip()
        if not ad:
            say["bos_ad"] += 1
            continue
        try:
            adaylar = amazon_tr.ara(oturum, ad, limit=6)
        except amazon_tr.AmazonEngel as e:
            say["engel"] += 1
            if len(ornek) < 8:
                ornek.append({"id": kayit["id"], "sonuc": "engel", "neden": e.neden})
            continue
        token = [w for w in amazon_tr._govde(ad) if len(w) >= 4][:2]
        hit = None
        for aday in adaylar:
            h = amazon_tr.fold(aday["ad"])
            if token and all(t in h for t in token):
                hit = aday
                break
        if hit:
            say["aday"] += 1
            if len(ornek) < 12:
                ornek.append({"id": kayit["id"], "sonuc": "aday", "ad": _kisa(hit["ad"])[:80]})
        else:
            say["yok"] += 1
    rapor.setdefault("ozet", {})["tekrar"] = {
        "bulunamadi_tekrar": sum(say.values()),
        "engel": say["engel"],
        "aday": say["aday"],
        "yok": say["yok"],
        "ornek": ornek,
        "not": "Birebir ad bir kez daha arandı. Engel captcha/503. Aday, adın iki kelimesi sonuçta duruyor. Yok, sayfa açıldı ama ad yok; yerine tip ürünü kondu.",
    }
    _yaz(RAPOR, rapor)
    print("tekrar", dict(say))
    return say


def main():
    plan = ihtiyac_haritasi()
    print(f"makale {len(plan)} ihtiyaç {sum(p['need'] for p in plan.values())}")
    oturum = amazon_tr.Oturum(bekle=0.6, deneme=2)
    havuz = havuz_cek(oturum, plan)
    yazilan = makalelere_yaz(plan, havuz)
    oyunlar = oyunlari_cek(oturum)
    kutu = kutu_yaz(oyunlar)
    tekrar = tekrar_bulunamayan(oturum)
    print("YERLESTIR", sum(yazilan.values()), "KUTU", kutu, "TEKRAR", dict(tekrar))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
