#!/usr/bin/env python3
"""Admitad deeplink üretici.

Biçim: <taban>?ulp=<urlencode edilmiş hedef URL>.
Anahtar kelime kategori eşlemesinden gelir (content/links.json → shop_topics).
Amazon arama linkleri ve Trendyol / Hepsiburada arama şablonları bu modülde üretilmez.
"""
import json
import os
import re
from urllib.parse import quote, quote_plus, unquote

BASE = os.path.dirname(os.path.abspath(__file__))
LINKS_PATH = os.path.join(BASE, "content", "links.json")

# Düğme sırası. Sözlük sırasına bırakılmaz.
SHOP_ORDER = ("aliexpress", "geekbuying")

_TR = str.maketrans({
    "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
    "Ç": "c", "Ğ": "g", "İ": "i", "I": "i", "Ö": "o", "Ş": "s", "Ü": "u",
    "â": "a", "î": "i", "û": "u", "Â": "a", "Î": "i", "Û": "u",
})


def load_links(path=None):
    with open(path or LINKS_PATH, encoding="utf-8") as f:
        return json.load(f)


def keyword_slug(keyword):
    """AliExpress toptan yolu: boşluklar tire, Türkçe harfler sadeleşir."""
    text = str(keyword or "").strip().translate(_TR).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def fill_target(template, keyword, style):
    """Hedef mağaza arama URL'si. Sorgu değerini bir kez kodlar."""
    template = str(template or "")
    if style == "slug":
        slug = keyword_slug(keyword)
        if not slug or "{slug}" not in template:
            return ""
        return template.replace("{slug}", slug)
    kw = " ".join(str(keyword or "").split())
    if not kw or "{keyword}" not in template:
        return ""
    return template.replace("{keyword}", quote_plus(kw))


def admitad_deeplink(base_url, target_url):
    """<taban>?ulp=<hedef URL'nin tam kodlanmış hali>.

    Hedefin içindeki ?, &, = ve / de kodlanır. Çözülünce hedef adres birebir çıkar.
    """
    base = str(base_url or "").strip()
    target = str(target_url or "").strip()
    if not base or not target.startswith("http"):
        return ""
    sep = "&" if "?" in base else "?"
    return base + sep + "ulp=" + quote(target, safe="")


def _topic_spec(topics, cat, sub):
    """Alt kategori kaydı varsa onu kullan. Yoksa ana kategoriye düş.

    Ana kategoriye düşmek, yeni açılan el sanatları veya teknoloji alt
    konularının da CTA almasını sağlar. Outdoor gibi karışık kategorilerde
    ana kayıt olmadığı için kamp yazısı balıkçılık linki almaz.
    """
    sub = str(sub or "").strip()
    if sub in ("", "_main"):
        sub = ""
    if sub:
        exact = topics.get(f"{cat}/{sub}")
        if exact is not None:
            return exact or {}
    return topics.get(cat) or {}


def _lead(links):
    places = [c["locative"] for c in links]
    if len(places) == 1:
        return f"Aynı malzemeye {places[0]} de bakabilirsin."
    if len(places) == 2:
        return f"Aynı malzemeye {places[0]} ve {places[1]} de bakabilirsin."
    return "Aynı malzemeye " + ", ".join(places[:-1]) + " ve " + places[-1] + " de bakabilirsin."


def shop_ctas_for(cat, sub="", links=None):
    """Eşleşen mağaza düğmeleri. links verilmezse content/links.json okunur.

    Dönüş: {"lead": str, "links": [{"network", "name", "label", "locative",
    "keyword", "href", "target_url", "track_id"}, ...]}
    """
    data = links if links is not None else load_links()
    networks = data.get("networks") or {}
    spec = _topic_spec(data.get("shop_topics") or {}, cat, sub)
    out = []
    for key in SHOP_ORDER:
        keyword = str(spec.get(key) or "").strip()
        if not keyword:
            continue
        net = networks.get(key) or {}
        if net.get("type") != "deeplink" or not net.get("active", True):
            continue
        target = fill_target(net.get("target_url", ""), keyword, net.get("keyword_style", "query"))
        href = admitad_deeplink(net.get("base_url", ""), target)
        if not href:
            continue
        out.append({
            "network": key,
            "name": net.get("name") or key,
            "label": net.get("label") or key,
            "locative": net.get("locative") or (net.get("name") or key),
            "keyword": keyword,
            "href": href,
            "target_url": target,
            "track_id": f"{key}:{keyword_slug(keyword)}",
        })
    return {"lead": _lead(out) if out else "", "links": out}


def _self_check():
    links = load_links()
    ae_net = links["networks"]["aliexpress"]
    target = fill_target(ae_net["target_url"], "knitting yarn", "slug")
    assert target == "https://www.aliexpress.com/w/wholesale-knitting-yarn.html"
    href = admitad_deeplink(ae_net["base_url"], target)
    assert href.startswith("https://rzekl.com/g/1e8d114494a8d7abb5f616525dc3e8/?ulp=")
    assert unquote(href.split("ulp=", 1)[1]) == target
    assert " " not in href

    gb_net = links["networks"]["geekbuying"]
    gb_target = fill_target(gb_net["target_url"], "3d printer", "query")
    assert gb_target == "https://www.geekbuying.com/search?keyword=3d+printer"
    gb_href = admitad_deeplink(gb_net["base_url"], gb_target)
    assert gb_href.startswith("https://bywiola.com/g/78tuvzaw8ka8d7abb5f60267b86f6e/?ulp=")
    assert unquote(gb_href.split("ulp=", 1)[1]) == gb_target
    assert "%3F" in gb_href and "%26" not in gb_href

    drone = shop_ctas_for("teknoloji", "drone", links)
    assert [c["network"] for c in drone["links"]] == ["aliexpress", "geekbuying"]
    assert drone["links"][0]["label"] == "AliExpress'te bak"
    assert drone["links"][1]["label"] == "Geekbuying'de bak"
    for c in drone["links"]:
        assert c["href"].count("ulp=") == 1
        assert unquote(c["href"].split("ulp=", 1)[1]) == c["target_url"]

    assert shop_ctas_for("spor-fitness", "yoga-pilates", links)["links"] == []
    assert shop_ctas_for("outdoor", "kampcilik", links)["links"] == []
    fishing = shop_ctas_for("outdoor", "balikcilik", links)
    assert [c["network"] for c in fishing["links"]] == ["aliexpress"]
    pc = shop_ctas_for("teknoloji", "oyun-pc-modlama", links)
    assert [c["network"] for c in pc["links"]] == ["aliexpress"]
    fallback = shop_ctas_for("el-sanatlari", "henuz-yok", links)
    assert fallback["links"] and fallback["links"][0]["keyword"] == "craft supplies"
    assert links["networks"]["amazon_tr"]["tag"] == "hobibulsite-21"
    assert links["networks"]["trendyol"]["base_url"] == "https://www.trendyol.com/sr"
    assert links["networks"]["hepsiburada"]["base_url"] == "https://www.hepsiburada.com/ara"
    print("deeplink self-check ok")


if __name__ == "__main__":
    _self_check()
