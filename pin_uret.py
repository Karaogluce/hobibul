#!/usr/bin/env python3
"""Hobi Bul icin dikey Pinterest pin taslaklari uretir (1000x1500, 2:3).

Taslaklar depoya kaydedilir; yayinlama elle yapilir. Bu betik hicbir sosyal
aglara baglanmaz, API kullanmaz ve icerik yayinlamaz.

Kullanim:
    python pin_uret.py
    python pin_uret.py --only aile-kutu-oyunlari

Gereksinim: Pillow. Yaziti tipleri Windows'ta varsayilan olarak bulunur;
baska bir sistemde HB_FONT_SERIF / HB_FONT_UI ortam degiskenleriyle verilebilir.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent
FONT_SERIF = Path(os.environ.get("HB_FONT_SERIF", "C:/Windows/Fonts/georgiab.ttf"))
FONT_UI = Path(os.environ.get("HB_FONT_UI", "C:/Windows/Fonts/seguisb.ttf"))

W, H = 1000, 1500
FOTO_H = 930
NIGHT = (15, 15, 26)
ORANGE = (254, 133, 0)
BLUE = (16, 91, 255)
PAPER = (246, 247, 251)
MUTED = (167, 173, 203)

# Her kayit bir pin taslagi. gorsel: makale gorseli (yoksa ayni kategoriden
# temsili bir gorsel kullanilabilir), link: pinin gidecegi makale.
PINLER = [
    {
        "ad": "aile-kutu-oyunlari",
        "ust": "KUTU OYUNLARI",
        "baslik": "Çocuklarla evde oynanacak kutu oyunları",
        "gorsel": "static/img/makale/yilbasi-hediyesi-kutu-oyunlari.webp",
        "cikti": "static/img/pin/aile-kutu-oyunlari.jpg",
    },
    {
        "ad": "punch-nakisi",
        "ust": "PUNCH NAKIŞI",
        "baslik": "Punch nakışına sıfırdan başla",
        "gorsel": "static/img/makale/punch-nakisi-nasil-yapilir-baslangic-seti.webp",
        "cikti": "static/img/pin/punch-nakisi-baslangic-seti.jpg",
    },
    {
        "ad": "bonsai-yeni-baslayan",
        "ust": "BONSAİ",
        "baslik": "Bonsai için ilk alınacak 3 ekipman",
        "gorsel": "static/img/makale/bonsai-icin-yeni-baslayanlar-rehberi-ilk-alinacak-ekipmanlar.webp",
        "cikti": "static/img/pin/bonsai-yeni-baslayan.jpg",
    },
    {
        "ad": "filtre-kahve",
        "ust": "FİLTRE KAHVE",
        "baslik": "Evde filtre kahve: ilk alışveriş listesi",
        "gorsel": "static/img/makale/kahve-barista-malzemeleri.webp",
        "cikti": "static/img/pin/filtre-kahve-baslangic-seti.jpg",
    },
    {
        "ad": "lego-baslangic",
        "ust": "LEGO & MODEL",
        "baslik": "LEGO'ya başlarken ilk set nasıl seçilir?",
        "gorsel": "static/img/makale/lego-model-icin-yeni-baslayanlar-rehberi-ilk-alinacak-ekipmanlar.webp",
        "cikti": "static/img/pin/lego-yeni-baslayan.jpg",
    },
]


def font_yolu(yol: Path, aciklama: str) -> str:
    if not yol.exists():
        raise SystemExit(f"{aciklama} yaziti bulunamadi: {yol}")
    return str(yol)


def dikey_gecis(im: Image.Image, y0: int, y1: int, renk, a0: int, a1: int) -> Image.Image:
    """y0-y1 arasinda alfa gecisi olan renk katmani uygular."""
    alfa = Image.new("L", (1, im.height), 0)
    px = alfa.load()
    for y in range(im.height):
        if y < y0:
            deger = a0
        elif y > y1:
            deger = a1
        else:
            oran = (y - y0) / max(1, y1 - y0)
            deger = round(a0 + (a1 - a0) * oran)
        px[0, y] = max(0, min(255, deger))
    katman = Image.new("RGBA", im.size, (*renk, 255))
    katman.putalpha(alfa.resize(im.size))
    return Image.alpha_composite(im.convert("RGBA"), katman)


def metin_eni(kalem: ImageDraw.ImageDraw, metin: str, font: ImageFont.FreeTypeFont) -> int:
    kutu = kalem.textbbox((0, 0), metin, font=font)
    return kutu[2] - kutu[0]


def baslik_sar(kalem, metin: str, azami_en: int, azami_yukseklik: int):
    """Basligi satirlara boler; sigana kadar puntoyu kucultur. En fazla 3 satir."""
    for boyut in range(88, 51, -2):
        font = ImageFont.truetype(font_yolu(FONT_SERIF, "Baslik"), boyut)
        satirlar, satir = [], ""
        for kelime in metin.split():
            deneme = f"{satir} {kelime}".strip()
            if metin_eni(kalem, deneme, font) <= azami_en:
                satir = deneme
            else:
                if satir:
                    satirlar.append(satir)
                satir = kelime
        if satir:
            satirlar.append(satir)
        satir_yuksekligi = int(boyut * 1.18)
        if (
            len(satirlar) <= 3
            and all(metin_eni(kalem, s, font) <= azami_en for s in satirlar)
            and len(satirlar) * satir_yuksekligi <= azami_yukseklik
        ):
            return font, satirlar, boyut, satir_yuksekligi
    raise SystemExit(f"Baslik sigmadi: {metin}")


def pin_uret(pin: dict) -> Path:
    gorsel_yolu = ROOT / pin["gorsel"]
    if not gorsel_yolu.exists():
        raise SystemExit(f"Gorsel bulunamadi: {gorsel_yolu}")

    tuval = Image.new("RGB", (W, H), NIGHT)

    foto = ImageOps.fit(
        Image.open(gorsel_yolu).convert("RGB"),
        (W, FOTO_H),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.42),
    )
    # Ustte logo okunurlugu, altta gece rengine yumusak gecis.
    foto = dikey_gecis(foto, 0, 210, NIGHT, 140, 0)
    foto = dikey_gecis(foto, 620, FOTO_H, NIGHT, 0, 255)
    tuval.paste(foto.convert("RGB"), (0, 0))

    tuval = tuval.convert("RGBA")
    kalem = ImageDraw.Draw(tuval)

    # Marka satiri: isaret + kelime markasi, koyu yari saydam zemin uzerinde.
    logo = Image.open(ROOT / "static/img/logo-mark.png").convert("RGBA")
    logo = logo.resize((56, 56), Image.Resampling.LANCZOS)
    ui_logo = ImageFont.truetype(font_yolu(FONT_UI, "Arayuz"), 34)
    marka = "HOBİ BUL"
    pill_en = 22 + 56 + 14 + metin_eni(kalem, marka, ui_logo) + 24
    kalem.rounded_rectangle((40, 40, 40 + pill_en, 120), radius=20, fill=(15, 15, 26, 178))
    tuval.alpha_composite(logo, (62, 52))
    kalem.text((132, 57), marka, font=ui_logo, fill=PAPER)

    # Mavi vurgu cizgisi + turuncu kategori etiketi.
    kalem.rectangle((56, 944, 232, 952), fill=BLUE)
    ui_ust = ImageFont.truetype(font_yolu(FONT_UI, "Arayuz"), 34)
    ust_kutu = kalem.textbbox((0, 0), pin["ust"], font=ui_ust)
    ust_en = ust_kutu[2] - ust_kutu[0]
    ust_y = 976
    kalem.rounded_rectangle(
        (56, ust_y, 56 + ust_en + 48, ust_y + 58), radius=29, fill=ORANGE
    )
    kalem.text((80, ust_y + 10), pin["ust"], font=ui_ust, fill=NIGHT)

    # Baslik: Georgia Bold, beyaz, en fazla 3 satir.
    baslik_ust = 1072
    font, satirlar, boyut, satir_yuksekligi = baslik_sar(
        kalem, pin["baslik"], W - 112, 1390 - baslik_ust
    )
    y = baslik_ust
    for satir in satirlar:
        kalem.text((56, y), satir, font=font, fill=PAPER)
        y += satir_yuksekligi

    # Alt bilgi: ince cizgi, kucuk logo ve alan adi.
    kalem.line((56, 1408, W - 56, 1408), fill=(255, 255, 255, 40), width=2)
    kucuk_logo = logo.resize((36, 36), Image.Resampling.LANCZOS)
    tuval.alpha_composite(kucuk_logo, (56, 1428))
    ui_alt = ImageFont.truetype(font_yolu(FONT_UI, "Arayuz"), 30)
    kalem.text((104, 1430), "hobibul.com.tr", font=ui_alt, fill=PAPER)
    etiket = "Başlangıç rehberi"
    kalem.text(
        (W - 56 - metin_eni(kalem, etiket, ui_alt), 1430),
        etiket,
        font=ui_alt,
        fill=MUTED,
    )

    cikti = ROOT / pin["cikti"]
    cikti.parent.mkdir(parents=True, exist_ok=True)
    tuval.convert("RGB").save(cikti, "JPEG", quality=88, optimize=True, progressive=True)
    return cikti


def main() -> None:
    ayar = argparse.ArgumentParser(description="Hobi Bul Pinterest pin taslaklari")
    ayar.add_argument("--only", help="Yalnizca bu ada sahip pini uret")
    argumanlar = ayar.parse_args()

    secili = [p for p in PINLER if not argumanlar.only or p["ad"] == argumanlar.only]
    if not secili:
        raise SystemExit(f"Pin bulunamadi: {argumanlar.only}")

    for pin in secili:
        yol = pin_uret(pin)
        print(f"{yol.relative_to(ROOT)} ({W}x{H})")


if __name__ == "__main__":
    main()
