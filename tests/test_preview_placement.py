"""Önizleme paneli ve sekme geçişi açık yerleştirmesi (P3-15, 10. parça, v2.6.10)."""

from __future__ import annotations

import os
import pathlib
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QSizePolicy  # noqa: E402

from app import ModernGutterApp  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def win(tmp_path_factory):
    folder = tmp_path_factory.mktemp("preview_placement")
    app = ModernGutterApp(settings_path=folder / "s.json", log_path=folder / "l.log")
    app.update()
    yield app
    app.destroy()


def _m(widget, kind="grid"):
    m = widget._ensure_layout(kind).contentsMargins()
    return (m.left(), m.top(), m.right(), m.bottom())


@pytest.mark.parametrize("name", ["preview.py", "window.py"])
def test_no_grid_or_pack_calls_left(name):
    text = (ROOT / "ui" / name).read_text(encoding="utf-8")
    assert not re.findall(r"\.(grid|pack)\(", text)


def test_preview_card_margins_are_explicit(win):
    assert _m(win.preview_panel.card) == (12, 10, 12, 2)


def test_preview_slots_fill_both_directions(win):
    for slot, canvas, _caption in win.preview_panel.slots:
        for widget in (slot, canvas):
            sp = widget.sizePolicy()
            assert sp.horizontalPolicy() == QSizePolicy.Policy.Expanding
            assert sp.verticalPolicy() == QSizePolicy.Policy.Expanding


def test_selected_tab_frame_fills_cell(win):
    frame = win._tab_frames_map[win.current_tab]
    sp = frame.sizePolicy()
    assert sp.horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert sp.verticalPolicy() == QSizePolicy.Policy.Expanding
    assert frame.grid_info()
