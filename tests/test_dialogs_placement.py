"""Diyaloglar (``ui/dialogs.py``) açık yerleştirmesi (P3-15, 11. parça, v2.6.11)."""

from __future__ import annotations

import os
import pathlib
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from app import ModernGutterApp  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def win(tmp_path_factory):
    folder = tmp_path_factory.mktemp("dialogs_placement")
    app = ModernGutterApp(settings_path=folder / "s.json", log_path=folder / "l.log")
    app.update()
    yield app
    app.destroy()


def _m(widget, kind="grid"):
    m = widget._ensure_layout(kind).contentsMargins()
    return (m.left(), m.top(), m.right(), m.bottom())


def _dialogs_before_after(win, opener):
    from ui import qt_compat as ctk
    before = set(win.findChildren(ctk.CTkToplevel))
    opener()
    return [d for d in win.findChildren(ctk.CTkToplevel) if d not in before]


def test_no_grid_or_pack_calls_anywhere_in_ui():
    for path in list((ROOT / "ui").rglob("*.py")) + [ROOT / "app.py"]:
        text = path.read_text(encoding="utf-8")
        assert not re.findall(r"\.(grid|pack|grid_configure)\(", text), path.name


def test_text_dialog_margins_are_explicit(win):
    (dlg,) = _dialogs_before_after(
        win, lambda: win._show_text_dialog("T", "Başlık", "gövde"))
    frame = dlg.layout().itemAt(0).widget()
    assert _m(dlg, "pack_v") == (14, 10, 14, 10)
    assert _m(frame) == (12, 10, 12, 4)
    dlg.destroy()


def test_about_dialog_margins_are_explicit(win):
    (dlg,) = _dialogs_before_after(win, win._show_about_dialog)
    frame = dlg.layout().itemAt(0).widget()
    assert _m(dlg, "pack_v") == (14, 10, 14, 10)
    assert _m(frame) == (14, 10, 14, 10)
    dlg.destroy()


def test_settings_dialog_margins_are_explicit(win):
    (dlg,) = _dialogs_before_after(win, win._show_settings_dialog)
    frame = dlg.layout().itemAt(0).widget()
    assert _m(dlg, "pack_v") == (14, 10, 14, 10)
    assert _m(frame) == (14, 10, 14, 2)
    dlg.destroy()
