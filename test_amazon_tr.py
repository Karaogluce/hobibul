"""Amazon çok satanlar ayıklayıcı. Ağ yok."""
import unittest

import amazon_tr

_HTML = """
<div data-asin="6052657480" class="x">
  <span class="zg-bdg-text">#1</span>
  <div class="_cDEzb_p13n-sc-css-line-clamp-1_abc">Portakal ve Ekmek Bıçağı</div>
  <div class="_cDEzb_p13n-sc-css-line-clamp-1_abc">Cheong Ye</div>
  <a href="/Portakal/dp/6052657480/ref=zg">kitap</a>
</div>
<div data-asin="6259568126">
  <span class="zg-bdg-text">#2</span>
  <div class="_cDEzb_p13n-sc-css-line-clamp-1_abc">Murdle 1</div>
  <div class="_cDEzb_p13n-sc-css-line-clamp-1_abc">G.T Karber</div>
</div>
<div data-asin="B0FSSJZ7TQ">
  <span class="zg-bdg-text">#1</span>
  <div class="_cDEzb_p13n-sc-css-line-clamp-3_g3dy1">Magly Manyetik Yapı Blokları</div>
</div>
"""


class AyiklaTest(unittest.TestCase):
    def test_ilk_iki_ve_yazar(self):
        # Aynı HTML'de iki ayrı liste karışmasın diye kitap parçası tek başına.
        kitap = _HTML.split('<div data-asin="B0FSSJZ7TQ">')[0]
        rows = amazon_tr.cok_satanlari_ayikla(kitap, limit=2)
        self.assertEqual([r["sira"] for r in rows], [1, 2])
        self.assertEqual(rows[0]["ad"], "Portakal ve Ekmek Bıçağı")
        self.assertEqual(rows[0]["yazar"], "Cheong Ye")
        self.assertEqual(rows[0]["asin"], "6052657480")
        self.assertIn("tag=hobibulsite-21", rows[0]["url"])

    def test_tek_ad(self):
        rows = amazon_tr.cok_satanlari_ayikla(_HTML.split("#2")[0] + _HTML[_HTML.find("B0FSSJZ7TQ") - 20:], limit=1)
        self.assertTrue(rows)
        self.assertIn(rows[0]["asin"], ("6052657480", "B0FSSJZ7TQ"))

    def test_baslik_eslesmesi(self):
        self.assertTrue(amazon_tr.baslik_uyuyor(
            "Portakal ve Ekmek Bıçağı : Cheong Ye: Amazon.com.tr: Kitap",
            "Portakal ve Ekmek Bıçağı", ""))
        self.assertFalse(amazon_tr.baslik_uyuyor(
            "Risk Kutu Oyunu | Strateji", "Sky Team", ""))
        self.assertFalse(amazon_tr.baslik_uyuyor(
            "21 Days to Glory: The Official Team Sky Book: Amazon.com.tr: Kitap",
            "Sky Team", ""))
        self.assertFalse(amazon_tr.baslik_uyuyor(
            "Splendor Solis: The World's Most Famous Alchemical Manuscript: Amazon.com.tr: Kitap",
            "Splendor", ""))

    def test_engel(self):
        self.assertEqual(amazon_tr._engel_mi(503, ""), "http 503")
        self.assertEqual(amazon_tr._engel_mi(200, "validateCaptcha"), "captcha")


if __name__ == "__main__":
    unittest.main()
