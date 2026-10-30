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
import struct
import sys
import zlib
from datetime import datetime
from urllib.parse import urlencode, quote as urlquote

from jinja2 import Environment, FileSystemLoader, select_autoescape

from deeplink import shop_ctas_for
from seo import extract_faq, fit_description, fit_title

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
DEFAULT_OG = "/img/og-default.png"


def public_image(url):
    """Paylaşım ve şema için mutlak görsel. Yoksa markalı varsayılan."""
    url = (url or "").strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return BASE_URL + DEFAULT_OG

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
_TR_MONTHS = (
    "", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
)


def format_tr_date(value):
    """2026-10-29 -> 29 Ekim 2026. Biçim uymuyorsa metni olduğu gibi bırak."""
    value = (value or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", value)
    if not m:
        return value
    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return value
    return f"{day} {_TR_MONTHS[month]} {year}"


_GENERIC_WORDS = {
    "en", "iyi", "yeni", "başlayan", "başlayanlar", "için", "başlangıç",
    "seti", "rehberi", "seçimi", "hakkında", "ve", "ile",
}


def _tr_key(word):
    """Turkce buyuk I/İ dahil karsilastirilabilir anahtar (casefold tek basina yetmez)."""
    w = word.replace("İ", "i").replace("I", "ı").lower()
    return re.sub(r"[\u0300-\u036f]", "", w)


def _link_phrases(article):
    """Aday ifadeler: basligin ilk 2-3 kelimesi, sonra alt kategori adi.

    Ana kategori adi (\"Teknoloji\", \"Muzik\") bilerek kullanilmaz: tek kelimelik
    genel adlar cumlenin anlamindan bagimsiz link uretiyor. Ayni sekilde
    \"Yeni Baslayanlar Icin\" gibi tamamen genel baslik kaliplari atlanir.
    """
    title = re.sub(r"^En İyi\s+", "", article["title"], flags=re.I).strip()
    out = []
    words = title.split()
    for n in (3, 2):
        if len(words) >= n:
            phrase = " ".join(words[:n]).rstrip(" :,.-–—")
            if len(phrase) < 10:
                continue
            if all(_tr_key(w) in _GENERIC_WORDS for w in phrase.split()):
                continue
            out.append(phrase)
    name = article.get("subcategory_name")
    if name and len(name) >= 5:
        out.append(name)
    return out


def inject_internal_links(html, article, all_articles, limit=3):
    """Govdede baska makalelere en fazla `limit` baglam ic linki ekler.

    Mevcut <a> bloklari ve h1-h4 basliklari korunur; ayni hedefe ikinci kez
    link verilmez, her ifade yalnizca ilk gectigi yerde linklenir.
    """
    if not html or limit <= 0:
        return html
    adaylar, gorulen = [], set()
    for other in all_articles:
        if other["slug"] == article["slug"]:
            continue
        for phrase in _link_phrases(other):
            key = phrase.casefold()
            if key in gorulen:
                continue
            gorulen.add(key)
            desen = re.compile(r"(?<![\w])" + re.escape(phrase) + r"(?![\w])", re.I)
            adaylar.append((len(phrase), desen, other["slug"]))
    if not adaylar:
        return html
    adaylar.sort(key=lambda x: -x[0])

    parcalar = re.split(r"(<[^>]+>)", html)
    eklenen, canli_hedefler, icinde_a, icinde_baslik = 0, set(), 0, 0
    for h in re.finditer(r'<a\s[^>]*href="/makale/([^"/]+)/', html, re.I):
        canli_hedefler.add(h.group(1))
    kullanilan = {article["slug"]} | canli_hedefler
    for i, parca in enumerate(parcalar):
        if parca.startswith("<"):
            low = parca.lower()
            if re.match(r"<a[\s>]", low):
                icinde_a += 1
            elif low.startswith("</a"):
                icinde_a = max(0, icinde_a - 1)
            elif re.match(r"<h[1-4][\s>]", low):
                icinde_baslik += 1
            elif re.match(r"</h[1-4]", low):
                icinde_baslik = max(0, icinde_baslik - 1)
            continue
        if icinde_a or icinde_baslik or eklenen >= limit or not parca.strip():
            continue
        for _, desen, slug in adaylar:
            if slug in kullanilan:
                continue
            m = desen.search(parca)
            if not m:
                continue
            parcalar[i] = (parca[:m.start()] + f'<a href="/makale/{slug}/">{m.group(0)}</a>'
                           + parca[m.end():])
            kullanilan.add(slug)
            eklenen += 1
            break
    return "".join(parcalar)


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
            author_meta = site.get("author") or {}
            author_name = meta.get("author") or author_meta.get("name") or "Hobi Bul Editör Ekibi"
            author_slug = meta.get("author_slug") or author_meta.get("slug") or "hobi-bul-editor"
            published = meta.get("date") or ""
            updated = meta.get("updated") or published
            image = meta.get("image") or CAT_CARD_IMG.get(meta.get("category", ""), "")
            image_alt = (meta.get("image_alt") or "").strip() or meta.get("title") or slug
            raw_title = meta.get("meta_title") or meta.get("title") or slug
            raw_desc = meta.get("meta_description") or ""
            excerpt = meta.get("excerpt") or ""
            articles.append({
                "slug": slug,
                "title": meta.get("title", slug),
                "category": meta.get("category", ""),
                "subcategory": meta.get("subcategory", ""),
                "category_name": cat_name(meta.get("category", "")),
                "subcategory_name": sub_name(meta.get("category", ""), meta.get("subcategory", "")),
                "meta_title": fit_title(raw_title),
                "meta_description": fit_description(raw_desc, extra=excerpt),
                "excerpt": excerpt,
                "faq": extract_faq(body),
                "date": published,
                "date_label": format_tr_date(published),
                "updated": updated,
                "updated_label": format_tr_date(updated),
                "author_name": author_name,
                "author_url": f"/yazar/{author_slug}/",
                "image": image,
                "image_alt": image_alt,
                "og_image": public_image(image),
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
    for a in articles:
        a["body_html"] = inject_internal_links(a["body_html"], a, articles)
    return articles


articles = load_articles()


def load_info_pages():
    """content/pages/*.md -> footer ve sitemap'e giren sabit sayfalar."""
    pdir = os.path.join(CONTENT, "pages")
    pages = []
    email = site.get("contact_email") or ""
    if not os.path.isdir(pdir):
        return pages
    for fn in sorted(os.listdir(pdir)):
        if not fn.endswith(".md"):
            continue
        meta, body = parse_article(os.path.join(pdir, fn))
        body = body.replace("{{contact_email}}", email)
        path = meta.get("path") or ("/" + fn[:-3] + "/")
        if not path.startswith("/"):
            path = "/" + path
        if not path.endswith("/"):
            path += "/"
        updated = meta.get("updated", "")
        footer_flag = str(meta.get("footer", "true")).lower()
        pages.append({
            "path": path,
            "title": meta.get("title", fn[:-3]),
            "nav": meta.get("nav", meta.get("title", fn[:-3])),
            "order": int(meta.get("order") or 100),
            "in_footer": footer_flag not in ("false", "0", "hayir", "hayır"),
            "meta_title": fit_title(meta.get("meta_title") or (meta.get("title", "") + " | " + site["site_name"])),
            "meta_description": fit_description(meta.get("meta_description") or "", extra=meta.get("title") or ""),
            "updated": updated,
            "updated_label": format_tr_date(updated),
            "body_html": render_markdown(body.strip()),
            "noindex": False,
        })
    pages.sort(key=lambda p: (p["order"], p["path"]))
    return pages


info_pages = load_info_pages()


def info_page_ld(page):
    path = page["path"]
    data = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": page["title"],
        "url": BASE_URL + path,
        "description": page.get("meta_description") or "",
        "inLanguage": "tr",
        "isPartOf": {"@type": "WebSite", "name": site["site_name"], "url": BASE_URL + "/"},
    }
    if page.get("updated"):
        data["dateModified"] = page["updated"]
    email = site.get("contact_email") or ""
    if path == "/hakkimizda/":
        data["@type"] = "AboutPage"
    elif path == "/iletisim/":
        data["@type"] = "ContactPage"
        if email:
            data["mainEntity"] = {
                "@type": "ContactPoint",
                "contactType": "customer support",
                "email": email,
                "availableLanguage": ["Turkish"],
            }
    elif path.startswith("/yazar/"):
        author = site.get("author") or {}
        data["@type"] = "ProfilePage"
        data["mainEntity"] = {
            "@type": "Organization",
            "name": author.get("name") or "Hobi Bul Editör Ekibi",
            "url": BASE_URL + path,
            "description": page.get("meta_description") or "",
        }
    return data


# ---------------------------------------------------------------- jinja
env = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=select_autoescape(["html", "xml"]),
)

def search_index():
    """Üst arama kutusu: kategori, alt kategori ve rehber."""
    rows = []
    for c in categories:
        rows.append({
            "title": c["name"],
            "url": f"/kategori/{c['slug']}/",
            "kind": "Kategori",
            "hay": " ".join(
                [c["name"], c.get("description") or ""]
                + [s["name"] for s in c["subcategories"]]
            ),
        })
        for s in c["subcategories"]:
            rows.append({
                "title": s["name"],
                "url": f"/kategori/{c['slug']}/{s['slug']}/",
                "kind": c["name"],
                "hay": f"{s['name']} {s.get('description') or ''} {c['name']}",
            })
    for a in articles:
        rows.append({
            "title": a["title"],
            "url": f"/makale/{a['slug']}/",
            "kind": a.get("category_name") or "Rehber",
            "hay": f"{a['title']} {a.get('excerpt') or ''}",
        })
    return rows


def latest_articles(n=8):
    return sorted(articles, key=lambda a: a.get("date") or "", reverse=True)[:n]


def featured_articles(n=8):
    """Son listede olmayan kategorilerden birer rehber. Sahte okunma sayısı yok."""
    latest_slugs = {a["slug"] for a in latest_articles(8)}
    latest_cats = {a["category"] for a in latest_articles(8)}
    out = []
    seen = set()
    ordered = sorted(articles, key=lambda a: a.get("date") or "", reverse=True)
    for a in ordered:
        if a["slug"] in latest_slugs or a["category"] in latest_cats or a["category"] in seen:
            continue
        seen.add(a["category"])
        out.append(a)
        if len(out) >= n:
            break
    return out


env.globals.update(
    site=site,
    links=links,
    all_categories=categories,
    cat_meta=CATEGORY_META,
    articles=articles,
    info_pages=info_pages,
    search_index=search_index(),
    default_og=BASE_URL + DEFAULT_OG,
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


def as_graph(*nodes):
    clean = []
    for node in nodes:
        if not node:
            continue
        item = dict(node)
        item.pop("@context", None)
        clean.append(item)
    return {"@context": "https://schema.org", "@graph": clean}


def breadcrumb_ld(crumbs):
    """crumbs: (ad, yol) listesi. yol / ile başlar."""
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i + 1,
                "name": name,
                "item": BASE_URL + path,
            }
            for i, (name, path) in enumerate(crumbs)
        ],
    }


def faq_ld(faqs):
    if not faqs:
        return None
    return {
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item["q"],
                "acceptedAnswer": {"@type": "Answer", "text": item["a"]},
            }
            for item in faqs
        ],
    }


def article_crumbs(a):
    crumbs = [
        ("Ana Sayfa", "/"),
        (a["category_name"], f"/kategori/{a['category']}/"),
    ]
    if a.get("subcategory"):
        crumbs.append((
            a["subcategory_name"],
            f"/kategori/{a['category']}/{a['subcategory']}/",
        ))
    crumbs.append((a["title"], f"/makale/{a['slug']}/"))
    return crumbs


def article_ld(a):
    return {
        "@type": "Article",
        "headline": a["title"],
        "image": a["og_image"],
        "datePublished": str(a["date"]),
        "dateModified": str(a.get("updated") or a["date"]),
        "description": a["meta_description"],
        "inLanguage": "tr",
        "author": {
            "@type": "Organization",
            "name": a["author_name"],
            "url": BASE_URL + a["author_url"],
        },
        "publisher": {
            "@type": "Organization",
            "name": site["site_name"],
            "url": BASE_URL + "/",
        },
        "mainEntityOfPage": BASE_URL + f"/makale/{a['slug']}/",
    }


def _png_rgba(size, pixel):
    """Saf Python PNG (8-bit RGBA). pixel(x, y, size) -> (r, g, b, a)."""
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            raw.extend(pixel(x, y, size))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")


def _favicon_pixel(x, y, n):
    """favicon.svg ile aynı yeşil hedef işareti. Köşeler saydam."""
    px, py = x + 0.5, y + 0.5
    radius = n * 0.25
    half = n / 2
    qx = abs(px - half) - (half - radius)
    qy = abs(py - half) - (half - radius)
    dist = (max(qx, 0) ** 2 + max(qy, 0) ** 2) ** 0.5 + min(max(qx, qy), 0)
    if dist > 0.8:
        return (0, 0, 0, 0)
    alpha = 255 if dist <= 0 else int(255 * (1 - dist / 0.8))
    t = (px + py) / (2 * n)
    r = int(22 + (15 - 22) * t)
    g = int(163 + (118 - 163) * t)
    b = int(74 + (110 - 74) * t)
    scale = n / 48.0
    center = ((px - half) ** 2 + (py - half) ** 2) ** 0.5
    stroke = max(1.2, 2.5 * scale)
    white = center <= 2.6 * scale
    for ring in (13.0, 6.5):
        if abs(center - ring * scale) <= stroke / 2:
            white = True
            break
    if white:
        return (255, 255, 255, alpha)
    return (r, g, b, alpha)


def write_og_image(path):
    """1200x630 markalı paylaşım görseli. Yazı tipi yoksa mevcut dosyayı bırakır."""
    font_bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    font_reg = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        if os.path.exists(path):
            return
        raise
    if not (os.path.exists(font_bold) and os.path.exists(font_reg)):
        if os.path.exists(path):
            return
        raise RuntimeError("OG görseli için DejaVu yazı tipi yok")
    w, h = 1200, 630
    img = Image.new("RGB", (w, h), "#0b0d1e")
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((40, 20, 640, 610), fill=(22, 163, 74, 58))
    gd.ellipse((720, -120, 1320, 420), fill=(15, 118, 110, 46))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    draw = ImageDraw.Draw(img)
    cx, cy = 210, 300
    draw.rounded_rectangle((cx - 118, cy - 118, cx + 118, cy + 118), radius=40, fill="#16a34a")
    draw.ellipse((cx - 78, cy - 78, cx + 78, cy + 78), outline="white", width=10)
    draw.ellipse((cx - 40, cy - 40, cx + 40, cy + 40), outline="white", width=10)
    draw.ellipse((cx - 12, cy - 12, cx + 12, cy + 12), fill="white")
    title_font = ImageFont.truetype(font_bold, 92)
    sub_font = ImageFont.truetype(font_reg, 36)
    host_font = ImageFont.truetype(font_reg, 28)
    draw.text((390, 210), "Hobi Bul", font=title_font, fill="white")
    draw.text((394, 330), "Hobini bul, ekipmanını seç.", font=sub_font, fill="#d7f5e3")
    draw.text((394, 400), "hobibul.com.tr", font=host_font, fill="#94a3b8")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path, "PNG", optimize=True)


def write_favicon(path):
    """Kök /favicon.ico. PNG gömülü ICO; dış kütüphane yok."""
    sizes = (16, 32, 48)
    blobs = [_png_rgba(s, _favicon_pixel) for s in sizes]
    count = len(blobs)
    header = struct.pack("<HHH", 0, 1, count)
    entries = b""
    payload = b""
    offset = 6 + 16 * count
    for size, blob in zip(sizes, blobs):
        entries += struct.pack("<BBBBHHII", size, size, 0, 0, 1, 32, len(blob), offset)
        payload += blob
        offset += len(blob)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(header + entries + payload)


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
    write_og_image(os.path.join(STATIC, "img", "og-default.png"))
    if os.path.isdir(STATIC):
        shutil.copytree(STATIC, SITE, dirs_exist_ok=True)
    write_favicon(os.path.join(SITE, "favicon.ico"))

    # ---- home ----
    first_article = {}
    for a in articles:
        first_article.setdefault(a["category"], a)
    render("home.html", os.path.join(SITE, "index.html"), {
        "first_article": first_article,
        "latest_articles": latest_articles(),
        "featured_articles": featured_articles(),
        "canonical_path": "/",
        "jsonld": jsonld({
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": site["site_name"],
            "url": BASE_URL + "/",
            "description": fit_description(site["default_meta"]["description"]),
            "potentialAction": {
                "@type": "SearchAction",
                "target": BASE_URL + "/?q={search_term_string}",
                "query-input": "required name=search_term_string",
            },
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
                "meta_title": fit_title(cat["meta_title"]),
                "meta_description": fit_description(cat["meta_description"], extra=cat.get("description") or ""),
            },
            "jsonld": jsonld(as_graph(
                guides_ld(cat["name"], cat_guides, cat_path, cat.get("description", "")),
                breadcrumb_ld([("Ana Sayfa", "/"), (cat["name"], cat_path)]),
            )),
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
                    "meta_title": fit_title(sub["meta_title"]),
                    "meta_description": fit_description(sub["meta_description"], extra=sub.get("description") or ""),
                },
                "jsonld": jsonld(as_graph(
                    guides_ld(sub["name"], sub_guides, sub_path, sub.get("description", "")),
                    breadcrumb_ld([
                        ("Ana Sayfa", "/"),
                        (cat["name"], cat_path),
                        (sub["name"], sub_path),
                    ]),
                )),
            })

    # ---- rehberler (tüm makaleler) ----
    render("guides.html", os.path.join(SITE, "rehberler", "index.html"), {
        "canonical_path": "/rehberler/",
    })

    # ---- hakkımızda, iletişim, yasal sayfalar, editör ----
    for page in info_pages:
        render("page.html", os.path.join(SITE, page["path"].strip("/"), "index.html"), {
            "canonical_path": page["path"],
            "page": page,
            "jsonld": jsonld(info_page_ld(page)),
        })

    # ---- makale sayfalari ----
    for a in articles:
        render("article.html", os.path.join(SITE, "makale", a["slug"], "index.html"), {
            "canonical_path": f"/makale/{a['slug']}/",
            "article": a,
            "related": related_for(a),
            "jsonld": jsonld(as_graph(
                article_ld(a),
                breadcrumb_ld(article_crumbs(a)),
                faq_ld(a.get("faq")),
            )),
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
    def lastmod(value):
        v = (value or "").strip()
        return v if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) else None

    def newest(items):
        vals = [d for d in (lastmod(x.get("updated") or x.get("date")) for x in items) if d]
        return max(vals) if vals else None

    urls = [("/", newest(articles)), ("/rehberler/", newest(articles))]
    for page in info_pages:
        urls.append((page["path"], lastmod(page.get("updated"))))
    for cat in categories:
        in_cat = [a for a in articles if a["category"] == cat["id"]]
        urls.append((f"/kategori/{cat['slug']}/", newest(in_cat)))
        for sub in cat["subcategories"]:
            in_sub = [a for a in in_cat if a.get("subcategory") == sub["id"]]
            urls.append((f"/kategori/{cat['slug']}/{sub['slug']}/", newest(in_sub)))
    for a in articles:
        urls.append((f"/makale/{a['slug']}/", lastmod(a.get("updated") or a.get("date"))))

    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u, lm in urls:
        suffix = f"<lastmod>{lm}</lastmod>" if lm else ""
        sitemap.append(f"  <url><loc>{BASE_URL}{u}</loc>{suffix}</url>")
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

    render("page.html", os.path.join(SITE, "404.html"), {
        "canonical_path": "/404.html",
        "page": {
            "title": "Sayfa bulunamadı",
            "meta_title": "Sayfa bulunamadı | " + site["site_name"],
            "meta_description": "Aradığın sayfa hobibul.com.tr üzerinde yok.",
            "updated": "",
            "updated_label": "",
            "noindex": True,
            "body_html": (
                "<p>Aradığın adres burada yok. Bağlantı eski olabilir ya da yazım hatası vardır.</p>"
                '<p><a href="/">Ana sayfaya dön</a></p>'
            ),
        },
        "jsonld": "",
    })

    # özet
    n_cat = len(categories) + sum(len(c["subcategories"]) for c in categories)
    print(f"✓ {n_cat} kategori sayfası")
    print(f"✓ {len(articles)} makale sayfası")
    print(f"✓ {len(info_pages)} bilgi sayfası")
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
