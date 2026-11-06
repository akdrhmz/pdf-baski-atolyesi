"""P2-33 (birim etiketi) ve P2-34 (hedef ebat notu) yerleşim testleri (v2.6.12).

Saha bulgusu: dar pencerede birim etiketi (\"mm\") giriş kutusunun içine biniyordu ve
\"Hedef ebat\" notunun ikinci satırı görünmüyordu. Ölçüm ekran dışı Qt'de, birkaç
pencere genişliğinde yapılır.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui import qt_compat as ctk  # noqa: E402
from ui.widgets import FieldRow  # noqa: E402

# Gerçek içerik alanı en az CENTER_MIN_W (540) px; 420 bunun altında bir güvenlik payıdır.
WIDTHS = (900, 600, 420)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def shown(qapp):
    from tests.fake_context import FakeContext
    from ui.tabs.page_layout import PageLayoutTab
    root = ctk.CTk()
    frame = ctk.CTkFrame(root)
    frame.put("v", fill="both", expand=True)
    tab = PageLayoutTab("Sayfa Düzeni", FakeContext(), frame)
    tab.ensure_built()

    def resize(width: int) -> None:
        root.resize(width, 900)
        root.show()
        qapp.processEvents()
        qapp.processEvents()

    yield tab, frame, resize
    frame.destroy()
    root.destroy()


def _field_rows(tab):
    return [(name, w) for name, w in vars(tab).items() if isinstance(w, FieldRow)]


@pytest.mark.parametrize("width", WIDTHS)
def test_unit_label_never_overlaps_entry(shown, width):
    """Tüm ``FieldRow``'larda birim etiketinin sol kenarı ≥ giriş kutusunun sağ kenarı."""
    tab, frame, resize = shown
    # Güvenli kenar satırı yalnız sabit ebat + "İçerik küçülsün" iken görünür (P2-36).
    import page_layout_model as plm
    tab.set_overflow_choice(plm.CHOICE_SHRINK)
    resize(width)
    checked = 0
    for name, row in _field_rows(tab):
        if not row.isVisibleTo(frame):
            continue
        entry_right = row.entry.mapTo(row, row.entry.rect().topRight()).x()
        unit_left = row.unit_label.mapTo(row, row.unit_label.rect().topLeft()).x()
        assert unit_left >= entry_right, f"{name} @ {width}: birim={unit_left} < kutu sağı={entry_right}"
        checked += 1
    assert checked >= 9


def test_unit_label_keeps_text_width(shown):
    """Birim etiketi metin genişliğinin altına sıkıştırılamaz (kök neden: ezilen etiket)."""
    tab, _frame, resize = shown
    resize(420)
    for name, row in _field_rows(tab):
        want = row.unit_label.fontMetrics().horizontalAdvance(row.unit_label.text())
        assert row.unit_label.width() >= want, name


def test_unit_label_follows_unit_change(shown):
    tab, _frame, resize = shown
    resize(600)
    row = tab.f_width
    row.change_unit("mm", "in")
    text = row.unit_label.text()
    assert text != "mm"
    assert row.unit_label.width() >= row.unit_label.fontMetrics().horizontalAdvance(text)


@pytest.mark.parametrize("width", WIDTHS)
def test_target_row_wraps_instead_of_overlapping(shown, width):
    """Genişlik / Yükseklik sığmayınca alt satıra geçer; üst üste binmez."""
    tab, frame, resize = shown
    resize(width)
    items = [tab.f_width, tab.f_height]
    boxes = []
    for w in items:
        assert w.isVisibleTo(frame)
        top_left = w.mapTo(tab.target_line, w.rect().topLeft())
        boxes.append((top_left.x(), top_left.y(), w.width(), w.height()))
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            apart_x = a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0]
            apart_y = a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1]
            assert apart_x or apart_y, (width, a, b)
        assert a[0] + a[2] <= tab.target_line.width() + 1, (width, a)


def test_target_row_height_covers_all_rows(shown):
    """Sarılan satırların toplam yüksekliği kapsayıcıya sığar (alt satır kesilmez)."""
    tab, _frame, resize = shown
    resize(420)
    line = tab.target_line
    bottoms = [w.mapTo(line, w.rect().bottomLeft()).y()
               for w in (tab.f_width, tab.f_height)]
    assert max(bottoms) <= line.height() + 1


def _needed_height(label) -> int:
    rect = label.fontMetrics().boundingRect(0, 0, max(label.width(), 1), 10000,
                                            int(Qt.TextWordWrap), label.text())
    return rect.height()


@pytest.mark.parametrize("mode", ("fixed", "auto"))
@pytest.mark.parametrize("width", (1100, 800, 600, 420))
def test_target_note_fully_visible(shown, mode, width):
    """P2-34: not metninin tamamı görünür (etiket yüksekliği ≥ sarılmış metin yüksekliği)."""
    from ui.tabs.page_layout import SIZE_MODE_LABELS
    tab, _frame, resize = shown
    label = next(k for k, v in SIZE_MODE_LABELS.items() if v == mode)
    tab.seg_size_mode.set(label)
    tab.update_safe_edge_state()
    resize(width)
    notes = [tab.lbl_size_note] + ([tab.lbl_target_note] if mode == "fixed" else [])
    for note in notes:
        assert note.height() >= _needed_height(note), (mode, width, note.height(), _needed_height(note))


def test_apply_button_sits_in_the_paper_row_not_the_size_row(shown):
    """v2.6.15: "Hedefe uygula" kağıt + yön ile aynı satırda, genişlik/yükseklikten ayrı.

    v2.6.19'dan beri satır sarar: geniş alanda üçü tek çizgide, dar alanda düğme alt satıra
    iner (üst üste binme ``test_paper_row_widgets_never_overlap`` ile denetlenir).
    """
    tab, frame, resize = shown
    resize(900)
    assert tab.btn_apply_size.master is tab.paper_menu.master
    assert tab.btn_apply_size.master is not tab.target_line
    centers = [w.mapTo(frame, w.rect().center()).y()
               for w in (tab.paper_menu, tab.orientation_menu, tab.btn_apply_size)]
    assert max(centers) - min(centers) <= 2, centers
    a = tab.orientation_menu.mapTo(frame, tab.orientation_menu.rect().topRight()).x()
    b = tab.btn_apply_size.mapTo(frame, tab.btn_apply_size.rect().topLeft()).x()
    assert b > a


def test_apply_button_is_not_taller_than_its_neighbours(shown):
    """v2.6.18: kenarlıksız dolgu düğme, menü/segmentten taşıp üste girmesin."""
    from ui.theme import BTN_H
    tab, frame, resize = shown
    resize(600)
    assert tab.btn_apply_size.height() <= BTN_H - 2
    assert tab.btn_apply_size.height() <= tab.paper_menu.height()


@pytest.mark.parametrize("width", [900, 600, 420])
def test_paper_row_widgets_never_overlap(shown, width):
    """v2.6.19: kağıt menüsü, yön seçici ve \"Hedefe uygula\" dar alanda üst üste binmez."""
    tab, frame, resize = shown
    resize(width)
    boxes = []
    for w in (tab.paper_menu, tab.orientation_menu, tab.btn_apply_size):
        top_left = w.mapTo(frame, w.rect().topLeft())
        boxes.append((top_left.x(), top_left.y(), w.width(), w.height()))
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            apart = (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0]
                     or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1])
            assert apart, (width, a, b)
    # menü kilitli genişliğinden küçülmez (ok işareti kırpılmaz)
    assert tab.paper_menu.width() >= 150
