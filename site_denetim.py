#!/usr/bin/env python3
"""Üretilen statik sitede bozuk iç bağlantı ve yerel görsel denetimi.

Ağ isteği yapmaz; dış sitelerin bot koruması build'i etkilemez. İç hedefler,
boş/# bağlantılar, çözülmemiş aff:// adresleri ve yerel dosyalar kesin hata sayılır.
"""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class Baglantilar(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hedefler = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for alan in ("href", "src", "poster"):
            if attrs.get(alan):
                self.hedefler.append((tag, alan, attrs[alan].strip()))


def _hedef_dosya(site, url):
    """Site içi URL'nin diskteki karşılığı; dış/özel şemalarda None."""
    if url.startswith(("https://", "http://", "//", "mailto:", "tel:", "data:", "javascript:")):
        return None
    yol = unquote(urlsplit(url).path)
    if not yol:
        return None
    if not yol.startswith("/"):
        # Şablonlar kök göreli adres kullanır; göreli adresi de güvenli biçimde çöz.
        yol = "/" + yol
    hedef = site / yol.lstrip("/")
    if yol.endswith("/"):
        return hedef / "index.html"
    if hedef.is_dir():
        return hedef / "index.html"
    return hedef


def denetle(site):
    site = Path(site)
    hatalar = []
    sayi = 0
    for html in sorted(site.rglob("*.html")):
        parser = Baglantilar()
        parser.feed(html.read_text(encoding="utf-8"))
        for tag, alan, url in parser.hedefler:
            sayi += 1
            if not url or url == "#" or url.startswith("aff://"):
                hatalar.append(f"{html.relative_to(site)}: geçersiz {alan}={url!r}")
                continue
            if url.startswith("#"):
                continue  # sayfa içi bölüm bağlantısı
            hedef = _hedef_dosya(site, url)
            if hedef is not None and not hedef.is_file():
                hatalar.append(f"{html.relative_to(site)}: bulunamayan {url}")
    if hatalar:
        raise RuntimeError("Site bağlantı denetimi başarısız:\n" + "\n".join(hatalar[:30]))
    return sayi
