#!/usr/bin/env python3
"""Amazon.com.tr okuyucu.

Çok satanlar listesi ve ürün sayfası. Captcha veya 503 olursa istisna yerine
yumuşak hata döner; engeli aşmaya çalışmaz.
"""
import html as html_lib
import http.cookiejar
import re
import time
import urllib.error
import urllib.parse
import urllib.request

TAG = "hobibulsite-21"
HOST = "https://www.amazon.com.tr"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_TR = str.maketrans({
    "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
    "â": "a", "î": "i", "û": "u",
})
_STOP = {
    "icin", "ile", "yeni", "baslangic", "seti", "kutu", "oyunu", "oyun",
    "rehber", "secimi", "the", "and", "for", "bir", "bu", "ve",
}


class AmazonEngel(Exception):
    """Captcha, 503 veya boş engel sayfası. Ürün uydurulmaz."""

    def __init__(self, url, neden):
        super().__init__(f"{neden}: {url}")
        self.url = url
        self.neden = neden


def fold(text):
    return str(text or "").replace("İ", "i").replace("I", "ı").lower().translate(_TR)


def dp_url(asin, tag=TAG):
    asin = re.sub(r"[^A-Z0-9]", "", str(asin or "").upper())
    if len(asin) != 10:
        return ""
    return f"{HOST}/dp/{asin}?tag={urllib.parse.quote(tag)}"


def _engel_mi(status, body):
    if status in (429, 503, 302):
        return f"http {status}"
    low = (body or "")[:8000].lower()
    if "captcha" in low or "validatecaptcha" in low or "/errors/validatecaptcha" in low:
        return "captcha"
    if status == 200 and len(body or "") < 4000 and "üzgünüz" in fold(body):
        return "kisa engel"
    return ""


class Oturum:
    def __init__(self, bekle=0.8, deneme=3):
        self.bekle = bekle
        self.deneme = deneme
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.hazir = False
        self.son = 0.0

    def getir(self, url, referer=None):
        if not self.hazir and "/gp/bestsellers" not in url:
            try:
                self._iste("https://www.amazon.com.tr/gp/bestsellers/books")
            except AmazonEngel:
                pass
            self.hazir = True
        return self._iste(url, referer)

    def _iste(self, url, referer=None):
        son_hata = None
        for deneme in range(self.deneme):
            ara = self.bekle - (time.time() - self.son)
            if ara > 0:
                time.sleep(ara)
            if deneme:
                time.sleep(1.5 * deneme)
            headers = {
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
            }
            if referer:
                headers["Referer"] = referer
            req = urllib.request.Request(url, headers=headers)
            try:
                with self.opener.open(req, timeout=25) as resp:
                    status = getattr(resp, "status", 200) or 200
                    body = resp.read().decode("utf-8", "replace")
                    final = resp.geturl()
            except urllib.error.HTTPError as e:
                self.son = time.time()
                body = ""
                try:
                    body = e.read().decode("utf-8", "replace")
                except Exception:
                    body = ""
                neden = _engel_mi(e.code, body) or f"http {e.code}"
                son_hata = AmazonEngel(url, neden)
                if e.code in (429, 503) and deneme + 1 < self.deneme:
                    continue
                raise son_hata from e
            except (urllib.error.URLError, TimeoutError) as e:
                self.son = time.time()
                son_hata = AmazonEngel(url, "baglanti")
                if deneme + 1 < self.deneme:
                    continue
                raise son_hata from e
            self.son = time.time()
            if "/gp/bestsellers" in url:
                self.hazir = True
            neden = _engel_mi(status, body)
            if neden:
                son_hata = AmazonEngel(final or url, neden)
                if deneme + 1 < self.deneme and neden != "captcha":
                    continue
                raise son_hata
            return body, final or url
        raise son_hata or AmazonEngel(url, "bos")


def cok_satanlari_ayikla(html, limit=3):
    """Çok satanlar sayfasından sıra, ASIN ve görünen ad.

    Kitap listesinde ad ve yazar ayrı satırdadır. Diğer listelerde tek ürün adı vardır.
    """
    html = html or ""
    parcalar = re.split(r'data-asin="([A-Z0-9]{10})"', html)
    gorulen = []
    for i in range(1, len(parcalar), 2):
        asin = parcalar[i]
        if len(asin) != 10:
            continue
        chunk = parcalar[i + 1][:12000]
        rank_m = re.search(r'zg-bdg-text">#(\d+)', chunk)
        if not rank_m:
            continue
        rank = int(rank_m.group(1))
        adlar = [
            re.sub(r"\s+", " ", a).strip()
            for a in re.findall(r'p13n-sc-css-line-clamp-\d+_[^"]*">([^<]+)', chunk)
        ]
        adlar = [a for a in adlar if a]
        if not adlar:
            alt = re.search(r'<img[^>]+alt="([^"]+)"', chunk)
            if alt:
                adlar = [re.sub(r"\s+", " ", alt.group(1)).strip()]
        if not adlar:
            continue
        yazar = ""
        ad = html_lib.unescape(adlar[0].split("|")[0].strip())
        if len(ad) > 160:
            ad = ad[:160].rsplit(" ", 1)[0].rstrip(" ,;:-–")
        if len(adlar) >= 2 and "line-clamp-1" in chunk:
            yazar = html_lib.unescape(adlar[1].split("|")[0].strip())
        yol = ""
        href = re.search(r'href="([^"]*/dp/' + re.escape(asin) + r'[^"]*)"', chunk)
        if href:
            yol = href.group(1).split("?")[0]
            if yol.startswith("/"):
                yol = HOST + yol
        gorulen.append({
            "sira": rank,
            "asin": asin,
            "ad": ad,
            "yazar": yazar,
            "yol": yol,
            "url": dp_url(asin),
        })
    gorulen.sort(key=lambda x: x["sira"])
    tek = []
    kullanilan = set()
    for item in gorulen:
        if item["asin"] in kullanilan or item["sira"] < 1:
            continue
        kullanilan.add(item["asin"])
        tek.append(item)
        if len(tek) >= limit:
            break
    return tek


def _govde(text):
    words = re.findall(r"[a-z0-9]+", fold(text))
    out = []
    for w in words:
        if w in _STOP:
            continue
        if w.isdigit() or len(w) >= 3:
            out.append(w)
    return out


def _sirali(metin, kelimeler):
    pos = 0
    for kelime in kelimeler:
        yer = metin.find(kelime, pos)
        if yer < 0:
            return False
        pos = yer + len(kelime)
    return True


def baslik_uyuyor(baslik, ad, marka=""):
    """Ürün sayfası başlığı, aranan adı aynı sırayla taşıyor mu.

    Kitap sayfası, hobi ürününün adıyla açılmıyorsa kabul edilmez.
    'Team Sky' kitabı 'Sky Team' oyununu tutmaz.
    """
    hedef = fold(baslik)
    if not hedef:
        return False
    govde = _govde(ad)
    if not govde or not _sirali(hedef, govde):
        return False
    marka_f = fold(marka)
    if marka_f and len(marka_f) >= 3 and marka_f not in _STOP and marka_f not in hedef:
        # Marka yoksa ad sırası yeter. Marka varsa başlıkta da durmalı.
        return False
    if hedef.startswith("prime video"):
        return False
    if "amazon.com.tr: kitap" in hedef and "kitap" not in fold(ad):
        # Tek kelimelik ad, başka bir kitabın adıyla çakışmasın.
        if len(govde) == 1:
            return False
        return _sirali(hedef.split(":")[0], govde)
    return True


def _temiz_html(parca):
    parca = re.sub(r"<script[\s\S]*?</script>", " ", parca or "", flags=re.I)
    parca = re.sub(r"<style[\s\S]*?</style>", " ", parca, flags=re.I)
    parca = re.sub(r"<br\s*/?>", "\n", parca, flags=re.I)
    parca = re.sub(r"</(p|div|li|tr|h\d)>", "\n", parca, flags=re.I)
    parca = re.sub(r"<[^>]+>", " ", parca)
    parca = html_lib.unescape(parca)
    parca = parca.replace("\u200e", "").replace("\u200f", "")
    parca = re.sub(r"[ \t]+", " ", parca)
    parca = re.sub(r"\n\s*", "\n", parca)
    return parca.strip()


def _blok(html, id_):
    m = re.search(rf'id="{re.escape(id_)}"[^>]*>([\s\S]*?)(?=<div id="|\Z)', html or "")
    return m.group(1) if m else ""


def _madde_ciftleri(html):
    """Ürün bilgisi satırları: Yayıncı, baskı uzunluğu, madde işaretleri."""
    cift = []
    for m in re.finditer(
        r'class="a-text-bold">\s*([^<:]{2,80}?)\s*(?:&rlm;|&lrm;|\s)*:',
        html or "",
        re.I,
    ):
        etiket = re.sub(r"\s+", " ", html_lib.unescape(m.group(1))).strip(" :")
        geri = html[m.end(): m.end() + 500]
        deger_m = re.search(r"<span>\s*([^<]{1,200})\s*</span>", geri)
        if not deger_m:
            continue
        deger = re.sub(r"\s+", " ", html_lib.unescape(deger_m.group(1))).strip()
        if etiket and deger and (etiket, deger) not in cift:
            cift.append((etiket, deger))
    return cift


def _maddeler(html):
    """Özellik maddeleri. A+ pazarlama blokları karışmasın diye feature-bullets ile sınırlı."""
    m = re.search(r'id="feature-bullets"[\s\S]{0,12000}', html or "", re.I)
    parca = m.group(0) if m else ""
    out = []
    for li in re.findall(r"<li[^>]*>([\s\S]*?)</li>", parca, re.I):
        metin = _temiz_html(li)
        metin = re.sub(r"\s+", " ", metin).strip(" ·•-")
        if len(metin) < 12 or len(metin) > 400:
            continue
        if metin.lower().startswith("bu ürün") and "amazon" in metin.lower():
            continue
        if metin not in out:
            out.append(metin)
    return out[:12]


def urun_ayrintisi(html):
    """Ürün sayfasından başlık, açıklama, madde ve bilgi satırları.

    Sayfada olmayan alan boş kalır. Uydurma yok.
    """
    baslik = _sayfa_basligi(html)
    aciklama = ""
    for id_ in ("bookDescription_feature_div", "productDescription", "productDescription_feature_div"):
        ham = _temiz_html(_blok(html, id_))
        ham = re.sub(r"\n{3,}", "\n\n", ham)
        if len(ham.split()) > len(aciklama.split()):
            aciklama = ham
    # Kitap açıklaması bazen expander içinde, id bloğu kısa kalabilir.
    if len(aciklama.split()) < 40:
        m = re.search(r'id="bookDescription_feature_div"[^>]*>([\s\S]{0,20000})', html or "", re.I)
        if m:
            aday = _temiz_html(m.group(1))
            if len(aday.split()) > len(aciklama.split()):
                aciklama = aday
    bilgiler = []
    for etiket, deger in _madde_ciftleri(html):
        bilgiler.append({"etiket": etiket, "deger": deger})
    return {
        "baslik": baslik,
        "aciklama": aciklama.strip(),
        "maddeler": _maddeler(html),
        "bilgiler": bilgiler,
    }


def bilgi_degeri(ayrinti, *etiketler):
    """Bilgi satırından ilk uyan değer. Yoksa boş."""
    istenen = {fold(e) for e in etiketler}
    for satir in (ayrinti or {}).get("bilgiler") or []:
        if fold(satir.get("etiket")) in istenen:
            return str(satir.get("deger") or "").strip()
    return ""


def _sayfa_basligi(html):
    m = re.search(r"<title>([^<]+)</title>", html or "", re.I)
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1)).strip()


def arama_adaylari(html, limit=8):
    """Arama sayfasındaki sonuçlar: ASIN ve görünen ad."""
    parcalar = re.split(r'data-component-type="s-search-result"', html or "")
    out = []
    for parca in parcalar[1:]:
        asin_m = re.search(r'data-asin="([A-Z0-9]{10})"', parca)
        h2 = re.search(r"<h2[^>]*>(.*?)</h2>", parca, re.S)
        if not asin_m or not h2:
            continue
        ad = re.sub(r"<[^>]+>", "", h2.group(1))
        ad = html_lib.unescape(re.sub(r"\s+", " ", ad).strip())
        if len(ad) < 18:
            for uzun in re.findall(r'(?:alt|aria-label)="([^"]{18,200})"', parca):
                uzun = html_lib.unescape(re.sub(r"\s+", " ", uzun).strip())
                if "amazon" in uzun.lower():
                    continue
                ad = uzun
                break
        if not ad:
            continue
        out.append({"asin": asin_m.group(1), "ad": ad})
        if len(out) >= limit:
            break
    return out


def urun_basligi(oturum, asin):
    url = f"{HOST}/dp/{asin}"
    html, _final = oturum.getir(url, referer=HOST + "/")
    return _sayfa_basligi(html), dp_url(asin)


def oyun_bul(oturum, ad):
    """Kutu oyunu. Kitap ve video sayfası kabul edilmez."""
    sorgu = f"{ad} kutu oyunu"
    url = HOST + "/s?" + urllib.parse.urlencode({"k": sorgu})
    html, _final = oturum.getir(url, referer=HOST + "/gp/bestsellers/toys")
    for aday in arama_adaylari(html, limit=12):
        if not baslik_uyuyor(aday["ad"], ad, ""):
            continue
        if "kitap" in fold(aday["ad"]) or fold(aday["ad"]).startswith("prime video"):
            continue
        try:
            baslik, dp = urun_basligi(oturum, aday["asin"])
        except AmazonEngel:
            continue
        h = fold(baslik)
        if "amazon.com.tr: kitap" in h or h.startswith("prime video"):
            continue
        if not baslik_uyuyor(baslik, ad, ""):
            continue
        if not any(k in h for k in ("kutu", "oyun", "oyuncak", "board")):
            continue
        return {"asin": aday["asin"], "ad": aday["ad"], "baslik": baslik, "url": dp}
    return None


def tip_uyuyor(baslik, gruplar, kitap_olur=False):
    """Başlık, gruplardan birinin bütün kelimelerini taşıyor mu.

    Birebir marka aranmaz. 'yoga matı' aranıyorsa başlıkta yoga ve mat geçer.
    Kitap ve Prime Video sayfası, konu kitap değilse elenir.
    """
    hedef = fold(baslik)
    if not hedef or hedef.startswith("prime video"):
        return False
    if not kitap_olur and "amazon.com.tr: kitap" in hedef:
        return False
    for grup in gruplar:
        kelimeler = [fold(k) for k in grup if fold(k)]
        if kelimeler and all(k in hedef for k in kelimeler):
            return True
    return False


def ara(oturum, sorgu, limit=8):
    url = HOST + "/s?" + urllib.parse.urlencode({"k": sorgu})
    html, _final = oturum.getir(url, referer=HOST + "/gp/bestsellers")
    return arama_adaylari(html, limit=limit)


def tip_bul(oturum, sorgular, gruplar, limit=4, kitap_olur=False, ekstra_red=()):
    """Sorguları sırayla dener. Başlığı tipe uyan ilk ürünleri doğrular.

    Dönüş: doğrulanmış ürün listesi. Engel, o sorguyu atlar.
    """
    bulunan = []
    gorulen = set()
    red = tuple(fold(x) for x in ekstra_red)
    for sorgu in sorgular:
        try:
            adaylar = ara(oturum, sorgu, limit=12)
        except AmazonEngel:
            continue
        for aday in adaylar:
            if aday["asin"] in gorulen:
                continue
            if not tip_uyuyor(aday["ad"], gruplar, kitap_olur=kitap_olur):
                continue
            if any(k in fold(aday["ad"]) for k in red):
                continue
            try:
                baslik, dp = urun_basligi(oturum, aday["asin"])
            except AmazonEngel:
                continue
            if not tip_uyuyor(baslik, gruplar, kitap_olur=kitap_olur):
                continue
            if any(k in fold(baslik) for k in red):
                continue
            gorulen.add(aday["asin"])
            bulunan.append({
                "asin": aday["asin"],
                "ad": aday["ad"],
                "baslik": baslik,
                "url": dp,
                "sorgu": sorgu,
            })
            if len(bulunan) >= limit:
                return bulunan
    return bulunan


def urun_bul(oturum, ad, marka=""):
    """Arama sonuçlarından adı taşıyan ilk ürünün sayfasını doğrula.

    Dönüş: {asin, ad, baslik, url} veya None. Engel olursa AmazonEngel.
    """
    sorgu = " ".join(x for x in (ad, marka) if x).strip()
    url = HOST + "/s?" + urllib.parse.urlencode({"k": sorgu})
    html, _final = oturum.getir(url, referer=HOST + "/gp/bestsellers")
    for aday in arama_adaylari(html):
        if not baslik_uyuyor(aday["ad"], ad, marka):
            continue
        try:
            baslik, dp = urun_basligi(oturum, aday["asin"])
        except AmazonEngel:
            continue
        if baslik_uyuyor(baslik, ad, marka):
            return {
                "asin": aday["asin"],
                "ad": aday["ad"],
                "baslik": baslik,
                "url": dp,
            }
    return None
