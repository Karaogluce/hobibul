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


def _ngram(metin, n=10):
    kelime = re.findall(r"[a-z0-9çğıöşü]+", amazon_tr.fold(metin or ""))
    if len(kelime) < n:
        return set()
    return {" ".join(kelime[i:i + n]) for i in range(len(kelime) - n + 1)}


def _buyuk(s):
    return s[0].upper() + s[1:] if s and s[0].islower() else s


def _kucuk(s):
    return s[0].lower() + s[1:] if s and s[0].isupper() and not s[:2].isupper() else s


def _kopyayi_kir(cumle, kaynak):
    """Uzun birebir diziyi cümle ortasından kesmeden boz.

    Önce virgülden sonraki parçayı başa alır, olmazsa 've' bağlacını iki
    cümleye ayırır. Kelime ortasından bölünmez. Hâlâ 10 kelimelik dizi
    duruyorsa cümle yazıya girmez.
    """
    yeni = re.sub(r"\bmükemmel\b", "", cumle or "", flags=re.I)
    yeni = re.sub(r"\s+", " ", yeni).strip(" .,;:")
    if not yeni:
        return ""
    if not (_ngram(yeni, 10) & kaynak):
        return _buyuk(yeni)
    adaylar = []
    if "," in yeni:
        sol, sag = yeni.rsplit(",", 1)
        sol, sag = sol.strip(), sag.strip(" .")
        if len(sol.split()) >= 3 and len(sag.split()) >= 3:
            adaylar.append(f"{_buyuk(sag)}; {_kucuk(sol)}")
    if " ve " in yeni:
        sol, sag = yeni.split(" ve ", 1)
        sol, sag = sol.strip(" ."), sag.strip(" .")
        if len(sol.split()) >= 4 and len(sag.split()) >= 4:
            adaylar.append(f"{_buyuk(sol)}. {_buyuk(sag)}")
    for aday in adaylar:
        aday = re.sub(r"\s+", " ", aday).strip()
        if aday and not (_ngram(aday, 10) & kaynak):
            return aday if aday.endswith(".") else aday + "."
    return ""


def parafraz(aciklama):
    """Kapak veya ürün metnini yeniden kur. Uzun birebir alıntı kalmaz."""
    kaynak = _ngram(aciklama, 10)
    metin = re.sub(r"\s+", " ", aciklama or "").strip()
    out = []
    for cumle in re.split(r"(?<=[.!?])\s+", metin):
        cumle = cumle.strip()
        if len(cumle.split()) < 6 or cumle[:1] in "“\"«" or cumle.startswith("—"):
            continue
        yeni = _kopyayi_kir(cumle, kaynak)
        if not yeni:
            continue
        if yeni[0].islower():
            yeni = yeni[0].upper() + yeni[1:]
        if yeni not in out:
            out.append(yeni)
    return out


def _ilgili_makaleler(cat, sub, kendi, limit=3):
    """Aynı kategorideki başka rehberler. Başlık sitedeki kayıttan gelir."""
    aday = []
    if not os.path.isdir(ARTICLES):
        return aday
    for fn in sorted(os.listdir(ARTICLES)):
        if not fn.endswith(".md"):
            continue
        slug = fn[:-3]
        if slug == kendi or "cok-satan" in slug or "en-cok-satan" in slug:
            continue
        text = open(os.path.join(ARTICLES, fn), encoding="utf-8").read(800)
        cm = re.search(r'category:\s*"([^"]+)"', text)
        sm = re.search(r'subcategory:\s*"([^"]+)"', text)
        tm = re.search(r'title:\s*"([^"]+)"', text)
        if not cm or not tm or cm.group(1) != cat:
            continue
        ayni = 0 if (sm and sm.group(1) == sub) else 1
        aday.append((ayni, tm.group(1), slug))
    aday.sort()
    sonuc = [{"baslik": b, "slug": s} for _, b, s in aday[:3]]
    if len(sonuc) >= 2 or not cat:
        return sonuc
    # Aynı kategoride rehber yoksa (kitapta olduğu gibi) kategori sayfasına bağla.
    sonuc.append({"baslik": "Bu kategorinin sayfası", "url": f"/kategori/{cat}/"})
    if sub:
        sonuc.append({"baslik": "Bu alt kategorinin sayfası", "url": f"/kategori/{cat}/{sub}/"})
    return sonuc


def _alan(ayrinti, *etiketler):
    return amazon_tr.bilgi_degeri(ayrinti or {}, *etiketler)


# Bu haftanın ürün sayfalarından kurulmuş anlatı. Sayfa gelmezse kullanılmaz.
# Uzun kapak metni birebir alınmaz; bilgi satırı ve maddeyle aynı olgular kalır.
ANLATI = {
    "6052657480": (
        "Kapak, herkesin birbirine benzediği ve görünmez kurallara uymanın zorunlu görüldüğü bir düzen kuruyor. "
        "Oh Yeong-a bu düzenin içinde duran bir öğretmen: gülümseyen, alttan alan, gününü başkalarının beklentisine göre ayarlayan biri. "
        "Sürekli uyum çabası onda çaresizlik ve öfke biriktiriyor. "
        "Çıkış için dört haftalık bir duygu düzenleme programına başvuruyor. "
        "Program, kişiyi daha iyi bir haline taşıyacağını söylüyor ve son teknoloji ürünü diye anılıyor. "
        "Müdahale beklenenden farklı işliyor. "
        "Yeong-a sosyal filtreleri ve yorucu sorumlulukları bırakıp ilk kez kuralsız haliyle karşılaşıyor. "
        "Toplumun dayattığı idealleri de dağıtmaya yöneliyor. "
        "Kapak, bu hâlin hem tehlikeli hem çekici göründüğünü yazıyor. "
        "Cheong Ye, Kore edebiyatında öne çıkan genç yazarlar arasında anılıyor. "
        "Roman, herkesi tek tipe zorlayan toplumu ve kişinin kendi sınırını konu ediyor."
    ),
    "6259568126": (
        "Kapak, Çıkarım Ustası Logıco ile Murdle’ın ilk cildindeki cinayetleri kurcalamaya çağırıyor. "
        "Minik gizem bulmacaları yalnızca katilin kim olduğunu değil, cinayetin nasıl, nerede ve neden işlendiğini de sorduruyor. "
        "İpucu, tanık ve çıkarım aynı turda kullanılıyor. "
        "Alttaki sıraya, bulmacaların hepsi bitince ulaşılıyor. "
        "Sayfa illüstrasyon, şifre ve haritadan söz ediyor ve kitabı zekâ ile entrika tarafına koyuyor."
    ),
    "6256756207": (
        "Kapak, Virginia Evans’ın Muhabbet romanını mektuplar üzerinden anlatıyor. "
        "Sybil her sabah masaya oturup mektup yazıyor: erkek kardeşine, en yakın arkadaşına, bahçecilik kulübüne, "
        "derse kabul etmeyen üniversite dekanına, sevdiği yazarlara, editörlere ve ajanslara. "
        "Bir mektup da bir türlü gönderemediği kişiye. "
        "Sybil Van Antwerp otuz yıldır mektuplarla dünyaya tutunurken yakınındakileri uzakta tutuyor. "
        "İnziva bitmek üzere. Geçmişten gelen mektuplar onu en ağır dönemle karşılaştırıyor. "
        "Devam edebilmek için önce kendini affetmesi, sonra gerçekleri anlatması gerektiği yazılı. "
        "Sayfa şu notları da taşıyor: 26 haftadır New York Times çok satanlar birincisi, "
        "2026 PEN/Hemingway en iyi roman ödülü, 2026 Women’s Prize en iyi roman, "
        "Goodreads okur ödüllerinde üç dalda final ve 500.000 oy ile 4.5 puan, "
        "2026 Indies Choice yılın romanı ve 3.000 bağımsız kitabevinin seçimi."
    ),
    "B0H1MXJKJY": (
        "Sayfa bunu, ebeveyn ile çocuğun birlikte oynadığı manyetik taş oyunu diye anlatıyor. "
        "Taşlar güçlü ve kontrol edilebilir. Malzemenin toksik madde içermediği ve dayanıklı olduğu yazılı. "
        "Zorluk, ayarlanabilir bir iple değişiyor. Oyun odak, mantık ve problem çözmeye bağlanıyor. "
        "Kutu taşınabilir; seyahat, tatil ve arkadaş buluşması için diye geçiyor. "
        "İçinde 24 manyetik taş, 1 ayarlanabilir ip ve 1 taşıma çantası var. Yaş sınırı 8 ve üzeri. "
        "Kutunun eni 14,9 cm, boyu 10,6 cm, yüksekliği 6,6 cm. "
        "Küçük parça uyarısı var; 8 yaşından küçük çocuklar için uygun olmadığı yazılı. "
        "Oynanış da sayfada: ip alanı belirliyor, oyuncular sırayla taş bırakıyor, "
        "taşlar birbirini çekerse birleşenleri o oyuncu alıyor, elindeki taşları ilk bitiren kazanıyor."
    ),
    "B07CP2RFRT": (
        "Sayfa, 24 renkli pastel boyayı çocukların evde ve okulda kullanması için anlatıyor. "
        "Renkler canlı ve örtücü. Boya kâğıt ve kartonda yayılıyor, yoğunluğunu kaybetmeden. "
        "Yumuşak olduğu ve kâğıt üzerinde kaydığı yazılı. Tutacak sayesinde daha uzun kullanıldığı söyleniyor. "
        "Özel çantasıyla ev, okul ve oyun buluşmasına taşınıyor. "
        "Başlıca faydalar satırında yaratıcılık, ev ve okul işi, yumuşak kullanım, tutacak ve çanta geçiyor."
    ),
}


KONU = {
    "6052657480": (
        "Herkesin birbirine benzediği, görünmez kurallara uymanın zorunlu sayıldığı bir düzen var. "
        "Oh Yeong-a o düzenin içinde gülümseyen, alttan alan bir öğretmen; gününü başkalarının beklentisine göre kuruyor. "
        "Bu uyum onda çaresizlik ve öfke biriktiriyor. Çıkışı, dört haftalık bir duygu düzenleme programında arıyor. "
        "Program, kişiyi daha iyi bir haline taşıyacağını söylüyor. Müdahale beklenenden farklı işliyor. "
        "Yeong-a sosyal filtreleri ve yorucu sorumlulukları bırakıp ilk kez kuralsız haliyle karşılaşıyor "
        "ve toplumun dayattığı idealleri dağıtmaya yöneliyor. Bu hâl hem tehlikeli hem çekici duruyor. "
        "Cheong Ye, Kore edebiyatında öne çıkan genç yazarlar arasında anılıyor. "
        "Roman, herkesi tek tipe zorlayan toplumu ve kişinin kendi sınırını konu ediyor."
    ),
    "6259568126": (
        "Çıkarım Ustası Logıco ile Murdle’ın ilk cildindeki cinayetlere bakıyorsun. "
        "Minik gizem bulmacaları yalnızca katilin kim olduğunu değil, cinayetin nasıl, nerede ve neden "
        "işlendiğini de sorduruyor. İpucu, tanık ve çıkarım aynı turda. Alttaki sıraya, bulmacaların "
        "hepsi bitince ulaşıyorsun. İllüstrasyon, şifre ve harita da var. Kitap zekâ ile entrika tarafında duruyor."
    ),
    "6256756207": (
        "Sybil her sabah masaya oturup mektup yazıyor. Erkek kardeşine, en yakın arkadaşına, bahçecilik kulübüne, "
        "derse kabul etmeyen üniversite dekanına, sevdiği yazarlara, editörlere ve ajanslara. "
        "Bir mektup da bir türlü gönderemediği kişiye. Sybil Van Antwerp otuz yıldır mektuplarla dünyaya tutunurken "
        "yakınındakileri uzakta tutuyor. İnziva bitmek üzere. Geçmişten gelen mektuplar onu en ağır dönemle karşılaştırıyor. "
        "Devam edebilmek için önce kendini affetmesi, sonra gerçekleri anlatması gerekiyor. "
        "Kapakta 26 haftalık New York Times birinciliği, 2026 PEN/Hemingway ve Women’s Prize, "
        "Goodreads’te üç dalda final (500.000 oy, 4.5) ve 3.000 bağımsız kitabevinin Indies Choice seçimi de duruyor."
    ),
    "B0H1MXJKJY": (
        "Ebeveyn ile çocuğun aynı masada oynadığı manyetik taş oyunu. Taşlar birbirini çekiyor, "
        "alanı ayarlanabilir bir ip belirliyor. Kutuda 24 taş, bir ip ve bir taşıma çantası var. "
        "Odak, mantık ve problem çözme tarafı öne çıkıyor. Malzeme toksik madde içermiyor."
    ),
    "B07CP2RFRT": (
        "24 renkli pastel boya. Renkler canlı ve örtücü; kâğıt ve kartonda yayılıyor, yumuşak olduğu için "
        "kâğıt üzerinde kayıyor. Tutacak sayesinde daha uzun kullanılıyor. Özel çantasıyla ev, okul ve "
        "oyun buluşmasına taşınıyor."
    ),
}

KIMLER = {
    "6052657480": (
        "Toplumun içinde sürekli uyum sağlayan bir karakterin hikâyesini sevenlere gider. "
        "Rahat bir kaçış romanı arıyorsan burası daha tedirgin. Kore edebiyatından gelen, "
        "toplumsal baskıyı kurcalayan romanlara yakın."
    ),
    "6259568126": (
        "Çıkarım ve küçük gizem bulmacası sevenlere. Katilden çok, cinayetin nasıl kurulduğunu "
        "çözmek istiyorsan bu cilt orada. Düz roman temposu arayanı yorar."
    ),
    "6256756207": (
        "Mektupla ilerleyen, acele etmeyen romanları sevenlere. Sybil’in yıllarca sakladığı mesafe "
        "bu metnin omurgası. Hızlı bir polisiye arıyorsan tempo sana uymaz."
    ),
}

HOOK = {
    "6052657480": "Uyum ile öfke arasında sıkışan kısa bir roman.",
    "6259568126": "Masada çözülen bir cinayet bulmacası.",
    "6256756207": "Mektuplarla ilerleyen, acele etmeyen bir roman.",
}

HANGI_KITAP = (
    "Üçü aynı okumalık değil. Tedirgin, kısa bir kurgu istiyorsan Portakal ve Ekmek Bıçağı. "
    "Masada çözülecek bir gizem istiyorsan Murdle 1. Mektupla ilerleyen, daha uzun bir roman istiyorsan Muhabbet."
)

KAPANIS = (
    "Liste Amazon.com.tr çok satanlar sıralamasına göre hazırlandı, sıralama haftalık değişir."
)


def _bilgi(u):
    ayr = u.get("ayrinti") or {}
    return {
        "yazar": (u.get("yazar") or "").strip(),
        "yayinci": _alan(ayr, "Yayıncı", "Yayınevi") or "",
        "sayfa": _alan(ayr, "Baskı Uzunluğu", "Sayfa sayısı") or "",
        "tarih": _alan(ayr, "Yayınlanma Tarihi", "Yayın tarihi") or "",
        "dil": _alan(ayr, "Dil") or "",
    }


def _konu_metni(u):
    acik = ((u.get("ayrinti") or {}).get("aciklama") or "").strip()
    if not acik:
        return ""
    hazir = KONU.get(u.get("asin") or "") or ANLATI.get(u.get("asin") or "")
    if hazir:
        return hazir.strip()
    return " ".join(parafraz(acik)[:3]).strip()


def _kimler_kitap(u, konu):
    if ((u.get("ayrinti") or {}).get("aciklama") or "").strip() and KIMLER.get(u.get("asin") or ""):
        return KIMLER[u["asin"]]
    k = amazon_tr.fold(konu)
    if "bulmaca" in k or "cinayet" in k:
        return "Çıkarım ve küçük gizem bulmacası sevenlere gider. Düz bir roman temposu arıyorsan bu cilt seni yorar."
    if "mektup" in k:
        return "Mektupla ilerleyen, acele etmeyen romanları sevenlere gider."
    if "ogretmen" in k or "toplum" in k:
        return (
            "Toplumun içinde kaybolan bir karakterin hikâyesini sevenlere gider. "
            "Rahat bir kaçış romanı arıyorsan daha tedirgin bir yerde duruyor."
        )
    return ""


def _madde_satirlari(u, limit=5):
    out = []
    for madde in (u.get("ayrinti") or {}).get("maddeler") or []:
        ham = re.sub(r"^[^\wÇĞİÖŞÜçğıöşü]+", "", madde or "")
        ham = re.sub(r"\bmükemmel\b", "", ham, flags=re.I)
        ham = re.sub(r"\s+", " ", ham).strip(" .")
        if not ham:
            continue
        bas, govde = ham, ""
        for ayirici in (":", " – ", " - "):
            if ayirici in ham:
                bas, _, govde = ham.partition(ayirici)
                break
        bas, govde = bas.strip(" ."), govde.strip()
        if govde and len(govde.split()) <= 12:
            satir = f"{bas}: {govde}" if bas else govde
        else:
            satir = bas or ""
        if len(satir.split()) > 18:
            kisa = " ".join(satir.split()[:18])
            if "," in kisa:
                kisa = kisa.rsplit(",", 1)[0]
            satir = kisa.rstrip(",;:")
        if satir and satir not in out:
            out.append(satir)
        if len(out) >= limit:
            break
    return out


def _yas_cumlesi(u):
    metin = " ".join((u.get("ayrinti") or {}).get("maddeler") or [])
    metin += " " + ((u.get("ayrinti") or {}).get("aciklama") or "")
    kucuk = re.search(r"(\d+)\s*yaş[^\n.]{0,50}uygun değildir", metin, flags=re.I)
    ust = re.search(r"(\d+)\s*yaş\s+ve\s+üzeri", metin, flags=re.I)
    if ust and kucuk:
        return f"{ust.group(1)} yaş ve üzeri. {kucuk.group(1)} yaşın altı için uygun değil."
    if kucuk:
        return f"{kucuk.group(1)} yaşın altı için uygun değil."
    if ust:
        return f"{ust.group(1)} yaş ve üzeri."
    return ""


def _kullanim_cumlesi(u):
    for madde in (u.get("ayrinti") or {}).get("maddeler") or []:
        if amazon_tr.fold(madde).lstrip().startswith("nasil"):
            _, _, govde = madde.partition(":")
            govde = re.sub(r"\s+", " ", govde).strip()
            if not govde:
                continue
            cumle = re.split(r"(?<=[.!?])\s+", govde)[0].strip()
            kelime = cumle.split()
            if len(kelime) > 35:
                cumle = " ".join(kelime[:35]).rstrip(",;") + "."
            if cumle and cumle[-1] not in ".!?":
                cumle += "."
            return cumle
    metin = " ".join((u.get("ayrinti") or {}).get("maddeler") or [])
    if re.search(r"aküsüz|olmadan teslim", metin, flags=re.I):
        return "Akü ve şarj cihazı kutuda yok; ayrıca alman gerekiyor."
    return ""


def _link_cumlesi(ilgili, kitap):
    sec = [m for m in (ilgili or []) if m.get("slug")][:3]
    if kitap and len(sec) < 2:
        return (
            "Kitabın yanında evde oturan başka uğraşlar da var: "
            "[okuma](/kategori/yazi-edebiyat/okuma/), "
            "[Yetişkin Hobi Setleri](/makale/yetiskin-hobi-setleri/) ve "
            "[Evde Yapılacak Hobiler](/makale/evde-yapilacak-hobiler/)."
        )
    if not sec:
        return ""
    parca = []
    for m in sec:
        href = m.get("url") or f"/makale/{m['slug']}/"
        parca.append(f"[{m['baslik']}]({href})")
    if len(parca) == 1:
        birlesik = parca[0]
    elif len(parca) == 2:
        birlesik = f"{parca[0]} ve {parca[1]}"
    else:
        birlesik = f"{parca[0]}, {parca[1]} ve {parca[2]}"
    return f"Aynı taraftaki rehberler: {birlesik}."


def _kunye(u):
    b = _bilgi(u)
    satir = []
    if b["yazar"]:
        satir.append(f"- Yazar: {b['yazar']}")
    if b["yayinci"]:
        satir.append(f"- Yayınevi: {b['yayinci']}")
    if b["sayfa"]:
        satir.append(f"- Sayfa: {b['sayfa']}")
    if b["tarih"]:
        satir.append(f"- Yayın tarihi: {b['tarih']}")
    return satir


def _tablo(urunler, kitap):
    if kitap:
        bas = ["Kitap", "Yazar", "Yayınevi", "Sayfa"]
        anahtar = ("yazar", "yayinci", "sayfa")
    else:
        bas = ["Ürün", "Ne"]
        anahtar = None
    satir = [
        "| " + " | ".join(bas) + " |",
        "| " + " | ".join("---" for _ in bas) + " |",
    ]
    for u in urunler:
        if kitap:
            b = _bilgi(u)
            hucre = [u["ad"].replace("|", "/")] + [(b[k] or "").replace("|", "/") for k in anahtar]
        else:
            oz = _madde_satirlari(u, 1)
            hucre = [u["ad"].replace("|", "/"), (oz[0] if oz else "").replace("|", "/")]
        satir.append("| " + " | ".join(hucre) + " |")
    return satir


def _sss_kitap(urunler):
    blok = ["## Sıkça Sorulan Sorular", ""]
    sayfalilar = []
    for u in urunler:
        sayfa = _bilgi(u)["sayfa"]
        m = re.search(r"\d+", sayfa or "")
        if m:
            sayfalilar.append((int(m.group(0)), u, sayfa))
    if len(sayfalilar) >= 2:
        sayfalilar.sort()
        dizi = ", ".join(f"{u['ad']} {sayfa}" for _, u, sayfa in sayfalilar)
        blok += ["**Hangisi daha kısa?**", "", f"{dizi}. En kısası {sayfalilar[0][1]['ad']}.", ""]
    diller = {_bilgi(u)["dil"] for u in urunler if _bilgi(u)["dil"]}
    if diller == {"Türkçe"}:
        blok += ["**Türkçe baskı mı?**", "", "Üçünün de dili Türkçe.", ""]
    elif diller:
        blok += ["**Hangi dilde?**", "", ", ".join(sorted(diller)) + ".", ""]
    return blok


def _sss_urun(urunler):
    blok = ["## Sıkça Sorulan Sorular", ""]
    ilk = urunler[0]
    blok += [
        "**İlk sırada ne var?**",
        "",
        f"{ilk['sira']}. sırada {ilk['ad']} var. [Ürün sayfası]({ilk['url']}).",
        "",
    ]
    yaslar = []
    for u in urunler:
        yas = _yas_cumlesi(u)
        if yas:
            yaslar.append(f"{u['ad']}: {yas}")
    if yaslar:
        blok += ["**Yaş sınırı var mı?**", "", " ".join(yaslar), ""]
    aku = [u["ad"] for u in urunler if "ayrıca alman gerekiyor" in (_kullanim_cumlesi(u) or "")]
    if aku:
        blok += ["**Akü kutuda geliyor mu?**", "", f"{aku[0]} aküsüz teslim ediliyor.", ""]
    return blok


def _yedek_kitap(liste, gun_yazi, urunler):
    adlar = [u["ad"] for u in urunler]
    if len(adlar) >= 3:
        liste_ad = f"{adlar[0]}, {adlar[1]} ve {adlar[2]}"
    elif len(adlar) == 2:
        liste_ad = f"{adlar[0]} ve {adlar[1]}"
    else:
        liste_ad = adlar[0] if adlar else "bu haftanın kitapları"
    giris = f"{gun_yazi} tarihli kitap sıralamasının başında {liste_ad} var."
    if [u.get("asin") for u in urunler] == ["6052657480", "6259568126", "6256756207"]:
        giris += (
            " Biri tedirgin bir roman, biri çıkarım bulmacası, biri mektupla kurulan daha uzun bir metin. "
            "Vaktin hangisine yetiyorsa ona bak."
        )
    blok = [giris, ""]
    for u in urunler:
        b = _bilgi(u)
        konu = _konu_metni(u)
        blok += [f"## {u['sira']}. {u['ad']}", ""]
        kanca = HOOK.get(u.get("asin") or "")
        if kanca:
            blok += [kanca, ""]
        blok += ["### Konusu", ""]
        if konu:
            blok += [konu, ""]
        kim = _kimler_kitap(u, konu)
        if kim:
            blok += ["### Kimler sevmeli", "", kim, ""]
        kunye = _kunye(u)
        if kunye:
            blok += ["### Künye", ""] + kunye + [""]
        blok += [f"[{u['ad']}]({u['url']})", ""]
    if [u.get("asin") for u in urunler] == ["6052657480", "6259568126", "6256756207"]:
        hangi = HANGI_KITAP
    else:
        parcalar = []
        for u in urunler:
            kanca = HOOK.get(u.get("asin") or "")
            if kanca:
                parcalar.append(f"{u['ad']} için {kanca[0].lower()}{kanca[1:]}")
        hangi = " ".join(parcalar) if parcalar else "Künye ve konu özeti, hangisine vaktin yettiğini gösterir."
    blok += ["## Hangisini seçmeli?", "", hangi, ""]
    blok += ["## Karşılaştırma", ""] + _tablo(urunler, True) + [""]
    blok += _sss_kitap(urunler)
    link = _link_cumlesi(liste.get("ilgili"), True)
    if link:
        blok += [link, ""]
    blok += [KAPANIS, ""]
    return "\n".join(blok).strip() + "\n"


def _kisa_ad(ad):
    kelime = (ad or "").split()
    if len(kelime) <= 5:
        return ad
    return " ".join(kelime[:5])


def _ne_cumlesi(u):
    konu = _konu_metni(u)
    if not konu:
        return ""
    parca = []
    n = 0
    for cumle in re.split(r"(?<=[.!?])\s+", konu):
        if not cumle.strip():
            continue
        parca.append(cumle.strip())
        n += len(cumle.split())
        if n >= 55 or len(parca) == 2:
            break
    return " ".join(parca)


def _yedek_urun(liste, gun_yazi, urunler):
    ad = liste.get("ad") or "Ürün"
    isimler = ", ".join(_kisa_ad(u["ad"]) for u in urunler)
    blok = [
        f"{gun_yazi} tarihli {ad.lower()} sıralamasında {isimler} var.",
        "",
    ]
    for u in urunler:
        blok += [f"## {u['sira']}. {u['ad']}", ""]
        ne = _ne_cumlesi(u)
        if ne:
            blok += [ne, ""]
        oz = _madde_satirlari(u, 5)
        if oz:
            blok += ["### Öne çıkanlar", ""]
            for s in oz:
                blok.append(f"- {s}")
            blok.append("")
        yas = _yas_cumlesi(u)
        if yas:
            blok += ["### Kimler için", "", yas, ""]
        kull = _kullanim_cumlesi(u)
        if kull and kull not in (ne or ""):
            blok += ["### Kullanırken", "", kull, ""]
        blok += [f"[{u['ad']}]({u['url']})", ""]
    bilinen = {
        ("B0H1MXJKJY", "B002E2LUM4", "B00MUTZ0MW"): (
            "Kısa ve taşınabilir bir tur istiyorsan Stones. Anlatmalı, çizerek giden bir parti istiyorsan Tabu XL. "
            "Türkiye illeriyle kurulmuş bir emlak oyunu istiyorsan Monopoly."
        ),
    }
    anahtar = tuple(u.get("asin") for u in urunler)
    if anahtar in bilinen:
        hangi = bilinen[anahtar]
    else:
        ayir = []
        for u in urunler:
            oz = _madde_satirlari(u, 1)
            if oz:
                ayir.append(f"{_kisa_ad(u['ad'])} için {oz[0]}")
        hangi = ". ".join(ayir) + "." if ayir else "Üçü de aynı işi görmüyor."
    blok += ["## Hangisini seçmeli?", "", hangi, ""]
    blok += ["## Karşılaştırma", ""] + _tablo(urunler, False) + [""]
    blok += _sss_urun(urunler)
    link = _link_cumlesi(liste.get("ilgili"), False)
    if link:
        blok += [link, ""]
    blok += [KAPANIS, ""]
    return "\n".join(blok).strip() + "\n"


def _govde_uygun(govde, liste):
    """Gemini çıktısı linkleri, SSS başlığını ve yasak kalıpları taşısın."""
    if not govde or "çekim" in govde.lower():
        return False
    if "yazar satırı" in govde.lower() or "kapakta duran anlatı" in govde.lower():
        return False
    if "## Sıkça Sorulan Sorular" not in govde or "## Hangisini seçmeli?" not in govde:
        return False
    if govde.count("\n|") > 12:
        return False
    if re.search(r"\d+\s*(tl|₺)", govde, flags=re.I):
        return False
    for u in liste.get("urunler") or []:
        if u.get("url") and u["url"] not in govde:
            return False
    ham = " ".join(
        ((u.get("ayrinti") or {}).get("aciklama") or "")
        for u in liste.get("urunler") or []
    )
    if len(_ngram(ham, 10) & _ngram(govde, 10)) > 2:
        return False
    kelime = len(govde.split())
    return 450 <= kelime <= 1500


def _gemini_govde(liste, gun_yazi):
    """Anahtar varsa olguları Gemini'ye ver. Yoksa veya denetim düşerse boş döner."""
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        return ""
    kitap = liste.get("id") == "kitap"
    paket = []
    for u in (liste.get("urunler") or [])[:3]:
        b = _bilgi(u)
        ayr = u.get("ayrinti") or {}
        paket.append({
            "sira": u.get("sira"),
            "ad": u.get("ad"),
            "url": u.get("url"),
            "yazar": b["yazar"],
            "yayinci": b["yayinci"],
            "sayfa": b["sayfa"],
            "yayin_tarihi": b["tarih"],
            "dil": b["dil"],
            "kapak": (ayr.get("aciklama") or "")[:2200],
            "maddeler": (ayr.get("maddeler") or [])[:8],
        })
    if kitap:
        yapi = """Her kitap için şu sıra, başka başlık yok:
## {sıra}. {ad}
1-2 cümlelik kanca.
### Konusu
Kapak metnini kendi cümlelerinle 1-2 paragraf anlat. Olay uydurma.
### Kimler sevmeli
Okur tipi, ruh hali, yakın tür. Sayfada olmayan ödül veya satış iddiası yok.
### Künye
Tek liste. Yalnızca dolu alanlar: Yazar, Yayınevi, Sayfa, Yayın tarihi.
Ardından satın alma bağlantısı, url aynen."""
    else:
        yapi = """Her ürün için:
## {sıra}. {ad}
Ne olduğu, 1 paragraf.
### Öne çıkanlar
Kısa madde listesi. Uzun reklam cümlesini kopyalama.
### Kimler için
Yaş veya kullanım, sayfada varsa.
### Kullanırken
Sayfadaki kullanım veya uyarıdan tek ipucu. Yoksa bu başlığı yazma.
Ardından satın alma bağlantısı, url aynen."""
    ilgili = []
    for m in (liste.get("ilgili") or [])[:3]:
        href = m.get("url") or f"/makale/{m.get('slug')}/"
        ilgili.append({"baslik": m.get("baslik"), "yol": href})
    prompt = f"""Sen Hobi Bul için yazan bir Türkçe kitap ve ürün editörüsün. Okura "sen" diye seslen. Konuşur gibi yaz. Broşür, veri dökümü ve tekrar yok.

TARİH: {gun_yazi}
KATEGORİ: {liste.get("ad")}

OLGULAR (yalnızca bunlar; fiyat, ölçü, ödül, sayı veya olay ekleme; boş alanı doldurma):
{json.dumps(paket, ensure_ascii=False)}

İÇ LİNKLER (en fazla 3, cümle içinde):
{json.dumps(ilgili, ensure_ascii=False)}

YAPI:
Giriş: tek kısa paragraf. Üç adı geçir. "Bu yazıda", "bu makalede" yasak.
{yapi}
## Hangisini seçmeli?
Üçünü okur niyetine göre ayır. Aynı özeti tekrarlama.
## Karşılaştırma
Tek markdown tablo. Kitapta yazar, yayınevi, sayfa. Diğerinde ürün ve bir ayırıcı özellik.
## Sıkça Sorulan Sorular
3 veya 4 gerçek okur sorusu. Soru satırı **soru** biçiminde, altındaki satır cevap.
Kapanışta tam olarak şu cümle, başka kaynak açıklaması yok:
{KAPANIS}

UZUNLUK: yaklaşık 900-1300 kelime, dolu ve doğal. Sırf sayı tutsun diye aynı bilgiyi ikinci kez yazma. Eksik kalsın, dolgu yapma.
YASAK: çekim, yazar satırı, kapakta duran anlatı, sayfasında yayıncı olarak, mükemmel, keşfedin, sonuç olarak, günümüzde.
Kapak metninden 10 kelimeyi art arda kopyalama. Kod bloğu yok.
"""
    try:
        otomatik.ym.load_env()
        models, _acik = otomatik._modeller()
        idx = [0]
        yanit = otomatik._gemini(prompt, key, models, idx)
        govde = otomatik.govde_ayikla(str(yanit))
    except Exception as e:
        print("Gemini yazamadı, yedek metin kullanılacak: " + otomatik.ym._gemini_metin(e))
        return ""
    if not _govde_uygun(govde, liste):
        print("Gemini metni denetlenemedi, yedek metin kullanılacak.")
        return ""
    return govde.strip() + "\n"


def yazi_metni(liste, hafta, gun_yazi):
    """Editör metni. Anahtar varsa Gemini, yoksa kısa ve tekrarsız yedek."""
    govde = _gemini_govde(liste, gun_yazi)
    if govde:
        return govde
    urunler = (liste.get("urunler") or [])[:3]
    if liste.get("id") == "kitap":
        return _yedek_kitap(liste, gun_yazi, urunler)
    return _yedek_urun(liste, gun_yazi, urunler)




def _zenginlestir(oturum, urun):
    """Ürün sayfasını çek. Engel olursa ayrinti boş kalır, ASIN linki durur."""
    asin = urun.get("asin") or ""
    if not asin or urun.get("ayrinti"):
        return urun
    try:
        html, _ = oturum.getir(
            f"{amazon_tr.HOST}/dp/{asin}",
            referer=amazon_tr.HOST + "/gp/bestsellers",
        )
    except amazon_tr.AmazonEngel as e:
        print(f"! {asin} ayrıntı alınamadı ({e.neden})")
        urun["ayrinti"] = {}
        return urun
    urun["ayrinti"] = amazon_tr.urun_ayrintisi(html)
    print(f"  {asin}: açıklama {len((urun['ayrinti'].get('aciklama') or '').split())} kelime, "
          f"{len(urun['ayrinti'].get('bilgiler') or [])} bilgi")
    return urun


def yazi_yaz(liste, hafta, bugun, yenile=False):
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
    if os.path.exists(yol) and not yenile:
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


def calistir(yaz=False, bugun=None, oturum=None, yenile=False):
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
            for u in liste["urunler"]:
                _zenginlestir(oturum, u)
            liste["ilgili"] = _ilgili_makaleler(liste["cat"], liste.get("sub") or "", "")
            slug, yeni = yazi_yaz(liste, hafta, bugun, yenile=yenile)
            yazilan.append({"slug": slug, "yeni": yeni, "cat": liste["cat"]})
            print(("✓ yazıldı " if yeni else "· vardı ") + slug)
    kayit["secilen"] = [{"id": l["id"], "cat": l["cat"]} for l in sec]
    kayit["yazilan"] = yazilan
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        json.dump(kayit, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return kayit


def _fm_al(text, anahtar):
    m = re.search(rf'{anahtar}:\s*"([^"]*)"', text)
    return m.group(1) if m else ""


def _urunleri_govdeden(body):
    """Eski kısa kalıp ya da ## sıra başlığındaki /dp linkinden ürünleri topla."""
    urunler = []
    kalip = re.compile(
        r"(\d+)\. sırada (.+?) var\.(?: Yazar satırı (.+?)\.)?\s*"
        r"Ürün sayfası \[([^\]]+)\]\((https://www\.amazon\.com\.tr/dp/([A-Z0-9]{10})\?tag=hobibulsite-21)\)"
    )
    for m in kalip.finditer(body):
        urunler.append({
            "sira": int(m.group(1)),
            "ad": m.group(2).strip(),
            "yazar": (m.group(3) or "").strip(),
            "url": m.group(5),
            "asin": m.group(6),
        })
    if urunler:
        return urunler
    for parca in re.split(r"(?m)^## ", body):
        bas = re.match(r"(\d+)\.\s*(?:sıradaki\s+)?(.+)", parca)
        if not bas:
            continue
        link = re.search(
            r"\((https://www\.amazon\.com\.tr/dp/([A-Z0-9]{10})\?tag=hobibulsite-21)\)",
            parca,
        )
        if not link:
            continue
        yazar = ""
        for ym in (
            re.search(r"Yazar satırında (.+?) yazıyor", parca),
            re.search(r"Yazar satırı (.+?)\.\s", parca),
            re.search(r"(?m)^- Yazar: (.+)$", parca),
        ):
            if ym:
                yazar = ym.group(1).strip().rstrip(".")
                break
        urunler.append({
            "sira": int(bas.group(1)),
            "ad": bas.group(2).strip().split("\n")[0].strip(),
            "yazar": yazar,
            "url": link.group(1),
            "asin": link.group(2),
        })
    return urunler


def mevcut_yenile(oturum=None, hafta=None):
    """Bu haftanın çok satan yazılarını yeniden kur. Slug ve /dp linki aynı kalır."""
    oturum = oturum or amazon_tr.Oturum(bekle=2.2, deneme=2)
    hafta = hafta or hafta_kimligi()
    etiket = hafta.lower()
    bugun = date.today().isoformat()
    for fn in sorted(os.listdir(ARTICLES)):
        if not fn.endswith(".md") or etiket not in fn.lower():
            continue
        yol = os.path.join(ARTICLES, fn)
        text = open(yol, encoding="utf-8").read()
        if text.count("---") < 2:
            continue
        _, fm, body = text.split("---", 2)
        urunler = _urunleri_govdeden(body)
        if len(urunler) < 1:
            print("! ürün yok", fn)
            continue
        for u in urunler:
            _zenginlestir(oturum, u)
        fm_metin = "---" + fm
        liste = {
            "id": "diger",
            "ad": _fm_al(fm_metin, "image_alt").replace(" çok satanlar listesinden bir ürün", "") or "Ürün",
            "cat": _fm_al(fm_metin, "category"),
            "sub": _fm_al(fm_metin, "subcategory"),
            "urunler": urunler,
            "ilgili": _ilgili_makaleler(
                _fm_al(fm_metin, "category"),
                _fm_al(fm_metin, "subcategory"),
                fn[:-3],
            ),
        }
        if "kitap" in fn:
            liste["id"] = "kitap"
            liste["ad"] = "Kitap"
        gun = _fm_al(fm_metin, "date") or bugun
        govde = yazi_metni(liste, hafta, tarih_yaz(gun))
        if re.search(r'updated:\s*"', fm):
            fm2 = re.sub(r'updated:\s*"[^"]*"', f'updated: "{bugun}"', fm, count=1)
        else:
            fm2 = fm.rstrip() + f'\nupdated: "{bugun}"\n'
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            f.write("---" + fm2 + "---\n" + govde)
        print(f"✓ {fn[:-3]} {len(govde.split())} kelime")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yaz", action="store_true")
    ap.add_argument("--yenile", action="store_true", help="Bu haftanın çok satan yazılarını yeniden yaz")
    a = ap.parse_args()
    if a.yenile:
        try:
            mevcut_yenile()
        except amazon_tr.AmazonEngel as e:
            print(f"Amazon engeli, yumuşak çıkış: {e.neden}")
        return 0
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
