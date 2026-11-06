"""P1 1a: içerik 820 px ile sınırlıyken kaydırma alanının sağ boşluğu boyanmalı."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor

from ui import qt_compat as ctk
from ui.qt_compat import resolve_color
from ui.theme import COLOR_CARD, CONTENT_MAX_W


def test_viewport_outside_content_is_painted_with_card_color():
    ctk.ensure_qapp()
    host = ctk.CTkFrame(None, fg_color=COLOR_CARD)
    scroll = ctk.CTkScrollableFrame(host, fg_color="transparent")
    scroll._inner.setMaximumWidth(CONTENT_MAX_W)
    scroll.resize(CONTENT_MAX_W + 400, 300)
    scroll.show()
    image = scroll.grab().toImage()
    expected = QColor(resolve_color(COLOR_CARD))
    x = CONTENT_MAX_W + 200            # iç çerçevenin sağında kalan bölge
    pixel = QColor(image.pixel(x, 150))
    assert pixel.alpha() == 255
    assert (pixel.red(), pixel.green(), pixel.blue()) == (
        expected.red(), expected.green(), expected.blue())
    scroll.close()
