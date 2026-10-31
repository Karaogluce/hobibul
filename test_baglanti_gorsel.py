"""İç bağlantı ve makale görseli güvenlik testleri; ağ isteği yok."""
import tempfile
import unittest
from pathlib import Path

import build
import otomatik
import site_denetim
import urun_denetim


class SiteDenetimTest(unittest.TestCase):
    def test_gecerli_ic_baglanti_ve_gorsel(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "makale/ornek").mkdir(parents=True)
            (root / "makale/ornek/index.html").write_text("ok", encoding="utf-8")
            (root / "img").mkdir()
            (root / "img/ornek.webp").write_bytes(b"webp")
            (root / "index.html").write_text(
                '<a href="/makale/ornek/">makale</a><img src="/img/ornek.webp">', encoding="utf-8")
            self.assertEqual(site_denetim.denetle(root), 2)

    def test_eksik_hedef_ve_aff_build_hatasi(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "index.html").write_text(
                '<a href="/makale/yok/">yok</a><a href="aff://yok">ürün</a>', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Site bağlantı denetimi"):
                site_denetim.denetle(root)

    def test_bilinmeyen_aff_sessizce_duz_metin_olmaz(self):
        with self.assertRaises(urun_denetim.UrunVerisiHatasi):
            build.resolve_aff("kesinlikle-olmayan-urun")

    def test_yerel_gorsel_og_icin_mutlak_url_olur(self):
        self.assertEqual(
            build.public_image("/img/makale/lego.webp"),
            build.BASE_URL + "/img/makale/lego.webp")


class GorselSecimTest(unittest.TestCase):
    def test_konu_disinda_kalan_sonuc_elenir(self):
        photo = {"alt_description": "A bird eating from a feeder on a pole"}
        self.assertEqual(otomatik.gorsel_puani(photo, "weather station wind sensor"), 0)
        photo["alt_description"] = "Weather station sensors in a backyard"
        self.assertGreater(otomatik.gorsel_puani(photo, "weather station wind sensor"), 0)

    def test_butun_makalelerin_acik_ve_yerel_gorseli_var(self):
        for article in build.articles:
            with self.subTest(makale=article["slug"]):
                self.assertTrue(article["image"].startswith("/img/makale/"))
                self.assertTrue(article["image_alt"])
                self.assertTrue((build.STATIC + article["image"]).endswith(".webp"))
                self.assertTrue(Path(build.STATIC + article["image"]).is_file())


if __name__ == "__main__":
    unittest.main()
