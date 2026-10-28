#!/usr/bin/env python3
"""Hobi Bul — GA4 günlük veri çekici.

GA4 Data API'den (sunucu tarafında, servis hesabıyla) son 30 günün
tekil kullanıcı/trafik kaynağı/en çok okunan sayfa verisini çekip
content/analytics_ga4.json dosyasına yazar. Bu dosya GÜVENLİDİR:
GA4'ün kendisine ait gizli anahtar içermez, sadece özet sayılar içerir
ve siteyle birlikte herkese açık yayınlanır (panel bu dosyayı okur).

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
import sys
from datetime import date, timedelta

CONTENT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content")
OUT = os.path.join(CONTENT, "analytics_ga4.json")
DAYS = 30


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
        info, scopes=["https://www.googleapis.com/auth/analytics.readonly"])
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


if __name__ == "__main__":
    main()
