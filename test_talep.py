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

    def test_brif_kuyrugu_yilbasi_ile_baslar_ve_gsc_den_once_gelir(self):
        otomatik._BRIEF_CACHE = None
        liste = otomatik.talep_brif_listesi()
        self.assertEqual(liste[0]["slug"], "yilbasi-hediyesi-kutu-oyunlari")
        self.assertEqual(liste[0]["oncelik"], 1)
        sec, guc = otomatik.talep_brif_sec(liste, {"talep": [], "done": []}, [], 2)
        self.assertEqual(guc, [])
        self.assertEqual([b["slug"] for b in sec], [
            "yilbasi-hediyesi-kutu-oyunlari",
            "erkekler-icin-hobiler",
        ])

    def test_yayindaki_brif_slugi_gecilir(self):
        briefs = [
            {"slug": "yilbasi-hediyesi-kutu-oyunlari", "oncelik": 1,
             "sorgu": "yılbaşı kutu oyunu önerileri", "h1": "Yılbaşı Hediyesi Kutu Oyunları",
             "zorunlu_linkler": []},
            {"slug": "erkekler-icin-hobiler", "oncelik": 2,
             "sorgu": "erkekler için hobiler", "h1": "Erkekler İçin Hobiler ve Hobi Setleri",
             "zorunlu_linkler": []},
        ]
        mak = [{"slug": "yilbasi-hediyesi-kutu-oyunlari", "baslik": "Yılbaşı Hediyesi Kutu Oyunları"}]
        sec, _ = otomatik.talep_brif_sec(briefs, {"talep": [], "done": []}, mak, 2)
        self.assertEqual([b["slug"] for b in sec], ["erkekler-icin-hobiler"])

    def test_ayni_konu_guclendir_slotu_doldurmaz(self):
        briefs = [
            {"slug": "bonsai-kopya", "oncelik": 1, "sorgu": "bonsai başlangıç seti",
             "h1": "Bonsai Başlangıç Seti: Makas ve Tel", "zorunlu_linkler": []},
            {"slug": "erkekler-icin-hobiler", "oncelik": 2, "sorgu": "erkekler için hobiler",
             "h1": "Erkekler İçin Hobiler ve Hobi Setleri", "zorunlu_linkler": []},
        ]
        mak = [{"slug": "bonsai-baslangic-seti-makas-tel-ve-toprak",
                "baslik": "Bonsai Başlangıç Seti: Makas, Tel ve Toprak"}]
        sec, guc = otomatik.talep_brif_sec(briefs, {"talep": [], "done": []}, mak, 2)
        self.assertIn("bonsai başlangıç seti", guc)
        self.assertEqual([b["slug"] for b in sec], ["erkekler-icin-hobiler"])

    def test_brif_bitince_gsc_secimi_ayri_kalir(self):
        briefs = [{"slug": "yilbasi-hediyesi-kutu-oyunlari", "oncelik": 1,
                   "sorgu": "yılbaşı kutu oyunu önerileri", "h1": "Yılbaşı",
                   "zorunlu_linkler": []}]
        mak = [{"slug": "yilbasi-hediyesi-kutu-oyunlari", "baslik": "Yılbaşı"}]
        sec, guc = otomatik.talep_brif_sec(briefs, {"talep": [], "done": []}, mak, 2)
        self.assertEqual(sec, [])
        self.assertEqual(guc, [])
        rows = [{"query": "robotik kodlama robotu", "impressions": 3, "clicks": 1, "sira": 0}]
        gsc, _ = otomatik.talep_sec(rows, {"talep": [], "done": []}, [], 1)
        self.assertEqual(gsc[0]["sorgu"], "robotik kodlama robotu")

    def test_kadin_brifi_ev_hubi_ile_cakismaz(self):
        brief = {
            "slug": "kadinlar-icin-evde-yapilacak-hobiler",
            "sorgu": "evde yapılacak hobiler kadın",
            "h1": "Kadınlar İçin Evde Yapılacak 20 Hobi (Başlangıç Malzemeleriyle)",
            "zorunlu_linkler": ["/makale/evde-yapilacak-hobiler/"],
        }
        makale = {"slug": "evde-yapilacak-hobiler",
                  "baslik": "Evde Yapılacak Hobiler: 30 Fikir ve İlk Malzeme"}
        self.assertFalse(otomatik.brif_makaleyle_cakisir(brief, makale))

    def test_brif_promptu_slug_ve_sss_basligini_tasir(self):
        otomatik._BRIEF_CACHE = None
        metin = otomatik._brief_prompt({
            "brief": "yilbasi-hediyesi-kutu-oyunlari",
            "title": "Yılbaşı Hediyesi Kutu Oyunları: Kime Hangi Oyun? (2026)",
            "slug": "yilbasi-hediyesi-kutu-oyunlari",
            "tip": "talep",
        })
        self.assertIn("yilbasi-hediyesi-kutu-oyunlari", metin)
        self.assertIn("URL'ye yıl ekleme", metin)
        self.assertIn("## Sıkça Sorulan Sorular", metin)
        self.assertIn("# Brief #18:", metin)

    def test_ham_anahtar_dogal_basliga_donusur_ve_anlamsiz_elenir(self):
        self.assertEqual(
            otomatik.baslik_kur("barista kahve nasıl"),
            "Barista Gibi Evde Kahve Nasıl Yapılır?")
        self.assertEqual(otomatik.baslik_kur("model auto lego"), "LEGO Model Araba Setleri")
        self.assertEqual(otomatik.baslik_kur("gitar nasıl öğrenilir"), "Gitar Nasıl Öğrenilir?")
        self.assertEqual(otomatik.baslik_kur("drone nasıl yapılır"), "")
        self.assertEqual(otomatik.baslik_kur("lego model a"), "")
        self.assertEqual(otomatik.baslik_kur("lego model airport"), "")

    def test_genel_brif_ince_alt_kategoriden_cikar(self):
        brief = {
            "slug": "emekliler-icin-hobiler",
            "h1": "Emekliler ve Yaşlılar İçin 20 Hobi: Zihni ve Bedeni Aktif Tutan Fikirler",
            "sorgu": "emekli erkekler için hobiler",
            "meta_description": "Emekliler için hobiler: bahçe, bonsai, balık ve kutu oyunu.",
            "kategori": "bahce-bitki",
            "alt": "bonsai",
        }
        cats = [{"id": "bahce-bitki", "name": "Bahçe & Bitki"},
                {"id": "koleksiyon", "name": "Koleksiyon"}]
        yer = otomatik.brief_yerini_duzelt(brief, cats)
        self.assertEqual(yer["kategori"], "bahce-bitki")
        self.assertEqual(yer["alt"], "_main")
        spesifik = {"h1": "Amigurumi Başlangıç Seti", "sorgu": "amigurumi seti",
                    "kategori": "el-sanatlari", "alt": "orgu-tig"}
        self.assertEqual(otomatik.brief_yerini_duzelt(spesifik, cats)["alt"], "orgu-tig")

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
