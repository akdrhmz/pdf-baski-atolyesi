"""``PreviewCanvas`` (P3 13c): oranlı sığdırma, boyutsuz asgari ölçü, tema uyumu."""

from __future__ import annotations

import pytest
from PIL import Image
from PySide6.QtGui import QColor

from ui import qt_compat as ctk
from ui.preview import PreviewPanel, fit_size
from ui.preview_canvas import PreviewCanvas


@pytest.fixture
def canvas(qapp_instance=None):
    ctk.ensure_qapp()
    host = ctk.CTkFrame(None)
    widget = PreviewCanvas(host, bg="#112233")
    yield widget
    host.destroy()


def _pixmap(width, height, color="#ff0000"):
    return ctk.pil_to_pixmap(Image.new("RGB", (width, height), color))


def test_fit_size_is_shared_with_preview_module():
    assert fit_size is __import__("ui.preview_canvas", fromlist=["fit_size"]).fit_size
    assert PreviewPanel  # panel hâlâ içe aktarılabilir


def test_no_source_has_empty_fit_rect(canvas):
    canvas.resize(300, 400)
    assert canvas.fit_rect().isEmpty() and canvas.source() is None


def test_fit_rect_keeps_aspect_ratio_and_is_centered(canvas):
    canvas.resize(400, 400)
    canvas.configure(image=_pixmap(200, 400))     # dik sayfa, kare alan
    rect = canvas.fit_rect()
    assert (rect.width(), rect.height()) == (200, 400)
    assert rect.left() == 100 and rect.top() == 0
    canvas.resize(800, 400)
    rect = canvas.fit_rect()
    assert rect.width() / rect.height() == pytest.approx(0.5, abs=0.01)
    assert rect.center().x() == pytest.approx(400, abs=1)


def test_large_pixmap_does_not_force_a_minimum_size(canvas):
    canvas.configure(image=_pixmap(2000, 3000))
    assert canvas.minimumSizeHint().width() <= 1 or canvas.minimumSize().width() <= 1
    canvas.resize(120, 160)                        # küçülebilir
    assert canvas.width() == 120 and canvas.height() == 160


def test_paint_draws_scaled_page_inside_fit_rect(canvas):
    canvas.resize(300, 300)
    canvas.configure(image=_pixmap(100, 200, "#ff0000"))
    image = canvas.grab().toImage()
    inside = QColor(image.pixel(150, 150))
    outside = QColor(image.pixel(5, 150))
    assert inside.red() > 200 and inside.green() < 60          # sayfa (kırmızı)
    assert outside.name() == "#112233"                         # zemin (tema rengi)


def test_clearing_image_and_theme_color(canvas):
    canvas.resize(200, 200)
    canvas.configure(image=_pixmap(50, 50))
    canvas.configure(image="")
    assert canvas.source() is None
    canvas.configure(bg="#445566")
    assert str(canvas.cget("bg")) == "#445566"
    assert QColor(canvas.grab().toImage().pixel(100, 100)).name() == "#445566"


def test_scaled_cache_refreshes_only_when_size_changes(canvas):
    canvas.resize(200, 300)
    canvas.configure(image=_pixmap(100, 150))
    canvas.grab()
    first = canvas._scaled
    canvas.grab()
    assert canvas._scaled is first                 # aynı boyut: önbellek
    canvas.resize(300, 450)
    canvas.grab()
    assert canvas._scaled is not first
