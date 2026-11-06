"""Birleştirme listesinde sürükleyerek sıralama (P3-40).

Sürükleme sırasında satırlar **yerinde kalır**; yalnızca bırakma yerini gösteren ince bir
çizgi taşınır (her fare adımında tüm satırları yeniden yerleştirmek uzun listede titretiyordu).
Fare bırakılınca seçili satırlar (tek ya da blok) çizginin gösterdiği aralığa tek hamlede taşınır.

* **Bırakma çizgisi:** satır ortalarına göre en yakın aralık (``slot_at``) vurgulanır.
* **Otomatik kaydırma:** fare listenin alt/üst kenar şeridine ya da dışına gelince, fare
  kımıldamasa da zamanlayıcı listeyi kaydırır.
* **Yalnız tutamaktan sürükleme:** ``chk_merge_handle_only`` açıkken sürükleme yalnız ⠿
  tutamacından başlar; satırın başka yerine tıklamak yalnızca seçer.
"""

from __future__ import annotations

from typing import Any, List, Optional

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from ui import qt_compat as ctk
from ui.theme import (COLOR_ACCENT, DRAG_SCROLL_MAX_STEP, DRAG_SCROLL_MS, DRAG_SCROLL_ZONE,
                      DRAG_START_PX, DROP_LINE_H)


def autoscroll_step(y: int, top: int, bottom: int) -> int:
    """Fare ``y`` konumuna göre kaydırma adımı (eksi: yukarı, artı: aşağı, 0: kaydırma yok).

    Kenar şeridine girince hız artar; şeridin sonunda ve listenin dışında en yüksek hızdadır.
    """
    height = bottom - top
    if height <= 0:
        return 0
    zone = max(1, min(DRAG_SCROLL_ZONE, height // 3))
    if y < top + zone:
        depth = min(top + zone - y, zone)
        return -max(1, -(-DRAG_SCROLL_MAX_STEP * depth // zone))
    if y > bottom - zone:
        depth = min(y - (bottom - zone), zone)
        return max(1, -(-DRAG_SCROLL_MAX_STEP * depth // zone))
    return 0


def reorder_for_drop(count: int, chosen: List[int], slot: int) -> List[int]:
    """Seçili satırlar ``slot`` aralığına bırakılınca yeni sıra (eski indekslerin listesi).

    ``slot`` bırakma anındaki sıraya göredir: 0 = ilk satırın önü, ``count`` = son satırın sonrası.
    Seçilenlerin kendi sırası korunur; seçili olmayanlar da birbirine göre yerinde kalır.
    """
    block = sorted(chosen)
    taken = set(block)
    rest = [i for i in range(count) if i not in taken]
    position = slot - sum(1 for index in block if index < slot)
    position = max(0, min(position, len(rest)))
    return rest[:position] + block + rest[position:]


class _DropLine(QWidget):
    """Liste içeriğinin üstünde duran, fareyi geçiren ince bırakma çizgisi."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.hide()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt adı)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(ctk.resolve_color(COLOR_ACCENT)))
        painter.end()


class MergeDragMixin:
    """``MergeTab`` sürükleme davranışı (durum alanları ``_init_drag_state`` ile kurulur)."""

    def _init_drag_state(self) -> None:
        self.drag_idx: Optional[int] = None          # basılan satır (yalnız sürükleme açıkken)
        self._press_collapse: Optional[int] = None   # çoklu seçimde tıkla-bırak ile tekilleştirme
        self._press_y = 0
        self._last_y = 0
        self._dragged = False
        self._drag_slot: Optional[int] = None
        self._drop_line: Optional[_DropLine] = None
        self._drag_timer: Optional[QTimer] = None

    # -- Ayar ---------------------------------------------------------------------
    def handle_only(self) -> bool:
        box = getattr(self, "chk_merge_handle_only", None)
        return bool(self.built and box is not None and box.get() == 1)

    # -- Olay bağlama -------------------------------------------------------------
    def bind_row_drag(self, row: Any, index: int) -> None:
        widgets = [row] + [child for child in row.winfo_children()
                           if not isinstance(child, ctk.CTkEntry)]

        def current_index() -> Optional[int]:
            # Satırlar bırakmada yeniden sıralanır; bağlama anındaki indeks eskir.
            for i, candidate in enumerate(self.rows):
                if candidate is row:
                    return i
            return None

        def on_press(event):
            idx = current_index()
            if idx is None:
                return
            self._end_drag()
            self._press_y = self._last_y = int(getattr(event, "y_root", 0))
            ctrl = bool(getattr(event, "ctrl", False))
            shift = bool(getattr(event, "shift", False))
            if ctrl or shift:  # seçimi düzenler; sürükleme başlatmaz
                self.select_item(idx, ctrl=ctrl, shift=shift)
                return
            handle = getattr(row, "_handle_label", None)
            armed = not self.handle_only() or getattr(event, "widget", None) is handle
            self.drag_idx = idx if armed else None
            chosen = self.selection()
            if len(chosen) > 1 and idx in chosen:
                # Çoklu seçili satırdan sürükleme bloğu taşır; sürüklenmeden bırakılırsa
                # seçim bu satıra indirilir (dosya yöneticilerindeki davranış).
                self._press_collapse = idx
                return
            self.select_item(idx)

        def on_motion(event):
            if self.drag_idx is None:
                return
            self._last_y = int(event.y_root)
            if not self._dragged:
                if abs(self._last_y - self._press_y) < DRAG_START_PX:
                    return
                self._begin_drag()
            self._update_drop_target()

        def on_release(event):
            if self._dragged:
                slot = self.slot_at(int(getattr(event, "y_root", self._last_y)))
                self._end_drag()
                self.drop_selection_at(slot)
                return
            collapse = self._press_collapse
            self._end_drag()
            if collapse is not None:
                self.select_item(collapse)

        for widget in widgets:
            widget.bind("<Button-1>", on_press, add="+")
            widget.bind("<B1-Motion>", on_motion, add="+")
            widget.bind("<ButtonRelease-1>", on_release, add="+")

    # -- Sürükleme yaşam döngüsü ---------------------------------------------------
    def _begin_drag(self) -> None:
        self._dragged = True
        if self._drag_timer is None:
            self._drag_timer = QTimer(self.merge_list_frame)
            self._drag_timer.setInterval(DRAG_SCROLL_MS)
            self._drag_timer.timeout.connect(self._tick_autoscroll)
        self._drag_timer.start()

    def _end_drag(self) -> None:
        """Sürükleme durumunu ve çizgiyi sıfırlar (bırakma, yenileme, yeni basış)."""
        if self._drag_timer is not None:
            self._drag_timer.stop()
        if self._drop_line is not None:
            self._drop_line.hide()
        self._dragged = False
        self._drag_slot = None
        self._press_collapse = None
        self.drag_idx = None

    def _update_drop_target(self) -> None:
        slot = self.slot_at(self._last_y)
        self._drag_slot = slot
        self._show_drop_line(slot)

    def _tick_autoscroll(self) -> None:
        if not self._dragged or self.drag_idx is None:
            if self._drag_timer is not None:
                self._drag_timer.stop()
            return
        frame = self.merge_list_frame
        viewport = frame.viewport()
        top = viewport.mapToGlobal(QPoint(0, 0)).y()
        step = autoscroll_step(self._last_y, top, top + viewport.height())
        if not step:
            return
        bar = frame.verticalScrollBar()
        before = bar.value()
        bar.setValue(before + step)
        if bar.value() != before:
            self._update_drop_target()

    # -- Bırakma yeri ---------------------------------------------------------------
    def slot_at(self, y_root: int) -> int:
        """Ekran ``y_root`` konumuna en yakın bırakma aralığı (0 … satır sayısı).

        Satırlar yukarıdan aşağıya sıralı olduğundan ikili aramayla ``log n`` satır sorgulanır.
        """
        low, high = 0, len(self.rows)
        while low < high:
            mid = (low + high) // 2
            row = self.rows[mid]
            center = row.winfo_rooty() + row.winfo_height() // 2
            if y_root < center:
                high = mid
            else:
                low = mid + 1
        return low

    def drop_line_y(self, slot: int) -> Optional[int]:
        """Bırakma çizgisinin liste içeriği koordinatlarındaki orta y'si (satır yoksa ``None``)."""
        if not self.rows:
            return None
        slot = max(0, min(slot, len(self.rows)))
        if slot == 0:
            return self.rows[0].y()
        above = self.rows[slot - 1]
        bottom = above.y() + above.height()
        if slot == len(self.rows):
            return bottom
        return (bottom + self.rows[slot].y()) // 2

    def _show_drop_line(self, slot: int) -> None:
        mid = self.drop_line_y(slot)
        if mid is None:
            return
        inner = self.merge_list_frame._content_host()
        if self._drop_line is None:
            self._drop_line = _DropLine(inner)
        first = self.rows[0]
        self._drop_line.setGeometry(first.x(), mid - DROP_LINE_H // 2, first.width(), DROP_LINE_H)
        self._drop_line.raise_()
        self._drop_line.show()

    def drop_selection_at(self, slot: int) -> bool:
        """Seçili satırları ``slot`` aralığına taşır; sıra değiştiyse ``True`` döner."""
        chosen = self.selection()
        if not chosen:
            return False
        order = reorder_for_drop(len(self.files), chosen, slot)
        if order == list(range(len(self.files))):
            return False
        new_pos = {old: new for new, old in enumerate(order)}
        matched = self._rows_match_files()
        primary = new_pos[self._primary] if self._primary in new_pos else None
        self.files[:] = [self.files[i] for i in order]
        if matched:
            self.rows[:] = [self.rows[i] for i in order]
        self._set_selection([new_pos[i] for i in chosen], primary)
        self._anchor = self._primary
        if matched:
            self.reorder_rows()
            self.ctx.schedule_preview()
        else:
            self.refresh_list()
        return True
