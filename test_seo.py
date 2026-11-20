"""Meta açıklama sınırları ve site adı ekinin ayıklanması. Ağ yok."""
import unittest

import seo


class FitTitleTest(unittest.TestCase):
    def test_uzun_baslik_baglacla_bitmez(self):
        out = seo.fit_title(
            "Teknoloji Ekipmanı Alırken Yapılan 7 Hata ve Nasıl Kaçınılır | Hobi Bul")
        self.assertLessEqual(len(out), seo.TITLE_MAX)
        self.assertFalse(out.rstrip(".").endswith(" ve"), out)
        self.assertFalse(out.endswith("Nasıl"), out)

    def test_yarim_ifade_ve_marka_eklenmez(self):
        out = seo.fit_title(
            "Mikroskopta Preparat Hazırlarken Hava Kabarcığından Kaçınma")
        self.assertLessEqual(len(out), seo.TITLE_MAX)
        self.assertFalse(out.endswith("Hava"), out)

    def test_sigan_baslik_aynen_kalir(self):
        metin = "Kısa ve Tam Başlık | Hobi Bul"
        self.assertEqual(seo.fit_title(metin), metin)

    def test_noktalama_sinirinda_keser(self):
        out = seo.fit_title(
            "En İyi Kamp Çadırı Seçimi 2026: 2 ve 4 Kişilik Karşılaştırma | Hobi Bul")
        self.assertLessEqual(len(out), seo.TITLE_MAX)
        self.assertTrue(out.startswith("En İyi Kamp Çadırı Seçimi 2026"), out)


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
