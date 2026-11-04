"""Search Console mülk seçimi ve yumuşak hata. Ağ yok."""
import json
import os
import tempfile
import unittest
from datetime import date

import fetch_analytics as fa


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self.text = payload if isinstance(payload, str) else json.dumps(payload)


class _Session:
    def __init__(self, by_site):
        self.by_site = by_site
        self.urls = []

    def post(self, url, json=None, timeout=None):
        self.urls.append(url)
        for site, handler in self.by_site.items():
            if fa.quote(site, safe="") in url:
                return handler(json or {})
        return _Resp(404, {"error": {"message": "yok"}})


def _rows(key, values):
    return {"rows": [{
        "keys": [key],
        "clicks": values[0],
        "impressions": values[1],
        "ctr": values[2],
        "position": values[3],
    }]}


class AdayTest(unittest.TestCase):
    def test_auto_iki_mulk(self):
        self.assertEqual(
            fa.gsc_property_candidates("auto", "hobibul.com.tr"),
            ["sc-domain:hobibul.com.tr", "https://hobibul.com.tr/"])
        self.assertEqual(
            fa.gsc_property_candidates("", "https://hobibul.com.tr/"),
            ["sc-domain:hobibul.com.tr", "https://hobibul.com.tr/"])

    def test_sabit_deger_tek_aday(self):
        self.assertEqual(
            fa.gsc_property_candidates("sc-domain:hobibul.com.tr", "hobibul.com.tr"),
            ["sc-domain:hobibul.com.tr"])
        self.assertEqual(
            fa.gsc_property_candidates("https://hobibul.com.tr/", "hobibul.com.tr"),
            ["https://hobibul.com.tr/"])


class ToplamaTest(unittest.TestCase):
    def test_domain_403_sonra_url_prefix(self):
        start, end = date(2026, 10, 8), date(2026, 11, 4)

        def handle(body):
            dim = body["dimensions"][0]
            if dim == "query":
                return _Resp(200, _rows("bonsai makası", (3, 40, 0.075, 6.2)))
            if dim == "page":
                return _Resp(200, _rows("https://hobibul.com.tr/makale/bonsai/", (2, 10, 0.2, 4)))
            return _Resp(200, _rows("2026-11-04", (1, 5, 0.2, 3)))

        session = _Session({
            "sc-domain:hobibul.com.tr": lambda body: _Resp(403, {"error": {"message": "forbidden"}}),
            "https://hobibul.com.tr/": handle,
        })
        data, note = fa.collect_gsc(
            session, ["sc-domain:hobibul.com.tr", "https://hobibul.com.tr/"], start, end)
        self.assertEqual(note, "")
        self.assertEqual(data["property"], "https://hobibul.com.tr/")
        self.assertEqual(data["queries"][0]["query"], "bonsai makası")
        self.assertEqual(data["queries"][0]["clicks"], 3)
        self.assertEqual(len(data["daily"]), 28)
        self.assertEqual(data["daily"][0]["date"], "2026-10-08")
        self.assertEqual(data["daily"][0]["clicks"], 0)
        self.assertEqual(data["daily"][-1]["impressions"], 5)
        self.assertTrue(any("sc-domain%3Ahobibul.com.tr" in u for u in session.urls))
        self.assertTrue(any("https%3A%2F%2Fhobibul.com.tr%2F" in u for u in session.urls))

    def test_sabit_mulk_digerini_denemez(self):
        session = _Session({
            "sc-domain:hobibul.com.tr": lambda body: _Resp(403, {"error": {"message": "User does not have sufficient permission"}}),
        })
        data, note = fa.collect_gsc(
            session, ["sc-domain:hobibul.com.tr"], date(2026, 11, 1), date(2026, 11, 4))
        self.assertIsNone(data)
        self.assertIn("permission", note)
        self.assertEqual(len(session.urls), 1)

    def test_not_anahtar_yazmaz(self):
        note = fa.gsc_note(403, json.dumps({
            "error": {"message": "forbidden"},
            "private_key": "-----BEGIN PRIVATE KEY-----\nSECRET\n-----END PRIVATE KEY-----\n",
        }))
        self.assertNotIn("SECRET", note)
        self.assertNotIn("BEGIN", note)


class YayinTest(unittest.TestCase):
    def test_hata_ga4_dosyasina_dokunmaz_ve_mesaj_kaydi_yazar(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "site.json"), "w", encoding="utf-8") as f:
                json.dump({"domain": "hobibul.com.tr", "gsc_property": "auto"}, f)
            ga4 = os.path.join(d, "analytics_ga4.json")
            with open(ga4, "w", encoding="utf-8") as f:
                f.write('{"visitors_daily":[{"users":1}]}')
            session = _Session({})
            ok = fa.publish_gsc({}, d, today=date(2026, 11, 4), session=session)
            self.assertFalse(ok)
            with open(ga4, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["visitors_daily"][0]["users"], 1)
            with open(os.path.join(d, "analytics_gsc.json"), encoding="utf-8") as f:
                gsc = json.load(f)
            self.assertFalse(gsc["ok"])
            self.assertEqual(gsc["queries"], [])

    def test_eski_basarili_veri_hata_sonrasi_kalir(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "site.json"), "w", encoding="utf-8") as f:
                json.dump({"domain": "hobibul.com.tr", "gsc_property": "https://hobibul.com.tr/"}, f)
            previous = {
                "ok": True,
                "queries": [{"query": "kamp", "clicks": 2, "impressions": 9, "ctr": 0.2, "position": 3}],
                "pages": [],
                "daily": [{"date": "2026-11-03", "clicks": 2, "impressions": 9}],
            }
            with open(os.path.join(d, "analytics_gsc.json"), "w", encoding="utf-8") as f:
                json.dump(previous, f)
            session = _Session({
                "https://hobibul.com.tr/": lambda body: _Resp(403, {"error": {"message": "forbidden"}}),
            })
            fa.publish_gsc({}, d, today=date(2026, 11, 4), session=session)
            with open(os.path.join(d, "analytics_gsc.json"), encoding="utf-8") as f:
                self.assertEqual(json.load(f)["queries"][0]["query"], "kamp")


if __name__ == "__main__":
    unittest.main()
