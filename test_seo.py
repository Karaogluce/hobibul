"""Meta açıklama sınırları ve site adı ekinin ayıklanması. Ağ yok."""
import unittest

import seo


class FitDescriptionTest(unittest.TestCase):
    def test_sondaki_marka_eki_ayiklanir(self):
        ham = ("En iyi bonsai ekipmanları ile bonsai ağacı bakımı nasıl yapılır? "
               "Hobi meraklıları için doğru alet ve toprak seçimi rehberi. | Hobi Bul")
        out = seo.fit_description(ham)
        self.assertNotIn("Hobi Bul", out)
        self.assertGreaterEqual(len(out), seo.DESC_MIN)
        self.assertLessEqual(len(out), seo.DESC_MAX)

    def test_ortadaki_marka_eki_ayiklanir(self):
        ham = ("Kahve ve barista dünyasına adım atın. Çekirdek seçimi, öğütücü ve demleme "
               "ipuçları bu kısa rehberde. | Hobi Bul. Yeni başlayan için artı ve eksi notu da var.")
        out = seo.fit_description(ham)
        self.assertNotIn("Hobi Bul", out)
        self.assertNotIn("|", out)
        self.assertGreaterEqual(len(out), seo.DESC_MIN)
        self.assertLessEqual(len(out), seo.DESC_MAX)

    def test_aralikta_olan_metne_dokunmaz(self):
        metin = ("Kendi meteoroloji istasyonunu kurmak isteyenler için hava durumu başlangıç "
                 "seti rehberi. İlk alınacak cihazlar ve kurulum önerileri burada.")
        self.assertEqual(seo.fit_description(metin), metin)

    def test_kisa_metin_marka_eklemeden_tamamlanir(self):
        out = seo.fit_description(
            "Lego ve model hobisine yeni başlayanlar için ilk set seçiminde nelere dikkat etmeli?")
        self.assertNotIn("Hobi Bul", out)
        self.assertGreaterEqual(len(out), seo.DESC_MIN)
        self.assertLessEqual(len(out), seo.DESC_MAX)

    def test_yalniz_marka_kalirsa_basa_nokta_koymaz(self):
        out = seo.fit_description(" | Hobi Bul")
        self.assertFalse(out.startswith("."))
        self.assertNotIn("Hobi Bul", out)


if __name__ == "__main__":
    unittest.main()
