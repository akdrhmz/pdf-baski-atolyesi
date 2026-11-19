"""
PDF Baskı & Cilt Stüdyosu - Motor testleri.

Tüm testler gerçek PDF üretir ve PyMuPDF ile sonucu yeniden okur; hiçbir
kontrol mock veriye dayanmaz.
"""

from __future__ import annotations

import os

import pymupdf
import pytest

from core.gutter_engine import (
    CLIP_TOLERANCE_PT,
    MarginSettings,
    OutputPathError,
    PageBoxSettings,
    PageNumberSettings,
    PdfOpenError,
    PdfPasswordError,
    PdfProcessConfig,
    ProcessCancelled,
    StudioError,
    compute_layout,
    config_from_dict,
    config_to_dict,
    format_page_number_text,
    get_pdf_info,
    merge_pdfs,
    mm_to_pt,
    normalize_page_rotations,
    numbering_plan,
    open_pdf,
    parse_page_ranges,
    process_pdf,
    pt_to_mm,
    render_preview,
    resolve_number_font,
    same_path,
    scan_clipping,
    to_roman,
    unique_output_path,
    validate_config,
    verify_output,
)
from tests.pdf_factory import (
    create_encrypted_pdf,
    create_mixed_sample_pdf,
    create_sample_a4_pdf,
    word_bbox,
)


def config_for(**overrides) -> PdfProcessConfig:
    config = PdfProcessConfig(
        page_boxes=PageBoxSettings(enabled=False),
        margins=MarginSettings(enabled=False),
        page_numbers=PageNumberSettings(enabled=False),
    )
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def test_parse_page_ranges():
    assert parse_page_ranges("1, 2, 5-7, 10,  15 - 16 , abc, -5") == {1, 2, 5, 6, 7, 10, 15, 16}
    assert parse_page_ranges("") == set()
    assert parse_page_ranges("5-3") == {3, 4, 5}


def test_get_pdf_info(tmp_path):
    path = str(tmp_path / "info.pdf")
    create_sample_a4_pdf(path, pages=4)
    info = get_pdf_info(path)
    assert info["page_count"] == 4
    assert round(info["width_mm"]) == 210
    assert round(info["height_mm"]) == 297
    assert info["is_portrait"] is True
    assert info["mixed_sizes"] is False

    mixed = str(tmp_path / "mixed.pdf")
    create_mixed_sample_pdf(mixed)
    assert get_pdf_info(mixed)["mixed_sizes"] is True


def test_get_pdf_info_uses_the_dominant_page_size(tmp_path):
    """Kapak A3, gövde A4: hedef ebat çoğunluğa (A4) göre verilir."""
    path = str(tmp_path / "kapakli.pdf")
    doc = pymupdf.open()
    doc.new_page(width=mm_to_pt(297), height=mm_to_pt(420))
    for _ in range(3):
        doc.new_page(width=mm_to_pt(210), height=mm_to_pt(297))
    doc.save(path)
    doc.close()
    info = get_pdf_info(path)
    assert info["mixed_sizes"] is True
    assert round(info["width_mm"]) == 210 and round(info["height_mm"]) == 297
    quick = get_pdf_info(path, quick=True)
    assert round(quick["width_mm"]) == 297      # hızlı tarama yalnız ilk sayfaya bakar
    first = get_pdf_info(path, size_policy="first")
    largest = get_pdf_info(path, size_policy="largest")
    assert round(first["width_mm"]) == 297
    assert round(largest["width_mm"]) == 297 and round(largest["height_mm"]) == 420


def test_duplex_gutter_transformation(tmp_path):
    input_path = str(tmp_path / "gutter_in.pdf")
    output_path = str(tmp_path / "gutter_out.pdf")
    create_sample_a4_pdf(input_path, pages=4)
    source = pymupdf.open(input_path)
    source_x = word_bbox(source, 0, "Sayfa")[0]
    source.close()

    config = PdfProcessConfig(
        page_boxes=PageBoxSettings(
            target_width_mm=225.0, target_height_mm=297.0,
            odd_x_mm=15.0, odd_y_mm=0.0, even_x_mm=0.0, even_y_mm=0.0,
        ),
        margins=MarginSettings(enabled=False),
        page_numbers=PageNumberSettings(enabled=False),
    )
    process_pdf(input_path, output_path, config)

    doc = pymupdf.open(output_path)
    assert len(doc) == 4
    for page in doc:
        assert abs(pt_to_mm(page.rect.width) - 225.0) < 0.2
        assert abs(pt_to_mm(page.rect.height) - 297.0) < 0.2
    # Tek sayfada içerik 15 mm sağa kayar, çift sayfada yerinde kalır.
    assert abs(word_bbox(doc, 0, "Sayfa")[0] - (source_x + mm_to_pt(15.0))) < 1.0
    assert abs(word_bbox(doc, 1, "Sayfa")[0] - source_x) < 1.0
    doc.close()


def test_expand_mode_adds_height_without_touching_content(tmp_path):
    input_path = str(tmp_path / "expand_in.pdf")
    output_path = str(tmp_path / "expand_out.pdf")
    create_sample_a4_pdf(input_path, pages=2)
    source = pymupdf.open(input_path)
    source_y = word_bbox(source, 0, "Sayfa")[1]
    source.close()

    config = config_for(
        page_boxes=PageBoxSettings(target_width_mm=210.0, target_height_mm=297.0,
                                   odd_x_mm=0.0, even_x_mm=0.0),
        margins=MarginSettings(enabled=True, extra_bottom_mm=25.0, bottom_mode="expand"),
    )
    process_pdf(input_path, output_path, config)

    doc = pymupdf.open(output_path)
    for page in doc:
        assert abs(pt_to_mm(page.rect.height) - 322.0) < 0.2
    assert abs(word_bbox(doc, 0, "Sayfa")[1] - source_y) < 1.0
    doc.close()

    assert scan_clipping(input_path, config).has_issues is False


def test_fit_mode_scales_content_without_clipping(tmp_path):
    input_path = str(tmp_path / "fit_in.pdf")
    output_path = str(tmp_path / "fit_out.pdf")
    create_sample_a4_pdf(input_path, pages=2, width_mm=210.0, height_mm=297.0)

    config = config_for(
        page_boxes=PageBoxSettings(target_width_mm=210.0, target_height_mm=250.0,
                                   odd_x_mm=0.0, even_x_mm=0.0),
        margins=MarginSettings(enabled=True, extra_bottom_mm=20.0, extra_top_mm=0.0,
                               bottom_mode="fit"),
    )
    layout = compute_layout(mm_to_pt(210), mm_to_pt(297), config, 0)
    assert 0.70 < layout.scale < 0.80
    assert layout.content.x0 >= 0
    assert layout.content.x1 <= layout.target_w + 0.01
    assert layout.content.y0 >= 0
    assert layout.content.y1 <= layout.target_h + 0.01

    assert scan_clipping(input_path, config).has_issues is False
    process_pdf(input_path, output_path, config)
    report = verify_output(input_path, output_path, config)
    assert report.ok, report.lines()
    doc = pymupdf.open(output_path)
    assert abs(pt_to_mm(doc[0].rect.height) - 250.0) < 0.2
    assert "Sayfa" in doc[0].get_text()
    doc.close()


def test_shift_mode_is_reported_before_processing(tmp_path):
    input_path = str(tmp_path / "shift_in.pdf")
    create_sample_a4_pdf(input_path, pages=2)

    config = config_for(
        page_boxes=PageBoxSettings(target_width_mm=210.0, target_height_mm=297.0,
                                   odd_x_mm=0.0, even_x_mm=0.0),
        margins=MarginSettings(enabled=True, extra_bottom_mm=25.0, bottom_mode="shift"),
    )
    report = scan_clipping(input_path, config)
    assert report.has_issues
    assert report.issues[0].page == 1
    assert report.issues[0].top_mm > 1.0
    # Uyarı metni kullanıcıya ne olacağını söyler.
    assert "Kırpma riski" in report.summary() or "taşıyor" in report.summary()


def test_fixed_target_smaller_than_source_is_detected(tmp_path):
    input_path = str(tmp_path / "small_in.pdf")
    create_sample_a4_pdf(input_path, pages=2)

    config = config_for(
        page_boxes=PageBoxSettings(target_width_mm=200.0, target_height_mm=250.0,
                                   odd_x_mm=0.0, even_x_mm=0.0),
    )
    report = scan_clipping(input_path, config)
    assert report.has_issues
    first = report.issues[0]
    assert first.right_mm > 1.0
    assert first.bottom_mm > 1.0


def test_same_path_is_blocked(tmp_path):
    path = str(tmp_path / "same.pdf")
    create_sample_a4_pdf(path, pages=1)
    with pytest.raises(OutputPathError):
        process_pdf(path, path, config_for())
    assert same_path(path, path)
    assert unique_output_path(path) != path


def test_encrypted_pdf_raises_turkish_error(tmp_path):
    path = str(tmp_path / "encrypted.pdf")
    create_encrypted_pdf(path)
    with pytest.raises(PdfPasswordError) as excinfo:
        open_pdf(path)
    assert "parola" in str(excinfo.value).lower()


def test_corrupt_pdf_raises_turkish_error(tmp_path):
    path = tmp_path / "bozuk.pdf"
    path.write_bytes(b"bu bir pdf degil")
    with pytest.raises(PdfOpenError) as excinfo:
        open_pdf(str(path))
    assert "açılamadı" in str(excinfo.value).lower()


def test_y_offsets_preserved_in_merge_pipeline(tmp_path):
    pdf1 = str(tmp_path / "merge_y_1.pdf")
    pdf2 = str(tmp_path / "merge_y_2.pdf")
    merged = str(tmp_path / "merged_y.pdf")
    output = str(tmp_path / "merged_y_out.pdf")
    create_sample_a4_pdf(pdf1, pages=2)
    create_sample_a4_pdf(pdf2, pages=2)
    merge_pdfs([pdf1, pdf2], merged)

    merged_doc = pymupdf.open(merged)
    base = [word_bbox(merged_doc, i, "Sayfa")[1] for i in range(4)]
    merged_doc.close()

    config = config_for(
        page_boxes=PageBoxSettings(target_width_mm=210.0, target_height_mm=317.0,
                                   odd_x_mm=0.0, even_x_mm=0.0,
                                   odd_y_mm=10.0, even_y_mm=20.0),
    )
    process_pdf(merged, output, config)
    doc = pymupdf.open(output)
    deltas = [word_bbox(doc, i, "Sayfa")[1] - base[i] for i in range(4)]
    assert abs(deltas[0] - mm_to_pt(10.0)) < 1.0
    assert abs(deltas[1] - mm_to_pt(20.0)) < 1.0
    assert abs(deltas[2] - mm_to_pt(10.0)) < 1.0
    assert abs(deltas[3] - mm_to_pt(20.0)) < 1.0
    doc.close()


def test_links_are_offset_and_preserved(tmp_path):
    input_path = str(tmp_path / "ref.pdf")
    output_path = str(tmp_path / "ref_out.pdf")
    create_mixed_sample_pdf(input_path)

    config = config_for(
        page_boxes=PageBoxSettings(size_mode="auto",
                                   target_width_mm=225.0, target_height_mm=297.0,
                                   odd_x_mm=15.0, even_x_mm=0.0),
        page_numbers=PageNumberSettings(enabled=False),
    )
    source = pymupdf.open(input_path)
    source_links = source[0].get_links()
    assert len(source_links) == 2
    source_rect = source_links[0]["from"]
    source_goto = next(link for link in source_links if link["kind"] == pymupdf.LINK_GOTO)
    source_to = source_goto["to"]
    source.close()

    process_pdf(input_path, output_path, config)
    doc = pymupdf.open(output_path)
    links = doc[0].get_links()
    assert len(links) == 2
    assert abs(links[0]["from"].x0 - (source_rect.x0 + mm_to_pt(15.0))) < 1.0
    goto = next(link for link in links if link["kind"] == pymupdf.LINK_GOTO)
    assert goto.get("page") == 2
    assert abs(goto["to"].x - (source_to.x + mm_to_pt(15.0))) < 1.5
    assert abs(goto["to"].y - source_to.y) < 1.5
    assert doc.get_toc() == [[1, "Birinci Bölüm", 1], [2, "Alt Başlık", 2], [1, "İkinci Bölüm", 4]]
    doc.close()


def test_reference_annotations_forms_and_text_are_preserved(tmp_path):
    input_path = str(tmp_path / "reference.pdf")
    output_path = str(tmp_path / "reference_out.pdf")
    create_mixed_sample_pdf(input_path)

    config = config_for(
        page_boxes=PageBoxSettings(size_mode="auto", odd_x_mm=15.0, even_x_mm=0.0),
        margins=MarginSettings(enabled=True, extra_bottom_mm=10.0, bottom_mode="expand"),
        page_numbers=PageNumberSettings(enabled=True, start_page=2),
        flatten_annotations=True,
    )
    report = scan_clipping(input_path, config)
    assert not report.has_issues, report.summary()

    process_pdf(input_path, output_path, config)
    verification = verify_output(input_path, output_path, config)
    assert verification.ok, verification.lines()
    assert verification.has_text is True
    assert verification.dropped_annots >= 3
    assert verification.flattened is True
    assert any("gömüldü" in line for line in verification.lines())
    doc = pymupdf.open(output_path)
    assert len(doc) == 4
    assert "Referans Belge" in doc[0].get_text()
    assert doc.get_toc() == [[1, "Birinci Bölüm", 1], [2, "Alt Başlık", 2], [1, "İkinci Bölüm", 4]]
    doc.close()


def test_without_flatten_annotations_are_reported_as_lost(tmp_path):
    input_path = str(tmp_path / "reference2.pdf")
    output_path = str(tmp_path / "reference2_out.pdf")
    create_mixed_sample_pdf(input_path)
    config = config_for(flatten_annotations=False)
    process_pdf(input_path, output_path, config)
    report = verify_output(input_path, output_path, config)
    assert report.dropped_annots >= 3
    assert report.flattened is False
    assert any("taşınmadı" in line for line in report.lines())


def test_verify_output_detects_lost_text(tmp_path):
    input_path = str(tmp_path / "verify_in.pdf")
    output_path = str(tmp_path / "verify_out.pdf")
    create_sample_a4_pdf(input_path, pages=2)
    process_pdf(input_path, output_path, config_for())

    # Çıktıyı bilerek boz: ikinci sayfayı sil.
    doc = pymupdf.open(output_path)
    doc.delete_page(1)
    broken = str(tmp_path / "verify_broken.pdf")
    doc.save(broken)
    doc.close()
    report = verify_output(input_path, broken, config_for())
    assert not report.ok
    assert report.pages_out == 1


def test_atomic_save_leaves_no_temp_files(tmp_path):
    input_path = str(tmp_path / "atomic_in.pdf")
    output_dir = tmp_path / "cikti" / "alt"
    output_path = str(output_dir / "atomic_out.pdf")
    create_sample_a4_pdf(input_path, pages=2)
    process_pdf(input_path, output_path, config_for())
    assert os.path.exists(output_path)
    leftovers = [name for name in os.listdir(output_dir) if name.startswith(".~")]
    assert leftovers == []


def test_cancel_stops_processing(tmp_path):
    input_path = str(tmp_path / "cancel_in.pdf")
    output_path = str(tmp_path / "cancel_out.pdf")
    create_sample_a4_pdf(input_path, pages=4)
    with pytest.raises(ProcessCancelled):
        process_pdf(input_path, output_path, config_for(), should_cancel=lambda: True)
    assert not os.path.exists(output_path)


def test_merge_preserves_toc_metadata_and_warns_missing(tmp_path):
    first = str(tmp_path / "first.pdf")
    second = str(tmp_path / "second.pdf")
    output = str(tmp_path / "merged.pdf")
    create_mixed_sample_pdf(first)
    create_sample_a4_pdf(second, pages=2)
    warnings: list = []
    merge_pdfs([first, second, str(tmp_path / "yok.pdf")], output, warnings=warnings)

    assert any("atlandı" in warning for warning in warnings)
    doc = pymupdf.open(output)
    assert len(doc) == 6
    assert doc.metadata.get("title") == "Referans PDF Seti"
    assert doc.get_toc() == [[1, "Birinci Bölüm", 1], [2, "Alt Başlık", 2], [1, "İkinci Bölüm", 4]]
    doc.close()


def test_merge_output_equals_input_is_blocked(tmp_path):
    first = str(tmp_path / "m1.pdf")
    second = str(tmp_path / "m2.pdf")
    create_sample_a4_pdf(first, pages=1)
    create_sample_a4_pdf(second, pages=1)
    with pytest.raises(OutputPathError):
        merge_pdfs([first, second], first)


def test_merge_missing_only_file_raises(tmp_path):
    with pytest.raises(Exception):
        merge_pdfs([str(tmp_path / "yok1.pdf")], str(tmp_path / "out.pdf"))


def test_numbering_plan_continuous_and_styles():
    config = config_for(page_numbers=PageNumberSettings(
        enabled=True, start_num=1, start_page=1, skip_pages_str="1, 4",
        continuous_numbering=True, format_style="dash",
    ))
    assert numbering_plan(6, config) == [None, "- 1 -", "- 2 -", None, "- 3 -", "- 4 -"]

    config.page_numbers.continuous_numbering = False
    assert numbering_plan(6, config) == [None, "- 2 -", "- 3 -", None, "- 5 -", "- 6 -"]

    assert format_page_number_text("total", 3, 12) == "3 / 12"
    assert format_page_number_text("label", 3, 12) == "Sayfa 3"


def test_validation_reports_bad_values():
    config = PdfProcessConfig(
        page_boxes=PageBoxSettings(target_width_mm=0, target_height_mm=-5),
        margins=MarginSettings(extra_bottom_mm=-1),
        page_numbers=PageNumberSettings(font_size=0, start_page=0, position="yanlis"),
    )
    result = validate_config(config)
    assert not result.ok
    assert len(result.errors) >= 4


def test_roman_and_custom_number_templates():
    assert format_page_number_text("roman", 4, 10) == "iv"
    assert format_page_number_text("roman_upper", 9, 10) == "IX"
    assert format_page_number_text("number", 4, 10,
                                   "{n}/{N} - {ROMAN}") == "4/10 - IV"
    assert format_page_number_text("number", 4, 10, "Sayfa {n} / {N}") == "Sayfa 4 / 10"
    assert to_roman(3999) == "MMMCMXCIX"
    assert to_roman(0) == "0"

    config = config_for(page_numbers=PageNumberSettings(
        enabled=True, format_style="roman", start_num=1, start_page=1,
    ))
    assert numbering_plan(3, config) == ["i", "ii", "iii"]


def test_unicode_number_template_embeds_font(tmp_path):
    input_path = str(tmp_path / "unicode_in.pdf")
    output_path = str(tmp_path / "unicode_out.pdf")
    create_sample_a4_pdf(input_path, pages=1)
    settings = PageNumberSettings(
        enabled=True, format_style="number", start_num=1,
        text_template="Sayfa {n} • İĞŞ",
    )
    if resolve_number_font(settings, ["Sayfa 1 • İĞŞ"]) is None:
        pytest.skip("Sistemde gömülebilir Unicode yazı tipi bulunamadı.")
    config = config_for(page_numbers=settings)
    process_pdf(input_path, output_path, config)
    doc = pymupdf.open(output_path)
    text = doc[0].get_text()
    assert "Sayfa 1" in text
    assert "İĞŞ" in text
    doc.close()


def test_pad_to_multiple_of_four(tmp_path):
    input_path = str(tmp_path / "pad_in.pdf")
    output_path = str(tmp_path / "pad_out.pdf")
    create_sample_a4_pdf(input_path, pages=5)
    config = config_for(pad_to_multiple=4,
                        page_numbers=PageNumberSettings(enabled=False))
    process_pdf(input_path, output_path, config)
    doc = pymupdf.open(output_path)
    assert len(doc) == 8
    assert "Sayfa 5" in doc[4].get_text()
    assert doc[5].get_text().strip() == ""
    assert doc[7].get_text().strip() == ""
    assert abs(pt_to_mm(doc[7].rect.width) - 210.0) < 0.2
    doc.close()
    report = verify_output(input_path, output_path, config)
    assert report.ok, report.lines()
    assert report.pages_out == 8
    assert report.pad_pages == 3
    assert any("boş" in line for line in report.lines())


def test_merge_page_ranges_and_bookmarks(tmp_path):
    first = str(tmp_path / "range_1.pdf")
    second = str(tmp_path / "range_2.pdf")
    output = str(tmp_path / "range_out.pdf")
    create_sample_a4_pdf(first, pages=4)
    create_sample_a4_pdf(second, pages=3)
    merge_pdfs([
        {"path": first, "pages": "2-3", "bookmark": "Bölüm A"},
        {"path": second, "pages": "2", "bookmark": "Bölüm B"},
    ], output, add_bookmarks=True)
    doc = pymupdf.open(output)
    assert len(doc) == 3
    assert "Sayfa 2" in doc[0].get_text()
    assert "Sayfa 3" in doc[1].get_text()
    assert "Sayfa 2" in doc[2].get_text()
    toc = doc.get_toc()
    assert [1, "Bölüm A", 1] in toc
    assert [1, "Bölüm B", 3] in toc
    doc.close()


def test_merge_page_selection_maps_existing_toc(tmp_path):
    source = str(tmp_path / "toc_source.pdf")
    output = str(tmp_path / "toc_selected.pdf")
    create_mixed_sample_pdf(source)
    merge_pdfs([{"path": source, "pages": "1,4"}], output)
    doc = pymupdf.open(output)
    assert len(doc) == 2
    assert doc.get_toc() == [[1, "Birinci Bölüm", 1], [1, "İkinci Bölüm", 2]]
    doc.close()


def test_merge_invalid_page_range_warns_and_skips(tmp_path):
    source = str(tmp_path / "invalid_range.pdf")
    output = str(tmp_path / "invalid_range_out.pdf")
    create_sample_a4_pdf(source, pages=2)
    warnings: list = []
    with pytest.raises(StudioError):
        merge_pdfs([{"path": source, "pages": "99"}], output, warnings=warnings)
    assert any("sayfa bulunmadı" in warning for warning in warnings)


def test_config_roundtrip():
    config = PdfProcessConfig(
        page_boxes=PageBoxSettings(size_mode="auto", odd_x_mm=18.5,
                                   exclude_pages_str="2, 7-8"),
        margins=MarginSettings(extra_bottom_mm=12.0, bottom_mode="fit",
                               exclude_pages_str="5"),
        page_numbers=PageNumberSettings(skip_pages_set={1, 5}, skip_pages_str="9",
                                        format_style="total", start_num=3),
        quality_mode="standard",
        flatten_annotations=False,
    )
    restored = config_from_dict(config_to_dict(config))
    assert restored.page_boxes == config.page_boxes
    assert restored.margins == config.margins
    assert restored.page_numbers.skip_pages_set == {1, 5}
    assert restored.page_boxes.exclude_pages_str == "2, 7-8"
    assert restored.margins.exclude_pages_str == "5"
    assert restored.quality_mode == "standard"
    assert restored.flatten_annotations is False
    # Eksik/bozuk profil çökmeden varsayılana döner.
    fallback = config_from_dict({"page_boxes": {"target_width_mm": "abc"}})
    assert fallback.page_boxes.target_width_mm == 225.0


def test_excluded_pages_keep_source_size_and_get_no_pay(tmp_path):
    input_path = str(tmp_path / "exclude_in.pdf")
    output_path = str(tmp_path / "exclude_out.pdf")
    create_sample_a4_pdf(input_path, pages=5)
    source = pymupdf.open(input_path)
    base_x = word_bbox(source, 0, "Sayfa")[0]
    source.close()

    config = config_for(
        page_boxes=PageBoxSettings(target_width_mm=225.0, target_height_mm=297.0,
                                   odd_x_mm=15.0, even_x_mm=0.0,
                                   exclude_pages_str="1, 3"),
        margins=MarginSettings(enabled=True, extra_bottom_mm=20.0, bottom_mode="expand",
                               exclude_pages_str="1, 3"),
    )
    assert scan_clipping(input_path, config).has_issues is False
    process_pdf(input_path, output_path, config)

    doc = pymupdf.open(output_path)
    sizes = [(round(pt_to_mm(page.rect.width), 1), round(pt_to_mm(page.rect.height), 1))
             for page in doc]
    assert sizes == [(210.0, 297.0), (225.0, 317.0), (210.0, 297.0),
                     (225.0, 317.0), (225.0, 317.0)]
    assert abs(word_bbox(doc, 0, "Sayfa")[0] - base_x) < 1.0
    assert abs(word_bbox(doc, 1, "Sayfa")[0] - base_x) < 1.0
    assert abs(word_bbox(doc, 4, "Sayfa")[0] - (base_x + mm_to_pt(15.0))) < 1.0
    verify = verify_output(input_path, output_path, config)
    assert verify.ok, verify.lines()
    doc.close()


def test_module_exclusions_are_independent():
    base = dict(target_width_mm=225.0, target_height_mm=297.0,
                odd_x_mm=15.0, even_x_mm=0.0)
    margins = MarginSettings(enabled=True, extra_bottom_mm=20.0, bottom_mode="expand")

    # Yalnızca cilt payından çıkarılan sayfa: kenar boşluğu yine uygulanır.
    boxes_only = PageBoxSettings(exclude_pages_str="1", **base)
    layout = compute_layout(mm_to_pt(210), mm_to_pt(297),
                            config_for(page_boxes=boxes_only, margins=margins), 0)
    assert abs(pt_to_mm(layout.target_w) - 210.0) < 0.2
    assert abs(pt_to_mm(layout.target_h) - 317.0) < 0.2
    assert layout.content.x0 == 0
    assert abs(pt_to_mm(layout.content.y0)) < 0.01  # alt pay eklenir, içerik yine üstte

    # Yalnızca kenar boşluğundan çıkarılan sayfa: cilt payı yine uygulanır.
    margins_only = MarginSettings(enabled=True, extra_bottom_mm=20.0, bottom_mode="expand",
                                  exclude_pages_str="1")
    layout = compute_layout(mm_to_pt(210), mm_to_pt(297),
                            config_for(page_boxes=PageBoxSettings(**base),
                                       margins=margins_only), 0)
    assert abs(pt_to_mm(layout.target_w) - 225.0) < 0.2
    assert abs(pt_to_mm(layout.target_h) - 297.0) < 0.2
    assert abs(pt_to_mm(layout.content.x0) - 15.0) < 0.2


def test_excluded_page_preview_uses_source_size(tmp_path):
    input_path = str(tmp_path / "exclude_preview.pdf")
    create_sample_a4_pdf(input_path, pages=2)
    config = config_for(
        page_boxes=PageBoxSettings(target_width_mm=225.0, target_height_mm=297.0,
                                   odd_x_mm=15.0, even_x_mm=0.0,
                                   exclude_pages_set={1}),
    )
    pages = render_preview(input_path, config, pages=(0, 1), zoom=1.0)
    assert abs(pages[0].width_mm - 210.0) < 0.2
    assert abs(pages[1].width_mm - 225.0) < 0.2


def _decodes(data: bytes) -> bool:
    """Önizleme baytları (PPM/PNG) Pillow ile açılabilmeli."""
    import io
    from PIL import Image
    return Image.open(io.BytesIO(data)).size[0] > 0


def test_preview_contains_layout_and_number(tmp_path):
    input_path = str(tmp_path / "preview.pdf")
    create_sample_a4_pdf(input_path, pages=3)
    config = config_for(
        page_boxes=PageBoxSettings(target_width_mm=225.0, target_height_mm=297.0,
                                   odd_x_mm=15.0, even_x_mm=0.0),
        margins=MarginSettings(enabled=True, extra_bottom_mm=20.0, bottom_mode="expand"),
        page_numbers=PageNumberSettings(enabled=True, start_num=1, format_style="number"),
    )
    pages = render_preview(input_path, config, pages=(0, 1), zoom=1.0)
    assert len(pages) == 2
    assert _decodes(pages[0].png)
    assert abs(pages[0].width_mm - 225.0) < 0.2
    assert abs(pages[0].height_mm - 317.0) < 0.2
    assert pages[0].number_text == "1"
    assert pages[1].number_text == "2"
    assert pages[0].clipped is False


def test_preview_handles_rotated_and_mixed_sizes(tmp_path):
    input_path = str(tmp_path / "preview_mixed.pdf")
    create_mixed_sample_pdf(input_path)
    config = config_for(page_boxes=PageBoxSettings(size_mode="auto", odd_x_mm=15.0))
    pages = render_preview(input_path, config, pages=(0, 1, 2, 3), zoom=1.0)
    assert len(pages) == 4
    for page in pages:
        assert _decodes(page.png)
        assert page.width_mm > 0 and page.height_mm > 0
    # 3. sayfa 90° döndürülmüş kaynak; önizleme yine de üretilebilir.
    assert pages[2].clipped is False


def test_preview_flags_clipping_in_shift_mode(tmp_path):
    input_path = str(tmp_path / "preview_shift.pdf")
    create_sample_a4_pdf(input_path, pages=2)
    config = config_for(
        page_boxes=PageBoxSettings(target_width_mm=210.0, target_height_mm=297.0,
                                   odd_x_mm=0.0, even_x_mm=0.0),
        margins=MarginSettings(enabled=True, extra_bottom_mm=30.0, bottom_mode="shift"),
    )
    pages = render_preview(input_path, config, pages=(0,), zoom=1.0)
    assert pages[0].clipped is True
    assert pages[0].clip_mm[2] > 1.0


def test_clip_tolerance_ignores_submillimeter_noise():
    assert CLIP_TOLERANCE_PT < mm_to_pt(0.5)


# ---------------------------------------------------------------------------
# Döndürülmüş (/Rotate) ve kırpılmış (CropBox) sayfalar
# ---------------------------------------------------------------------------
CORNER_LABELS = ("KOSE1", "KOSE2", "KOSE3", "KOSE4")


def create_rotated_pdf(path: str, rotation: int, crop: bool = False,
                       cropbox: pymupdf.Rect | None = None) -> None:
    """Dört köşesinde ayrı etiket olan, istenen açıda döndürülmüş örnek sayfa."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for x, y, label in ((40, 60, "KOSE1"), (420, 60, "KOSE2"),
                        (40, 780, "KOSE3"), (420, 780, "KOSE4")):
        page.insert_text((x, y), label, fontsize=22)
    if crop:
        page.set_cropbox(cropbox or pymupdf.Rect(30, 50, 565, 792))
    page.set_rotation(rotation)
    doc.save(path)
    doc.close()


def visible_words(page: pymupdf.Page) -> list[str]:
    """Sayfa sınırı içinde kalan sözcükler (glif taşması sayılmaz)."""
    rect = page.rect
    words = []
    for w in page.get_text("words"):
        x0, y0, x1, y1 = w[:4]
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        if rect.x0 <= cx <= rect.x1 and rect.y0 <= cy <= rect.y1:
            words.append(w[4])
    return sorted(words)


def word_boxes(page: pymupdf.Page, offset: tuple[float, float] = (0.0, 0.0)):
    """Sözcükleri (metin, x, y) üçlüsü olarak; istenen kaydırma uygulanmış hâlde."""
    dx, dy = offset
    return sorted((w[4], round(w[0] - dx, 1), round(w[1] - dy, 1))
                  for w in page.get_text("words"))


def differing_pixels(first: pymupdf.Pixmap, second: pymupdf.Pixmap) -> float:
    """İki aynı boyutlu pixmap'in farklı piksellerinin oranı."""
    a, b = first.samples, second.samples
    total = len(a) // 3
    different = sum(1 for i in range(0, len(a), 3) if a[i:i + 3] != b[i:i + 3])
    return different / total if total else 0.0


def assert_boxes_close(first, second, tolerance: float = 0.6) -> None:
    assert len(first) == len(second), (first, second)
    for (word_a, xa, ya), (word_b, xb, yb) in zip(first, second):
        assert word_a == word_b
        assert abs(xa - xb) <= tolerance and abs(ya - yb) <= tolerance, (word_a, (xa, ya), (xb, yb))


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("crop", [False, True])
def test_rotation_and_cropbox_preserve_content_exactly(tmp_path, rotation, crop):
    input_path = str(tmp_path / f"rot{rotation}_crop{int(crop)}.pdf")
    output_path = str(tmp_path / "out.pdf")
    create_rotated_pdf(input_path, rotation, crop=crop)
    config = config_for(page_boxes=PageBoxSettings(size_mode="auto", odd_x_mm=15.0))

    report = scan_clipping(input_path, config)
    assert not report.has_issues, report.summary()
    process_pdf(input_path, output_path, config)

    source = open_pdf(input_path)
    layout = compute_layout(source[0].rect.width, source[0].rect.height, config, 0)
    normalize_page_rotations(source)
    reference = source[0].get_pixmap(dpi=100, alpha=False)
    source_boxes = word_boxes(source[0])

    out = pymupdf.open(output_path)
    assert len(out) == 1
    assert abs(out[0].rect.width - layout.target_w) < 0.5
    assert abs(out[0].rect.height - layout.target_h) < 0.5
    # Görünür alandaki dört köşe etiketi de çıktıda olmalı.
    assert visible_words(out[0]) == sorted(CORNER_LABELS)
    # Sözcükler cilt payı kadar kayar, başka hiçbir şey değişmez.
    offset = (layout.content.x0, layout.content.y0)
    assert_boxes_close(word_boxes(out[0], offset), source_boxes)
    # Görüntü de aynı olmalı: yalnızca yeniden yerleştirmenin kenar yumuşatma
    # farkına izin verilir (ölçülen fark %0,1'in altında).
    pixel_layout = compute_layout(source[0].rect.width, source[0].rect.height,
                                  config_for(page_boxes=PageBoxSettings(size_mode="auto")), 0)
    rendered = out[0].get_pixmap(dpi=100, alpha=False, clip=pixel_layout.content)
    assert (rendered.width, rendered.height) == (reference.width, reference.height)
    assert differing_pixels(reference, rendered) < 0.005
    out.close()
    source.close()

    verification = verify_output(input_path, output_path, config)
    assert verification.ok, verification.lines()
    assert verification.lost_words == 0


def test_rotated_preview_matches_processed_output(tmp_path):
    input_path = str(tmp_path / "rot_preview.pdf")
    create_rotated_pdf(input_path, 90)
    config = config_for(page_boxes=PageBoxSettings(size_mode="auto", odd_x_mm=15.0))
    pages = render_preview(input_path, config, pages=(0,), zoom=1.0)
    assert len(pages) == 1
    assert pages[0].clipped is False
    # 90° döndürülmüş dikey sayfa, görünür hâlde yataydır: 842 x 595 pt.
    assert abs(pages[0].width_mm - pt_to_mm(842 + mm_to_pt(15.0))) < 0.3
    assert abs(pages[0].height_mm - pt_to_mm(595)) < 0.3


# ---------------------------------------------------------------------------
# "Cilt payına sığdır": taşan içeriği kırpmak yerine küçültme
# ---------------------------------------------------------------------------
LANDSCAPE_WORDS = [f"kelime{index}" for index in range(1, 11)]


def create_wide_pdf(path: str, rotation: int = 0) -> None:
    """Hedef sayfaya sığmayan, geniş bir sayfa üretir."""
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    x = 60
    for word in LANDSCAPE_WORDS:
        page.insert_text((x, 300), word, fontsize=14)
        x += 72
    page.set_rotation(rotation)
    doc.save(path)
    doc.close()


def test_shrink_fits_oversized_content_without_clipping(tmp_path):
    input_path = str(tmp_path / "wide.pdf")
    output_path = str(tmp_path / "wide_out.pdf")
    create_wide_pdf(input_path)
    config = config_for(
        page_boxes=PageBoxSettings(
            size_mode="fixed", target_width_mm=225.0, target_height_mm=297.0,
            odd_x_mm=15.0, even_x_mm=0.0, overflow_mode="shrink",
        ),
    )

    assert scan_clipping(input_path, config).has_issues is False
    process_pdf(input_path, output_path, config)

    out = pymupdf.open(output_path)
    assert len(out) == 1
    assert abs(pt_to_mm(out[0].rect.width) - 225.0) < 0.2
    assert abs(pt_to_mm(out[0].rect.height) - 297.0) < 0.2
    text = out[0].get_text()
    assert [word for word in LANDSCAPE_WORDS if word in text] == LANDSCAPE_WORDS
    out.close()

    verification = verify_output(input_path, output_path, config)
    assert verification.ok, verification.lines()
    assert verification.lost_words == 0


def test_clip_mode_keeps_old_behaviour_and_reports_risk(tmp_path):
    input_path = str(tmp_path / "wide_clip.pdf")
    output_path = str(tmp_path / "wide_clip_out.pdf")
    create_wide_pdf(input_path)
    config = config_for(
        page_boxes=PageBoxSettings(
            size_mode="fixed", target_width_mm=225.0, target_height_mm=297.0,
            odd_x_mm=15.0, even_x_mm=0.0, overflow_mode="clip",
        ),
    )
    assert scan_clipping(input_path, config).has_issues is True
    process_pdf(input_path, output_path, config)
    verification = verify_output(input_path, output_path, config)
    assert verification.lost_words > 0  # tarama ile gerçek sonuç aynı şeyi söyler


def test_shrink_scale_and_roundtrip(tmp_path):
    config = PdfProcessConfig(
        page_boxes=PageBoxSettings(size_mode="fixed", overflow_mode="shrink",
                                   target_width_mm=225.0, target_height_mm=297.0,
                                   safe_edge_mm=5.0, odd_x_mm=15.0),
        margins=MarginSettings(enabled=False),
        page_numbers=PageNumberSettings(enabled=False),
    )
    restored = config_from_dict(config_to_dict(config))
    assert restored.page_boxes.overflow_mode == "shrink"
    assert restored.page_boxes.safe_edge_mm == pytest.approx(5.0)

    layout = compute_layout(842, 595, config, 0)
    assert 0.0 < layout.scale < 1.0
    assert layout.content.width <= mm_to_pt(225.0 - 15.0 - 5.0) + 0.01
    assert layout.content.height <= mm_to_pt(297.0 - 5.0) + 0.01

    config.page_boxes.overflow_mode = "clip"
    assert compute_layout(842, 595, config, 0).scale == 1.0



# ---------------------------------------------------------------------------
# Regresyon: inceleme turunda bulunan hatalar
# ---------------------------------------------------------------------------
def _make_toc_pdf(path, pages, toc):
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page()
    if toc:
        doc.set_toc(toc)
    doc.save(str(path))
    doc.close()


def test_merge_bookmark_precedes_and_nests_file_toc(tmp_path):
    a, b = tmp_path / "a.pdf", tmp_path / "b.pdf"
    _make_toc_pdf(a, 3, [[1, "A1", 1], [2, "A1.1", 2]])
    _make_toc_pdf(b, 2, [[1, "B1", 1]])
    out = tmp_path / "m.pdf"
    merge_pdfs([str(a), str(b)], str(out), add_bookmarks=True)
    toc = pymupdf.open(str(out)).get_toc()
    assert toc == [[1, "a", 1], [2, "A1", 1], [3, "A1.1", 2],
                   [1, "b", 4], [2, "B1", 4]]


def test_merge_page_range_with_orphan_toc_level_does_not_crash(tmp_path):
    src = tmp_path / "f.pdf"
    _make_toc_pdf(src, 4, [[1, "K1", 1], [2, "K1.1", 2], [2, "K1.2", 3], [1, "K2", 4]])
    out = tmp_path / "m.pdf"
    merge_pdfs([{"path": str(src), "pages": "2-3"}], str(out))
    toc = pymupdf.open(str(out)).get_toc()
    assert toc[0][0] == 1 and [t[1] for t in toc] == ["K1.1", "K1.2"]


def test_sanitize_toc_fixes_first_level_and_jumps():
    from core.gutter_engine import sanitize_toc
    assert sanitize_toc([[3, "a", 1], [5, "b", 2], [1, "c", 3]]) == [
        [1, "a", 1], [2, "b", 2], [1, "c", 3]]


def test_parse_page_ranges_accepts_en_dash_semicolon_and_caps_huge_ranges():
    from core.gutter_engine import MAX_PAGE_NUMBER, invalid_range_tokens
    assert parse_page_ranges("3–5; 9") == {3, 4, 5, 9}
    huge = parse_page_ranges("1-999999999")
    assert len(huge) == MAX_PAGE_NUMBER
    assert parse_page_ranges("0") == set()
    assert invalid_range_tokens("1-3, abc, 5-") == ["abc", "5-"]


def test_number_text_without_unicode_font_raises_instead_of_bullets(tmp_path, monkeypatch):
    import core.gutter_engine as ge
    monkeypatch.setattr(ge, "_number_font_candidates", lambda: [])
    src = tmp_path / "s.pdf"
    _make_toc_pdf(src, 2, None)
    cfg = ge.PdfProcessConfig()
    cfg.page_boxes.enabled = True
    cfg.page_numbers.enabled = True
    cfg.page_numbers.text_template = "Şube {n}"
    with pytest.raises(ge.ConfigError):
        ge.process_pdf(str(src), str(tmp_path / "o.pdf"), cfg)


def _make_marked_pdf(path, rotation=0, pages=3):
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), f"UST {i}", fontsize=24)
        page.insert_text((72, 780), "ALT satir", fontsize=24)
        page.draw_rect(pymupdf.Rect(300, 300, 500, 500), fill=(0.2, 0.2, 0.2))
        if rotation:
            page.set_rotation(rotation)
    doc.save(str(path))
    doc.close()


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_verify_render_check_passes_for_correct_output(tmp_path, rotation):
    from core.gutter_engine import verify_output
    src = tmp_path / "s.pdf"
    _make_marked_pdf(src, rotation)
    cfg = PdfProcessConfig()
    cfg.page_boxes.enabled = True
    cfg.page_boxes.odd_x_mm = cfg.page_boxes.even_x_mm = 15
    cfg.page_boxes.overflow_mode = "shrink"
    cfg.page_numbers.enabled = True
    out = tmp_path / "o.pdf"
    process_pdf(str(src), str(out), cfg)
    report = verify_output(str(src), str(out), cfg)
    assert report.render_checked == 3
    assert report.render_mismatch_pages == [] and report.ok


def test_verify_render_check_catches_unrotated_output(tmp_path):
    """Eski hata: /Rotate yok sayılarak basılan sayfa görsel karşılaştırmada yakalanmalı."""
    from core.gutter_engine import verify_output
    src = tmp_path / "s.pdf"
    _make_marked_pdf(src, 90)
    cfg = PdfProcessConfig()
    cfg.page_boxes.enabled = True
    cfg.page_boxes.overflow_mode = "shrink"
    source, bad = pymupdf.open(str(src)), pymupdf.open()
    for pno in range(len(source)):
        lay = compute_layout(842, 595, cfg, pno)
        page = bad.new_page(width=lay.target_w, height=lay.target_h)
        page.show_pdf_page(lay.content, source, pno)   # normalize edilmeden
    bad_path = tmp_path / "bad.pdf"
    bad.save(str(bad_path))
    report = verify_output(str(src), str(bad_path), cfg)
    assert report.render_mismatch_pages == [1, 2, 3] and not report.ok


# ---------------------------------------------------------------------------
# Birleştirme: sayfa aralığı tam kopya çıkarmadan eklenir
# ---------------------------------------------------------------------------
def test_contiguous_runs_groups_consecutive_pages():
    from core.gutter_engine import _contiguous_runs
    assert _contiguous_runs([1, 2, 3, 7, 9, 10]) == [(1, 3), (7, 7), (9, 10)]
    assert _contiguous_runs([5]) == [(5, 5)]
    assert _contiguous_runs([]) == []


def _make_linked_pdf(path, pages):
    doc = pymupdf.open()
    for i in range(pages):
        doc.new_page(width=595, height=842).insert_text((72, 100), f"SAYFA {i + 1}", fontsize=20)
    for i in range(pages):
        doc[i].insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(72, 160, 200, 180),
                            "uri": f"https://example.com/{i + 1}"})
    doc.set_toc([[1, "A", 1], [2, "A1", 2], [1, "B", 6], [2, "B1", pages]])
    doc.save(str(path))
    doc.close()


def test_merge_non_contiguous_ranges_keep_order_text_links_and_toc(tmp_path):
    src = tmp_path / "kaynak.pdf"
    _make_linked_pdf(src, 12)
    out = tmp_path / "m.pdf"
    merge_pdfs([{"path": str(src), "pages": "2-4, 9, 11-12"}], str(out))
    doc = pymupdf.open(str(out))
    assert [p.get_text().strip() for p in doc] == [
        f"SAYFA {n}" for n in (2, 3, 4, 9, 11, 12)]
    assert [[l["uri"] for l in p.get_links()] for p in doc] == [
        [f"https://example.com/{n}"] for n in (2, 3, 4, 9, 11, 12)]
    # Yer imleri yalnızca seçili sayfalara taşınır; "A1" 2. sayfada, "B1" son sayfada.
    assert doc.get_toc() == [[1, "A1", 1], [2, "B1", 6]]


def test_merge_range_inserts_pages_without_whole_file_copy(tmp_path, monkeypatch):
    """Aralık seçilince kaynağın tamamı hiçbir belgeye eklenmemeli (bellek)."""
    src = tmp_path / "kaynak.pdf"
    _make_linked_pdf(src, 12)
    calls = []
    original = pymupdf.Document.insert_pdf

    def spy(self, docsrc, *args, **kwargs):
        calls.append((kwargs.get("from_page", -1), kwargs.get("to_page", -1), docsrc.page_count))
        return original(self, docsrc, *args, **kwargs)

    monkeypatch.setattr(pymupdf.Document, "insert_pdf", spy)
    merge_pdfs([{"path": str(src), "pages": "2-3, 9"}], str(tmp_path / "m.pdf"))
    assert calls == [(1, 2, 12), (8, 8, 12)]
