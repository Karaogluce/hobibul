"""İç link raporu, yetim güçlendirme ve geri link. Ağ isteği yok."""
import json
import os
import tempfile
import unittest
from pathlib import Path

import ic_link


def _md(slug, title, cat, sub, body, focus=""):
    return (
        "---\n"
        f'title: "{title}"\n'
        f'slug: "{slug}"\n'
        f'category: "{cat}"\n'
        f'subcategory: "{sub}"\n'
        'date: "2026-10-01"\n'
        'updated: "2026-10-01"\n'
        f'focus_keyword: "{focus or title}"\n'
        "draft: \"false\"\n"
        "---\n\n"
        + body.strip()
        + "\n"
    )


_CATS = [
    {
        "id": "muzik",
        "name": "Müzik",
        "slug": "muzik",
        "subcategories": [
            {"id": "gitar", "name": "Gitar", "slug": "gitar"},
            {"id": "dj-produksiyon", "name": "DJ & Prodüksiyon", "slug": "dj-produksiyon"},
        ],
    },
    {
        "id": "bilim-astronomi",
        "name": "Bilim",
        "slug": "bilim-astronomi",
        "subcategories": [
            {"id": "kimya-deney", "name": "Kimya", "slug": "kimya-deney"},
        ],
    },
]


_UZUN = (
    "İlk hafta tek bir düzen seçip onu tekrar etmek, aynı akşam üç ayrı aleti birden açmaktan daha az yorar. "
    "Parmağın tellere alışması için her gün kısa bir oturuş yeter."
)


class KokTest(unittest.TestCase):
    def test_yanlis_kok_eslesmez(self):
        self.assertFalse(ic_link.ayni_kok("deri", "derin"))
        self.assertFalse(ic_link.ayni_kok("oyun", "oyuncak"))
        self.assertFalse(ic_link.ayni_kok("deney", "deneyeceksen"))
        self.assertFalse(ic_link.ayni_kok("hava", "havalandirmasi"))
        self.assertFalse(ic_link.ayni_kok("kimya", "kimyasal"))
        self.assertFalse(ic_link.ayni_kok("deney", "deneyimli"))
        self.assertFalse(ic_link.ayni_kok("orgu", "orgusune"))
        self.assertTrue(ic_link.ayni_kok("gitar", "gitara"))
        self.assertTrue(ic_link.ayni_kok("klavye", "klavyeyi"))


class GscHedefTest(unittest.TestCase):
    def test_dosya_yoksa_ve_ok_degilse_bos(self):
        makale = [{"title": "Kamp çadırı", "focus": "çadır", "slug": "cadir", "yol": "/makale/cadir/"}]
        self.assertEqual(ic_link.gsc_hedef_yollar(None, makale), [])
        self.assertEqual(ic_link.gsc_hedef_yollar({"ok": False, "queries": [
            {"query": "kamp çadırı", "position": 12},
        ]}, makale), [])

    def test_pozisyon_8_20_sorgusu_sayfaya_baglanir(self):
        makaleler = [
            {"title": "Kamp Çadırı Seçimi", "focus": "kamp çadırı", "slug": "kamp-cadiri", "yol": "/makale/kamp-cadiri/"},
            {"title": "Yoga Matı", "focus": "yoga matı", "slug": "yoga", "yol": "/makale/yoga/"},
        ]
        data = {"ok": True, "queries": [
            {"query": "kamp çadırı", "position": 12.4},
            {"query": "yoga matı", "position": 3},
            {"query": "trekking bot", "position": 21},
            {"query": "filtre kahve", "position": 9, "page": "https://hobibul.com.tr/makale/kahve/"},
        ], "pages": [
            {"page": "/makale/drone-secimi/", "position": 15},
        ]}
        yollar = ic_link.gsc_hedef_yollar(data, makaleler)
        self.assertIn("/makale/kamp-cadiri/", yollar)
        self.assertIn("/makale/kahve/", yollar)
        self.assertIn("/makale/drone-secimi/", yollar)
        self.assertNotIn("/makale/yoga/", yollar)


class GuclendirTest(unittest.TestCase):
    def _kur(self, d, yazilar):
        root = Path(d)
        (root / "articles").mkdir()
        (root / "categories.json").write_text(json.dumps(_CATS), encoding="utf-8")
        for slug, title, cat, sub, body in yazilar:
            (root / "articles" / f"{slug}.md").write_text(
                _md(slug, title, cat, sub, body), encoding="utf-8")
        return root

    def test_ayni_alt_kategori_linklenir_alakasiz_linklenmez(self):
        with tempfile.TemporaryDirectory() as d:
            root = self._kur(d, [
                ("gitar-a", "Akustik Gitar Tutuş Düzeni", "muzik", "gitar",
                 _UZUN + "\n\n## Sık Sorulan Sorular\n\nTutuş nedir?\nParmak perdenin arkasına basar.\n"),
                ("gitar-b", "Elektro Gitar Amfi Düzeni", "muzik", "gitar",
                 _UZUN + " Akor çalışması her gün kısa sürer.\n\n## Sık Sorulan Sorular\n\nAmfi şart mı?\nİlk hafta hayır.\n"),
                ("gitar-c", "Gitar Teli Kalınlığı", "muzik", "gitar",
                 _UZUN + " Tel kalınlığı sesi değiştirir.\n\n## Sık Sorulan Sorular\n\nHangi tel?\nİnce tel ilk hafta daha az acıtır.\n"),
                ("kimya", "Kimya Deney Seti", "bilim-astronomi", "kimya-deney",
                 _UZUN + " Deney kabı ayrı durur.\n\n## Sık Sorulan Sorular\n\nEvde olur mu?\nEvet, havalı odada.\n"),
            ])
            sonuc = ic_link.guclendir(
                str(root / "articles"), bugun="2026-11-09", gsc={"ok": False}, uygula=True)
            self.assertGreater(sonuc["eklenen_sayisi"], 0)
            self.assertLess(sonuc["sonra"]["yetim_makale"], sonuc["once"]["yetim_makale"])
            kimya = (root / "articles" / "kimya.md").read_text(encoding="utf-8")
            self.assertNotIn("/makale/gitar-", kimya)
            for e in sonuc["eklenen"]:
                self.assertFalse(ic_link.yasak_var(e["cumle"]))
            anchorlar = [e["anchor"].casefold() for e in sonuc["eklenen"]]
            self.assertEqual(len(anchorlar), len(set(anchorlar)))
            # İkinci geçiş yeni cümle eklemez.
            tekrar = ic_link.guclendir(
                str(root / "articles"), bugun="2026-11-09", gsc={"ok": False}, uygula=True)
            self.assertEqual(tekrar["eklenen_sayisi"], 0)

    def test_sayfa_basina_en_fazla_bes_yeni_link(self):
        with tempfile.TemporaryDirectory() as d:
            yazilar = [(
                "kaynak", "Gitar Ekipmanı Rehberi", "muzik", "gitar",
                _UZUN + "\n\n## Sık Sorulan Sorular\n\nNe alınır?\nTel ve pena.\n",
            )]
            for i in range(6):
                yazilar.append((
                    f"hedef-{i}", f"Gitar Parçası {i} Seçimi", "muzik", "gitar",
                    _UZUN + "\n\n## Sık Sorulan Sorular\n\nHangisi?\nİnce olan.\n",
                ))
            root = self._kur(d, yazilar)
            sonuc = ic_link.guclendir(
                str(root / "articles"), bugun="2026-11-09", gsc={"ok": False}, uygula=True)
            kaynaktan = [e for e in sonuc["eklenen"] if e["kaynak"] == "/makale/kaynak/"]
            self.assertLessEqual(len(kaynaktan), ic_link.MAX_YENI)
            self.assertGreater(len(kaynaktan), 0)

    def test_geri_link_iki_uc_eski_makale(self):
        with tempfile.TemporaryDirectory() as d:
            root = self._kur(d, [
                ("gitar-a", "Gitar Nasıl Çalınır Akor", "muzik", "gitar", _UZUN + "\n\n## Sık Sorulan Sorular\n\nNe?\nTutuş.\n"),
                ("gitar-b", "Elektro Gitar Amfi Seti", "muzik", "gitar", _UZUN + "\n\n## Sık Sorulan Sorular\n\nNe?\nAmfi.\n"),
                ("gitar-c", "Gitar Teli Kalınlığı", "muzik", "gitar", _UZUN + "\n\n## Sık Sorulan Sorular\n\nNe?\nTel.\n"),
                ("yeni", "Gitar Penası Tutuş Düzeni", "muzik", "gitar", _UZUN + "\n\n## Sık Sorulan Sorular\n\nNe?\nPena.\n"),
                ("kimya", "Kimya Deney Seti", "bilim-astronomi", "kimya-deney", _UZUN + "\n"),
            ])
            n = ic_link.yeni_makaleye_geri_link(
                "yeni", str(root / "articles"), bugun="2026-11-09")
            self.assertGreaterEqual(n, 2)
            self.assertLessEqual(n, 3)
            kimya = (root / "articles" / "kimya.md").read_text(encoding="utf-8")
            self.assertNotIn("/makale/yeni/", kimya)
            alan = 0
            for slug in ("gitar-a", "gitar-b", "gitar-c"):
                text = (root / "articles" / f"{slug}.md").read_text(encoding="utf-8")
                if "/makale/yeni/" in text:
                    alan += 1
                    self.assertIn('updated: "2026-11-09"', text)
            self.assertEqual(alan, n)
            # Taslak slug diskte yoksa 0.
            self.assertEqual(ic_link.yeni_makaleye_geri_link(
                "yok", str(root / "articles"), bugun="2026-11-09"), 0)


class ErisimTest(unittest.TestCase):
    def test_footer_icerik_sayilmaz(self):
        html = (
            '<header class="site-header"><a href="/kategori/muzik/">Müzik</a></header>'
            '<nav class="breadcrumb"><a href="/">Ana</a></nav>'
            '<main><a href="/makale/gitar-a/">gitar</a></main>'
            '<footer class="site-footer"><a href="/hakkimizda/">Hakkımızda</a></footer>'
        )
        parser = ic_link._BaglantiAyikla()
        parser.feed(html)
        icerik = [ic_link.norm_yol(h) for h, ic in parser.links if ic]
        tum = [ic_link.norm_yol(h) for h, _ic in parser.links]
        self.assertEqual(icerik, ["/makale/gitar-a/"])
        self.assertIn("/hakkimizda/", tum)

    def test_linksiz_ve_uzak_sayfa_buildi_dusurur(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "content").mkdir()
            (root / "content" / "articles").mkdir()
            (root / "content" / "categories.json").write_text("[]", encoding="utf-8")
            (root / "content" / "site.json").write_text(
                '{"base_url": "https://hobibul.com.tr"}', encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs" / "index.html").write_text('<a href="/rehberler/">rehber</a>', encoding="utf-8")
            (root / "docs" / "rehberler").mkdir()
            (root / "docs" / "rehberler" / "index.html").write_text('<a href="/">ana</a>', encoding="utf-8")
            (root / "docs" / "makale").mkdir()
            (root / "docs" / "makale" / "yalniz").mkdir()
            (root / "docs" / "makale" / "yalniz" / "index.html").write_text("<p>tek</p>", encoding="utf-8")
            (root / "docs" / "eski").mkdir()
            (root / "docs" / "eski" / "index.html").write_text(
                '<meta http-equiv="refresh" content="0;url=/">', encoding="utf-8")
            (root / "docs" / "sitemap.xml").write_text(
                "<?xml version='1.0'?><urlset>"
                "<loc>https://hobibul.com.tr/</loc>"
                "<loc>https://hobibul.com.tr/rehberler/</loc>"
                "<loc>https://hobibul.com.tr/makale/yalniz/</loc>"
                "<loc>https://hobibul.com.tr/eski/</loc>"
                "</urlset>", encoding="utf-8")
            rapor = ic_link.raporu_yaz(
                str(root / "docs"), str(root / "content"), yonlendirmeler={"/eski/"})
            self.assertIn("/makale/yalniz/", rapor["ozet"]["sitemap_linksiz"])
            self.assertNotIn("/eski/", rapor["ozet"]["sitemap_linksiz"])
            with self.assertRaises(RuntimeError):
                ic_link.erisim_denetle(rapor)


if __name__ == "__main__":
    unittest.main()
