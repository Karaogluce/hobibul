"""Canonical, og:url, sitemap ve iç bağlantılar tek biçimde https + sondaki /.

Cloudflare ayarları bu testin dışında: burada yalnız repo çıktısı denetlenir.
Build geçici bir klasöre yazılır, docs/ ellenmez.
"""
import glob
import json
import os
import re
import shutil
import tempfile
import unittest

import build

HOST = "https://hobibul.com.tr"
SAYFA_DISI = re.compile(r"\.(?:css|js|svg|png|jpe?g|webp|ico|txt|xml|json|pdf)$")


class CiktiUrlTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eski_site = build.SITE
        cls.hedef = tempfile.mkdtemp(prefix="hobibul-url-")
        build.SITE = cls.hedef
        try:
            build.main()
        finally:
            build.SITE = cls.eski_site

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.hedef, ignore_errors=True)

    def _html(self):
        for yol in glob.glob(os.path.join(self.hedef, "**", "*.html"), recursive=True):
            with open(yol, encoding="utf-8") as f:
                yield yol, f.read()

    def test_base_url_https_ve_www_suz(self):
        with open(os.path.join(build.CONTENT, "site.json"), encoding="utf-8") as f:
            site = json.load(f)
        self.assertEqual(site["base_url"].rstrip("/"), HOST)
        self.assertEqual(build.BASE_URL, HOST)

    def test_canonical_mutlak_https_ve_sondaki_slash(self):
        sayi = 0
        for yol, metin in self._html():
            for url in re.findall(r'<link rel="canonical" href="([^"]*)"', metin):
                sayi += 1
                self.assertTrue(url.startswith(HOST + "/"), f"{yol}: {url}")
                self.assertNotIn("http://", url, yol)
                self.assertNotIn("www.", url, yol)
                self.assertTrue(url.endswith("/"), f"sondaki / yok: {yol}: {url}")
        self.assertGreater(sayi, 100)

    def test_og_url_https_ve_www_suz(self):
        sayi = 0
        for yol, metin in self._html():
            for url in re.findall(r'<meta property="og:url" content="([^"]*)"', metin):
                sayi += 1
                self.assertTrue(url.startswith(HOST + "/"), f"{yol}: {url}")
                self.assertNotIn("http://", url, yol)
                self.assertNotIn("www.", url, yol)
        self.assertGreater(sayi, 100)

    def test_sitemap_https_sondaki_slash_ve_yonlendirmesiz(self):
        with open(os.path.join(self.hedef, "sitemap.xml"), encoding="utf-8") as f:
            sitemap = f.read()
        yerler = re.findall(r"<loc>([^<]*)</loc>", sitemap)
        self.assertGreater(len(yerler), 100)
        yollar = set()
        for url in yerler:
            self.assertTrue(url.startswith(HOST + "/"), url)
            self.assertNotIn("http://", url)
            self.assertNotIn("www.", url)
            self.assertTrue(url.endswith("/"), f"sondaki / yok: {url}")
            yollar.add(url[len(HOST):])
        self.assertFalse(yollar & set(build.REDIRECTS), "sitemap yönlendirilen adres içeriyor")

    def test_ic_sayfa_baglantilari_sondaki_slash_tasir(self):
        for yol, metin in self._html():
            for href in re.findall(r'href="([^"]*)"', metin):
                self.assertNotIn("http://", href, f"{yol}: {href}")
                self.assertNotIn("www.hobibul", href, f"{yol}: {href}")
                if not href.startswith("/") or href.startswith("//"):
                    continue
                path = href.split("#")[0].split("?")[0]
                if SAYFA_DISI.search(path) or not path:
                    continue
                self.assertTrue(path.endswith("/"), f"sondaki / yok: {yol}: {href}")

    def test_kaynaklarda_http_ve_www_gecmez(self):
        dosyalar = glob.glob(os.path.join(build.CONTENT, "**", "*.md"), recursive=True)
        dosyalar += glob.glob(os.path.join(build.TEMPLATES, "**", "*.html"), recursive=True)
        for yol in dosyalar:
            with open(yol, encoding="utf-8") as f:
                metin = f.read()
            self.assertNotIn("http://hobibul", metin, yol)
            self.assertNotIn("www.hobibul", metin, yol)


if __name__ == "__main__":
    unittest.main()
