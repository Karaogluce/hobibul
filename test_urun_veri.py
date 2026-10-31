"""Ürün verisi: tekilleştirme, çelişki, aff:// çözümü ve üç ürün kuralı. Ağ yok."""
import copy
import hashlib
import os
import tempfile
import unittest
from urllib.parse import unquote

import build
import otomatik
import urun_denetim
import yeni_makale as ym

KATEGORILER = [{
    "id": "outdoor", "name": "Outdoor",
    "subcategories": [{"id": "cadir", "name": "Kamp Çadırı"}],
}]


def urun(rid, **kw):
    asin = hashlib.sha1(rid.encode("utf-8")).hexdigest()[:10].upper()
    rec = dict(
        id=rid, name=f"Ürün {rid}", desc="Kullanışlı bir ürün.",
        query=f"ürün {rid}", network="amazon_tr", asin=asin,
        dogrulama={
            "durum": "dogrulanmis",
            "tarih": "2026-10-31",
            "kaynak_url": f"https://www.amazon.com.tr/dp/{asin}",
            "yontem": "manuel-test",
        })
    rec.update(kw)
    return rec


def urunler(*listeler):
    """outdoor/cadir listesini verilen kayıtlarla kur; her argüman bir kayıt."""
    return {"outdoor": {"cadir": [urun(r) if isinstance(r, str) else r for r in listeler]}}


class _GeciciMakaleler(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)

    @property
    def articles(self):
        return self._dir.name


class TekillestirmeTest(_GeciciMakaleler):
    def test_ayni_kayit_iki_listede_tek_sayilir(self):
        a = urun("a")
        p = {"outdoor": {
            "cadir": [a, urun("b"), urun("c")],
            "_ek": [dict(a, alt="cadir")],
        }}
        self.assertEqual(len(urun_denetim.gecerli_urunler(p, "outdoor", "cadir")), 3)
        rapor = urun_denetim.dogrula(p, KATEGORILER, articles_dir=self.articles)
        self.assertEqual(rapor["mukerrer"]["ayni"], ["a"])
        self.assertEqual(rapor["mukerrer"]["celiskili"], [])
        self.assertEqual(rapor["hatalar"], [])

    def test_celiskili_kopya_sessizce_sec_ilmez(self):
        p = {"outdoor": {
            "cadir": [urun("a", desc="Kısa açıklama.")],
            "_main": [urun("a", desc="Tamamen farklı ve daha uzun bir açıklama.")],
        }}
        with self.assertRaises(urun_denetim.UrunVerisiHatasi):
            urun_denetim.urun_haritasi(p)
        rapor = urun_denetim.dogrula(p, KATEGORILER, articles_dir=self.articles)
        self.assertEqual(rapor["mukerrer"]["celiskili"], ["a"])
        self.assertTrue(any("çelişkili kopya" in h for h in rapor["hatalar"]))

    def test_birlestirme_bos_alanin_ustune_yazmaz(self):
        zengin = urun("a", asin="B0ABC12345", desc="Uzun ve doyurucu açıklama.")
        fakir = urun("a", desc="")
        birlesik, _ = urun_denetim.birlestir([fakir, zengin])
        self.assertEqual(birlesik["asin"], "B0ABC12345")
        self.assertEqual(birlesik["desc"], "Uzun ve doyurucu açıklama.")

    def test_ayni_asinde_farkli_id_uyarir(self):
        p = {"outdoor": {"cadir": [
            urun("a", asin="B0ABC12345"), urun("b", asin="b0abc12345")]}}
        rapor = urun_denetim.dogrula(p, KATEGORILER, articles_dir=self.articles)
        self.assertEqual(rapor["ayni_asin_farkli_id"], {"B0ABC12345": ["a", "b"]})
        self.assertTrue(rapor["uyarilar"])


class GecersizUrunTest(_GeciciMakaleler):
    def test_gecersiz_kayit_sayilmaz(self):
        bozuk = urun("bozuk", desc="")
        gecersiz_asin = urun("asin", asin="KISA")
        p = {"outdoor": {"cadir": [urun("a"), urun("b"), bozuk, gecersiz_asin]}}
        ids = [r["id"] for r in urun_denetim.gecerli_urunler(p, "outdoor", "cadir")]
        self.assertEqual(ids, ["a", "b"])

    def test_gecersiz_url_ve_asin_raporlanir(self):
        p = {"outdoor": {"cadir": [
            urun("a", url="ftp://ornek"), urun("b", asin="123")]}}
        rapor = urun_denetim.dogrula(p, KATEGORILER, articles_dir=self.articles)
        self.assertTrue(any("geçersiz ASIN" in h for h in rapor["hatalar"]))
        self.assertTrue(any("geçersiz URL" in h for h in rapor["hatalar"]))

    def test_bilinmeyen_kategori_ve_alt_kategori(self):
        p = {
            "olmayan-kategori": {"x": [urun("a")]},
            "outdoor": {"olmayan-alt": [urun("b")]},
        }
        rapor = urun_denetim.dogrula(p, KATEGORILER, articles_dir=self.articles)
        self.assertIn("olmayan-kategori", rapor["kategori_hata"])
        self.assertTrue(rapor["alt_kategori_hata"])
        self.assertTrue(any("Bilinmeyen kategori" in h for h in rapor["hatalar"]))

    def test_urun_bul_gecersizi_atlar(self):
        p = {"outdoor": {"cadir": [
            urun("a"), urun("b"), urun("c"), urun("bozuk", desc="")]}}
        bulunan = otomatik._urun_bul(p, ["a", "bozuk", "yok", "a"])
        self.assertEqual([r["id"] for r in bulunan], ["a"])


class UcUrunKuraliTest(_GeciciMakaleler):
    def _kat(self):
        return KATEGORILER[0]

    def test_iki_gecerli_urun_baslangic_konusu_uretmez(self):
        p = urunler("a", "b", urun("bozuk", desc=""))
        konular = otomatik.ticari_konulari(p, self._kat(), [], set())
        self.assertFalse([k for k in konular if k["sub"] == "cadir"])

    def test_uc_gecerli_urun_baslangic_konusu_uretir(self):
        p = urunler("a", "b", "c")
        konular = otomatik.ticari_konulari(p, self._kat(), [], set())
        baslangic = [k for k in konular if k["sub"] == "cadir" and k["kaynak"] == "sablon"]
        self.assertEqual(len(baslangic), 1)
        self.assertEqual(len(baslangic[0]["ids"]), 3)

    def test_ek_liste_alt_eslesmesi_ve_gecersiz_kayit(self):
        p = {"outdoor": {
            "cadir": [urun("a"), urun("b")],
            "_ek": [
                dict(urun("c"), alt="cadir"),
                dict(urun("bozuk", desc=""), alt="cadir"),
            ],
        }}
        ids = [r["id"] for r in urun_denetim.alt_kategori_urunleri(p, "outdoor", "cadir")]
        self.assertEqual(ids, ["a", "b", "c"])

    def test_urun_odakli_tiplerde_esik_uc(self):
        for tip in ("ticari", "rehber", "yeni_baslayan"):
            self.assertEqual(otomatik._gerekli_urun(tip), 3, tip)
        for tip in ("hatalar", "sss", "kontrol_listesi", "nasil_yapilir"):
            self.assertEqual(otomatik._gerekli_urun(tip), 2, tip)


class GercekUrunDogrulamaTest(_GeciciMakaleler):
    def test_kanitsiz_urun_uretime_giremez(self):
        products = urunler("a", "b", "c")
        for _, _, rec in urun_denetim.iter_kayitlar(products):
            rec.pop("dogrulama")
        konu = {"ids": ["a", "b", "c"], "tip": "ticari"}
        sonuc, neden = otomatik.uret(
            konu, products, "gizli", [], 0, "gizli", {"photos": []}, False, "2026-10-31")
        self.assertIsNone(sonuc)
        self.assertIn("doğrulanmamış ürün", neden)

    def test_asin_tek_basina_dogrulama_degildir(self):
        rec = urun("a")
        rec.pop("dogrulama")
        self.assertFalse(urun_denetim.dogrulanmis_mi(rec))
        self.assertEqual(urun_denetim.dogrulama_durumu(rec), "incelenecek")

    def test_devre_disi_urun_sayilmaz(self):
        products = urunler("a", "b", "c")
        self.assertEqual(urun_denetim.devre_disi_isaretle(products, "a"), 1)
        ids = [r["id"] for r in urun_denetim.gecerli_urunler(products, "outdoor", "cadir")]
        self.assertEqual(ids, ["b", "c"])

    def test_kaynak_urldeki_asin_urunle_ayni_olmali(self):
        rec = urun("a")
        rec["dogrulama"]["kaynak_url"] = "https://www.amazon.com.tr/dp/B000000000"
        self.assertFalse(urun_denetim.dogrulanmis_mi(rec))

    def test_dogrulama_butun_kopyalara_islenir(self):
        a = urun("a")
        products = {"outdoor": {"cadir": [a], "_main": [copy.deepcopy(a)]}}
        n = urun_denetim.dogrulama_isaretle(
            products, "a", "B0ABC12345", "https://www.amazon.com.tr/dp/B0ABC12345", "2026-10-31")
        self.assertEqual(n, 2)
        self.assertTrue(all(urun_denetim.dogrulanmis_mi(r) for _, _, r in urun_denetim.iter_kayitlar(products)))

    def test_arama_urlsi_kanit_olamaz(self):
        rec = urun("a")
        rec["dogrulama"]["kaynak_url"] = "https://www.amazon.com.tr/s?k=kamp"
        self.assertFalse(urun_denetim.dogrulanmis_mi(rec))

    def test_mevcut_makale_riski_yayini_silmeden_raporlanir(self):
        rec = urun("a")
        rec.pop("dogrulama")
        products = urunler(rec, "b", "c")
        dosya = os.path.join(self.articles, "riskli.md")
        with open(dosya, "w", encoding="utf-8") as f:
            f.write("---\ntitle: Riskli\ncategory: outdoor\nsubcategory: cadir\n---\n[Ürün](aff://a)\n")
        rapor = urun_denetim.dogrula(products, KATEGORILER, articles_dir=self.articles)
        self.assertEqual(rapor["makale_dogrulama"]["riskli_sayi"], 1)
        self.assertEqual(rapor["makale_dogrulama"]["riskli"][0]["urunler"], ["a"])
        self.assertTrue(os.path.isfile(dosya))


class AffCozumTest(unittest.TestCase):
    def test_asin_amazon_tr_dp_linkine_donusur(self):
        url = build.affiliate_url(dict(
            network="amazon_tr", asin="b0abc-12345", name="Ürün", query="ürün"))
        self.assertEqual(url, "https://www.amazon.com.tr/dp/B0ABC12345?tag=hobibulsite-21")

    def test_dogrulanmis_urun_sayfasi_arama_linki_yerine_kullanilir(self):
        url = build.affiliate_url(dict(
            network="amazon_tr", asin="B0ABC12345",
            amazon_url="https://www.amazon.com.tr/ornek/dp/B0ABC12345", name="Ürün"))
        self.assertTrue(url.startswith("https://www.amazon.com.tr/ornek/dp/B0ABC12345"))
        self.assertIn("tag=hobibulsite-21", url)

    def test_asin_yoksa_arama_linkine_duser(self):
        url = build.affiliate_url(dict(network="amazon_tr", name="Kamp Çadırı", query="kamp çadırı"))
        self.assertTrue(url.startswith("https://www.amazon.com.tr/s?"))
        self.assertIn("k=Kamp", unquote(url))
        self.assertIn("tag=hobibulsite-21", url)

    def test_diger_agda_url_korunur(self):
        url = build.affiliate_url(dict(
            network="trendyol", url="https://www.trendyol.com/urun", name="Ürün"))
        self.assertEqual(url, "https://www.trendyol.com/urun")

    def test_bilinmeyen_ag_bos_link_dondurur(self):
        self.assertEqual(build.affiliate_url(dict(network="yok", name="Ürün")), "#")


class MakaleSecimiTest(_GeciciMakaleler):
    def test_yeni_makale_celiskili_veride_durur(self):
        p = {"outdoor": {
            "cadir": [urun("a"), urun("b"), urun("c")],
            "_main": [urun("a", desc="Bambaşka bir açıklama metni.")],
        }}
        with self.assertRaises(SystemExit):
            ym.pick_products(p, "outdoor", "cadir", ["a"])

    def test_bilinmeyen_id_durur(self):
        p = urunler("a", "b", "c")
        with self.assertRaises(SystemExit):
            ym.pick_products(p, "outdoor", "cadir", ["a", "yok"])

    def test_id_verilmezse_dogrulanmis_havuz_doner(self):
        p = urunler("a", "b", urun("bozuk", desc=""))
        secilen = ym.pick_products(p, "outdoor", "cadir", [])
        self.assertEqual([r["id"] for r in secilen], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
