"""Önizleme sayfa tuvali: ``paintEvent`` ile en-boy oranını koruyarak sığdırır.

Eskiden her panel/pencere boyutu değişiminde görüntü PIL ile yeniden örnekleniyor
(``QLabel`` + ``fit_images``, 80 ms birleştirme) ve etikete atanıyordu. ``PreviewCanvas``
çözülmüş sayfayı bir kez ``QPixmap`` olarak tutar; her boyama alanın boyutuna göre
ölçekler. Böylece ayraç sürüklenirken önizleme gecikmesiz ve oransız gerilmeden
büyür/küçülür; ölçekleme önbelleği yalnızca boyut değişince yenilenir.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QRect, QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QSizePolicy

from ui import qt_compat as ctk
from ui.theme import COLOR_BORDER, COLOR_CARD, COLOR_TEXT_SECONDARY


def fit_size(src_w: float, src_h: float, avail_w: float, avail_h: float) -> tuple:
    """Kaynağın en-boy oranını koruyarak ``avail`` alanına sığan (w, h) boyutu.

    Yükseklik sınırı genişliği de orantılı düşürür; görüntü asla gerilmez.
    """
    if src_w <= 0 or src_h <= 0:
        return (max(1, int(avail_w)), max(1, int(avail_h)))
    scale = min(max(avail_w, 1) / src_w, max(avail_h, 1) / src_h)
    return (max(1, int(round(src_w * scale))), max(1, int(round(src_h * scale))))


class PreviewCanvas(ctk.CTkLabel):
    """Tek bir önizleme sayfasını alanına oranlı sığdırarak çizen etiket.

    ``CTkLabel`` yüzeyini korur (``configure(image=..., bg=...)``, ``cget``), böylece
    tema yenileme ve mevcut testler değişmeden çalışır. Pixmap etikete *atanmaz*;
    atansaydı ``QLabel`` asgari boyutu görüntüden alır ve panel küçülemezdi.
    """

    def __init__(self, master, bg: Any = None, **kwargs: Any):
        super().__init__(master, text="", bg=bg, **kwargs)
        self._source: Optional[QPixmap] = None
        self._placeholder: Optional[str] = None
        self._scaled: Optional[QPixmap] = None
        self._scaled_key: Optional[tuple] = None
        self._zoom = 1.0
        self._rotation = 0
        self._pan = QPoint()
        self._drag_origin = None
        # Görüntü boyutu panelin asgari boyutunu belirlemesin.
        self.setMinimumSize(1, 1)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    # -- Etiket uyumu ---------------------------------------------------------
    def configure(self, **kwargs: Any) -> None:
        if "image" in kwargs:
            image = kwargs.pop("image")
            self.set_source(image if isinstance(image, QPixmap) else None)
        super().configure(**kwargs)

    # -- Kaynak ---------------------------------------------------------------
    def set_source(self, pixmap: Optional[QPixmap]) -> None:
        self._source = pixmap if (pixmap is not None and not pixmap.isNull()) else None
        self._placeholder = None
        self._scaled = None
        self._scaled_key = None
        self.update()

    def set_placeholder(self, mode: Optional[str]) -> None:
        """Belge yokken çizilecek vektör sayfa maketini seçer (``None`` temizler)."""
        self._source = None
        self._placeholder = mode
        self._scaled = None
        self._scaled_key = None
        self.update()

    def source(self) -> Optional[QPixmap]:
        return self._source

    def zoom_by(self, factor: float) -> None:
        self._zoom = max(1.0, min(8.0, self._zoom * factor))
        if self._zoom == 1:
            self._pan = QPoint()
        self.update()

    def rotate_view(self) -> None:
        self._rotation = (self._rotation + 90) % 360
        self._scaled_key = None
        self.update()

    def reset_view(self) -> None:
        self._zoom, self._rotation = 1.0, 0
        self._pan = QPoint()
        self._scaled_key = None
        self.update()

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom_by(1.2 if event.angleDelta().y() > 0 else 1 / 1.2)
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._zoom > 1:
            self._drag_origin = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_origin is not None:
            point = event.position().toPoint()
            self._pan += point - self._drag_origin
            self._drag_origin = point
            self.update()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_origin = None
        self.unsetCursor()
        super().mouseReleaseEvent(event)

    def fit_rect(self) -> QRect:
        """Görüntünün bu alanda kaplayacağı (ortalanmış) dikdörtgen; kaynak yoksa boş."""
        if self._source is None:
            return QRect()
        area = self.rect()
        sw, sh = self._source.width(), self._source.height()
        if self._rotation % 180:
            sw, sh = sh, sw
        w, h = fit_size(sw, sh, area.width(), area.height())
        w, h = round(w * self._zoom), round(h * self._zoom)
        return QRect(area.x() + (area.width() - w) // 2 + self._pan.x(),
                     area.y() + (area.height() - h) // 2 + self._pan.y(), w, h)

    # -- Boyama ---------------------------------------------------------------
    def _scaled_pixmap(self, width: int, height: int, ratio: float) -> QPixmap:
        key = (width, height, round(ratio, 2), self._rotation)
        if self._scaled is None or self._scaled_key != key:
            target_w, target_h = max(1, int(width * ratio)), max(1, int(height * ratio))
            source = self._source.transformed(QTransform().rotate(self._rotation)) if self._rotation else self._source
            self._scaled = source.scaled(
                target_w, target_h, Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self._scaled.setDevicePixelRatio(ratio)
            self._scaled_key = key
        return self._scaled

    def _paint_placeholder(self) -> None:
        """Belge yokken sayfa maketini vektör olarak çizer (her boyutta keskin)."""
        area = self.rect().adjusted(8, 8, -8, -8)
        if area.width() < 8 or area.height() < 8:
            return
        w, h = fit_size(595, 842, area.width(), area.height())
        target = QRect(area.x() + (area.width() - w) // 2,
                       area.y() + (area.height() - h) // 2, w, h)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(target).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(ctk.resolve_color(COLOR_BORDER)), 1))
        painter.setBrush(QColor(ctk.resolve_color(COLOR_CARD)))
        painter.drawRoundedRect(rect, 5, 5)
        ink = QColor(ctk.resolve_color(COLOR_TEXT_SECONDARY))
        ink.setAlpha(90)
        painter.setPen(QPen(ink, 1.2))
        left = target.left() + int(w * 0.10)
        right = target.right() - int(w * 0.10)
        step = max(6, int(h * 0.045))
        y = target.top() + int(h * 0.12)
        index = 0
        while y < target.bottom() - int(h * 0.08):
            end = left + int((right - left) * 0.55) if index % 5 == 4 else right
            painter.drawLine(left, y, end, y)
            index += 1
            y += step
        painter.end()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)   # zemin rengi (tema)
        if self._source is None:
            if self._placeholder:
                self._paint_placeholder()
            return
        target = self.fit_rect()
        if target.isEmpty():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawPixmap(target.topLeft(),
                           self._scaled_pixmap(target.width(), target.height(),
                                               self.devicePixelRatioF()))
        painter.end()
