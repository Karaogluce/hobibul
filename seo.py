"""Meta başlık ve açıklama sınırları.

Başlık en fazla 60 karakter (60–65 bandının altı).
Açıklama 120–160 karakter, benzersiz ve düz Türkçe.
otomatik.py ve build.py aynı fonksiyonları kullanır.
"""
import re

TITLE_MAX = 60
DESC_MIN = 120
DESC_MAX = 160
BRAND = " | Hobi Bul"

_BOILER = re.compile(
    r"\s*Artıları, eksileri ve doğrudan satın alma bağlantılarıyla kapsamlı rehber\.?$",
    re.I,
)


def _squash(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


def fit_title(text, limit=TITLE_MAX):
    """Uzun başlığı kelime sınırında kısaltır. Sığanı olduğu gibi bırakır."""
    text = _squash(text)
    if not text:
        text = "Hobi Bul"
    if len(text) <= limit:
        return text
    core = text[:-len(BRAND)].rstrip() if text.endswith(BRAND) else text
    room = limit - len(BRAND)
    if room >= 16 and len(core) > room:
        chunk = core[:room].rstrip(" -:|,")
        if " " in chunk:
            cut = chunk.rsplit(" ", 1)[0].rstrip(" -:|,")
            if len(cut) >= 16:
                chunk = cut
        text = chunk + BRAND
    if len(text) > limit:
        text = text[:limit].rstrip(" -:|,")
    return text


_DANGLING = {
    "ve", "ile", "için", "veya", "ya", "da", "de", "bir", "bu", "şu", "o",
    "ki", "gibi", "kadar", "daha", "en", "çok",
}


def _finish(chunk, limit_max=DESC_MAX):
    """Sonda yarım bağlaç bırakmadan noktayı koyar."""
    words = chunk.strip().rstrip(".,;:!?–-").split()
    while words and words[-1].lower().strip(".,;:") in _DANGLING:
        words.pop()
    out = " ".join(words).strip()
    if not out.endswith((".", "!", "?")):
        if len(out) + 1 <= limit_max:
            out += "."
        else:
            out = out[: limit_max - 1].rstrip(" ,;:-") + "."
    return out


def _trim_desc(text, limit_min=DESC_MIN, limit_max=DESC_MAX):
    """160 üstünü cümle ya da kelime sınırında 120–160 aralığına indirir."""
    if len(text) <= limit_max:
        return text
    window = text[: limit_max + 1]
    best = None
    for i, ch in enumerate(window):
        if ch in ".!?" and limit_min <= i + 1 <= limit_max:
            best = text[: i + 1].strip()
    if best:
        return best
    sp = text.rfind(" ", 0, limit_max)
    chunk = text[:sp] if sp >= limit_min else text[: limit_max - 1]
    out = _finish(chunk, limit_max)
    if len(out) < limit_min:
        out = _finish(text[:limit_max], limit_max)
    if len(out) > limit_max:
        out = out[: limit_max - 1].rstrip(" ,;:-") + "."
    return out


def fit_description(text, extra="", limit_min=DESC_MIN, limit_max=DESC_MAX):
    """Açıklamayı 120–160 karaktere çeker. Aralıkta olan metne dokunmaz.

    Kısa metne yalnızca sığan tam bir cümle eklenir; kelime yarım kalmaz.
    """
    text = _BOILER.sub("", _squash(text)).strip()
    if limit_min <= len(text) <= limit_max:
        return text
    if len(text) > limit_max:
        return _trim_desc(text, limit_min, limit_max)
    base = text.rstrip(".")
    options = []
    if extra:
        options.append(_squash(extra).rstrip("."))
    options.extend([
        "Yeni başlayan için artı ve eksi notu da var",
        "Karşılaştırma yeni başlayan içindir",
        "Kısa alım notu da burada",
    ])
    for opt in options:
        merged = f"{base}. {opt}."
        if limit_min <= len(merged) <= limit_max:
            return merged
    # En uzun sığan tam seçenek yoksa, ilk seçeneği kelime sınırında kısalt.
    opt = options[0]
    room = limit_max - len(base) - 2  # ". " 
    piece = opt[: max(room - 1, 0)].rstrip()
    if " " in piece:
        piece = piece.rsplit(" ", 1)[0]
    merged = _finish(f"{base}. {piece}", limit_max)
    if len(merged) < limit_min:
        merged = _finish(f"{base}. Yeni başlayan için artı ve eksi notu da var", limit_max)
    if len(merged) > limit_max:
        return _trim_desc(merged, limit_min, limit_max)
    return merged


def extract_faq(markdown):
    """## Sıkça Sorulan Sorular / SSS / FAQ altındaki **soru** + cevap çiftleri."""
    if not markdown:
        return []
    m = re.search(r"(?m)^##\s+(Sıkça Sorulan Sorular|SSS|FAQ)\s*$", markdown, re.I)
    if not m:
        return []
    rest = markdown[m.end():]
    nxt = re.search(r"(?m)^##\s+", rest)
    block = rest[: nxt.start()] if nxt else rest
    parts = re.split(r"\*\*(.+?)\*\*", block)
    faqs = []
    i = 1
    while i + 1 < len(parts):
        q = _squash(parts[i]).strip(" *")
        a = parts[i + 1]
        a = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", a)
        a = _squash(a)
        if q and a:
            faqs.append({"q": q, "a": a})
        i += 2
    return faqs
