"""Deterministik, gerçek PDF test belgeleri üretir (mock veri değildir)."""

from __future__ import annotations

from typing import Iterable, Tuple

import pymupdf

from gutter_engine import mm_to_pt


def create_sample_a4_pdf(file_path: str, pages: int = 4,
                         width_mm: float = 210.0, height_mm: float = 297.0) -> str:
    """A4 (veya verilen ölçüde) numaralı metin sayfaları üretir."""
    doc = pymupdf.open()
    width, height = mm_to_pt(width_mm), mm_to_pt(height_mm)
    for index in range(pages):
        page = doc.new_page(width=width, height=height)
        page.draw_rect(pymupdf.Rect(20, 20, width - 20, height - 20),
                       color=(0, 0, 1), width=1.5)
        page.insert_text(pymupdf.Point(50, 80), f"Sayfa {index + 1} Metin", fontsize=20)
    doc.save(file_path)
    doc.close()
    return file_path


def create_mixed_sample_pdf(file_path: str) -> str:
    """Karışık ebatlı, bağlantılı, yer imli ve form alanlı referans belge."""
    doc = pymupdf.open()

    # 1) A4 dikey: metin, vurgu açıklaması, not, form alanı, iki bağlantı
    page1 = doc.new_page(width=mm_to_pt(210), height=mm_to_pt(297))
    page1.insert_text(pymupdf.Point(60, 85), "Referans Belge - Birinci Sayfa", fontsize=16)
    page1.insert_text(pymupdf.Point(60, 115), "Türkçe: ğüşiöç İstanbul ĞŞİ", fontsize=12)
    page1.draw_rect(pymupdf.Rect(40, 40, mm_to_pt(210) - 40, mm_to_pt(297) - 40),
                     color=(0.1, 0.3, 0.7), width=1.2)
    page1.add_highlight_annot(pymupdf.Rect(56, 70, 320, 92))
    page1.add_text_annot(pymupdf.Point(360, 150), "Bu bir açıklama notudur.")

    widget = pymupdf.Widget()
    widget.field_name = "ad_soyad"
    widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
    widget.rect = pymupdf.Rect(60, 140, 300, 165)
    widget.field_value = ""
    widget.text_fontsize = 10
    page1.add_widget(widget)

    # 2) A5 dikey: farklı ebat
    page2 = doc.new_page(width=mm_to_pt(148), height=mm_to_pt(210))
    page2.insert_text(pymupdf.Point(40, 70), "İkinci Sayfa - A5", fontsize=14)
    page2.draw_rect(pymupdf.Rect(25, 25, mm_to_pt(148) - 25, mm_to_pt(210) - 25),
                     color=(0.2, 0.6, 0.3), width=1.0)

    # 3) A4 yatay (90° döndürülmüş)
    page3 = doc.new_page(width=mm_to_pt(210), height=mm_to_pt(297))
    page3.insert_text(pymupdf.Point(60, 90), "Üçüncü Sayfa - Döndürülmüş", fontsize=14)
    page3.set_rotation(90)

    # 4) Görsel içeren A4 sayfa
    page4 = doc.new_page(width=mm_to_pt(210), height=mm_to_pt(297))
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 80, 60), 0)
    pixmap.clear_with(0x3366CC)
    page4.insert_image(pymupdf.Rect(60, 100, 320, 295), pixmap=pixmap)
    page4.insert_text(pymupdf.Point(60, 350), "Dördüncü Sayfa - Görsel", fontsize=14)

    # Hedef sayfalar oluştuktan sonra bağlantılar eklenir.
    page1 = doc[0]
    page1.insert_link({
        "kind": pymupdf.LINK_GOTO,
        "from": pymupdf.Rect(60, 780, 260, 805),
        "page": 2,                       # 0 tabanlı: 3. sayfa
        "to": pymupdf.Point(0, 0),
    })
    page1.insert_link({
        "kind": pymupdf.LINK_URI,
        "from": pymupdf.Rect(60, 815, 260, 840),
        "uri": "https://example.com/referans",
    })

    doc.set_toc([
        [1, "Birinci Bölüm", 1],
        [2, "Alt Başlık", 2],
        [1, "İkinci Bölüm", 4],
    ])
    doc.set_metadata({
        "title": "Referans PDF Seti",
        "author": "PDF Baskı & Cilt Stüdyosu",
        "subject": "Bağlantı, yer imi, açıklama ve form testi",
    })
    doc.save(file_path)
    doc.close()
    return file_path


def create_encrypted_pdf(file_path: str, password: str = "gizli") -> str:
    """Parola korumalı PDF üretir (hata sınıfı testi)."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text(pymupdf.Point(60, 80), "Parolalı belge", fontsize=14)
    doc.save(file_path, encryption=pymupdf.PDF_ENCRYPT_AES_256,
             user_pw=password, owner_pw="sahip")
    doc.close()
    return file_path


def word_bbox(doc: pymupdf.Document, page_index: int, word: str) -> Tuple[float, float]:
    """Sayfadaki ilk eşleşen sözcüğün (x0, y0) konumunu döndürür."""
    for item in doc[page_index].get_text("words"):
        if item[4] == word:
            return item[0], item[1]
    raise AssertionError(f"'{word}' sözcüğü {page_index + 1}. sayfada bulunamadı")


def link_rects(doc: pymupdf.Document, page_index: int) -> Iterable[pymupdf.Rect]:
    return [link["from"] for link in doc[page_index].get_links()]
