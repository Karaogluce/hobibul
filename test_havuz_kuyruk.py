"""Havuz sınıflandırması ve alt kategori bazlı adil kuyruk. Ağ yok, dry-run."""
import copy
import os
import tempfile
import unittest
from unittest import mock

import havuz_siniflandir as hs
import otomatik

KATEGORILER = [
    {"id": "outdoor", "name": "Outdoor", "subcategories": [
        {"id": "cadir", "name": "Kamp Çadırı"},
        {"id": "matara", "name": "Matara"},
    ]},
    {"id": "muzik", "name": "Müzik", "subcategories": [
        {"id": "gitar", "name": "Gitar"},
    ]},
]


def urun(rid):
    return dict(id=rid, name=f"Ürün {rid}", desc="Kullanışlı bir ürün.",
                query=f"ürün {rid}", network="amazon_tr")


def urunler(**adetler):
    """outdoor__cadir=3 → o alt kategoriye üç doğrulanmış ürün koy."""
    out = {}
    for anahtar, n in adetler.items():
        cat, sub = anahtar.split("__")
        out.setdefault(cat, {})[sub] = [urun(f"{cat}-{sub}-{i}") for i in range(n)]
    return out


def havuz_kaydi(sorgu, cat, sub, tip=None):
    return {"sorgu": sorgu, "kategori": cat, "alt": sub, "tip_onerisi": tip}


class _GeciciMakaleler(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)

    @property
    def articles(self):
        return self._dir.name


class HavuzSiniflandirmaTest(_GeciciMakaleler):
    def siniflandir(self, pool, products, log=None):
        return hs.siniflandir(pool, KATEGORILER, products,
                              articles_dir=self.articles, log=log or {})

    def test_tip_onerisi_none_kayit_siniflandirilir(self):
        pool = [havuz_kaydi("kamp çadırı nasıl seçilir", "outdoor", "cadir")]
        rapor = self.siniflandir(pool, urunler(outdoor__cadir=3))
        kayit = pool[0]
        self.assertEqual(rapor["durum"]["uygun"], 1)
        self.assertEqual(kayit["tip_onerisi"], "ticari")
        self.assertEqual(kayit["siniflandirma"]["durum"], "uygun")
        self.assertEqual(kayit["siniflandirma"]["tip"], "ticari")
        self.assertIsNone(kayit["siniflandirma"]["ham_tip_onerisi"])
        self.assertEqual(kayit["siniflandirma"]["urun"], 3)
        self.assertEqual(kayit["sorgu"], "kamp çadırı nasıl seçilir")

    def test_urun_esigi_altinda_incelemeye_alinir(self):
        pool = [havuz_kaydi("matara bakım rehberi", "outdoor", "matara")]
        rapor = self.siniflandir(pool, urunler(outdoor__matara=2))
        sinif = pool[0]["siniflandirma"]
        self.assertEqual(sinif["durum"], "incelenecek")
        self.assertIn("ürün eşiği (2/3)", sinif["neden"])
        self.assertIsNone(pool[0]["tip_onerisi"])
        self.assertEqual(rapor["incelenecek"]["ürün eşiği (2/3)"], 1)

    def test_uc_urun_varsa_ayni_rehber_uygun_olur(self):
        pool = [havuz_kaydi("matara bakım rehberi", "outdoor", "matara")]
        self.siniflandir(pool, urunler(outdoor__matara=3))
        self.assertEqual(pool[0]["siniflandirma"]["durum"], "uygun")
        self.assertEqual(pool[0]["tip_onerisi"], "rehber")

    def test_yakin_niyet_ikinci_kayit_yinelenen_olur(self):
        pool = [
            havuz_kaydi("kamp çadırı nasıl seçilir", "outdoor", "cadir"),
            havuz_kaydi("kamp çadırı nasıl seçilir acaba", "outdoor", "cadir"),
        ]
        rapor = self.siniflandir(pool, urunler(outdoor__cadir=3))
        self.assertEqual(pool[0]["siniflandirma"]["durum"], "uygun")
        ikinci = pool[1]["siniflandirma"]
        self.assertEqual(ikinci["durum"], "yinelenen")
        self.assertEqual(ikinci["neden"], "yakın niyet")
        self.assertIsNone(pool[1]["tip_onerisi"])
        self.assertEqual(rapor["yinelenen"]["yakın niyet"], 1)

    def test_tamamlanmis_konu_yinelenen_olarak_isaretlenir(self):
        pool = [havuz_kaydi("kamp çadırı nasıl seçilir", "outdoor", "cadir")]
        log = {"done": [{"anahtar": "ticari:outdoor:cadir:kamp-cadiri-nasil-secilir",
                         "tarih": "2026-10-01"}]}
        self.siniflandir(pool, urunler(outdoor__cadir=3), log=log)
        sinif = pool[0]["siniflandirma"]
        self.assertEqual(sinif["durum"], "yinelenen")
        self.assertEqual(sinif["neden"], "mevcut kuyruk")
        self.assertEqual(sinif["eslesen"], "tamamlanmış kayıt")

    def test_ayni_havuzda_ikinci_calisma_ayni_sonucu_verir(self):
        pool = [
            havuz_kaydi("kamp çadırı nasıl seçilir", "outdoor", "cadir"),
            havuz_kaydi("matara bakım rehberi", "outdoor", "matara"),
            havuz_kaydi("gitar teli nasıl değiştirilir", "muzik", "gitar"),
            havuz_kaydi("çadır fiyatları", "outdoor", "cadir"),
            havuz_kaydi("gitar akort rehberi", "muzik", "gitar", tip="rehber"),
        ]
        products = urunler(outdoor__cadir=3, outdoor__matara=2, muzik__gitar=3)
        ilk = self.siniflandir(copy.deepcopy(pool), products)
        ikinci = self.siniflandir(pool, products)
        self.assertEqual(ilk, ikinci)
        self.assertEqual(ilk["dokunulmayan"], 1)
        # Kendi atadığımız tip ikinci turda ham değere döner, kaybolmaz.
        self.assertIsNone(pool[0]["siniflandirma"]["ham_tip_onerisi"])
        self.assertEqual(pool[4]["tip_onerisi"], "rehber")
        self.assertNotIn("siniflandirma", pool[4])

    def test_elenen_ve_inceleme_bekleyen_sinif_verisi_bozulmaz(self):
        pool = [
            havuz_kaydi("çadır fiyatları ucuz", "outdoor", "cadir"),
            havuz_kaydi("çadır kumaş türleri", "outdoor", "cadir"),
        ]
        self.siniflandir(pool, urunler(outdoor__cadir=3))
        self.assertEqual(pool[0]["siniflandirma"]["durum"], "elendi")
        self.assertEqual(pool[1]["siniflandirma"]["durum"], "incelenecek")
        self.assertEqual(pool[1]["siniflandirma"]["neden"], "tip sinyali yok")


class AdilSiraTest(unittest.TestCase):
    def test_round_robin_ve_ardisik_kategori_yok(self):
        gruplar = [
            {"cat": "a", "sub": "a1", "konular": [{"c": "a", "n": 1}, {"c": "a", "n": 2}]},
            {"cat": "a", "sub": "a2", "konular": [{"c": "a", "n": 3}]},
            {"cat": "b", "sub": "b1", "konular": [{"c": "b", "n": 4}, {"c": "b", "n": 5}]},
        ]
        sira = otomatik._adil_sira(copy.deepcopy(gruplar),
                                   {("a", "a1"): 1, ("a", "a2"): 1, ("b", "b1"): 1}, {})
        self.assertEqual(sorted(x["n"] for x in sira), [1, 2, 3, 4, 5])
        cats = [x["c"] for x in sira]
        self.assertTrue(all(a != b for a, b in zip(cats, cats[1:])), cats)
        self.assertIn(cats[1], ("b",))

    def test_makalesiz_gruba_oncelik_ve_main_sonda(self):
        anahtar = lambda cat, sub: otomatik._grup_anahtari(
            {"cat": cat, "sub": sub},
            {("a", "dolu"): 2, ("a", "bos"): 0, ("a", "_main"): 4}, {})
        self.assertEqual(anahtar("a", "bos")[0], 0)
        self.assertEqual(anahtar("a", "dolu")[0], 1)
        self.assertEqual(anahtar("a", "_main")[0], 2)
        self.assertLess(anahtar("a", "bos"), anahtar("a", "dolu"))

    def test_en_eski_uretim_once(self):
        log = {"done": [
            {"anahtar": "rehber:outdoor:cadir:yeni", "tarih": "2026-10-10"},
            {"anahtar": "rehber:outdoor:cadir:eski", "tarih": "2026-10-01"},
            {"anahtar": "rehber:muzik:gitar:orta", "tarih": "2026-10-05"},
        ]}
        son = otomatik._son_uretim_gunu(log)
        # Grup başına en son üretim tarihi tutulur; en eski tarihli grup öne geçer.
        self.assertEqual(son[("outdoor", "cadir")], "2026-10-10")
        self.assertEqual(son[("muzik", "gitar")], "2026-10-05")
        makale = {("outdoor", "cadir"): 2, ("muzik", "gitar"): 2}
        sira = sorted(
            [{"cat": "muzik", "sub": "gitar"}, {"cat": "outdoor", "sub": "cadir"}],
            key=lambda g: otomatik._grup_anahtari(g, makale, son))
        self.assertEqual([(g["cat"], g["sub"]) for g in sira],
                         [("muzik", "gitar"), ("outdoor", "cadir")])


class KuyrukTest(_GeciciMakaleler):
    def kuyruk(self, products, pool=None, log=None):
        with mock.patch.object(otomatik, "load_pool", return_value=copy.deepcopy(pool or [])):
            return otomatik.topic_queue(products, KATEGORILER, log=log or {},
                                        articles_dir=self.articles)

    def test_konusuz_alt_kategori_kuyruga_girmez(self):
        sira = self.kuyruk(urunler(outdoor__cadir=3))
        self.assertTrue(sira)
        self.assertEqual({k["sub"] for k in sira}, {"cadir"})

    def test_urunu_olmayan_kategoriden_konu_gelmez(self):
        sira = self.kuyruk(urunler(outdoor__cadir=3))
        self.assertNotIn("muzik", {k["cat"] for k in sira})

    def test_siniflandirmayla_elenen_kayit_kuyruga_girmez(self):
        pool = [
            dict(havuz_kaydi("kamp çadırı fiyatları", "outdoor", "cadir", tip="ticari"),
                 siniflandirma={"durum": "elendi", "tip": "ticari",
                                "neden": "fiyat/indirim niyeti", "ham_tip_onerisi": None}),
            dict(havuz_kaydi("matara bakım rehberi", "outdoor", "matara", tip="rehber"),
                 siniflandirma={"durum": "incelenecek", "tip": "rehber",
                                "neden": "başka bağlam (inceleme)", "ham_tip_onerisi": None}),
        ]
        sira = self.kuyruk(urunler(outdoor__cadir=3, outdoor__matara=3), pool=pool)
        sorgular = {k.get("sorgu") for k in sira}
        self.assertNotIn("kamp çadırı fiyatları", sorgular)
        self.assertNotIn("matara bakım rehberi", sorgular)

    def test_uygun_havuz_konusu_kuyrukta_one_gelir(self):
        pool = [havuz_kaydi("kamp çadırı nasıl seçilir", "outdoor", "cadir", tip="ticari")]
        sira = self.kuyruk(urunler(outdoor__cadir=3), pool=pool)
        self.assertEqual(sira[0]["sorgu"], "kamp çadırı nasıl seçilir")
        self.assertEqual(sira[0]["kaynak"], "havuz")

    def test_main_konulari_gercek_alt_kategoriden_sonra(self):
        products = urunler(outdoor__cadir=3, outdoor__matara=3)
        products["outdoor"]["_main"] = [urun("ana-1"), urun("ana-2"), urun("ana-3")]
        sira = self.kuyruk(products)
        self.assertNotEqual(sira[0]["sub"], "_main")
        self.assertNotEqual(sira[1]["sub"], "_main")
        self.assertIn("_main", {k["sub"] for k in sira})

    def test_kuyruk_deterministik(self):
        pool = [
            havuz_kaydi("kamp çadırı nasıl seçilir", "outdoor", "cadir", tip="ticari"),
            havuz_kaydi("matara bakım rehberi", "outdoor", "matara", tip="rehber"),
        ]
        products = urunler(outdoor__cadir=3, outdoor__matara=3, muzik__gitar=3)
        ilk = self.kuyruk(products, pool=pool)
        ikinci = self.kuyruk(products, pool=pool)
        self.assertEqual([k["key"] for k in ilk], [k["key"] for k in ikinci])


if __name__ == "__main__":
    unittest.main()
