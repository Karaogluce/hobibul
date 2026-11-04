#!/usr/bin/env python3
"""Hobi Bul — GA4 ve Search Console günlük veri çekici.

GA4 Data API'den (sunucu tarafında, servis hesabıyla) son 30 günün
tekil kullanıcı/trafik kaynağı/en çok okunan sayfa verisini çekip
content/analytics_ga4.json dosyasına yazar. Aynı kimlikle Search Console
searchAnalytics.query çağrılır; son 28 gün content/analytics_gsc.json
dosyasına yazılır. Bu dosyalar GÜVENLİDİR: gizli anahtar içermez, sadece
özet sayılar içerir ve siteyle birlikte herkese açık yayınlanır (panel okur).

Neden tarayıcıdan değil, burada (GitHub Actions'ta) çalışır:
GA4 Data API bir servis hesabı anahtarı ister; bu anahtar tarayıcıda
çalışan koda asla konulmaz, yoksa herkes senin GA4 hesabına erişebilir.
Bu script SADECE GitHub Actions'ın güvenli ortamında, GA4_SERVICE_ACCOUNT_JSON
secret'ından okuyarak çalışır.

Ortam değişkenleri (GitHub Secrets'tan gelir):
  GA4_PROPERTY_ID          — GA4 mülk numarası, örn. 123456789 (G- ile başlayan ölçüm kodu DEĞİL)
  GA4_SERVICE_ACCOUNT_JSON — servis hesabı JSON anahtarının tüm içeriği (tek satır/çok satır, aynen)
"""
import json
import os
import re
import sys
from datetime import date, timedelta
from urllib.parse import quote

CONTENT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content")
OUT = os.path.join(CONTENT, "analytics_ga4.json")
GSC_OUT = os.path.join(CONTENT, "analytics_gsc.json")
DAYS = 30
GSC_DAYS = 28
GSC_ROW_LIMIT = 25
GA4_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
GSC_QUERY = "https://www.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"


def load_articles():
    """slug -> başlık eşleşmesi (en çok okunan sayfayı makale başlığıyla göstermek için)."""
    out = {}
    adir = os.path.join(CONTENT, "articles")
    if not os.path.isdir(adir):
        return out
    import re
    for fn in os.listdir(adir):
        if not fn.endswith(".md"):
            continue
        with open(os.path.join(adir, fn), encoding="utf-8") as f:
            head = f.read().split("---", 2)
        if len(head) >= 3:
            t = re.search(r'title:\s*"([^"]*)"', head[1])
            if t:
                out[fn[:-3]] = t.group(1)
    return out


def main():
    prop = os.environ.get("GA4_PROPERTY_ID", "").strip()
    sa_json = os.environ.get("GA4_SERVICE_ACCOUNT_JSON", "").strip()
    if not prop or not sa_json:
        sys.exit("GA4_PROPERTY_ID ve GA4_SERVICE_ACCOUNT_JSON ortam değişkenleri gerekli.")

    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            DateRange, Dimension, Metric, OrderBy, RunReportRequest,
        )
        from google.oauth2 import service_account
    except ImportError:
        sys.exit("google-analytics-data paketi yok. requirements: pip install google-analytics-data")

    try:
        info = json.loads(sa_json)
    except json.JSONDecodeError as e:
        sys.exit(f"GA4_SERVICE_ACCOUNT_JSON geçerli JSON değil: {e}")

    creds = service_account.Credentials.from_service_account_info(
        info, scopes=[GA4_SCOPE, GSC_SCOPE])
    client = BetaAnalyticsDataClient(credentials=creds)
    date_range = [DateRange(start_date=f"{DAYS}daysAgo", end_date="today")]
    hata = 0

    # ---- 1) günlük tekil kullanıcı ----
    visitors = []
    try:
        r = client.run_report(RunReportRequest(
            property=f"properties/{prop}",
            dimensions=[Dimension(name="date")],
            metrics=[Metric(name="activeUsers")],
            date_ranges=date_range,
            order_bys=[OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date"))],
        ))
        for row in r.rows:
            d = row.dimension_values[0].value  # YYYYMMDD
            visitors.append({"date": f"{d[:4]}-{d[4:6]}-{d[6:]}", "users": int(row.metric_values[0].value)})
    except Exception as e:
        hata += 1
        print(f"! Ziyaretçi verisi çekilemedi: {e}")

    # ---- 2) trafik kaynakları ----
    channels = []
    try:
        r = client.run_report(RunReportRequest(
            property=f"properties/{prop}",
            dimensions=[Dimension(name="sessionDefaultChannelGroup")],
            metrics=[Metric(name="sessions")],
            date_ranges=date_range,
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
            limit=8,
        ))
        for row in r.rows:
            channels.append({"name": row.dimension_values[0].value, "sessions": int(row.metric_values[0].value)})
    except Exception as e:
        hata += 1
        print(f"! Trafik kaynağı verisi çekilemedi: {e}")

    # ---- 3) en çok okunan sayfalar (yalnızca makale sayfaları) ----
    pages = []
    try:
        r = client.run_report(RunReportRequest(
            property=f"properties/{prop}",
            dimensions=[Dimension(name="pagePath")],
            metrics=[Metric(name="screenPageViews")],
            date_ranges=date_range,
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="screenPageViews"), desc=True)],
            limit=50,
        ))
        titles = load_articles()
        for row in r.rows:
            path = row.dimension_values[0].value.rstrip("/")
            if not path.startswith("/makale/"):
                continue
            slug = path.split("/")[-1]
            pages.append({
                "path": path + "/",
                "slug": slug,
                "title": titles.get(slug, slug),
                "views": int(row.metric_values[0].value),
            })
        pages = pages[:10]
    except Exception as e:
        hata += 1
        print(f"! Sayfa verisi çekilemedi: {e}")

    if hata == 3:
        sys.exit("GA4 Data API üç raporu da döndüremedi; mevcut veri korunuyor, boş dosya yazılmadı. "
                 "GA4_PROPERTY_ID'nin sayısal mülk numarası olduğunu ve servis hesabı e-postasının "
                 "o mülkte 'Görüntüleyen' yetkisine sahip olduğunu kontrol et.")
    if not visitors and not channels and not pages:
        print("! GA4 üç rapor için de 0 satır döndürdü. Olası nedenler:")
        print("  - siteye gerçek GA4 ölçüm kodu ekli değil (aşağıdaki kontrol)")
        print("  - GA4 mülkünde henüz trafik yok (yeni kurulumda veri 24-48 saati bulabilir)")
        print("  - yanlış GA4_PROPERTY_ID")
        try:
            with open(os.path.join(CONTENT, "site.json"), encoding="utf-8") as f:
                gid = json.load(f).get("ga4_id", "")
            if not gid.startswith("G-") or "XXX" in gid:
                print(f"  ! content/site.json ga4_id = {gid!r} (placeholder). "
                      "GA4 → Yönetici → Veri akışları → Ölçüm kimliği (G-...) buraya yazılmalı.")
        except Exception:
            pass

    out = {
        "generated_at": date.today().isoformat(),
        "period_days": DAYS,
        "visitors_daily": visitors,
        "channels": channels,
        "top_pages": pages,
    }
    os.makedirs(CONTENT, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"✓ content/analytics_ga4.json yazıldı ({len(visitors)} gün, {len(channels)} kanal, {len(pages)} sayfa)")
    publish_gsc(info, CONTENT)


def gsc_property_candidates(value, domain):
    """Config sabit bir mülk verirse yalnız onu dene; auto ise domain ve URL-prefix."""
    raw = (value or "").strip()
    host = re.sub(r"^https?://", "", (domain or "").strip(), flags=re.I).strip("/")
    if raw and raw.lower() != "auto":
        return [raw]
    if not host:
        return []
    return [f"sc-domain:{host}", f"https://{host}/"]


def gsc_note(status, text):
    """API hata metnini kısalt. Anahtar veya pem bloğu loga düşmesin."""
    blob = text or ""
    blob = re.sub(r"-----BEGIN [^-]+-----.*?-----END [^-]+-----", "[gizli]", blob, flags=re.S)
    blob = re.sub(r'"private_key"\s*:\s*"[^"]*"', '"private_key":"[gizli]"', blob)
    message = ""
    try:
        err = json.loads(blob).get("error") or {}
        message = str(err.get("message") or "")
    except (json.JSONDecodeError, AttributeError):
        message = ""
    message = re.sub(r"\s+", " ", message).strip()
    if not message:
        message = f"HTTP {status}"
    return message[:180]


def _gsc_post(session, site_url, body):
    url = GSC_QUERY.format(site=quote(site_url, safe=""))
    resp = session.post(url, json=body, timeout=60)
    return resp.status_code, getattr(resp, "text", "") or ""


def _rows(payload, key):
    out = []
    for row in (payload or {}).get("rows") or []:
        keys = row.get("keys") or [""]
        out.append({
            key: keys[0],
            "clicks": int(row.get("clicks") or 0),
            "impressions": int(row.get("impressions") or 0),
            "ctr": round(float(row.get("ctr") or 0), 4),
            "position": round(float(row.get("position") or 0), 2),
        })
    return out


def fill_gsc_daily(rows, start, end):
    by = {r["date"]: r for r in rows}
    out, day = [], start
    while day <= end:
        hit = by.get(day.isoformat())
        out.append({
            "date": day.isoformat(),
            "clicks": int(hit["clicks"]) if hit else 0,
            "impressions": int(hit["impressions"]) if hit else 0,
        })
        day += timedelta(days=1)
    return out


def collect_gsc(session, candidates, start, end):
    """İlk çalışan mülkten sorgu, sayfa ve günlük trendi topla.

    Dönüş: (veri, not). veri None ise hiçbir mülk 200 vermedi.
    """
    body_base = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dataState": "all",
        "type": "web",
    }
    last = "erişim yok"
    for site in candidates:
        code, text = _gsc_post(session, site, dict(body_base, dimensions=["query"], rowLimit=GSC_ROW_LIMIT))
        if code != 200:
            last = gsc_note(code, text)
            continue
        try:
            queries = _rows(json.loads(text), "query")
        except json.JSONDecodeError:
            return None, "yanıt okunamadı"
        code_p, text_p = _gsc_post(session, site, dict(body_base, dimensions=["page"], rowLimit=GSC_ROW_LIMIT))
        code_d, text_d = _gsc_post(session, site, dict(body_base, dimensions=["date"], rowLimit=1000))
        if code_p != 200 or code_d != 200:
            return None, gsc_note(code_p if code_p != 200 else code_d, text_p if code_p != 200 else text_d)
        try:
            pages = _rows(json.loads(text_p), "page")
            daily = _rows(json.loads(text_d), "date")
        except json.JSONDecodeError:
            return None, "yanıt okunamadı"
        pages.sort(key=lambda r: (-r["clicks"], -r["impressions"], r["page"]))
        queries.sort(key=lambda r: (-r["clicks"], -r["impressions"], r["query"]))
        return {
            "ok": True,
            "generated_at": end.isoformat() if end == date.today() else date.today().isoformat(),
            "period_days": GSC_DAYS,
            "property": site,
            "queries": queries,
            "pages": pages,
            "daily": fill_gsc_daily(daily, start, end),
        }, ""
    return None, last


def _gsc_dates(today):
    end = today
    start = today - timedelta(days=GSC_DAYS - 1)
    return start, end


def _write_json(path, payload):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
        f.write("\n")


def _keep_previous_gsc(path):
    if not os.path.exists(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            old = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False
    if not old.get("ok"):
        return False
    return bool(old.get("queries") or old.get("pages") or old.get("daily"))


def _mark_gsc_missing(path, today):
    _write_json(path, {
        "ok": False,
        "generated_at": today.isoformat(),
        "period_days": GSC_DAYS,
        "queries": [],
        "pages": [],
        "daily": [],
    })


def _gsc_session(info):
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    creds = service_account.Credentials.from_service_account_info(info, scopes=[GSC_SCOPE])
    return AuthorizedSession(creds)


def publish_gsc(info, content_dir, today=None, session=None):
    """Search Console özetini yaz. Hata olursa GA4'ü bozmadan yumuşak çıkar."""
    today = today or date.today()
    path = os.path.join(content_dir, "analytics_gsc.json")
    try:
        with open(os.path.join(content_dir, "site.json"), encoding="utf-8") as f:
            site = json.load(f)
        domain = site.get("domain") or "hobibul.com.tr"
        candidates = gsc_property_candidates(site.get("gsc_property"), domain)
        if not candidates:
            print("! Search Console mülkü yok. GA4 yayını sürüyor.")
            if not _keep_previous_gsc(path):
                _mark_gsc_missing(path, today)
            return False
        if session is None:
            session = _gsc_session(info)
        start, end = _gsc_dates(today)
        data, note = collect_gsc(session, candidates, start, end)
        if not data:
            print(f"! Search Console alınamadı ({note}). GA4 yayını sürüyor.")
            if not _keep_previous_gsc(path):
                _mark_gsc_missing(path, today)
            return False
        data["generated_at"] = today.isoformat()
        _write_json(path, data)
        print(f"✓ content/analytics_gsc.json yazıldı ({data['property']}, "
              f"{len(data['queries'])} sorgu, {len(data['pages'])} sayfa, {len(data['daily'])} gün)")
        return True
    except Exception as e:
        kind = type(e).__name__
        print(f"! Search Console adımı tamamlanamadı ({kind}). GA4 yayını sürüyor.")
        try:
            if not _keep_previous_gsc(path):
                _mark_gsc_missing(path, today)
        except OSError:
            print("! Search Console boş kaydı da yazılamadı. GA4 dosyası duruyor.")
        return False


if __name__ == "__main__":
    main()
