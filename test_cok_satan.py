#!/usr/bin/env python3
"""Çok satan yedek metni robotik döküm üretmesin."""
import os
import unittest

os.environ.pop("GEMINI_API_KEY", None)

import cok_satan


class YedekMetinTest(unittest.TestCase):
    def test_kitap_yedek_temiz(self):
        liste = {
            "id": "kitap",
            "ad": "Kitap",
            "ilgili": [],
            "urunler": [{
                "sira": 1,
                "ad": "Örnek Roman",
                "yazar": "Deneme Yazar",
                "asin": "6052657480",
                "url": "https://www.amazon.com.tr/dp/6052657480?tag=hobibulsite-21",
                "ayrinti": {
                    "aciklama": "Kapak metni burada duruyor ve konu için yeterli uzunlukta bir özet taşıyor.",
                    "bilgiler": [
                        {"etiket": "Yayıncı", "deger": "İthaki"},
                        {"etiket": "Baskı Uzunluğu", "deger": "136 sayfa"},
                        {"etiket": "Yayınlanma Tarihi", "deger": "25 Haziran 2026"},
                    ],
                    "maddeler": [],
                },
            }],
        }
        govde = cok_satan.yedek_metin(liste, "9 Kasım 2026") if hasattr(cok_satan, "yedek_metin") else cok_satan.yazi_metni(liste, "2026-W46", "9 Kasım 2026")
        self.assertNotIn("çekim", govde.lower())
        self.assertNotIn("yazar satırı", govde.lower())
        self.assertNotIn("sayfasında yayıncı", govde.lower())
        self.assertIn("### Konusu", govde)
        self.assertIn("### Künye", govde)
        self.assertIn("## Hangisini seçmeli?", govde)
        self.assertIn("## Sıkça Sorulan Sorular", govde)
        self.assertEqual(govde.count("## Karşılaştırma"), 1)
        self.assertIn("6052657480", govde)
        self.assertIn("Liste Amazon.com.tr çok satanlar sıralamasına göre hazırlandı", govde)


if __name__ == "__main__":
    unittest.main()
