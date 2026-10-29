"""Gemini uzunluk kapısı: token tavanı, MAX_TOKENS ve devam çağrısı. Ağ yok."""
import io
import json
import unittest
import urllib.error
import urllib.request

import otomatik
import yeni_makale as ym


def _konu():
    return dict(
        title="Teleskop Başlangıç Seti", tip="ticari", cat="bilim-astronomi",
        cat_name="Bilim", sub="teleskop-astronomi", sub_name="Teleskop")


def _urun():
    return [dict(id="mini-teleskop", name="Mini Teleskop", brand="Optik", desc="Başlangıç tüpü",
                 pros=["hafif"], cons=["dar görüş"])]


def _uzun_govde():
    govde = [
        "## Satın Almadan Önce Nelere Bakmalı?",
        "",
        "Balkonda Ay'a bakacaksan önce üçayak titremesini düşün. Dar balkonda uzun bir tüp kapıya çarpar.",
        "",
        "## Ürün Ürün Set",
        "",
    ]
    paragraf = (
        "Hafta sonu iki saatlik bir gözlemde tüpün ağırlığı bileği yorar; "
        "yeni başlayan biri önce hafif modeli kurmayı öğrenir, çünkü karanlıkta vida aramak gözlemi bitirir. "
    )
    govde.append(paragraf * 220)
    return "\n".join(govde)


class UzunlukTest(unittest.TestCase):
    def test_hedef_ve_alt_sinir_ayni_kalir(self):
        self.assertEqual(otomatik.GUNLUK_HEDEF, 3)
        self.assertEqual(otomatik.TIPLER["ticari"]["min"], 1550)
        self.assertEqual(otomatik.TIPLER["rehber"]["min"], 1500)
        self.assertEqual(otomatik.kelime_hedef("ticari"), 1700)
        self.assertEqual(otomatik.kelime_hedef("rehber"), 1650)
        adet, _ = otomatik.kosu_plani(8, {"done": [], "makaleler": []}, "2026-10-29")
        self.assertEqual(adet, 3)

    def test_kisa_kapisi_siniri_soyler(self):
        why = otomatik.gate("kelime " * 700, "ticari", [], [])
        self.assertEqual(why, "kısa (700 kelime, alt sınır 1550)")
        uzun = otomatik.gate("kelime " * 1600, "rehber", [{"id": "a"}, {"id": "b"}], [])
        self.assertFalse(uzun and uzun.startswith("kısa"))

    def test_prompt_alt_siniri_ve_dolguyu_soyler(self):
        t = _konu()
        metin = otomatik.build_prompt(t, _urun(), ["teleskop nasıl seçilir"], "rehber")
        self.assertIn("1700–2000", metin)
        self.assertIn("1550 kelimenin altı", metin)
        self.assertIn("tekrarlayarak uzatma", metin)
        self.assertNotIn("Kısa giriş", metin)
        edit = otomatik.edit_prompt("taslak", _urun(), "rehber", 1550)
        self.assertIn("1550 kelimenin altına düşürme", edit)
        devam = otomatik.devam_prompt("kısa taslak", t, _urun(), "rehber", "MAX_TOKENS")
        self.assertIn("token sınırında", devam)
        self.assertIn("Dolgu cümle yazma", devam)
        self.assertIn("mini-teleskop", devam)
        self.assertIn("denedim", devam)
        durmus = otomatik.devam_prompt("kısa taslak", t, _urun(), "", "STOP")
        self.assertIn("Erken durmuş", durmus)
        self.assertNotIn("token sınırında", durmus)

    def test_gemini_yaniti_dusunceyi_ayirir(self):
        yanit = ym.gemini_yaniti({
            "candidates": [{
                "finishReason": "MAX_TOKENS",
                "content": {"parts": [
                    {"text": "gizli plan", "thought": True},
                    {"text": "asıl metin"},
                ]},
            }],
            "usageMetadata": {"thoughtsTokenCount": 900, "candidatesTokenCount": 40},
        })
        self.assertIsInstance(yanit, str)
        self.assertEqual(str(yanit), "asıl metin")
        self.assertEqual(yanit.finish_reason, "MAX_TOKENS")
        self.assertEqual(yanit.usage["thoughtsTokenCount"], 900)
        self.assertIn("düşünce token=900", ym.dusunce_notu(yanit.usage))
        with self.assertRaises(ym.GeminiError):
            ym.gemini_yaniti({"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}})

    def test_cikti_token_reddi(self):
        self.assertTrue(ym.cikti_token_reddi("maxOutputTokens exceeds model limit"))
        self.assertTrue(ym.cikti_token_reddi("max_output_tokens: invalid"))
        self.assertFalse(ym.cikti_token_reddi("API key not valid"))
        self.assertEqual(ym.CIKTI_TOKEN_BASAMAKLARI[0], 65536)
        self.assertEqual(ym.generation_config(65536)["maxOutputTokens"], 65536)

    def test_call_gemini_yuksek_tavan_ve_basamak(self):
        gorulen = []

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({
                    "candidates": [{
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": "merhaba dünya"}]},
                    }]
                }).encode()

        def urlopen(req, timeout=0):
            govde = json.loads(req.data.decode())
            gorulen.append(govde["generationConfig"]["maxOutputTokens"])
            self.assertNotIn("test-anahtar", req.data.decode())
            if len(gorulen) == 1:
                raise urllib.error.HTTPError(
                    req.full_url, 400, "Bad Request", {},
                    io.BytesIO(b'{"error":"maxOutputTokens exceeds the maximum"}'))
            return Resp()

        orig_open, orig_gap = urllib.request.urlopen, ym._MIN_GAP
        urllib.request.urlopen = urlopen
        ym._MIN_GAP = 0
        ym._last_call[0] = 0
        try:
            out = ym.call_gemini("yaz", "test-anahtar", "gemini-flash-lite-latest")
        finally:
            urllib.request.urlopen = orig_open
            ym._MIN_GAP = orig_gap
        self.assertEqual(gorulen, [65536, 32768])
        self.assertEqual(str(out), "merhaba dünya")
        self.assertEqual(out.finish_reason, "STOP")

    def test_birlestir_ve_ayikla(self):
        eski = (
            "## Satın Almadan Önce Nelere Bakmalı?\n\n"
            "İlk cümle dar balkonda tüpün kapıya çarptığını anlatır.\n\n"
            "## Ürün Ürün Set\n\n"
            "İkinci cümle tüpün ağırlığının bileği neden yorduğunu anlatır."
        )
        ek = "Yeni bölüm karanlıkta vida aramanın neden gözlemi böldüğünü anlatır."
        birlesik = otomatik.birlestir_taslak(eski, ek)
        self.assertIn("kapıya çarptığını", birlesik)
        self.assertIn("vida aramanın", birlesik)
        uzun = (eski + "\n\n" + ("Bu kullanım durumu yeni bir ayrım taşır. " * 40)).strip()
        self.assertEqual(otomatik.birlestir_taslak(eski, uzun), uzun)
        self.assertEqual(otomatik.birlestir_taslak(eski, ""), eski)
        kisa_yine = (
            "## Satın Almadan Önce Nelere Bakmalı?\n\n"
            "İlk cümle dar balkonda tüpün kapıya çarptığını anlatır."
        )
        self.assertEqual(otomatik.birlestir_taslak(eski, kisa_yine), eski)
        ham = "```markdown\nGORSEL: telescope\nANAHTAR: teleskop\nACIKLAMA: başlangıç tüpü\n---\n## Bölüm\n\nGövde.\n```"
        ayik = otomatik.govde_ayikla(ham)
        self.assertIn("## Bölüm", ayik)
        self.assertNotIn("GORSEL", ayik)

    def test_genisletme_karari(self):
        self.assertTrue(otomatik.genisletme_gerekli("kelime " * 700, "ticari", "STOP"))
        self.assertFalse(otomatik.genisletme_gerekli("kelime " * 1600, "ticari", "STOP"))
        self.assertTrue(otomatik.genisletme_gerekli("kelime " * 1600, "ticari", "MAX_TOKENS"))

    def test_uzat_kisa_taslagi_tamamlar_ve_uzun_taslage_dokunmaz(self):
        t = _konu()
        uzun = _uzun_govde()
        self.assertGreaterEqual(len(uzun.split()), 1550)
        calls = []

        def fake(prompt, key, models, idx):
            calls.append(prompt)
            self.assertNotIn("test-anahtar", prompt)
            return ym.GeminiYazi(uzun, "STOP", {"thoughtsTokenCount": 12})

        orig = otomatik._gemini
        otomatik._gemini = fake
        try:
            kisa = "## Satın Almadan Önce Nelere Bakmalı?\n\nKısa taslak.\n\n## Ürün Ürün Set\n\nErken bitti."
            out = otomatik.uzat_taslak(kisa, t, _urun(), "rehber", "test-anahtar", ["yedek"], [0], "MAX_TOKENS")
            self.assertGreaterEqual(len(out.split()), 1550)
            self.assertEqual(len(calls), 1)
            self.assertIn("token sınırında", calls[0])
            calls.clear()
            ayni = otomatik.uzat_taslak(uzun, t, _urun(), "rehber", "test-anahtar", ["yedek"], [0], "STOP")
            self.assertEqual(ayni, uzun)
            self.assertEqual(calls, [])
        finally:
            otomatik._gemini = orig

    def test_uzat_iki_turdan_sonra_durur(self):
        t = _konu()
        calls = {"n": 0}

        def fake(prompt, key, models, idx):
            calls["n"] += 1
            return ym.GeminiYazi(
                f"Tur {calls['n']} karanlıkta kurulumun neden yarım kaldığını yeni bir durumla anlatır.",
                "STOP", {})

        orig = otomatik._gemini
        otomatik._gemini = fake
        try:
            out = otomatik.uzat_taslak("Kısa taslak cümlesi.", t, _urun(), "", "k", ["m"], [0], "STOP", hak=2)
        finally:
            otomatik._gemini = orig
        self.assertEqual(calls["n"], 2)
        self.assertLess(len(out.split()), 1550)

    def test_kota_yedek_modeli_korunur(self):
        calls = []

        def fake(prompt, key, model):
            calls.append(model)
            if model == "gemini-flash-latest":
                raise ym.GeminiQuotaError("günlük kota")
            return ym.GeminiYazi("metin", "STOP", {})

        orig = ym.call_gemini
        ym.call_gemini = fake
        try:
            idx = [0]
            out = otomatik._gemini("p", "k", ["gemini-flash-latest", "gemini-flash-lite-latest"], idx)
        finally:
            ym.call_gemini = orig
        self.assertEqual(str(out), "metin")
        self.assertEqual(calls, ["gemini-flash-latest", "gemini-flash-lite-latest"])
        self.assertEqual(idx[0], 1)


if __name__ == "__main__":
    unittest.main()
