"""Önizleme sayfa tuvali: ``paintEvent`` ile en-boy oranını koruyarak sığdırır.

Eskiden her panel/pencere boyutu değişiminde görüntü PIL ile yeniden örnekleniyor
(``QLabel`` + ``fit_images``, 80 ms birleştirme) ve etikete atanıyordu. ``PreviewCanvas``
çözülmüş sayfayı bir kez ``QPixmap`` olarak tutar; her boyama alanın boyutuna göre
ölçekler. Böylece ayraç sürüklenirken önizleme gecikmesiz ve oransız gerilmeden
büyür/küçülür; ölçekleme önbelleği yalnızca boyut değişince yenilenir.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QSizePolicy

from ui import qt_compat as ctk


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
        self._scaled: Optional[QPixmap] = None
        self._scaled_key: Optional[tuple] = None
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
        self._scaled = None
        self._scaled_key = None
        self.update()

    def source(self) -> Optional[QPixmap]:
        return self._source

    def fit_rect(self) -> QRect:
        """Görüntünün bu alanda kaplayacağı (ortalanmış) dikdörtgen; kaynak yoksa boş."""
        if self._source is None:
            return QRect()
        area = self.rect()
        w, h = fit_size(self._source.width(), self._source.height(), area.width(), area.height())
        return QRect(area.x() + (area.width() - w) // 2, area.y() + (area.height() - h) // 2, w, h)

    # -- Boyama ---------------------------------------------------------------
    def _scaled_pixmap(self, width: int, height: int, ratio: float) -> QPixmap:
        key = (width, height, round(ratio, 2))
        if self._scaled is None or self._scaled_key != key:
            target_w, target_h = max(1, int(width * ratio)), max(1, int(height * ratio))
            self._scaled = self._source.scaled(
                target_w, target_h, Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self._scaled.setDevicePixelRatio(ratio)
            self._scaled_key = key
        return self._scaled

    def paintEvent(self, event) -> None:
        super().paintEvent(event)   # zemin rengi (tema)
        if self._source is None:
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
