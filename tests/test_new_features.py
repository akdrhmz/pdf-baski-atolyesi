"""v2.10.0 yeni özellik testleri: üst kenar numara, forma/RTL montaj, güvenlik/meta, canlı araç önizlemesi."""

from __future__ import annotations

import io

import pymupdf
import pytest
from PIL import Image

from gutter_engine import (
    PageNumberSettings,
    PdfProcessConfig,
    config_from_dict,
    config_to_dict,
    number_anchor,
    process_pdf,
)
from pdf_tools import (
    PrintOptions,
    SecurityMetaOptions,
    StampOptions,
    apply_security_and_metadata,
    booklet_order,
    impose_pdf,
    render_tool_preview,
    stamp_pdf,
)
from tests.pdf_factory import create_sample_a4_pdf


def test_top_page_number_anchor_and_roundtrip(tmp_path):
    cfg = PdfProcessConfig(
        page_numbers=PageNumberSettings(
            enabled=True,
            vertical_pos="top",
            position="center",
            font_color=(0.8, 0.1, 0.1),
            bottom_margin_mm=10.0,
        )
    )
    raw = config_to_dict(cfg)
    reloaded = config_from_dict(raw)
    assert reloaded.page_numbers.vertical_pos == "top"
    assert reloaded.page_numbers.font_color == pytest.approx((0.8, 0.1, 0.1))

    _x, baseline = number_anchor("1", reloaded.page_numbers, 595.0, 842.0, True)
    assert baseline < 100.0  # üst kenarda

    src = tmp_path / "src.pdf"
    out = tmp_path / "out.pdf"
    create_sample_a4_pdf(str(src), pages=2)
    process_pdf(str(src), str(out), reloaded)
    with pymupdf.open(str(out)) as doc:
        blocks = doc[0].get_text("blocks")
        assert any("1" in b[4] and b[1] < 100.0 for b in blocks)


def test_booklet_signatures_and_rtl(tmp_path):
    sig_order = booklet_order(10, signature_size=8)
    # İlk forma 0..7 (4 yüz), ikinci forma 8..9 (2 yüz, 2 boş) -> toplam 6 yüz
    assert len(sig_order) == 6
    assert sig_order[0] == [7, 0]
    assert sig_order[4] == [None, 8]

    rtl_order = booklet_order(8, rtl=True)
    assert rtl_order[0] == [0, 7]

    src = tmp_path / "book.pdf"
    out = tmp_path / "booklet.pdf"
    create_sample_a4_pdf(str(src), pages=8)
    impose_pdf(
        str(src),
        str(out),
        PrintOptions(mode="booklet", signature_size=8, divider_line=True, rtl=True),
    )
    assert out.exists()
    with pymupdf.open(str(out)) as doc:
        assert len(doc) == 4


def test_stamp_page_range_and_bates_top_right(tmp_path):
    src = tmp_path / "src.pdf"
    out = tmp_path / "stamped.pdf"
    create_sample_a4_pdf(str(src), pages=3)
    opts = StampOptions(
        watermark="TASLAK",
        color=(0.9, 0.1, 0.1),
        page_range="2",
        bates_enabled=True,
        bates_prefix="DOC-",
        bates_digits=4,
        bates_position="top_right",
    )
    stamp_pdf(str(src), str(out), opts)
    with pymupdf.open(str(out)) as doc:
        assert "TASLAK" not in doc[0].get_text()
        assert "TASLAK" in doc[1].get_text()
        assert "DOC-0001" in doc[1].get_text()
        assert "DOC-0001" not in doc[2].get_text()


def test_security_and_metadata(tmp_path):
    src = tmp_path / "src.pdf"
    out = tmp_path / "secured.pdf"
    create_sample_a4_pdf(str(src), pages=2)
    opts = SecurityMetaOptions(
        title="Baskı Deneme",
        author="Kadir",
        user_password="gizli",
        owner_password="sahip",
        allow_print=True,
        allow_copy=False,
    )
    apply_security_and_metadata(str(src), str(out), opts)
    with pymupdf.open(str(out)) as doc:
        assert doc.needs_pass
        assert doc.authenticate("gizli")
        assert doc.metadata.get("title") == "Baskı Deneme"
        assert doc.metadata.get("author") == "Kadir"


def test_render_tool_preview_returns_valid_image(tmp_path):
    src = tmp_path / "src.pdf"
    create_sample_a4_pdf(str(src), pages=4)
    stamp_bytes = render_tool_preview(str(src), "stamp", StampOptions(watermark="ONAY"), page_index=0)
    im1 = Image.open(io.BytesIO(stamp_bytes))
    assert im1.width > 50 and im1.height > 50

    impose_bytes = render_tool_preview(str(src), "impose", PrintOptions(mode="booklet", divider_line=True), page_index=0)
    im2 = Image.open(io.BytesIO(impose_bytes))
    assert im2.width > im2.height  # A4 yatay önizleme


def test_number_tab_vpos_and_color_ui(tmp_path):
    from app import ModernGutterApp

    app = ModernGutterApp(settings_path=tmp_path / "s.json", log_path=tmp_path / "l.log")
    try:
        app.select_tab("Sayfa Numaraları")
        nt = app._number_tab()
        nt.seg_vpos.set("Üst kenar")
        nt.on_vpos_changed()
        nt.set_num_color((0.2, 0.4, 0.6))
        cfg = app._build_config(notify=False)
        assert cfg is not None
        assert cfg.page_numbers.vertical_pos == "top"
        assert cfg.page_numbers.font_color == pytest.approx((0.2, 0.4, 0.6))
    finally:
        app.destroy()
