"""Konu kuyruğu takviyesi testleri.

Madde kapsamı: kategori eşleşmesinde geçerli ürün yedeği, yıl bazlı
başlık tazelemesi ve gerçek içerikle dry-run (en az 3 konu). Ağ yok,
Gemini yok.
"""
import os
import unittest
from collections import Counter

import otomatik
import yeni_makale as ym

REPO = os.path.dirname(os.path.abspath(__file__))

KATEGORILER = [
    {"id": "outdoor", "name": "Outdoor", "subcategories": [
        {"id": "cadir", "name": "Kamp Çadırı"},
        {"id": "balikcilik", "name": "Balıkçılık"},
    ]},
]


def gecerli_urun(rid):
    """Biçimce geçerli ama doğrulanmamış ürün (dogrulama alanı yok)."""
    return dict(
        id=rid, name=f"Ürün {rid}", desc="Kullanışlı bir ürün.",
        query=f"ürün {rid}", network="amazon_tr", asin="")


def dogrulanmis_urun(rid):
    asin = f"B0{rid.upper():08s}"[:10]
    rec = gecerli_urun(rid)
    rec["asin"] = asin
    rec["dogrulama"] = {
        "durum": "dogrulanmis",
        "tarih": "2026-10-31",
        "kaynak_url": f"https://www.amazon.com.tr/dp/{asin}",
        "yontem": "manuel-test",
    }
    return rec


class KategoriEslestirGevsekTest(unittest.TestCase):
    """Doğrulanmış ürün kalmayan alt kategori, geçerli ürünlerle eşleşir."""

    def test_gecerli_urunlerle_eslesir(self):
        products = {"outdoor": {
            "cadir": [gecerli_urun(f"cadir-{i}") for i in range(3)],
        }}
        sonuc = otomatik.kategori_eslestir(
            "kamp çadırı nasıl seçilir", KATEGORILER, products)
        self.assertIsNotNone(sonuc)
        cat, sub, _ad, _skor, durum = sonuc
        self.assertEqual((cat, sub), ("outdoor", "cadir"))
        self.assertEqual(durum, "gecerli")

    def test_dogrulanmis_oncelikli(self):
        products = {"outdoor": {
            "cadir": [dogrulanmis_urun(f"cd{i}") for i in range(2)]
                     + [gecerli_urun("cg")],
        }}
        sonuc = otomatik.kategori_eslestir(
            "kamp çadırı bakımı", KATEGORILER, products)
        self.assertIsNotNone(sonuc)
        self.assertEqual(sonuc[4], "dogrulanmis")

    def test_urunsuz_alt_kategori_eslesmez(self):
        products = {"outdoor": {"cadir": [gecerli_urun("tek")]}}
        sonuc = otomatik.kategori_eslestir(
            "kamp çadırı nasıl seçilir", KATEGORILER, products)
        self.assertIsNone(sonuc)

    def test_alakasiz_sorgu_none(self):
        products = {"outdoor": {
            "cadir": [dogrulanmis_urun(f"cd{i}") for i in range(3)],
        }}
        sonuc = otomatik.kategori_eslestir(
            "kuantum bilgisayar fiyatları", KATEGORILER, products)
        self.assertIsNone(sonuc)


class BaslikYilKuraliTest(unittest.TestCase):
    """Yıllık tazelenen başlıklar benzer-başlık filtresine takılmaz."""

    def cakisiyor(self, aday, mevcut):
        return otomatik._baslik_cakisiyor(
            otomatik._baslik_kelimeleri(aday),
            [otomatik._baslik_kelimeleri(m) for m in mevcut])

    def test_farkli_yil_cakismaz(self):
        self.assertFalse(self.cakisiyor(
            "Kamp Çadırı Alım Rehberi 2027",
            ["Kamp Çadırı Alım Rehberi 2026"]))

    def test_ayni_yil_cakisir(self):
        self.assertTrue(self.cakisiyor(
            "Kamp Çadırı Alım Rehberi 2026",
            ["Kamp Çadırı Alım Rehberi 2026"]))

    def test_yilsiz_eski_davranis(self):
        self.assertTrue(self.cakisiyor(
            "Kamp Çadırı Alım Rehberi",
            ["Kamp Çadırı Alım Rehberi"]))

    def test_tek_taraf_yilli_cakisir(self):
        self.assertTrue(self.cakisiyor(
            "Kamp Çadırı Alım Rehberi 2027",
            ["Kamp Çadırı Alım Rehberi"]))


class DryRunEntegrasyonTest(unittest.TestCase):
    """Gerçek content ile kuyruk ve çeşitli seçim: en az 3 konu çıkar."""

    def test_kuyruk_ve_secim(self):
        os.chdir(REPO)
        products = ym.load("products.json")
        cats = ym.load("categories.json")
        log = {"done": [], "photos": [], "atlanan": []}
        rapor = {}
        queue = list(otomatik.topic_queue(
            products, cats, log=log, rapor=rapor))
        self.assertGreaterEqual(
            len(queue), 3,
            f"kuyruk boş: rapor={rapor}")
        secim = otomatik.sec_cesitli(
            queue, 3, set(), Counter(), Counter(), set(),
            bugun="2026-11-19", son_alt={})
        self.assertGreaterEqual(len(secim), 3, f"seçim: {secim}")
        for t in secim:
            self.assertTrue(t.get("title"))
            self.assertTrue(t.get("cat"))


if __name__ == "__main__":
    unittest.main()
