"""Pencere kabuğu ve sekme denetleyicisi (PySide6 / Qt 6)."""

from __future__ import annotations

from contextlib import contextmanager
import sys
from typing import Any, Iterator

from ui import qt_compat as ctk


class TabNav:
    """Büyük düğmeli sekme denetleyicisi."""

    def __init__(self, app: Any):
        self.app = app

    def get(self) -> str:
        return self.app.current_tab

    def set(self, name: str) -> None:
        self.app.select_tab(name)


TAB_NAMES = ["Sayfa Düzeni", "Sayfa Numaraları", "Birleştirme", "Baskı ve Araçlar"]
TAB_FULL_NAMES = {
    "Sayfa Düzeni": "Sayfa Düzeni",
    "Sayfa Numaraları": "Sayfa Numaralandırma",
    "Birleştirme": "PDF Birleştirme",
    "Baskı ve Araçlar": "Baskı ve Araçlar",
}
#: Eski sürümlerdeki ayrı sekmeler birleşti; adlar geçiş için kabul edilir.
TAB_ALIASES = {
    "Cilt Payı": "Sayfa Düzeni",
    "Kenar Boşlukları": "Sayfa Düzeni",
}


def startup_window_sizes(screen_width: int, screen_height: int) -> tuple[int, int, int, int, bool]:
    """Return a usable startup/minimum size in Qt's device-independent pixels."""
    width, height = max(1, int(screen_width)), max(1, int(screen_height))
    compact = width < 1200 or height < 700
    target_w = min(1440, max(850 if compact else 1260, width - 32))
    target_h = min(920, max(480 if compact else 780, height - 32))
    minimum_w = min(1200 if not compact else 850, max(760 if compact else 1200, width - 16))
    minimum_h = min(700 if not compact else 480, max(480, height - 16))
    return target_w, target_h, minimum_w, minimum_h, compact


class StudioWindow(ctk.QtMainWindow):
    """
    PySide6 (Qt 6) ana uygulama penceresi.

    Tüm alt bileşenler tek bir çift tamponlu ``QBackingStore`` yüzeyinde çizilir;
    pencere büyütme/küçültme, sekme değişimi ve Açık/Koyu tema geçişlerinde
    pencere hiç gizlenmez ve parçalı çizim (flicker) oluşmaz.
    """

    def withdraw(self) -> None:
        """Pencereyi gizler; ``APP_PERF`` açıksa çağrıyı sayar (tema geçişinde 0 olmalı)."""
        perf = getattr(self, "perf", None)
        if perf is not None:
            perf.count("withdraw")
        super().withdraw()

    def _window_hwnd(self) -> int:
        if not sys.platform.startswith("win"):
            return 0
        try:
            return int(self.winId())
        except Exception:
            return 0

    @contextmanager
    def freeze_redraw(self) -> Iterator[None]:
        """Toplu arayüz güncellemelerini tek bir Qt çizim karesinde birleştirir."""
        depth = getattr(self, "_freeze_depth", 0)
        self._freeze_depth = depth + 1
        if depth == 0:
            self.setUpdatesEnabled(False)
        try:
            yield
        finally:
            self._freeze_depth = max(0, getattr(self, "_freeze_depth", 1) - 1)
            if self._freeze_depth == 0:
                self.setUpdatesEnabled(True)
                try:
                    if not getattr(self, "_closing", False):
                        self._invalidate_visible_subtree()
                        self.update_idletasks()
                except Exception:
                    pass

    def _invalidate_visible_subtree(self) -> None:
        """``setUpdatesEnabled(False)`` sırasında atlanan çizimleri görünür bileşenlerde yeniler."""
        from PySide6.QtWidgets import QWidget

        for w in self.findChildren(QWidget):
            if w.isVisible():
                w.update()
        self.update()

    def state(self, newstate: Any = None) -> Any:
        """Tam ekran / normal geçişini ölçer ve tek karede uygular."""
        if newstate is None:
            return super().state()
        perf = getattr(self, "perf", None)
        label = "buyutme" if newstate == "zoomed" else ("kucultme" if newstate == "normal" else f"state:{newstate}")
        self._last_wm_state = newstate
        if perf is not None:
            with perf.measure(label):
                with self.freeze_redraw():
                    result = super().state(newstate)
                return result
        with self.freeze_redraw():
            return super().state(newstate)

    def _mark_subtree_defer(self, root_widget: Any, defer: bool) -> None:
        stack = [root_widget]
        while stack:
            node = stack.pop()
            node._defer_theme_refresh = defer
            if not defer and getattr(node, "_theme_dirty", False):
                node._theme_dirty = False
                try:
                    node._refresh_style()
                except Exception:
                    pass
            stack.extend(getattr(node, "_child_widgets", []))

    def _show_tab_frame(self, name: str) -> None:
        """Yalnızca seçili sekmenin çerçevesini görünür tutar."""
        self._sync_layout_submenu(expand=(name == "Sayfa Düzeni"))
        deferred = getattr(self, "_deferred_theme_cbs", None)
        if deferred and name in deferred:
            cbs, mode_str = deferred.pop(name)
            for cb in cbs:
                try:
                    cb(mode_str)
                except Exception:
                    pass
        for tab_name, frame in self._tab_frames_map.items():
            if tab_name != name:
                self._mark_subtree_defer(frame, True)
                frame.grid_remove()
        target = self._tab_frames_map[name]
        self._mark_subtree_defer(target, False)
        target.place(0, 0, valign="fill", expand_x=True, expand_y=True)
        target.tkraise()

    def _set_appearance_mode_fast(self, mode: str) -> None:
        """Temayı tüm pencereye ve başlık çubuğuna tek atomik karede uygular."""
        frames = getattr(self, "_tab_frames_map", None) or {}
        for tab_name, frame in frames.items():
            self._mark_subtree_defer(frame, tab_name != getattr(self, "current_tab", ""))
        ctk.set_appearance_mode(mode)
        actual = ctk.get_appearance_mode()
        self._windows_set_titlebar_color(actual)
        deferred = getattr(self, "_deferred_theme_cbs", None)
        if deferred is None:
            deferred = self._deferred_theme_cbs = {}
        for tab_name in frames:
            if tab_name != getattr(self, "current_tab", "") and self._tabs[tab_name].built:
                deferred[tab_name] = ([lambda _m, f=frames[tab_name]: self._mark_subtree_defer(f, False)], actual)

    def _on_theme_changed(self, choice: str) -> None:
        mode = {"Açık": "Light", "Koyu": "Dark"}.get(choice, "System")
        with self.perf.measure("tema_degisimi"):
            with self.freeze_redraw():
                self._set_appearance_mode_fast(mode)
                self.store.theme = choice
                for tab in self._tabs.values():
                    if not tab.built:
                        continue
                    try:
                        tab.apply_theme()
                    except Exception:
                        self.log.exception("Sekme teması uygulanamadı: %s", tab.name)
                self.preview_panel.apply_theme()
                self.update_idletasks()
        # Windows, yeniden etkinleştirilen backing store'u bazen bir sonraki
        # giriş olayına kadar sunmuyordu. Boyamayı tıklama callback'i bittikten
        # sonraki olay turunda tamamla; ikinci bir kullanıcı hareketi gerekmesin.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self, self._flush_theme_paint)
        self.store.save()

    def _flush_theme_paint(self):
        if self._closing:
            return
        from PySide6.QtWidgets import QApplication, QWidget
        for window in QApplication.topLevelWidgets():
            if window.isVisible():
                QWidget.update(window)
                QWidget.repaint(window)

    def _windows_set_titlebar_color(self, color_mode: str) -> None:
        if not sys.platform.startswith("win"):
            return
        if getattr(self, "_deactivate_windows_window_header_manipulation", False):
            return
        try:
            import ctypes

            value = ctypes.c_int(1 if str(color_mode).lower() == "dark" else 0)
            hwnd = self._window_hwnd()
            if not hwnd:
                return
            for attribute in (20, 19):
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        ctypes.c_void_p(hwnd), attribute,
                        ctypes.byref(value), ctypes.sizeof(value)) == 0:
                    break
        except Exception:
            pass

    def begin_initial_hide(self) -> None:
        """Qt'de pencere ``mainloop()`` / ``show()`` çağrılana kadar zaten görünmezdir."""

    def finish_initial_show(self) -> None:
        """Açılış yerleşimi tamamlandıktan sonra başlık çubuğu rengini senkronize eder."""
        try:
            self.update_idletasks()
            self._windows_set_titlebar_color(ctk.get_appearance_mode())
        except Exception:
            pass

    def schedule_tab_prewarm(self, delay_ms: int = 120) -> None:
        """Açılış sonrası boşta kalan sekmeleri arka planda birer birer kurar."""
        if getattr(self, "_closing", False):
            return
        if getattr(self, "_prewarm_after", None) is None:
            self._prewarm_after = self.after(delay_ms, self._prewarm_next_tab)

    def cancel_tab_prewarm(self) -> None:
        job = getattr(self, "_prewarm_after", None)
        if job is not None:
            self._prewarm_after = None
            try:
                self.after_cancel(job)
            except Exception:
                pass

    def _prewarm_next_tab(self) -> None:
        self._prewarm_after = None
        if getattr(self, "_closing", False) or getattr(self, "_busy", False):
            return
        tabs = getattr(self, "_tabs", None) or {}
        for name in TAB_NAMES:
            tab = tabs.get(name)
            if tab is not None and not tab.built:
                with self.freeze_redraw():
                    tab.ensure_built()
                    frame = getattr(self, "_tab_frames_map", {}).get(name)
                    if frame is not None and name != getattr(self, "current_tab", ""):
                        frame.grid_remove()
                if not getattr(self, "_closing", False):
                    self._prewarm_after = self.after(60, self._prewarm_next_tab)
                return
