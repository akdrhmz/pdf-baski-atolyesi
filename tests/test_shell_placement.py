"""Kabuk (``ui/shell_build.py``) açık yerleştirmesi (P3-15, 9. parça, v2.6.9)."""

from __future__ import annotations

import os
import pathlib
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QSizePolicy  # noqa: E402

from app import ModernGutterApp  # noqa: E402
from ui import qt_compat as ctk  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def win(tmp_path_factory):
    folder = tmp_path_factory.mktemp("shell_placement")
    app = ModernGutterApp(settings_path=folder / "s.json", log_path=folder / "l.log")
    app.update()
    yield app
    app.destroy()


def _m(widget, kind="grid"):
    m = widget._ensure_layout(kind).contentsMargins()
    return (m.left(), m.top(), m.right(), m.bottom())


def test_shell_build_has_no_grid_or_pack_calls():
    text = (ROOT / "ui" / "shell_build.py").read_text(encoding="utf-8")
    assert not re.findall(r"\.(grid|pack)\(", text)


def test_window_margins_are_explicit(win):
    assert _m(win) == (14, 10, 14, 6)


def test_workspace_and_action_card_margins_are_explicit(win):
    assert _m(win._workspace) == (0, 6, 0, 0)
    assert _m(win._action_card) == (12, 6, 12, 1)


def test_status_row_and_options_margins_are_explicit(win):
    assert _m(win.status_label.master) == (12, 0, 0, 0)
    assert not hasattr(win, "chk_optimize")  # PDF output preferences are in Settings


def test_header_group_has_right_margin(win):
    assert _m(win.theme_segmented.master.master.layout().itemAt(0).widget(), "pack_h") \
        == (0, 0, 10, 0)


def test_sidebar_fills_both_directions(win):
    sp = win._sidebar.sizePolicy()
    assert sp.horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert sp.verticalPolicy() == QSizePolicy.Policy.Expanding
    assert win._sidebar.grid_info()["rowspan"] == 2


def test_place_expand_y_sets_vertical_expanding(qapp=None):
    root = ctk.CTkFrame(None)
    child = ctk.CTkFrame(root)
    child.place(0, 0, valign="fill", expand_x=True, expand_y=True)
    sp = child.sizePolicy()
    assert sp.verticalPolicy() == QSizePolicy.Policy.Expanding
    assert sp.horizontalPolicy() == QSizePolicy.Policy.Expanding
    other = ctk.CTkFrame(root)
    other.place(1, 0, expand_x=True)
    assert other.sizePolicy().verticalPolicy() != QSizePolicy.Policy.Expanding
