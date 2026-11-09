"""Kategori rotasyonu: günde bir ana kategori, son 7 gün cezası, brif kuyruğu."""
import unittest
from collections import Counter
from datetime import datetime, timedelta

import otomatik


def konu(cat, sub, n, sira=0):
    return {"key": f"k:{cat}:{sub}:{n}", "cat": cat, "sub": sub, "title": f"{cat} {sub} {n}"}


class CesitliSecimTest(unittest.TestCase):
    def test_ayni_gun_ayni_ana_kategori_bir_kez(self):
        aday = [konu("muzik", "gitar", 1), konu("muzik", "dj", 2), konu("outdoor", "kamp", 3)]
        sec = otomatik.sec_cesitli(aday, 3, set(), Counter(), {}, set())
        self.assertEqual([t["cat"] for t in sec], ["muzik", "outdoor"])

    def test_son_yedi_gun_cezasi_bos_kategoriyi_one_alir(self):
        aday = [konu("muzik", "gitar", 1), konu("outdoor", "kamp", 2), konu("sanat", "foto", 3)]
        gecmis = Counter({"muzik": 4, "outdoor": 1})
        sec = otomatik.sec_cesitli(aday, 1, set(), gecmis, {}, set())
        self.assertEqual(sec[0]["cat"], "sanat")

    def test_ceza_esitken_bos_alt_kategori_one_gecer(self):
        aday = [konu("outdoor", "kamp", 1), konu("sanat", "foto", 2)]
        sayim = {("outdoor", "kamp"): 3, ("sanat", "foto"): 0}
        sec = otomatik.sec_cesitli(aday, 1, set(), Counter(), sayim, set())
        self.assertEqual(sec[0]["sub"], "foto")

    def test_bugun_dolu_kategori_secilmez(self):
        aday = [konu("muzik", "gitar", 1), konu("outdoor", "kamp", 2)]
        sec = otomatik.sec_cesitli(aday, 2, {"muzik"}, Counter(), {}, set())
        self.assertEqual([t["cat"] for t in sec], ["outdoor"])


class BrifCesitTest(unittest.TestCase):
    def _brifler(self):
        return [
            {"slug": "yilbasi", "oncelik": 1, "kategori": "koleksiyon", "sorgu": "yılbaşı", "h1": "Yılbaşı"},
            {"slug": "erkekler", "oncelik": 2, "kategori": "teknoloji", "sorgu": "erkekler", "h1": "Erkekler"},
            {"slug": "punch", "oncelik": 6, "kategori": "sanat", "sorgu": "punch", "h1": "Punch"},
        ]

    def test_dolu_kategori_brifi_atlamaz_uyani_secer(self):
        sec = otomatik.brif_cesitli(self._brifler(), 2, {"koleksiyon"}, Counter())
        self.assertEqual([b["slug"] for b in sec], ["erkekler", "punch"])

    def test_cezali_oncelikli_brif_taze_kategori_varken_bekler(self):
        sec = otomatik.brif_cesitli(self._brifler(), 1, set(), Counter({"koleksiyon": 2, "teknoloji": 1}))
        self.assertEqual(sec[0]["slug"], "punch")

    def test_hepsi_cezaliysa_oncelik_sirasi_kalir(self):
        gecmis = Counter({"koleksiyon": 1, "teknoloji": 1, "sanat": 1})
        sec = otomatik.brif_cesitli(self._brifler(), 2, set(), gecmis)
        self.assertEqual([b["slug"] for b in sec], ["yilbasi", "erkekler"])

    def test_ertelenen_brif_ertesi_gun_yine_secilebilir(self):
        brifler = self._brifler()
        bugun = otomatik.brif_cesitli(brifler, 1, {"koleksiyon"}, Counter())
        self.assertEqual(bugun[0]["slug"], "erkekler")
        yarin = otomatik.brif_cesitli(brifler, 1, set(), Counter())
        self.assertEqual(yarin[0]["slug"], "yilbasi")


class DenemeTest(unittest.TestCase):
    def test_soguyan_kategori_ucuncu_denemeyi_alir(self):
        self.assertTrue(otomatik.konu_denenebilir("k", {"k": 2}, "outdoor", {}))
        self.assertFalse(otomatik.konu_denenebilir("k", {"k": 2}, "muzik", {"muzik": 3}))
        self.assertFalse(otomatik.konu_denenebilir("k", {"k": 3}, "outdoor", {}))


class GecmisTest(unittest.TestCase):
    def test_pencere_disindaki_gun_sayilmaz(self):
        bugun = "2026-11-10"
        eski = (datetime.strptime(bugun, "%Y-%m-%d").date() - timedelta(days=8)).isoformat()
        log = {"makaleler": [
            {"anahtar": "rehber:muzik:gitar", "tarih": bugun, "slug": "a"},
            {"anahtar": "rehber:outdoor:kamp", "tarih": eski, "slug": "b"},
        ], "done": [], "talep": []}
        sayac = otomatik.kategori_sayaclari(log, bugun, gun=7, harita={})
        self.assertEqual(sayac["muzik"], 1)
        self.assertNotIn("outdoor", sayac)


if __name__ == "__main__":
    unittest.main()
