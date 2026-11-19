"""P2-35: kırpma uyarılarının gösterimi (v2.6.13).

Gruplama (motor), terim sözlüğü (``page_layout_model``), önizleme uyarısı ve lejantı,
iki diyaloğun ortak iskeleti ve metin kutusu kenarlığı.
"""

from __future__ import annotations

import os
import tempfile
import pathlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402

import core.page_layout_model as plm  # noqa: E402
from core.gutter_engine import (  # noqa: E402
    ClipIssue,
    ScanReport,
    format_clip_group,
    group_clip_lines,
)
from ui import qt_compat as ctk  # noqa: E402


# --- gruplama (motor) -------------------------------------------------------
def test_identical_consecutive_pages_collapse_into_a_range():
    report = ScanReport(total_pages=9, issues=[ClipIssue(page=i, top_mm=4.0) for i in range(1, 10)])
    text = report.summary(10)
    assert "9 sayfada" in text
    assert "Sayfa 1–9: üst 4.0 mm" in text
    assert text.count("Sayfa ") == 1


def test_grouping_splits_on_value_change_and_page_gap():
    groups = group_clip_lines([(1, "üst 4.0 mm"), (2, "üst 4.0 mm"), (3, "alt 1.0 mm"),
                               (5, "alt 1.0 mm"), (4, "alt 1.0 mm")])
    assert groups == [(1, 2, "üst 4.0 mm"), (3, 5, "alt 1.0 mm")]
    assert group_clip_lines([(1, "a"), (3, "a")]) == [(1, 1, "a"), (3, 3, "a")]
    assert format_clip_group(3, 3, "x") == "Sayfa 3: x"
    assert format_clip_group(1, 9, "x") == "Sayfa 1–9: x"


def test_summary_limit_counts_groups_and_reports_remaining_pages():
    issues = [ClipIssue(page=p, top_mm=float(p % 2 + 1)) for p in range(1, 8)]  # hepsi ayrı grup
    text = ScanReport(total_pages=7, issues=issues).summary(limit=3)
    assert text.count("Sayfa ") == 3
    assert "… ve 4 sayfa daha." in text


def test_describe_and_clean_report_unchanged():
    assert ClipIssue(page=2, left_mm=1.25, top_mm=4.0).describe() == "Sayfa 2: sol 1.2 mm, üst 4.0 mm"
    assert "taşması yok" in ScanReport(total_pages=3).summary()


# --- terim sözlüğü ----------------------------------------------------------
def test_choice_names_come_from_the_ui_labels():
    assert plm.CHOICE_NAMES == {
        plm.CHOICE_EXTEND: "Sayfa uzasın",
        plm.CHOICE_SHRINK: "İçerik küçülsün",
        plm.CHOICE_CLIP: "Taşan kırpılsın",
    }
    for key, name in plm.CHOICE_NAMES.items():
        assert plm.OVERFLOW_CHOICES[key][0].startswith(name)


def test_engine_shift_warning_is_translated_to_ui_names():
    from core.gutter_engine import validate_config, PdfProcessConfig
    cfg = PdfProcessConfig()
    cfg.margins.enabled = True
    cfg.margins.bottom_mode = "shift"
    cfg.margins.extra_bottom_mm = 10
    engine_message = validate_config(cfg).warnings[0]
    assert "'Kaydır'" in engine_message              # motor çıktısı değişmedi
    text = plm.ui_warning(engine_message)
    assert "Kaydır" not in text and "'Uzat'" not in text and "'Sığdır'" not in text
    for name in plm.CHOICE_NAMES.values():
        assert name in text
    assert plm.ui_warning("başka bir uyarı") == "başka bir uyarı"


# --- önizleme uyarısı ve lejant -------------------------------------------
def _built_panel():
    from tests.test_preview_panel import FakeHost
    from ui.preview import PreviewPanel
    root = ctk.CTk()
    root.withdraw()
    panel = PreviewPanel(FakeHost())
    parent = ctk.CTkFrame(root)
    parent.put("v", fill="both", expand=True)
    panel.build(parent)
    return root, parent, panel


def test_preview_warning_groups_equal_spread_pages(monkeypatch):
    from tests.test_preview_panel import _page
    monkeypatch.setattr("ui.preview.config_to_dict", lambda config: {})
    root, parent, panel = _built_panel()
    try:
        panel.show(panel.gen, [_page(0, clipped=True), _page(1, clipped=True)], None)
        text = panel.preview_warning.cget("text")
        assert "Sayfa 1–2: sağ 2.5 mm taşıyor." in text
        assert text.count("Sayfa ") == 1
        panel.show(panel.gen, [_page(0, clipped=True), _page(1)], None)
        assert "Sayfa 1: sağ 2.5 mm" in panel.preview_warning.cget("text")
    finally:
        parent.destroy()
        root.destroy()


def test_legend_swatch_sits_next_to_its_label_and_items_hug_the_left(monkeypatch):
    monkeypatch.setattr("ui.preview.config_to_dict", lambda config: {})
    root, parent, panel = _built_panel()
    try:
        root.resize(900, 700)
        root.show()
        panel.legend.show()  # Legend is hidden in the no-document empty state.
        ctk_app = ctk.ensure_qapp()
        ctk_app.processEvents()
        items = [w for w in panel.legend.children() if isinstance(w, ctk.CTkFrame)]
        assert len(items) == 3
        assert items[0].pos().x() == 0
        for item in items:
            swatch, label = [c for c in item.children() if isinstance(c, ctk.CTkLabel)]
            gap = label.pos().x() - (swatch.pos().x() + swatch.width())
            assert 0 <= gap <= 8, gap
            assert item.width() <= swatch.width() + label.width() + 12
        # fazla genişlik sağdaki dolguya gider: son öge sağ kenara yapışmaz
        assert items[-1].pos().x() + items[-1].width() < panel.legend.width() - 40
    finally:
        parent.destroy()
        root.destroy()


# --- diyaloglar -------------------------------------------------------------
@pytest.fixture(scope="module")
def win():
    from app import ModernGutterApp
    folder = pathlib.Path(tempfile.mkdtemp())
    app = ModernGutterApp(settings_path=folder / "s.json", log_path=folder / "l.log")
    app.resize(1300, 800)
    app.show()
    app.update()
    yield app
    app.destroy()


def _open(win, opener):
    before = set(win.findChildren(ctk.CTkToplevel))
    opener()
    (dlg,) = [d for d in win.findChildren(ctk.CTkToplevel) if d not in before]
    return dlg


def _report():
    return ScanReport(total_pages=9, issues=[ClipIssue(page=i, top_mm=4.0) for i in range(1, 10)])


def _ask_dialog(win):
    captured = {}
    original = win.wait_window

    def fake(dialog):
        dialog.show()
        win.update()
        captured["dialog"] = dialog
        captured["image"] = dialog.grab().toImage()

    win.wait_window = fake
    try:
        win._ask_clip_action(_report())
    finally:
        win.wait_window = original
    return captured["dialog"], captured["image"]


def test_scan_and_ask_dialogs_share_title_heading_and_layout(win):
    scan = _open(win, lambda: win._show_scan_report(_report()))
    ask, _img = _ask_dialog(win)
    try:
        assert scan.windowTitle() == ask.windowTitle() == "Kırpma riski"
        heads = []
        for dlg in (scan, ask):
            frame = dlg.layout().itemAt(0).widget()
            label = next(c for c in frame.children() if isinstance(c, ctk.CTkLabel))
            heads.append((label.text(), label.palette().windowText().color().name()))
            box = next(c for c in frame.children() if isinstance(c, ctk.CTkTextbox))
            assert box.isReadOnly()
        assert heads[0] == heads[1]            # aynı başlık metni ve rengi
        assert scan.width() == ask.width()
    finally:
        scan.destroy()
        ask.destroy()


def test_dialog_textbox_is_sized_to_content_not_to_a_fixed_height(win):
    scan = _open(win, lambda: win._show_scan_report(_report()))
    try:
        frame = scan.layout().itemAt(0).widget()
        box = next(c for c in frame.children() if isinstance(c, ctk.CTkTextbox))
        needed = int(box.document().size().height())
        assert box.height() >= needed
        assert box.height() <= needed + 80      # eskiden gereğinden çok büyük ve boştu
        assert scan.height() < 400
    finally:
        scan.destroy()


def test_ask_dialog_uses_ui_terms(win):
    ask, _img = _ask_dialog(win)
    try:
        texts = {b.text() for b in ask.findChildren(ctk.CTkButton)}
        assert any(t.startswith(plm.CHOICE_NAMES[plm.CHOICE_SHRINK]) for t in texts)
        assert plm.CHOICE_NAMES[plm.CHOICE_CLIP] in texts
        assert "İptal" in texts
        assert "Sayfaya sığdır (önerilen)" not in texts
        body = next(c for c in ask.findChildren(ctk.CTkTextbox)).toPlainText()
        assert "Sayfaya sığdır" not in body and "Kırp ve devam et" not in body
        assert plm.CHOICE_NAMES[plm.CHOICE_SHRINK] in body
    finally:
        ask.destroy()


def test_textbox_border_is_self_painted_without_accent_line(win):
    """Alt kenarda yerel stilin vurgu çizgisi yok; kenarlık düz ``COLOR_BORDER`` rengi."""
    from ui.qt_compat import resolve_color
    from ui.theme import COLOR_BORDER
    scan = _open(win, lambda: win._show_scan_report(_report()))
    try:
        box = next(c for c in scan.findChildren(ctk.CTkTextbox))
        assert box.frameShape() == ctk.QFrame.Shape.NoFrame
        image = box.grab().toImage()
        want = QColor(resolve_color(COLOR_BORDER)).name()
        w, h = image.width(), image.height()
        for x, y in ((w // 2, h - 1), (w // 2, 0), (0, h // 2), (w - 1, h // 2)):
            assert image.pixelColor(x, y).name() == want, (x, y)
        # kenarlığın hemen içi zemin rengi (ikinci bir çizgi yok)
        assert image.pixelColor(w // 2, h - 2).name() != want
    finally:
        scan.destroy()
