"""Konu kuyruğu: elle eklenen bilgi konuları, kategori eşleme ve uyarılar.

Ağ yok; Gemini çağrılmaz. Seçim fonksiyonları doğrudan denenir.
"""
import unittest

import otomatik


def _kelimeler(text):
    return otomatik._baslik_kelimeleri(text)


class BilgiTipiTest(unittest.TestCase):
    def test_bilgi_tipi_urun_istemez(self):
        self.assertEqual(otomatik._gerekli_urun("bilgi"), 0)
        self.assertEqual(otomatik.TIPLER["bilgi"]["hedef"], 1000)
        self.assertEqual(otomatik._yayin_tabani("bilgi"), otomatik.DUZENLI_TABAN)

    def test_bilgi_tipi_linksiz_gecer_urun_linki_reddedilir(self):
        self.assertIsNone(otomatik._link_hatasi("düz metin", "bilgi", []))
        self.assertEqual(
            otomatik._link_hatasi("[Satın Al](aff://a)", "bilgi", []),
            "bilgi yazısında ürün linki olmaz")
        self.assertEqual(
            otomatik._link_hatasi("düz metin", "sss", [{"id": "a"}, {"id": "b"}]),
            "en az 2 ürün linki yok")

    def test_bilgi_promptu_urun_ve_aff_istemez(self):
        t = dict(
            title="Robotik Kodlamaya Başlarken İlk Proje Fikirleri", tip="bilgi",
            cat="teknoloji", cat_name="Teknoloji", sub="robotik",
            sub_name="Robotik & Kodlama")
        metin = otomatik.build_prompt(t, [], ["robotik kodlama ilk proje"], "rehber")
        self.assertIn("ÜRÜN KURALI", metin)
        self.assertIn("Ürün, marka veya model adı yazma", metin)
        self.assertNotIn("[Satın Al:", metin)
        self.assertIn("[Robotik & Kodlama](/kategori/teknoloji/robotik/)", metin)

    def test_bilgi_duzenleme_promptu_urun_eklemez(self):
        metin = otomatik.edit_prompt("## Başlık\n\nMetin.", [], "rehber", 1000)
        self.assertIn("Bu yazıda ürün, marka, model ve fiyat geçmemeli", metin)
        self.assertIn("aff:// linki ekleme", metin)


class HavuzTest(unittest.TestCase):
    def test_en_az_altmis_bilgi_konusu_ve_kategori_dagilimi(self):
        bilgi = [e for e in otomatik.load_pool()
                 if e.get("tip_onerisi") == "bilgi" and otomatik._havuz_uygun(e)]
        self.assertGreaterEqual(len(bilgi), 60)
        kategoriler = {e.get("kategori") for e in bilgi}
        self.assertEqual(len(kategoriler), 14)
        for e in bilgi:
            self.assertTrue(str(e.get("h1") or "").strip(), e.get("sorgu"))
            self.assertIsNone(otomatik.baslik_bozuk(e["h1"]), e["h1"])

    def test_kuyruk_en_az_uc_bilgi_konusu_verir(self):
        products = otomatik.ym.load("products.json")
        cats = otomatik.ym.load("categories.json")
        kuyruk = otomatik.topic_queue(products, cats)
        bilgi = [t for t in kuyruk if t.get("tip") == "bilgi"]
        self.assertGreaterEqual(len(bilgi), 60)
        secim = otomatik.sec_cesitli(
            kuyruk, 3, set(), {}, {}, set(), bugun="2026-11-19", son_alt={})
        self.assertEqual(len(secim), 3)
        self.assertEqual(len({t["cat"] for t in secim}), 3)

    def test_benzer_baslik_gercek_kopyayi_eler_farkli_konuyu_birakir(self):
        mevcut = [_kelimeler("Kamp Ekipmanı Alırken Yapılan 7 Hata ve Nasıl Kaçınılır")]
        ayni = _kelimeler("Kamp Ekipmanı Alırken Yapılan 7 Hata ve Nasıl Kaçınılır")
        farkli = _kelimeler("Kamp Ateşi Güvenli Yakma İçin Hatalar")
        self.assertTrue(otomatik._baslik_cakisiyor(ayni, mevcut, "Kampçılık"))
        self.assertFalse(otomatik._baslik_cakisiyor(farkli, mevcut, "Kampçılık"))

        serbest = [_kelimeler("Kamp Ateşi Nasıl Yakılır?")]
        self.assertTrue(otomatik._baslik_cakisiyor(
            _kelimeler("Kamp Ateşi Nasıl Yakılır?"), serbest, "Kampçılık"))
        self.assertFalse(otomatik._baslik_cakisiyor(
            _kelimeler("Kamp Ocağında Güvenli Yemek"), serbest, "Kampçılık"))


class KategoriEslemeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cats = otomatik.ym.load("categories.json")

    def test_robotik_sorgusu_hobi_elektronigine_gider(self):
        eslesen = otomatik.kategori_eslestir("robotik kodlama robotu", self.cats, None)
        self.assertEqual(eslesen[:2], ("teknoloji", "robotik"))

    def test_evde_spor_sorgusu_evde_fitness(self):
        eslesen = otomatik.kategori_eslestir("evde spor için gerekli malzemeler", self.cats, None)
        self.assertEqual(eslesen[:2], ("spor-fitness", "evde-fitness"))

    def test_cadir_sorgusu_outdoor_kampcilik(self):
        eslesen = otomatik.kategori_eslestir("en iyi çadır markaları", self.cats, None)
        self.assertEqual(eslesen[:2], ("outdoor", "kampcilik"))

    def test_ticari_sorgu_urunsuz_bilgiye_cevrilmez(self):
        self.assertTrue(otomatik._ticari_talep("en iyi çadır markaları"))
        self.assertTrue(otomatik._ticari_talep(
            "hobi dünyasında en iyi koleksiyon ürünlerini nereden bulabilirim"))
        self.assertFalse(otomatik._ticari_talep("robotik kodlama robotu"))
        self.assertFalse(otomatik._ticari_talep("evde spor için gerekli malzemeler"))


class KuyrukUyariTest(unittest.TestCase):
    def test_esik_altinda_uyari_yok_ustunde_var(self):
        self.assertEqual(otomatik.kuyruk_uyarilari(20), [])
        self.assertTrue(otomatik.kuyruk_uyarilari(10)[0].startswith("::warning::"))
        self.assertIn("azaldı", otomatik.kuyruk_uyarilari(10)[0])

    def test_bos_kuyruk_ayri_uyari(self):
        self.assertIn("boş", otomatik.kuyruk_uyarilari(0)[0])


if __name__ == "__main__":
    unittest.main()
