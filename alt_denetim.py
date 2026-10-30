#!/usr/bin/env python3
"""Hobi Bul — görsel alt metni denetimi (salt okunur rapor).

content/articles/*.md ve content/pages/*.md dosyalarında:
  - frontmatter'da "image" dolu ama "image_alt" boş/eksik olanları,
  - gövdedeki Markdown görsellerinde (![...](...)) alt metni boş olanları
listeler. Hiçbir dosyayı değiştirmez.

Kullanım:  python alt_denetim.py
"""
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(BASE, "content")
DIRS = (("articles", "makaleler"), ("pages", "bilgi sayfaları"))
MD_IMG = re.compile(r"!\[([^\]]*)\]\(([^)]*)\)")


def parse(path):
    """(frontmatter sözlüğü, gövde, gövdenin dosyadaki başlangıç satırı)."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if not text.startswith("---"):
        return {}, text, 1
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text, 1
    meta = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    body = parts[2]
    # gövde, kapanış "---" satırının hemen ardından başlar
    return meta, body, parts[0].count("\n") + parts[1].count("\n") + 1


def denetle(klasor, etiket):
    dizin = os.path.join(CONTENT, klasor)
    if not os.path.isdir(dizin):
        return 0, 0
    dosyalar = sorted(f for f in os.listdir(dizin) if f.endswith(".md"))
    uyarilar = []
    for fn in dosyalar:
        meta, body, baslangic = parse(os.path.join(dizin, fn))
        image = (meta.get("image") or "").strip()
        alt = (meta.get("image_alt") or "").strip()
        if image and not alt:
            uyarilar.append(f"  ! {fn}: frontmatter'da image dolu ama image_alt yok")
        bos = []
        for i, satir in enumerate(body.splitlines(), start=baslangic):
            for m in MD_IMG.finditer(satir):
                if not m.group(1).strip():
                    bos.append(i)
        if bos:
            satirlar = ", ".join(str(s) for s in bos)
            uyarilar.append(f"  ! {fn}: gövdede {len(bos)} görselde alt metin boş (satır {satirlar})")
    print(f"\n{etiket} — {len(dosyalar)} dosya")
    if uyarilar:
        print("\n".join(uyarilar))
    else:
        print("  ✓ sorun yok")
    return len(dosyalar), len(uyarilar)


def main():
    print("Görsel alt metni denetimi")
    toplam_dosya = toplam_uyari = 0
    for klasor, etiket in DIRS:
        d, u = denetle(klasor, etiket)
        toplam_dosya += d
        toplam_uyari += u
    print(f"\nÖzet: {toplam_dosya} dosya tarandı, {toplam_uyari} uyarı.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
