"""
PDF Baskı & Cilt Stüdyosu - uygulama simgesi üreticisi.

Tasarım: beyaz sayfa + belirgin cilt şeridi + halka dikişler. Küçük boyutlarda
ayrıntı azaltılır; 64 px ve altı Windows için BMP (DIB), büyük boyutlar PNG
olarak ICO içine yazılır. Böylece görev çubuğunda bulanıklaşma olmaz.

Kullanım: python make_icon.py
Çıktı: assets/icon.ico (16,24,32,48,64,128,256), assets/icon.png (512)
"""

from __future__ import annotations

import io
import os
import struct
from typing import Dict

from PIL import Image, ImageDraw

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

BG = (9, 84, 158)             # #09549E
BG_EDGE = (6, 64, 122)
PAGE = (255, 255, 255)
PAGE_EDGE = (223, 232, 244)
SPINE = (31, 111, 235)        # #1F6FEB
RING = (255, 255, 255)
LINE = (196, 210, 228)
LINE_DARK = (150, 171, 198)


def _rounded(size: int, box, radius: int, fill) -> Image.Image:
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius=radius, fill=fill)
    return layer


def render_icon(size: int) -> Image.Image:
    """Boyuta göre sadeleşen, keskin cilt aracı simgesi."""
    factor = 8 if size <= 64 else 4
    canvas = size * factor
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))

    # Arka plan: düz, yüksek kontrastlı yuvarlak kare.
    inset = max(1, int(canvas * 0.015))
    background = _rounded(canvas, (inset, inset, canvas - inset - 1, canvas - inset - 1),
                          int(canvas * 0.21), BG + (255,))
    image = Image.alpha_composite(image, background)
    edge = Image.new("RGBA", (canvas, canvas), BG_EDGE + (70,))
    edge_mask = Image.new("L", (canvas, canvas), 0)
    ImageDraw.Draw(edge_mask).rounded_rectangle(
        (inset, inset, canvas - inset - 1, canvas - inset - 1),
        radius=int(canvas * 0.21), outline=255, width=max(1, canvas // 200))
    image.paste(edge, (0, 0), edge_mask)

    detailed = size >= 48
    compact = size <= 32

    if compact:
        page_box = (int(canvas * 0.13), int(canvas * 0.08),
                    int(canvas * 0.87), int(canvas * 0.92))
        radius = int(canvas * 0.055)
    else:
        page_box = (int(canvas * 0.19), int(canvas * 0.10),
                    int(canvas * 0.81), int(canvas * 0.90))
        radius = int(canvas * 0.045)

    x0, y0, x1, y1 = page_box
    page_mask = Image.new("L", (canvas, canvas), 0)
    ImageDraw.Draw(page_mask).rounded_rectangle(page_box, radius=radius, fill=255)
    page = Image.new("RGBA", (canvas, canvas), PAGE + (255,))
    page.putalpha(page_mask)
    image = Image.alpha_composite(image, page)

    # Cilt şeridi: sol kenarda kalın, koyu mavi.
    band_width = int((x1 - x0) * (0.22 if compact else 0.17))
    band_x = x0 + band_width
    band_mask = Image.new("L", (canvas, canvas), 0)
    ImageDraw.Draw(band_mask).rectangle((x0, y0, band_x, y1), fill=255)
    band_mask = Image.composite(band_mask, Image.new("L", (canvas, canvas), 0), page_mask)
    spine = Image.new("RGBA", (canvas, canvas), SPINE + (255,))
    spine.putalpha(band_mask)
    image = Image.alpha_composite(image, spine)

    draw = ImageDraw.Draw(image)
    border = max(1, canvas // 220)
    draw.rounded_rectangle(page_box, radius=radius, outline=PAGE_EDGE + (255,), width=border)

    # Halka dikişler: cilt aracı olduğunu gösteren üç beyaz bağ.
    ring_count = 1 if compact else (2 if size < 128 else 3)
    ring_h = max(2, int((y1 - y0) * (0.055 if compact else 0.045)))
    ring_w = band_width + max(1, band_width // 4)
    positions = [0.5] if ring_count == 1 else (
        [0.28, 0.72] if ring_count == 2 else [0.22, 0.50, 0.78])
    for ratio in positions:
        cy = y0 + int((y1 - y0) * ratio)
        draw.rounded_rectangle(
            (x0 - ring_w // 5, cy - ring_h // 2, band_x + ring_w // 5, cy + ring_h // 2),
            radius=ring_h // 2, fill=RING + (255,),
            outline=(180, 205, 235, 255), width=max(1, canvas // 300),
        )

    if detailed:
        text_x0 = band_x + int((x1 - band_x) * 0.18)
        text_x1 = x1 - int((x1 - x0) * 0.10)
        spans = (0.90, 0.68, 0.84, 0.56)
        start_y = y0 + int((y1 - y0) * 0.20)
        line_h = max(2, int((y1 - y0) * 0.030))
        step = int((y1 - y0) * 0.105)
        for index, span in enumerate(spans):
            top = start_y + index * step
            right = text_x0 + int((text_x1 - text_x0) * span)
            draw.rounded_rectangle((text_x0, top, right, top + line_h),
                                   radius=line_h // 2, fill=LINE + (255,))
        # Alt satır: daha kısa ve koyu, sayfa dengesi için.
        top = start_y + len(spans) * step
        draw.rounded_rectangle((text_x0, top, text_x0 + int((text_x1 - text_x0) * 0.38),
                                top + line_h), radius=line_h // 2, fill=LINE_DARK + (255,))

    result = image.resize((size, size), Image.Resampling.LANCZOS)
    red, green, blue, alpha = result.split()
    alpha = alpha.point(lambda value: 0 if value < 10 else value)
    return Image.merge("RGBA", (red, green, blue, alpha))


def _png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _dib_bytes(image: Image.Image) -> bytes:
    """Windows'un küçük boyutlarda tercih ettiği 32 bit BMP (DIB) gövdesi."""
    image = image.convert("RGBA")
    width, height = image.size
    raw = image.tobytes()

    def pixel(x: int, y: int):
        index = (y * width + x) * 4
        return raw[index], raw[index + 1], raw[index + 2], raw[index + 3]

    rows = bytearray()
    for y in range(height - 1, -1, -1):
        for x in range(width):
            red, green, blue, alpha = pixel(x, y)
            rows += bytes((blue, green, red, alpha))

    mask_row = ((width + 31) // 32) * 4
    mask = bytearray()
    for y in range(height - 1, -1, -1):
        row = bytearray(mask_row)
        for x in range(width):
            if pixel(x, y)[3] == 0:
                row[x // 8] |= 1 << (7 - (x % 8))
        mask += row

    header = struct.pack(
        "<IiiHHIIiiII", 40, width, height * 2, 1, 32, 0,
        len(rows) + len(mask), 0, 0, 0, 0,
    )
    return header + bytes(rows) + bytes(mask)


def write_ico(path: str, images: Dict[int, Image.Image]) -> None:
    sizes = sorted(images)
    entries = []
    offset = 6 + 16 * len(sizes)
    for size in sizes:
        payload = _png_bytes(images[size]) if size >= 128 else _dib_bytes(images[size])
        entries.append((size, payload))
        offset += len(payload)

    with open(path, "wb") as handle:
        handle.write(struct.pack("<HHH", 0, 1, len(entries)))
        cursor = 6 + 16 * len(entries)
        for size, payload in entries:
            dimension = 0 if size >= 256 else size
            handle.write(struct.pack("<BBBBHHII", dimension, dimension, 0, 0, 1, 32,
                                     len(payload), cursor))
            cursor += len(payload)
        for _size, payload in entries:
            handle.write(payload)


def create_icons() -> None:
    os.makedirs(ASSETS_DIR, exist_ok=True)
    images = {size: render_icon(size) for size in (16, 24, 32, 48, 64, 128, 256)}
    write_ico(os.path.join(ASSETS_DIR, "icon.ico"), images)
    render_icon(512).save(os.path.join(ASSETS_DIR, "icon.png"), format="PNG")
    print("Simge üretildi:", ASSETS_DIR)


if __name__ == "__main__":
    create_icons()
