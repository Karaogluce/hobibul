#!/usr/bin/env python3
"""Hobi Bul — statik site üretici.

Veri dosyalarını (content/) ve şablonları (templates/) kullanarak
GitHub Pages'te yayınlanacak statik siteyi (site/) üretir.

Kullanım:  python build.py
"""
import json
import os
import re
import shutil
import html as html_mod
import hashlib
import sys
from datetime import datetime
from urllib.parse import urlencode, quote as urlquote

from jinja2 import Environment, FileSystemLoader, select_autoescape

from deeplink import shop_ctas_for

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(BASE, "content")
TEMPLATES = os.path.join(BASE, "templates")
STATIC = os.path.join(BASE, "static")
SITE = os.path.join(BASE, "docs")


# ---------------------------------------------------------------- loaders
def load(name):
    with open(os.path.join(CONTENT, name), encoding="utf-8") as f:
        return json.load(f)


site = load("site.json")
links = load("links.json")
categories = load("categories.json")
products = load("products.json")

BASE_URL = site["base_url"].rstrip("/")
YEAR = datetime.now().year

# global ürün haritası: id -> ürün
product_map = {}
for cat_id, subs in products.items():
    for sub_id, items in subs.items():
        for it in items:
            product_map.setdefault(it["id"], it)

# kategori id -> isim
cat_by_id = {c["id"]: c for c in categories}


def cat_name(cat_id):
    return cat_by_id.get(cat_id, {}).get("name", cat_id)


def sub_name(cat_id, sub_id):
    if not sub_id:
        return ""
    for s in (cat_by_id.get(cat_id) or {}).get("subcategories") or []:
        if s.get("id") == sub_id:
            return s.get("name", sub_id)
    return sub_id


# ---------------------------------------------------------------- affiliate
def _with_tag(url, tag):
    if not tag or re.search(r"[?&]tag=", url):
        return url
    return url + ("&" if "?" in url else "?") + "tag=" + urlquote(tag)


def affiliate_url(prod):
    net_key = prod.get("network", "amazon_tr")
    net = links["networks"].get(net_key, {})
    tag = (net.get("tag") or "").strip()
    amazon_url = str(prod.get("amazon_url") or "").strip()
    # Doğrulanmış ürün sayfası, arama linkinden önce gelir.
    if amazon_url.startswith("http") and "/dp/" in amazon_url and net_key in ("amazon_tr", "amazon"):
        return _with_tag(amazon_url, tag)
    asin = re.sub(r"[^A-Za-z0-9]", "", str(prod.get("asin") or "")).upper()
    if len(asin) == 10 and tag and net_key in ("amazon_tr", "amazon"):
        host = "www.amazon.com.tr" if net_key == "amazon_tr" else "www.amazon.com"
        return f"https://{host}/dp/{asin}?tag={urlquote(tag)}"
    if prod.get("url"):
        return prod["url"]
    if net.get("type") == "search" and net.get("base_url"):
        # Amazon TR'de Türkçe ürün adıyla ara; diğer ağlarda query alanını kullan.
        term = prod["name"] if net_key == "amazon_tr" else prod.get("query", prod["name"])
        params = {net.get("query_param", "k"): term}
        if net.get("tag_param") and net.get("tag"):
            params[net["tag_param"]] = net["tag"]
        return net["base_url"] + "?" + urlencode(params)
    return "#"


def resolve_aff(pid):
    prod = product_map.get(pid)
    return affiliate_url(prod) if prod else "#"


# kategori görsel meta (ürün görseli yer tutucuları için)
CATEGORY_META = {
    "outdoor": {"emoji": "🏕️", "c1": "#16a34a", "c2": "#15803d"},
    "el-sanatlari": {"emoji": "🧶", "c1": "#db2777", "c2": "#9d174d"},
    "muzik": {"emoji": "🎸", "c1": "#2563eb", "c2": "#1d4ed8"},
    "teknoloji": {"emoji": "🤖", "c1": "#475569", "c2": "#1e293b"},
    "koleksiyon": {"emoji": "🧩", "c1": "#d97706", "c2": "#b45309"},
    "spor-fitness": {"emoji": "🏃", "c1": "#dc2626", "c2": "#991b1b"},
    "sanat": {"emoji": "🎨", "c1": "#7c3aed", "c2": "#5b21b6"},
    "yemek-mutfak": {"emoji": "🍳", "c1": "#ea580c", "c2": "#c2410c"},
    "bahce-bitki": {"emoji": "🌱", "c1": "#65a30d", "c2": "#4d7c0f"},
    "evcil-hayvan": {"emoji": "🐾", "c1": "#0ea5e9", "c2": "#0369a1"},
    "bilim-astronomi": {"emoji": "🔭", "c1": "#6366f1", "c2": "#4338ca"},
    "seyahat-gezi": {"emoji": "✈️", "c1": "#0891b2", "c2": "#155e75"},
    "yazilim-kodlama": {"emoji": "💻", "c1": "#334155", "c2": "#0f172a"},
    "yazi-edebiyat": {"emoji": "✍️", "c1": "#a16207", "c2": "#713f12"},
}

PRODUCT_META = {}
for _cid, _slist in products.items():
    _m = CATEGORY_META.get(_cid, CATEGORY_META["outdoor"])
    for _sid, _items in _slist.items():
        for _it in _items:
            PRODUCT_META.setdefault(_it["id"], _m)

# kategori görsel listeleri (gerçek fotoğraflar): cat_id -> sub_id -> [url, ...]
CAT_IMAGES = {}
for _c in categories:
    CAT_IMAGES[_c["id"]] = {"_main": _c.get("images", [])}
    for _s in _c["subcategories"]:
        CAT_IMAGES[_c["id"]][_s["id"]] = _s.get("images", [])

# ürün id -> gerçek fotoğraf (kendi alt kategorisinin görsellerinden, sırayla)
PRODUCT_IMG = {}
for _cid, _slist in products.items():
    for _sid, _items in _slist.items():
        _imgs = CAT_IMAGES.get(_cid, {}).get(_sid, [])
        for _i, _it in enumerate(_items):
            if _imgs and not _it.get("image"):
                PRODUCT_IMG.setdefault(_it["id"], _imgs[_i % len(_imgs)])


def product_img(p):
    """Ürün görseli: `image` -> kategori gerçek fotoğrafı -> markalı SVG yer tutucu."""
    if p.get("image"):
        return p["image"]
    if PRODUCT_IMG.get(p["id"]):
        return PRODUCT_IMG[p["id"]]
    m = PRODUCT_META.get(p["id"], CATEGORY_META["outdoor"])
    emoji, c1, c2 = m["emoji"], m["c1"], m["c2"]
    brand = html_mod.escape(p.get("brand", "") or "")
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="360" viewBox="0 0 600 360">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient></defs>'
        '<rect width="600" height="360" fill="url(#g)"/>'
        '<circle cx="300" cy="150" r="74" fill="rgba(255,255,255,0.14)"/>'
        f'<text x="300" y="188" font-size="96" text-anchor="middle">{emoji}</text>'
        f'<text x="300" y="286" font-size="36" text-anchor="middle" fill="#ffffff" font-family="Arial,sans-serif" font-weight="700">{brand}</text>'
        '</svg>'
    )
    return "data:image/svg+xml," + urlquote(svg)


def cat_hero_img(cat, sub=None):
    """Kategori sayfası üst görseli: `hero` alanı varsa onu, yoksa markalı SVG banner."""
    node = sub or cat
    if node.get("hero"):
        return node["hero"]
    m = CATEGORY_META.get(cat["id"], CATEGORY_META["outdoor"])
    emoji, c1, c2 = m["emoji"], m["c1"], m["c2"]
    name = html_mod.escape(node["name"])
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="400" viewBox="0 0 1200 400">'
        '<defs><linearGradient id="hg" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient></defs>'
        '<rect width="1200" height="400" fill="url(#hg)"/>'
        '<circle cx="600" cy="170" r="96" fill="rgba(255,255,255,0.13)"/>'
        f'<text x="600" y="218" font-size="120" text-anchor="middle">{emoji}</text>'
        f'<text x="600" y="352" font-size="46" text-anchor="middle" fill="#ffffff" font-family="Arial,sans-serif" font-weight="800">{name}</text>'
        '</svg>'
    )
    return "data:image/svg+xml," + urlquote(svg)


# ---------------------------------------------------------------- markdown
def _esc(text):
    return html_mod.escape(text, quote=False)


def _make_link(label, url):
    if url.startswith("aff://"):
        pid = url[6:]
        target = resolve_aff(pid)
        if target == "#":
            return label
        net = product_map.get(pid, {}).get("network", "amazon_tr")
        return (f'<a class="aff-link" href="{target}" data-aff-link="{pid}" '
                f'data-network="{net}" target="_blank" '
                f'rel="nofollow sponsored noopener">{_esc(label)}</a>')
    if url.startswith(("http://", "https://")):
        return f'<a href="{url}" target="_blank" rel="noopener">{_esc(label)}</a>'
    return f'<a href="{url}">{_esc(label)}</a>'


def _inline(text):
    text = _esc(text)
    # links [text](url) — aff:// dahil
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: _make_link(m.group(1), m.group(2)), text)
    # bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # italic (tek yıldız)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    return text


def _is_table_sep(s):
    return bool(re.match(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$", s))


def _split_row(s):
    s = s.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def render_markdown(text):
    lines = text.split("\n")
    out = []
    in_ul = False
    in_ol = False
    i = 0

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    while i < len(lines):
        line = lines[i].rstrip()
        s = line.strip()
        if s.startswith("|") and i + 1 < len(lines) and _is_table_sep(lines[i + 1].strip()):
            close_lists()
            header = _split_row(s)
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_split_row(lines[i].strip()))
                i += 1
            width = len(header)
            out.append('<table class="pkg-table">')
            out.append("<thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in header) + "</tr></thead>")
            out.append("<tbody>")
            for row in rows:
                cells = (row + [""] * width)[:width]
                out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells) + "</tr>")
            out.append("</tbody></table>")
            continue
        if not s:
            close_lists()
            i += 1
            continue
        if s.startswith("### "):
            close_lists()
            out.append(f"<h3>{_inline(s[4:])}</h3>")
        elif s.startswith("## "):
            close_lists()
            out.append(f"<h2>{_inline(s[3:])}</h2>")
        elif s.startswith("# "):
            close_lists()
            out.append(f"<h2>{_inline(s[2:])}</h2>")
        elif re.match(r"^\d+\.\s", s):
            if not in_ol:
                close_lists()
                out.append("<ol>")
                in_ol = True
            item = re.sub(r"^\d+\.\s", "", s)
            out.append(f"<li>{_inline(item)}</li>")
        elif s.startswith(("- ", "* ", "• ")):
            if not in_ul:
                close_lists()
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{_inline(s[2:])}</li>")
        else:
            close_lists()
            out.append(f"<p>{_inline(s)}</p>")
        i += 1
    close_lists()
    return "\n".join(out)


# ---------------------------------------------------------------- articles
def parse_article(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    meta = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip('"').strip("'")
            body = parts[2]
    return meta, body


CAT_CARD_IMG = {c["id"]: c.get("card_image", "") for c in categories}


def load_articles():
    adir = os.path.join(CONTENT, "articles")
    articles = []
    if os.path.isdir(adir):
        for fn in sorted(os.listdir(adir)):
            if not fn.endswith(".md"):
                continue
            meta, body = parse_article(os.path.join(adir, fn))
            if str(meta.get("draft", "")).lower() in ("true", "1", "evet"):
                continue  # taslak: onaylanana kadar yayınlanmaz
            slug = meta.get("slug") or fn[:-3]
            starter_pid = meta.get("starter_product", "")
            starter_prod = product_map.get(starter_pid) if starter_pid else None
            articles.append({
                "slug": slug,
                "title": meta.get("title", slug),
                "category": meta.get("category", ""),
                "subcategory": meta.get("subcategory", ""),
                "category_name": cat_name(meta.get("category", "")),
                "subcategory_name": sub_name(meta.get("category", ""), meta.get("subcategory", "")),
                "meta_title": meta.get("meta_title", meta.get("title", slug)),
                "meta_description": meta.get("meta_description", ""),
                "excerpt": meta.get("excerpt", ""),
                "date": meta.get("date", f"{YEAR}"),
                "image": meta.get("image") or CAT_CARD_IMG.get(meta.get("category", ""), ""),
                "image_alt": meta.get("image_alt", meta.get("title", slug)),
                "image_credit": meta.get("image_credit", ""),
                "image_credit_url": meta.get("image_credit_url", ""),
                "starter_text": meta.get("starter_text", ""),
                "starter_label": meta.get("starter_label", ""),
                "starter_product": starter_pid,
                "starter_url": affiliate_url(starter_prod) if starter_prod else "",
                "starter_network": (starter_prod or {}).get("network", "amazon_tr"),
                "body_html": render_markdown(body.strip()),
                "word_count": len(body.split()),
            })
    return articles


articles = load_articles()


# ---------------------------------------------------------------- jinja
env = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=select_autoescape(["html", "xml"]),
)

env.globals.update(
    site=site,
    links=links,
    all_categories=categories,
    cat_meta=CATEGORY_META,
    articles=articles,
    year=YEAR,
    base_url=BASE_URL,
    shop_ctas_for=shop_ctas_for,
)


def _aff_filter(prod):
    return affiliate_url(prod)


env.filters["affiliate"] = _aff_filter
env.filters["product_img"] = product_img



def render(tpl, out_path, ctx):
    tmpl = env.get_template(tpl)
    html_out = tmpl.render(**ctx)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_out)
    return out_path


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def jsonld(obj):
    return json.dumps(obj, ensure_ascii=False)


# ---------------------------------------------------------------- build
def main():
    gid = site.get("ga4_id", "")
    if not gid.startswith("G-") or "XXX" in gid:
        print(f"! GA4 ölçüm kimliği ayarlı değil (content/site.json → ga4_id = {gid!r}). "
              "Gerçek G-... kodu yazılmadığı sürece Analytics'e veri gitmez ve panel boş kalır.")
    if os.path.isdir(SITE):
        shutil.rmtree(SITE)
    os.makedirs(SITE)

    # statik dosyalar
    if os.path.isdir(STATIC):
        shutil.copytree(STATIC, SITE, dirs_exist_ok=True)

    # ---- home ----
    first_article = {}
    for a in articles:
        first_article.setdefault(a["category"], a)
    render("home.html", os.path.join(SITE, "index.html"), {
        "first_article": first_article,
        "canonical_path": "/",
        "jsonld": jsonld({
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": site["site_name"],
            "url": BASE_URL,
            "description": site["default_meta"]["description"],
        }),
    })

    # ---- kategori sayfalari (ürün listesi yok; yayınlanmış rehberler) ----
    for cat in categories:
        cat_path = f"/kategori/{cat['slug']}/"
        cat_guides = articles_for(cat["id"])
        render("category.html", os.path.join(SITE, "kategori", cat["slug"], "index.html"), {
            "canonical_path": cat_path,
            "cat": cat,
            "sub": None,
            "cat_articles": cat_guides,
            "hero_img": cat_hero_img(cat),
            "page": {
                "name": cat["name"],
                "heading": cat["name"],
                "description": cat["description"],
                "meta_title": cat["meta_title"],
                "meta_description": cat["meta_description"],
            },
            "jsonld": jsonld(guides_ld(cat["name"], cat_guides, cat_path, cat.get("description", ""))),
        })
        for sub in cat["subcategories"]:
            sub_path = f"/kategori/{cat['slug']}/{sub['slug']}/"
            sub_guides = articles_for(cat["id"], sub["id"])
            render("category.html", os.path.join(SITE, "kategori", cat["slug"], sub["slug"], "index.html"), {
                "canonical_path": sub_path,
                "cat": cat,
                "sub": sub,
                "cat_articles": sub_guides,
                "hero_img": cat_hero_img(cat, sub),
                "page": {
                    "name": sub["name"],
                    "heading": sub["name"],
                    "description": sub["description"],
                    "meta_title": sub["meta_title"],
                    "meta_description": sub["meta_description"],
                },
                "jsonld": jsonld(guides_ld(sub["name"], sub_guides, sub_path, sub.get("description", ""))),
            })

    # ---- rehberler (tüm makaleler) ----
    render("guides.html", os.path.join(SITE, "rehberler", "index.html"), {
        "canonical_path": "/rehberler/",
    })

    # ---- makale sayfalari ----
    for a in articles:
        render("article.html", os.path.join(SITE, "makale", a["slug"], "index.html"), {
            "canonical_path": f"/makale/{a['slug']}/",
            "article": a,
            "related": related_for(a),
            "jsonld": jsonld({
                "@context": "https://schema.org",
                "@type": "Article",
                "headline": a["title"],
                "image": a["image"],
                "datePublished": str(a["date"]),
                "description": a["meta_description"],
                "inLanguage": "tr",
                "publisher": {"@type": "Organization", "name": site["site_name"]},
            }),
        })

    # ---- eski/yanlış adresler için yönlendirme sayfaları (GitHub Pages 301 vermez) ----
    for old, new in REDIRECTS.items():
        write(os.path.join(SITE, old.strip("/"), "index.html"),
              '<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8">'
              f'<title>Yönlendiriliyor…</title><link rel="canonical" href="{BASE_URL}{new}">'
              f'<meta http-equiv="refresh" content="0;url={new}"><meta name="robots" content="noindex">'
              f'</head><body><a href="{new}">Devam et</a></body></html>')

    # ---- dashboard ----
    render("dashboard.html", os.path.join(SITE, "dashboard", "index.html"), {
        "canonical_path": "/dashboard/",
        "jsonld": "",
        "articles_json": json.dumps(
            [{"path": f"/makale/{a['slug']}/", "title": a["title"]} for a in articles],
            ensure_ascii=False,
        ),
        "ga4_json": json.dumps(load_ga4(), ensure_ascii=False
        ),
    })

    # ---- config.js (analitik) ----
    an = site.get("analytics", {})
    pw = site.get("dashboard_password", "") or ""
    cfg = {
        "supabaseUrl": an.get("supabase_url", ""),
        "supabaseAnonKey": an.get("supabase_anon_key", ""),
        "dashboardHash": hashlib.sha256(pw.encode("utf-8")).hexdigest() if pw else "",
    }
    write(os.path.join(SITE, "js", "config.js"),
          "window.HOBIBUL_CONFIG = " + json.dumps(cfg, ensure_ascii=False) + ";\n")

    # ---- sitemap + robots + CNAME + 404 ----
    urls = ["/", "/rehberler/"]
    for cat in categories:
        urls.append(f"/kategori/{cat['slug']}/")
        for sub in cat["subcategories"]:
            urls.append(f"/kategori/{cat['slug']}/{sub['slug']}/")
    for a in articles:
        urls.append(f"/makale/{a['slug']}/")

    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        sitemap.append(f"  <url><loc>{BASE_URL}{u}</loc></url>")
    sitemap.append("</urlset>")
    write(os.path.join(SITE, "sitemap.xml"), "\n".join(sitemap))

    write(os.path.join(SITE, "robots.txt"),
          "User-agent: *\nAllow: /\nDisallow: /dashboard/\n\n"
          f"Sitemap: {BASE_URL}/sitemap.xml\n")

    # IndexNow doğrulama dosyası: kökte yayınlanır, indexnow.py bunu bildirir
    inkey = (site.get("indexnow_key") or "").strip()
    if inkey:
        write(os.path.join(SITE, inkey + ".txt"), inkey + "\n")

    # Search Console HTML dosyası. Alan boşsa dosya üretilmez.
    gfile = (site.get("google_site_verification_file") or "").strip()
    if gfile and "/" not in gfile and "\\" not in gfile and ".." not in gfile:
        body = (site.get("google_site_verification_file_content") or "").strip()
        if not body:
            body = "google-site-verification: " + gfile
        write(os.path.join(SITE, gfile), body + "\n")

    write(os.path.join(SITE, "CNAME"), site["domain"] + "\n")

    write(os.path.join(SITE, "404.html"),
          "<!DOCTYPE html><html lang=\"tr\"><head><meta charset=\"utf-8\">"
          "<title>Sayfa Bulunamadı | " + site["site_name"] + "</title>"
          "<meta http-equiv=\"refresh\" content=\"5;url=/\"></head>"
          "<body style=\"font-family:sans-serif;text-align:center;padding:4rem\">"
          "<h1>404 — Sayfa Bulunamadı</h1><p>Ana sayfaya yönlendiriliyorsunuz…</p>"
          "<a href=\"/\">Ana Sayfa</a></body></html>")

    # özet
    n_cat = len(categories) + sum(len(c["subcategories"]) for c in categories)
    print(f"✓ {n_cat} kategori sayfası")
    print(f"✓ {len(articles)} makale sayfası")
    print(f"✓ 1 ana sayfa + 1 dashboard + sitemap + robots + CNAME + 404"
          + (" + IndexNow anahtarı" if inkey else ""))
    print(f"✓ Çıktı: {SITE}")


REDIRECTS = {"/outdoor/": "/kategori/outdoor/"}


def load_ga4():
    p = os.path.join(CONTENT, "analytics_ga4.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return None


def articles_for(cat_id, sub_id=None):
    """Ana kategoride o kategorinin rehberleri; alt kategoride yalnızca eşleşenler."""
    out = []
    for a in articles:
        if a.get("category") != cat_id:
            continue
        sub = a.get("subcategory") or ""
        if sub_id and sub != sub_id:
            continue
        out.append(a)
    out.sort(key=lambda a: a.get("date") or "", reverse=True)
    return out


def related_for(a, n=3):
    """Önce aynı alt kategori, sonra aynı kategori, sonra diğer rehberler."""
    others = [x for x in articles if x["slug"] != a["slug"]]

    def newest(rows):
        return sorted(rows, key=lambda x: x.get("date") or "", reverse=True)

    sub = a.get("subcategory") or ""
    same_sub = newest([
        x for x in others
        if sub and x.get("category") == a.get("category") and (x.get("subcategory") or "") == sub
    ])
    same_cat = newest([
        x for x in others
        if x.get("category") == a.get("category") and x not in same_sub
    ])
    rest = newest([x for x in others if x.get("category") != a.get("category")])
    return (same_sub + same_cat + rest)[:n]


def guides_ld(name, guides, page_url, description=""):
    """Kategori sayfası şeması: rehberler varsa ItemList, yoksa boş koleksiyon."""
    page = BASE_URL + page_url
    if not guides:
        data = {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": name,
            "url": page,
        }
        if description:
            data["description"] = description
        return data
    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"{name} rehberleri",
        "url": page,
        "numberOfItems": len(guides),
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i + 1,
                "name": a["title"],
                "url": f"{BASE_URL}/makale/{a['slug']}/",
            }
            for i, a in enumerate(guides)
        ],
    }


if __name__ == "__main__":
    main()
