"""P1 1b: nihai sayfa ebadı = kaynak + cilt payı (yatay) + alt/üst boşluk (dikey)."""

from __future__ import annotations

import pymupdf
import pytest

from core.gutter_engine import PdfProcessConfig, compute_layout, mm_to_pt, process_pdf, pt_to_mm
from tests.pdf_factory import create_sample_a4_pdf


def _config(size_mode="auto", odd_x=15.0, even_x=0.0, bottom=10.0, top=0.0,
            mode="expand", numbers=False, tw=225.0, th=297.0) -> PdfProcessConfig:
    config = PdfProcessConfig()
    boxes = config.page_boxes
    boxes.enabled, boxes.size_mode = True, size_mode
    boxes.odd_x_mm, boxes.even_x_mm = odd_x, even_x
    boxes.target_width_mm, boxes.target_height_mm = tw, th
    config.margins.enabled = True
    config.margins.extra_bottom_mm, config.margins.extra_top_mm = bottom, top
    config.margins.bottom_mode = mode
    config.page_numbers.enabled = numbers
    return config


def _size_mm(config, pno=0):
    lay = compute_layout(mm_to_pt(210), mm_to_pt(297), config, pno)
    return round(pt_to_mm(lay.target_w), 1), round(pt_to_mm(lay.target_h), 1)


@pytest.mark.parametrize("size_mode", ["auto", "fixed"])
@pytest.mark.parametrize("pno", [0, 1])
def test_a4_plus_gutter_plus_bottom(size_mode, pno):
    assert _size_mm(_config(size_mode=size_mode), pno) == (225.0, 307.0)


def test_gutter_on_both_page_sides_is_not_summed():
    """Tek ve çift sayfada ikisi de 15 mm ise genişlik 240 değil 225 olur."""
    assert _size_mm(_config(odd_x=15, even_x=15)) == (225.0, 307.0)


def test_top_and_bottom_both_add_to_height():
    assert _size_mm(_config(bottom=10, top=5)) == (225.0, 312.0)


def test_only_gutter_and_only_margin():
    only_gutter = _config(bottom=0)
    assert _size_mm(only_gutter) == (225.0, 297.0)
    only_margin = _config(odd_x=0, bottom=10)
    assert _size_mm(only_margin) == (210.0, 307.0)


def test_fit_mode_keeps_target_height():
    assert _size_mm(_config(mode="fit")) == (225.0, 297.0)


@pytest.mark.parametrize("numbers", [False, True])
@pytest.mark.parametrize("size_mode", ["auto", "fixed"])
def test_output_mediabox_matches_layout(tmp_path, numbers, size_mode):
    """Sayfa numarası açık olsa da çıktı ebadı değişmez (numara mevcut alana yazılır)."""
    src = create_sample_a4_pdf(str(tmp_path / "a4.pdf"), pages=4)
    out = str(tmp_path / "out.pdf")
    process_pdf(src, out, _config(size_mode=size_mode, numbers=numbers))
    doc = pymupdf.open(out)
    try:
        sizes = {(round(pt_to_mm(p.mediabox.width), 1), round(pt_to_mm(p.mediabox.height), 1))
                 for p in doc}
    finally:
        doc.close()
    assert sizes == {(225.0, 307.0)}
