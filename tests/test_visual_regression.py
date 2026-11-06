"""
Görsel regresyon testi: motorun ürettiği sayfa görüntüsü altın görüntüyle
karşılaştırılır. Yerleşim, cilt şeridi veya numara konumu bozulursa yakalanır.

Altın görüntüleri bilinçli olarak güncellemek için:
    set UPDATE_GOLDENS=1 && python -m pytest tests/test_visual_regression.py
"""

from __future__ import annotations

import io
import os

import pymupdf
import pytest
from PIL import Image, ImageChops

from gutter_engine import (
    MarginSettings,
    PageBoxSettings,
    PageNumberSettings,
    PdfProcessConfig,
    process_pdf,
)
from tests.pdf_factory import create_sample_a4_pdf

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "golden")
DPI = 110


def render_page(pdf_path: str, page_index: int) -> Image.Image:
    doc = pymupdf.open(pdf_path)
    try:
        page = doc[page_index]
        pix = page.get_pixmap(matrix=pymupdf.Matrix(DPI / 72.0, DPI / 72.0), alpha=False)
        return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    finally:
        doc.close()


def compare_with_golden(image: Image.Image, name: str) -> None:
    os.makedirs(GOLDEN_DIR, exist_ok=True)
    golden_path = os.path.join(GOLDEN_DIR, name)
    if os.environ.get("UPDATE_GOLDENS") == "1" or not os.path.exists(golden_path):
        image.save(golden_path)
    golden = Image.open(golden_path).convert("RGB")
    assert image.size == golden.size, f"Sayfa boyutu değişti: {image.size} != {golden.size}"

    diff = ImageChops.difference(image, golden)
    histogram = diff.convert("L").histogram()
    total_pixels = image.width * image.height
    changed = sum(histogram[16:])
    mean = sum(value * count for value, count in enumerate(histogram)) / total_pixels
    assert mean < 1.5, f"Görsel fark ortalaması çok yüksek: {mean:.3f}"
    assert changed / total_pixels < 0.01, (
        f"Piksellerin %{changed / total_pixels * 100:.2f} kadarı değişti"
    )


def test_layout_visual_regression(tmp_path):
    source = str(tmp_path / "visual_in.pdf")
    output = str(tmp_path / "visual_out.pdf")
    create_sample_a4_pdf(source, pages=2)

    config = PdfProcessConfig(
        page_boxes=PageBoxSettings(
            target_width_mm=225.0, target_height_mm=297.0,
            odd_x_mm=15.0, even_x_mm=0.0,
        ),
        margins=MarginSettings(enabled=True, extra_bottom_mm=20.0, bottom_mode="expand"),
        page_numbers=PageNumberSettings(
            enabled=True, position="outer", format_style="dash",
            start_num=1, start_page=1, bottom_margin_mm=12.0, side_margin_mm=15.0,
        ),
    )
    process_pdf(source, output, config)

    compare_with_golden(render_page(output, 0), "layout_page1.png")
    compare_with_golden(render_page(output, 1), "layout_page2.png")


def test_excluded_cover_visual_regression(tmp_path):
    source = str(tmp_path / "cover_in.pdf")
    output = str(tmp_path / "cover_out.pdf")
    create_sample_a4_pdf(source, pages=2)
    config = PdfProcessConfig(
        page_boxes=PageBoxSettings(
            target_width_mm=225.0, target_height_mm=297.0,
            odd_x_mm=15.0, even_x_mm=0.0,
            exclude_pages_str="1",
        ),
        margins=MarginSettings(enabled=True, extra_bottom_mm=20.0, bottom_mode="expand",
                               exclude_pages_str="1"),
        page_numbers=PageNumberSettings(enabled=False),
    )
    process_pdf(source, output, config)
    compare_with_golden(render_page(output, 0), "cover_page1.png")
