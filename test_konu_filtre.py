"""Ham sorgu akıl kontrolü: argo, uzunluk, meta ve ilk kelime."""
import unittest

import konu_kesfet


class AkilKontroluTest(unittest.TestCase):
    K = {"kampçılık"}

    def test_uygun_sorgu_gecer(self):
        self.assertIsNone(konu_kesfet.akil_kontrolu("kampçılık nasıl yapılır", self.K))
        self.assertIsNone(konu_kesfet.akil_kontrolu("evde kampçılık nasıl yapılır", self.K))

    def test_argo_kelime_reddedilir(self):
        self.assertEqual(konu_kesfet.akil_kontrolu("kampçılık nasıl yapılır abi", self.K), "argo")
        self.assertEqual(konu_kesfet.akil_kontrolu("kampçılık nedir ya işte", self.K), "argo")

    def test_kisa_ve_uzun_sorgu_reddedilir(self):
        self.assertEqual(konu_kesfet.akil_kontrolu("kampçılık nedir", self.K), "uzunluk")
        self.assertEqual(
            konu_kesfet.akil_kontrolu("bir iki üç dört beş altı yedi sekiz dokuz", self.K),
            "uzunluk")

    def test_ilgisiz_ilk_kelime_reddedilir(self):
        self.assertEqual(konu_kesfet.akil_kontrolu("afad kampçılık eğitimi", self.K), "ilk-kelime")

    def test_meta_sorgu_reddedilir(self):
        self.assertEqual(
            konu_kesfet.akil_kontrolu("dj seti adı", {"dj", "prodüksiyon"}), "meta")
        self.assertEqual(
            konu_kesfet.akil_kontrolu("lego model ai", {"lego", "model"}), "meta")
        self.assertIsNone(
            konu_kesfet.akil_kontrolu("aile ile kamp nasıl yapılır", {"kamp", "aile"}))


if __name__ == "__main__":
    unittest.main()
