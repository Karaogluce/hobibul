"""Gemini uzunluk kapısı: yumuşak hedef, güvenlik tabanı ve devam çağrısı. Ağ yok."""
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


def _tam_makale():
    """Yaklaşık 740 kelime: eski 1500 sınırının altında, güvenlik tabanının üstünde."""
    ozne = [
        "Sabah", "Rota", "Ayakkabı", "Çanta", "Su", "Harita", "Hava", "Rehber", "Dönüş", "Mola",
        "Katman", "Eldiven", "Şapka", "Güneş", "Yağmur", "Rüzgar", "Patika", "Kaya", "Dere", "Kamp",
        "Çadır", "Uyku", "Yemek", "Ocak", "Fener", "Pil", "Telefon", "Arkadaş", "Grup", "Tempo",
        "Nefes", "Adım", "Bacak", "Omuz", "Sırt", "Bel", "Diz", "Ayak", "Taban", "Bağcık",
    ]
    yuklem = [
        "erken saatte çıktığın yürüyüşte ayakkabının tabanı ıslak taşta kaymamalı ve adımını güvenle atmalısın",
        "seçerken haritanın yanında hava durumunu da kontrol etmek işini belirgin biçimde kolaylaştırır",
        "bağcıklarını her molada kontrol etmek uzun yürüyüşlerde ayak sağlığını korur",
        "içine yedek çorap ve ince bir üst koymak hava değişiminde rahatlık sağlar",
        "tüketimini saat başı planlamak baş ağrısını ve halsizliği önlemeye yardım eder",
        "üzerindeki işaretleri takip etmek kaybolma riskini azaltır ve dönüş yolunu kısaltır",
        "sıcaklık düştüğünde rüzgarın yönünü okumak doğru giyinmeyi kolaylaştırır",
        "notlarını küçük bir deftere yazmak sonraki geziler için güvenilir bir kaynak oluşturur",
        "yolunu gün batmadan planlamak karanlıkta yön bulma stresini ortadan kaldırır",
        "süresini kısa tutmak bacakların dinlenmesine ve tempoyu korumana yardım eder",
        "kalınlığını mevsime göre seçmek vücut ısısını dengede tutar",
        "elde taşımak yerine cebe koymak parmaklarını soğuktan korur",
        "geniş kenarlı olanı tercih etmek yüzünü öğleden sonra güneşinden saklar",
        "koruyucu kremi iki saatte bir yenilemek ciltte yanık oluşmasını engeller",
        "başladığında mola yerini önceden belirlemek panik yapmanı önler",
        "sertleştiğinde adımlarını küçültmek dengeni korumana yardımcı olur",
        "taşlı bölümde yavaşlamak burkulma riskini belirgin biçimde düşürür",
        "geçişinde ayakkabının tutuşunu test etmek güvenli bir geçiş sağlar",
        "yakınında mola vermek hem serinlemeyi hem de su ikmalini kolaylaştırır",
        "alanını erkenden kurmak akşam karanlığında işlerini zorlaştırmaz",
        "gerginliğini doğru ayarlamak yağmurda içeri su girmesini engeller",
        "düzenini korumak sabah eşyalarını hızlıca bulmanı sağlar",
        "listesini önceden yapmak eksik malzemeyle yola çıkma riskini azaltır",
        "yakmak için kuru dal toplamak ıslak zeminde güvenli bir başlangıç sunar",
        "ışığını cebinde taşımak karanlıkta çevreyi görmeni kolaylaştırır",
        "durumunu her akşam kontrol etmek yolda kalma ihtimalini düşürür",
        "sinyalini yüksek noktada denemek acil durumda iletişimi hızlandırır",
        "grubunu önceden bilgilendirmek buluşma noktasını netleştirir",
        "hızını en yavaş kişiye göre ayarlamak kimsenin geride kalmasını önler",
        "sabırlı tutmak uzun yürüyüşlerde sakatlanma riskini azaltır",
        "verdiğin molalarda derin nefes almak kasların toparlanmasına yardım eder",
        "uzunluğunu kısa tutmak dizlerin yükünü hafifletir",
        "larını germe hareketleriyle rahatlatmak ertesi gün ağrıyı azaltır",
        "yükünü iki omuza eşit dağıtmak duruşunu düzeltir",
        "duruşunu ara ara kontrol etmek bel ağrısını önler",
        "bölgesini sıcak tutmak ani hareketlerde rahatlık sağlar",
        "bileğini burkmamak için düz zeminde ısınmak faydalıdır",
        "tabanını her geziden sonra temizlemek malzemenin ömrünü uzatır",
        "bağcığını çift düğümle sabitlemek uzun yürüyüşte çözülmeyi önler",
        "hazırlığını bir gün önceden tamamlamak sabah telaşını ortadan kaldırır",
    ]
    ek1 = [
        "bu yüzden küçük ayrıntıları atlamamak gerekir",
        "böylece gün sonunda daha az yorgun kalırsın",
        "çünkü doğru hazırlık beklenmedik durumları yönetmeyi kolaylaştırır",
        "ve bu alışkanlık zamanla kalıcı bir düzene dönüşür",
    ]
    ek2 = [
        "aynı zamanda yolda karşılaşabileceğin küçük sorunları büyümeden çözmene yardım eder",
        "üstelik grubun geri kalanıyla uyum içinde ilerlemeni sağlar",
        "böylece hem güvenliğini hem de keyfini birlikte korumuş olursun",
    ]
    cumleler = []
    for i, (a, b) in enumerate(zip(ozne, yuklem)):
        if i % 3 == 0:
            cumleler.append(f"{a} {b}, {ek1[i % 4]}, {ek2[i % 3]}.")
        elif i % 3 == 1:
            cumleler.append(f"{a} {b}, {ek1[i % 4]}.")
        else:
            cumleler.append(f"{a} {b}.")
    cumleler[3] += "\n\n[Satın Al: Ürün A](aff://a)"
    cumleler[22] += "\n\n[Satın Al: Ürün B](aff://b)"
    basliklar = ["## Hazırlık", "## Rota", "## Kamp", "## Dönüş", "## Sık Sorulan Sorular"]
    bolumler = []
    for i in range(0, len(cumleler), 8):
        bolumler.append(basliklar[i // 8] + "\n\n" + " ".join(cumleler[i:i + 8]))
    return "\n\n".join(bolumler)


class UzunlukTest(unittest.TestCase):
    def test_gunluk_hedef_ve_yumusak_hedef(self):
        self.assertEqual(otomatik.GUNLUK_HEDEF, 5)
        self.assertEqual(otomatik.TIPLER["ticari"]["hedef"], 1200)
        self.assertEqual(otomatik.TIPLER["rehber"]["hedef"], 1000)
        self.assertEqual(otomatik.kelime_hedef("ticari"), 1200)
        self.assertEqual(otomatik.kelime_hedef("rehber"), 1000)
        adet, _ = otomatik.kosu_plani(8, {"done": [], "makaleler": []}, "2026-10-29")
        self.assertEqual(adet, 5)

    def test_kisa_kapisi_guvenlik_tabanini_soyler(self):
        why = otomatik.gate("kelime " * 500, "ticari", [], [])
        self.assertEqual(why, "kısa (500 kelime, güvenlik tabanı 600)")
        yedi_yuz = otomatik.gate("kelime " * 700, "rehber", [{"id": "a"}, {"id": "b"}], [])
        self.assertFalse(yedi_yuz and yedi_yuz.startswith("kısa"))

    def test_kisa_ama_tam_makale_reddedilmez(self):
        body = _tam_makale()
        self.assertGreaterEqual(len(body.split()), otomatik.GUVENLIK_TABANI)
        self.assertLess(len(body.split()), 1500)
        self.assertIsNone(otomatik.gate(body, "sss", [{"id": "a"}, {"id": "b"}], []))

    def test_yarim_ve_bozuk_cikti_reddedilir(self):
        self.assertTrue(otomatik.gate("kelime " * 200, "sss", [], []).startswith("kısa"))
        yarim = _tam_makale().replace("## ", "### ")
        self.assertEqual(otomatik.gate(yarim, "sss", [{"id": "a"}, {"id": "b"}], []),
                         "yetersiz H2 bölümü")
        ssssiz = _tam_makale().replace("Sık Sorulan Sorular", "Ek Notlar")
        self.assertEqual(otomatik.gate(ssssiz, "sss", [{"id": "a"}, {"id": "b"}], []),
                         "SSS bölümü yok")
        linksiz = _tam_makale().replace("aff://a", "aff://yok").replace("aff://b", "aff://yok")
        self.assertEqual(otomatik.gate(linksiz, "sss", [{"id": "a"}, {"id": "b"}], []),
                         "en az 2 ürün linki yok")

    def test_prompt_yumusak_hedefi_ve_dolgu_yasagini_soyler(self):
        t = _konu()
        metin = otomatik.build_prompt(t, _urun(), ["teleskop nasıl seçilir"], "rehber")
        self.assertIn("Yaklaşık 1200 kelime yeterli", metin)
        self.assertIn("sırf kelime sayısını artırmak için uzatma", metin)
        self.assertIn("dolgu cümle yazma", metin)
        self.assertNotIn("1700–2000", metin)
        self.assertNotIn("kelimenin altı eksik sayılır", metin)
        self.assertNotIn("Kısa giriş", metin)
        edit = otomatik.edit_prompt("taslak", _urun(), "rehber", 600)
        self.assertIn("600 kelimenin altına düşürme", edit)
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
        self.assertTrue(otomatik.genisletme_gerekli("kelime " * 500, "ticari", "STOP"))
        self.assertFalse(otomatik.genisletme_gerekli("kelime " * 700, "ticari", "STOP"))
        self.assertTrue(otomatik.genisletme_gerekli("kelime " * 700, "ticari", "MAX_TOKENS"))

    def test_uzat_kisa_taslagi_tamamlar_ve_uzun_taslage_dokunmaz(self):
        t = _konu()
        uzun = _uzun_govde()
        self.assertGreaterEqual(len(uzun.split()), otomatik.GUVENLIK_TABANI)
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
            self.assertGreaterEqual(len(out.split()), otomatik.GUVENLIK_TABANI)
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
        self.assertLess(len(out.split()), otomatik.GUVENLIK_TABANI)

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
