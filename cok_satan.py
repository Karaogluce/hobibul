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
    sonuc = [{"baslik": b, "slug": s} for _, b, s in aday[:4]]
    if len(sonuc) >= 2 or not cat:
        return sonuc
    # Aynı kategoride rehber yoksa (kitapta olduğu gibi) kategori sayfasına bağla.
    sonuc.append({"baslik": "Bu kategorinin sayfası", "url": f"/kategori/{cat}/"})
    if sub:
        sonuc.append({"baslik": "Bu alt kategorinin sayfası", "url": f"/kategori/{cat}/{sub}/"})
    return sonuc


def _alan(ayrinti, *etiketler):
    return amazon_tr.bilgi_degeri(ayrinti or {}, *etiketler)


def _madde_parcasi(ad, madde):
    """Özellik maddesini başlık ve gövde olarak yaz. Madde kısa olduğu için bütün kalır."""
    ham = re.sub(r"^[^\wÇĞİÖŞÜçğıöşü]+", "", madde or "").strip()
    ham = re.sub(r"\bmükemmel\b", "", ham, flags=re.I)
    ham = re.sub(r"\s+", " ", ham).strip()
    if ":" in ham:
        baslik, _, govde = ham.partition(":")
    elif "–" in ham:
        baslik, _, govde = ham.partition("–")
    else:
        baslik, govde = ham, ""
    baslik, govde = baslik.strip(" ."), govde.strip()
    if baslik and govde:
        return f"{baslik}. {govde}"
    return ham


def _alan_parcasi(ad, etiket, deger):
    """Bilgi satırını yeni olgu eklemeden bir cümleye bağla."""
    return f"{ad} sayfasında {etiket.lower()} olarak {deger} yazıyor."


def _urun_bolumu(u, kitap):
    ad = u["ad"]
    link = f"[{ad}]({u['url']})"
    ayr = u.get("ayrinti") or {}
    satir = [f"## {u['sira']}. sıradaki {ad}", ""]
    giris = f"{u['sira']}. sıra {link}."
    if u.get("yazar"):
        giris += f" Yazar satırı {u['yazar']}."
    yayinci = _alan(ayr, "Yayıncı", "Yayınevi", "Marka", "Üretici")
    sayfa = _alan(ayr, "Baskı Uzunluğu", "Sayfa sayısı")
    dil = _alan(ayr, "Dil")
    tarih = _alan(ayr, "Yayınlanma Tarihi", "Yayın tarihi")
    if yayinci:
        giris += f" Yayıncı olarak {yayinci} yazıyor."
    if sayfa:
        giris += f" Baskı uzunluğu {sayfa}."
    if dil:
        giris += f" Dil satırı {dil}."
    if tarih:
        giris += f" Yayın tarihi {tarih}."
    satir += [giris, ""]
    anlati = ANLATI.get(u.get("asin") or "") if (ayr.get("aciklama") or "").strip() else ""
    cumleler = [anlati] if anlati else parafraz(ayr.get("aciklama") or "")
    if cumleler:
        baslik = "Kapakta duran anlatı" if kitap else "Sayfanın anlattığı"
        satir += [f"### {baslik}", ""]
        for cumle in cumleler:
            satir.append(cumle)
            satir.append("")
    maddeler = ayr.get("maddeler") or []
    if maddeler:
        satir += ["### Sayfadaki özellikler", ""]
        for madde in maddeler:
            parca = _madde_parcasi(ad, madde)
            if not parca:
                continue
            satir.append(parca)
            satir.append("")
    bilgiler = ayr.get("bilgiler") or []
    bilgi_satir = []
    for b in bilgiler:
        et, de = b.get("etiket") or "", b.get("deger") or ""
        if not et or not de or et.lower().startswith("isbn"):
            continue
        bilgi_satir.append(_alan_parcasi(ad, et, de))
    if bilgi_satir:
        satir += ["### Ürün bilgisi satırı", ""]
        for p in bilgi_satir:
            satir.append(p)
            satir.append("")
    kime = _kime_cumlesi(ad, ayr)
    if kime:
        satir += ["### Kime uyuyor", "", kime, ""]
    sinir = _sinir_cumlesi(ad, ayr)
    if sinir:
        satir += ["### Sınırı", "", sinir, ""]
    satir += [
        "### Bu sırada durmasının nedeni",
        "",
        (
            f"{ad} bu çekimde {u['sira']}. sırada. "
            "Bu numara, o günkü çok satanlar sayfasındaki yer. "
            "Sayfa başka bir satış gerekçesi yazmıyor."
        ),
        "",
    ]
    return "\n".join(satir).strip()


_KITLE = (
    "çocuk", "yetişkin", "yaş", "aile", "okul", "bahçe", "seyahat",
    "oyuncu", "başlangıç", "sulama", "çim", "bitki", "öğrenci",
)


def _sinir_cumlesi(ad, ayr):
    """Sayfada açıkça yazan yaş veya teslimat sınırını eksik bırakma."""
    metin = " ".join(list(ayr.get("maddeler") or []) + [ayr.get("aciklama") or ""])
    notlar = []
    yas = re.search(r"(\d+)\s*yaş[^\n.]{0,40}uygun değildir", metin, flags=re.I)
    if yas:
        notlar.append(f"{yas.group(1)} yaşından küçükler için uygun olmadığı yazılı")
    elif re.search(r"uygun değildir", metin, flags=re.I):
        notlar.append("sayfa bir grup için uygun olmadığını yazıyor")
    if re.search(r"aküsüz|olmadan teslim", metin, flags=re.I):
        notlar.append("teslimatın akü veya şarj cihazı olmadan yapıldığı yazılı")
    if not notlar:
        return ""
    return f"{ad} için sayfanın sınır notu: " + "; ".join(notlar) + "."


def _kime_cumlesi(ad, ayr):
    """Sayfada kitle veya kullanım bildiren 'için' ifadesi varsa onu aktar."""
    metin = " ".join(list(ayr.get("maddeler") or []))
    bulunan = []
    for m in re.finditer(r"([^.]{8,80}?)\biçin\b", metin, flags=re.I):
        parca = re.sub(r"\s+", " ", m.group(1)).strip(" ,;:-")
        parca = parca.split(":")[-1].split("–")[-1].strip()
        kucuk = amazon_tr.fold(parca)
        if not any(k in kucuk for k in _KITLE):
            continue
        if 2 <= len(parca.split()) <= 10 and parca.lower() not in bulunan:
            bulunan.append(parca.lower())
        if len(bulunan) == 3:
            break
    if not bulunan:
        return ""
    return f"{ad} sayfası bu kaydı şu kullanıma bağlıyor: " + "; ".join(bulunan) + " için."


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


def _yanyana_metni(urunler, kitap):
    """Üç kaydı, sayfada duran başlık ve bilgiyle yan yana anlat."""
    satir = ["## Üç kayıt yan yana", ""]
    for u in urunler:
        ayr = u.get("ayrinti") or {}
        parca = f"{u['sira']}. sırada [{u['ad']}]({u['url']}) var."
        if u.get("yazar"):
            parca += f" Yazar {u['yazar']}."
        for et in ("Yayıncı", "Yayınevi", "Baskı Uzunluğu", "Dil", "Yayınlanma Tarihi"):
            de = _alan(ayr, et)
            if de and et.lower() not in parca.lower():
                parca += f" {et} {de}."
        basliklar = []
        for madde in ayr.get("maddeler") or []:
            ham = re.sub(r"^[^\wÇĞİÖŞÜçğıöşü]+", "", madde or "").strip()
            bas = re.split(r"[:–]", ham, maxsplit=1)[0].strip()
            if bas and len(bas.split()) <= 8 and bas not in basliklar:
                basliklar.append(bas)
        if basliklar:
            parca += " Sayfadaki madde başlıkları: " + ", ".join(basliklar) + "."
        satir += [parca, ""]
    if kitap:
        satir.append(
            "Üç kitap da bu çekimin kitap listesinden. Sayfa sayısı, yayınevi ve kapak anlatısı "
            "her birinin kendi ürün sayfasından alındı."
        )
    else:
        satir.append(
            "Üç kayıt da aynı çok satanlar bölümünün bu çekiminden. "
            "Ayıran nokta, her sayfanın kendi madde listesi."
        )
    satir.append("")
    return satir


def yazi_metni(liste, hafta, gun_yazi):
    """Ürün sayfasındaki ad, açıklama ve bilgi satırlarından uzun tanıtım.

    Sayfada olmayan sayı, fiyat veya olay yazılmaz.
    """
    ad = liste["ad"]
    urunler = liste["urunler"][:3]
    kitap = liste["id"] == "kitap"
    if kitap:
        giris = (
            f"Amazon.com.tr kitap çok satanlar listesinin {gun_yazi} çekiminde "
            f"ilk üç sıra aşağıda. Sıra o sayfanın bu çekimdeki hali. "
            f"Her kitap için yalnızca ürün sayfasında duran ad, yazar, yayınevi, "
            f"baskı bilgisi ve kapak anlatısı kullanıldı."
        )
    else:
        giris = (
            f"Amazon.com.tr {ad.lower()} çok satanlar sayfasının {gun_yazi} çekiminde, "
            f"adı bu kategoriye uyan ilk üç kayıt aşağıda. Sayı, listenin o anki sırası. "
            f"Özellik cümleleri ürün sayfasındaki madde ve bilgi satırından geliyor."
        )
    blok = ["## Bu çekimin ilk üçü", "", giris, ""]
    for u in urunler:
        blok.append(_urun_bolumu(u, kitap))
        blok.append("")
    blok += _yanyana_metni(urunler, kitap)
    # Karşılaştırma: yalnızca dolu alanlar.
    alanlar = []
    if kitap:
        aday_alan = (
            ("Yazar", lambda u: u.get("yazar") or ""),
            ("Yayıncı", lambda u: _alan(u.get("ayrinti"), "Yayıncı", "Yayınevi")),
            ("Baskı", lambda u: _alan(u.get("ayrinti"), "Baskı Uzunluğu")),
            ("Dil", lambda u: _alan(u.get("ayrinti"), "Dil")),
        )
    else:
        aday_alan = (
            ("Sıra", lambda u: str(u.get("sira") or "")),
        )
        etiketler = []
        for u in urunler:
            for b in (u.get("ayrinti") or {}).get("bilgiler") or []:
                et = b.get("etiket") or ""
                if et and et not in etiketler and not et.lower().startswith("isbn"):
                    etiketler.append(et)
        for et in etiketler[:4]:
            aday_alan = aday_alan + ((et, lambda u, e=et: _alan(u.get("ayrinti"), e)),)
    basliklar = ["Ürün"] + [a[0] for a in aday_alan]
    satirlar = ["| " + " | ".join(basliklar) + " |", "| " + " | ".join("---" for _ in basliklar) + " |"]
    for u in urunler:
        hucre = [u["ad"]]
        for _, fn in aday_alan:
            hucre.append((fn(u) or "").replace("|", "/"))
        satirlar.append("| " + " | ".join(hucre) + " |")
    blok += [
        "## Sıra ne söylüyor",
        "",
        (
            f"Çok satanlar sayfasındaki sayı, {gun_yazi} çekimindeki yer. "
            "Bu bir okur puanı değil; Amazon.com.tr o bölümde o an görünen sıra. "
            "Ertesi hafta aynı ad aynı sayıda durmak zorunda değil. "
            "Buradaki üç kayıt, o sayfada adı bu hobi kategorisine uyan ilk ürünler. "
            "Altta kalan satırlar, adları kategoriye uymadığı için bu yazıya girmedi."
        ),
        "",
        *satirlar,
        "",
        "Tablodaki hücre, ürün sayfasında yazıyorsa duruyor. Boş hücre, o etiket o sayfada yok demek.",
        "",
    ]
    for u in urunler:
        basliklar = []
        for madde in (u.get("ayrinti") or {}).get("maddeler") or []:
            bas = re.sub(r"^[^\wÇĞİÖŞÜçğıöşü]+", "", (madde or "").split(":")[0]).strip()
            if bas and bas not in basliklar:
                basliklar.append(bas)
        etiketler = [
            b.get("etiket") for b in (u.get("ayrinti") or {}).get("bilgiler") or []
            if b.get("etiket") and not str(b.get("etiket")).lower().startswith("isbn")
        ]
        cumle = (
            f"{u['sira']}. sıradaki [{u['ad']}]({u['url']}) bu çekimin kaydı. "
            f"Ürün sayfası aynı adrese gidiyor."
        )
        if u.get("yazar"):
            cumle += f" Yazar satırında {u['yazar']} yazıyor."
        yay = _alan(u.get("ayrinti"), "Yayıncı", "Yayınevi", "Marka")
        if yay:
            cumle += f" Yayıncı veya marka satırı {yay}."
        sayfa = _alan(u.get("ayrinti"), "Baskı Uzunluğu")
        if sayfa:
            cumle += f" Baskı uzunluğu {sayfa}."
        if basliklar:
            cumle += " Madde başlıkları sayfada şöyle sıralanmış: " + ", ".join(basliklar) + "."
        if etiketler:
            cumle += " Bilgi etiketleri de şunlar: " + ", ".join(etiketler) + "."
        cumle += " Yukarıdaki bölüm, bu kaydın sayfasından kurulan cümleleri taşıyor."
        blok.append(cumle)
        blok.append("")
    ilgili = liste.get("ilgili") or []
    if ilgili:
        blok += ["## Sitede yanında duran rehberler", ""]
        if any(m.get("slug") for m in ilgili):
            blok.append("Aynı kategoride daha önce yayımlanan rehberler de duruyor. Başlıklar onların kendi sayfasından.")
        else:
            blok.append("Aynı kategoride başka rehber yok. Aşağıdaki bağlantılar kategori sayfasına gider.")
        blok.append("")
        for m in ilgili:
            href = m.get("url") or f"/makale/{m['slug']}/"
            blok.append(f"- [{m['baslik']}]({href})")
        blok.append("")
    blok += ["## Sıkça Sorulan Sorular", ""]
    blok.append("**Liste hangi sayfadan geliyor?**")
    blok.append(
        f"{gun_yazi} çekiminde Amazon.com.tr çok satanlar sayfasının ilgili bölümünden. "
        "Ertesi hafta sıra değişebilir."
    )
    blok.append("")
    ilk = urunler[0]
    blok.append(f"**İlk sırada hangi ürün var?**")
    blok.append(
        f"Bu çekimde {ilk['sira']}. sırada {ilk['ad']} var. "
        f"Bağlantı {ilk['url']} adresine gider."
    )
    blok.append("")
    if kitap and any(u.get("yazar") for u in urunler):
        blok.append("**Yazar adları nerede yazıyor?**")
        yazarlar = ", ".join(f"{u['ad']} için {u['yazar']}" for u in urunler if u.get("yazar"))
        blok.append(f"Çok satanlar satırındaki yazar alanı: {yazarlar}.")
        blok.append("")
    adlar = ", ".join(u["ad"] for u in urunler)
    blok.append("**Üç kaydın bağlantısı nereye gidiyor?**")
    blok.append(
        f"Her bağlantı Amazon.com.tr üzerindeki ürün sayfasına gider ve hobibulsite-21 etiketini taşır. "
        f"Bu çekimdeki kayıtlar: {adlar}."
    )
    blok.append("")
    if any(_alan(u.get("ayrinti"), "Baskı Uzunluğu") for u in urunler):
        blok.append("**Sayfa sayısı görünen kitap hangisi?**")
        sayfalar = ", ".join(
            f"{u['ad']} { _alan(u.get('ayrinti'), 'Baskı Uzunluğu') }"
            for u in urunler if _alan(u.get("ayrinti"), "Baskı Uzunluğu")
        )
        blok.append(sayfalar + ".")
        blok.append("")
    return "\n".join(blok).strip() + "\n"


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
            for u in liste["urunler"]:
                _zenginlestir(oturum, u)
            liste["ilgili"] = _ilgili_makaleler(liste["cat"], liste.get("sub") or "", "")
            slug, yeni = yazi_yaz(liste, hafta, bugun)
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


def mevcut_yenile(oturum=None):
    """Var olan haftalık yazıların gövdesini ürün sayfasıyla yeniden kur.

    Slug, ASIN ve /dp linki aynı kalır. Eksik ayrıntı boş bırakılır.
    """
    oturum = oturum or amazon_tr.Oturum(bekle=2.2, deneme=2)
    for fn in sorted(os.listdir(ARTICLES)):
        if not fn.endswith(".md") or "2026-w46" not in fn:
            continue
        yol = os.path.join(ARTICLES, fn)
        text = open(yol, encoding="utf-8").read()
        if "---" not in text:
            continue
        _, fm, body = text.split("---", 2)
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
        if len(urunler) < 1:
            print("! ürün yok", fn)
            continue
        for u in urunler:
            _zenginlestir(oturum, u)
        liste = {
            "id": "kitap" if "kitap" in fn else "diger",
            "ad": _fm_al("---" + fm, "image_alt").replace(" çok satanlar listesinden bir ürün", "") or "Ürün",
            "cat": _fm_al("---" + fm, "category"),
            "sub": _fm_al("---" + fm, "subcategory"),
            "urunler": urunler,
            "ilgili": _ilgili_makaleler(
                _fm_al("---" + fm, "category"),
                _fm_al("---" + fm, "subcategory"),
                fn[:-3],
            ),
        }
        if "kitap" in fn:
            liste["id"] = "kitap"
            liste["ad"] = "Kitap"
        govde = yazi_metni(liste, "2026-W46", "9 Kasım 2026")
        fm2 = re.sub(r'updated:\s*"[^"]*"', 'updated: "2026-11-12"', fm, count=1)
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            f.write("---" + fm2 + "---\n" + govde)
        print(f"✓ {fn[:-3]} {len(govde.split())} kelime")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yaz", action="store_true")
    ap.add_argument("--yenile", action="store_true", help="Bu haftanın çok satan yazılarını ürün sayfasıyla uzat")
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
