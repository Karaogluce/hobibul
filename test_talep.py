"""Arama talebi: sorgu seçimi, yakın eşleme ve günlük kota."""
import json
import os
import tempfile
import unittest

import otomatik


class YakinTest(unittest.TestCase):
    def test_yazim_farki_ve_evde_spor_birlesir(self):
        self.assertTrue(otomatik.sorgular_yakin("akvaryum çeşitleri", "akvaryum cesitleri"))
        self.assertTrue(otomatik.sorgular_yakin(
            "evde spor için gerekli malzemeler",
            "evde spor için hangi aletler alınmalı"))
        self.assertFalse(otomatik.sorgular_yakin(
            "ideal yoga matı ölçüleri", "en iyi çadır markaları"))

    def test_cadir_sorgusu_mevcut_secim_yazisini_karsilar(self):
        self.assertTrue(otomatik.makale_sorguyu_karsilar(
            "en iyi çadır markaları",
            "En İyi Kamp Çadırı Seçimi 2026: 2 ve 4 Kişilik Karşılaştırma",
            "en-iyi-kamp-cadiri-secimi-2026-2-ve-4-kisilik-karsilastirma"))

    def test_akvaryum_cesitleri_ekipman_yazisindan_ayri(self):
        self.assertFalse(otomatik.makale_sorguyu_karsilar(
            "akvaryum çeşitleri",
            "Akvaryum Ekipmanı Seçimi: Tank, Filtre, Isıtıcı ve Hava Pompası",
            "akvaryum-ekipmani-secimi-tank-filtre-isitici"))


class SecimTest(unittest.TestCase):
    def test_tohum_iki_sorgu_ve_evde_spor_tek_kume(self):
        rows, kaynak = otomatik.talep_ham_sorgular(
            gsc_path=os.path.join(tempfile.gettempdir(), "yok-gsc.json"),
            seed_path=os.path.join(otomatik.CONTENT, "gsc_seed_queries.json"))
        self.assertEqual(kaynak, "seed")
        kumeler = otomatik.talep_kumeleri(rows)
        spor = [k for k in kumeler if "spor" in k["sorgu"]]
        self.assertEqual(len(spor), 1)
        self.assertEqual(len(spor[0]["uyeler"]), 2)
        secilen, _ = otomatik.talep_sec(rows, {"talep": [], "done": []}, [], 2)
        self.assertEqual(len(secilen), 2)
        self.assertEqual(secilen[0]["sorgu"], "akvaryum çeşitleri")
        self.assertEqual(secilen[1]["sorgu"], "en iyi çadır markaları")

    def test_gsc_gosterim_sirasi_ve_kopya_birlesir(self):
        with tempfile.TemporaryDirectory() as d:
            gsc = os.path.join(d, "analytics_gsc.json")
            with open(gsc, "w", encoding="utf-8") as f:
                json.dump({"ok": True, "queries": [
                    {"query": "robotik kodlama robotu", "impressions": 5, "clicks": 1},
                    {"query": "akvaryum çeşitleri", "impressions": 50, "clicks": 2},
                    {"query": "akvaryum cesitleri", "impressions": 40, "clicks": 1},
                    {"query": "evde spor için gerekli malzemeler", "impressions": 30, "clicks": 1},
                    {"query": "evde spor için hangi aletler alınmalı", "impressions": 20, "clicks": 4},
                ]}, f)
            rows, kaynak = otomatik.talep_ham_sorgular(gsc_path=gsc, seed_path=os.path.join(d, "yok.json"))
            self.assertEqual(kaynak, "gsc")
            secilen, guclendir = otomatik.talep_sec(rows, {"talep": [], "done": []}, [], 2)
            self.assertEqual(guclendir, [])
            self.assertEqual([k["sorgu"] for k in secilen], [
                "akvaryum çeşitleri",
                "evde spor için gerekli malzemeler",
            ])
            self.assertEqual(secilen[0]["impressions"], 90)

    def test_yazilmis_sorgu_tekrar_secilmez(self):
        rows, _ = otomatik.talep_ham_sorgular(
            gsc_path=os.path.join(tempfile.gettempdir(), "yok-gsc-2.json"),
            seed_path=os.path.join(otomatik.CONTENT, "gsc_seed_queries.json"))
        log = {"talep": [{
            "sorgu": "akvaryum çeşitleri",
            "anahtar": "talep:akvaryum-cesitleri",
            "durum": "yazildi",
        }], "done": []}
        secilen, _ = otomatik.talep_sec(rows, log, [], 1)
        self.assertNotEqual(secilen[0]["sorgu"], "akvaryum çeşitleri")
        self.assertFalse(any(otomatik.sorgular_yakin(k["sorgu"], "akvaryum cesitleri") for k in secilen))

    def test_yakin_makale_guclendir_adayi_olur_ve_slot_dolmaz(self):
        rows = [
            {"query": "en iyi çadır markaları", "impressions": 100, "clicks": 9, "sira": 0},
            {"query": "robotik kodlama robotu", "impressions": 40, "clicks": 2, "sira": 1},
            {"query": "ideal yoga matı ölçüleri", "impressions": 10, "clicks": 1, "sira": 2},
        ]
        makaleler = [{
            "baslik": "En İyi Kamp Çadırı Seçimi 2026: 2 ve 4 Kişilik Karşılaştırma",
            "slug": "en-iyi-kamp-cadiri-secimi-2026-2-ve-4-kisilik-karsilastirma",
        }]
        secilen, guclendir = otomatik.talep_sec(rows, {"talep": [], "done": []}, makaleler, 2)
        self.assertIn("en iyi çadır markaları", guclendir)
        self.assertEqual([k["sorgu"] for k in secilen], [
            "robotik kodlama robotu",
            "ideal yoga matı ölçüleri",
        ])

    def test_talep_makaleleri_duzenli_kotayi_doldurmaz(self):
        log = {"done": [], "makaleler": [
            {"anahtar": "talep:akvaryum-cesitleri", "tarih": "2026-11-04", "slug": "a"},
            {"anahtar": "talep:robotik-kodlama-robotu", "tarih": "2026-11-04", "slug": "b"},
        ]}
        adet, _ = otomatik.kosu_plani(3, log, "2026-11-04")
        self.assertEqual(adet, 3)
        self.assertEqual(otomatik.bugun_talep_say(log, "2026-11-04"), 2)


if __name__ == "__main__":
    unittest.main()
