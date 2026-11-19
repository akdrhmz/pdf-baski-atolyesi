"""
PDF Baskı & Cilt Stüdyosu - Masaüstü arayüzü

Kayıpsız duplex cilt payı, sabit alt/üst boşluk, kesintisiz sayfa
numaralandırma, kırpma taraması, sonuç doğrulama ve PDF birleştirme.

Arayüz tek bir ``build_config`` üzerinden motora bağlanır: önizleme, tarama,
işleme ve birleştirme aynı ayarları kullanır; kopya kod yoktur.
"""

from __future__ import annotations

import faulthandler
import logging
import os
import queue
import sys
import threading
from typing import List, Optional

from ui import qt_compat as ctk
from ui.qt_compat import messagebox

HAS_WINDND = True

from core.gutter_engine import (
    UNITS,
    PdfProcessConfig,
)
from core.settings_store import LOG_PATH, SettingsStore, setup_logging
from core.version import APP_ID, APP_NAME, VERSION
from ui.bridge import forward
from ui.config_binding import ConfigBindingMixin, field_row_names
from ui.dialogs import DialogsMixin
from ui.dnd import DropMixin
from ui.document import DocumentMixin
from ui.merge_job import MergeJobMixin
from ui.paths import ASSETS_DIR
from ui.perf import PerfRecorder
from ui.pipeline import PipelineMixin
from ui.preview import AppPreviewHost, PreviewPanel
from ui.shell_build import ShellBuildMixin
from ui.shortcuts import ShortcutsMixin
from ui.theme import *  # noqa: F401,F403  (testler ve dış kod buradan okur)
from ui.widgets import FieldError, FieldRow, WrapButtonRow  # noqa: F401
from ui.window import (TAB_ALIASES, TAB_FULL_NAMES, TAB_NAMES, StudioWindow, TabNav,
                       startup_window_sizes)  # noqa: F401
from ui.workflow import WorkflowMixin


class ModernGutterApp(
    ConfigBindingMixin, ShellBuildMixin, PipelineMixin, DocumentMixin, ShortcutsMixin,
    MergeJobMixin, DialogsMixin, WorkflowMixin, DropMixin, StudioWindow,
):
    """Pencere kabuğu: yaşam döngüsü, sekme seçimi, ortak durum ve geçiş köprüleri.

    Kurulum, belge yükleme, işlem hattı özeti ve kısayollar karışımlardadır; sekmelerin
    kendi davranışı ``ui/tabs/`` altındadır.
    """

    def __init__(self, settings_path=None, log_path=None):
        self.perf = PerfRecorder()  # APP_PERF=1 ile açılır; super().__init__ içindeki withdraw'ı da sayar
        super().__init__()
        self._closing = False
        self.begin_initial_hide()

        self.log = setup_logging(log_path)
        # Doğal olmayan kapanmalarda (ctypes geri çağrısı, erişim ihlali) Python
        # yığın izi günlüğe düşsün; "uygulama sessizce kapandı" tanısı kolaylaşır.
        try:
            self._crash_stream = open(log_path or LOG_PATH, "a", encoding="utf-8")
            faulthandler.enable(file=self._crash_stream)
        except Exception:
            self._crash_stream = None
        self.store = SettingsStore(settings_path)
        from ui.i18n import set_language
        set_language(self.store.data.get("language", "tr"))
        self.log.info("%s %s başlatıldı", APP_NAME, VERSION)

        self.title(APP_NAME)  # sürüm uygulama içi başlıkta; çift başlık yok (v2.3.0)
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self._apply_app_icon()
        self.configure(fg_color=COLOR_BG)

        # QScreen geometry (exposed by winfo_screen*) is already in Qt's
        # device-independent pixels. Compact layouts relax the docked preview
        # and center-column minima so 125/150% screens do not force a window
        # larger than the available work area.
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        self._startup_size = startup_window_sizes(screen_w, screen_h)
        self._compact_screen = self._startup_size[4]
        if self._compact_screen:
            self.CENTER_MIN = 360
            self._preview_min_width = 240
        else:
            self._preview_min_width = PREVIEW_MIN_W

        # Belge durumu
        self.input_pdf_path = ""
        self.output_pdf_path = ""
        self.orig_width_mm = 210.0
        self.orig_height_mm = 297.0
        self.orig_page_count = 0
        self.orig_mixed_sizes = False

        self.current_tab = TAB_NAMES[0]

        # Çalışma durumu
        self._cancel_event = threading.Event()
        self._busy = False
        self._work_config: Optional[PdfProcessConfig] = None
        self._pending_merge: Optional[tuple] = None  # (geçici birleşik PDF, uyarılar)
        self._work_paths = ("", "")
        self.preview_panel = PreviewPanel(AppPreviewHost(self))
        self._queue_after = None
        self._last_valid_config: Optional[PdfProcessConfig] = None
        self.unit = self.store.unit if self.store.unit in DISPLAY_UNITS else "mm"
        self._ui_queue: "queue.Queue" = queue.Queue()

        with self.perf.measure("acilis_arayuz_kurulumu"):
            self._build_ui()
        self._init_drag_and_drop()
        self._bind_shortcuts()
        # Kayıtlı birim mm değilse alanlar daha ilk değer atanmadan önce hazırlanır.
        for row in self._all_field_rows():
            row.reset_unit(self.unit)
        self._restore_settings()
        self._update_pipeline_summary()
        self._refresh_profile_menu()
        self._update_unit_button()
        self._announce_restored_settings()
        self._schedule_preview()
        self._queue_after = self.after(50, self._drain_ui_queue)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.update_idletasks()
        width, height, minimum_w, minimum_h, _compact = self._startup_size
        self.geometry(f"{width}x{height}")
        self.minsize(minimum_w, minimum_h)
        self.finish_initial_show()

    # =====================================================================
    # Yaşam döngüsü
    # =====================================================================
    def _ui(self, callback) -> None:
        """Arka plan iş parçacıklarından gelen işi ana iş parçacığı kuyruğuna koyar."""
        if self._closing:
            return
        self._ui_queue.put(callback)

    def _drain_ui_queue(self) -> None:
        """Kuyruktaki arayüz güncellemelerini ana iş parçacığında çalıştırır."""
        if self._closing:
            return
        while True:
            try:
                callback = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception:
                self.log.exception("Arayüz güncellemesi başarısız")
        if not self._closing:
            self._queue_after = self.after(50, self._drain_ui_queue)

    def destroy(self) -> None:
        if not self._closing:
            try:
                self.perf.log_summary(self)
            except Exception:
                pass
        self._closing = True
        merge = getattr(self, "_tabs", {}).get("Birleştirme")
        if merge is not None:
            merge._thumb_pool.shutdown(wait=False, cancel_futures=True)
        tools_window = getattr(self, "_pdf_tools_window", None)
        if tools_window is not None:
            tools_window._cancel.set()
            tools_window._pool.shutdown(wait=False, cancel_futures=True)
        batch_dialog = getattr(self, "_batch_dialog", None)
        if batch_dialog is not None and batch_dialog._busy:
            batch_dialog._cancel.set()
        self._discard_pending_merge()
        try:
            self._cancel_event.set()
        except Exception:
            pass
        self.cancel_tab_prewarm()
        self._close_preview_window()
        self.preview_panel.cancel_pending()
        if self._queue_after is not None:
            try:
                self.after_cancel(self._queue_after)
            except Exception:
                pass
            self._queue_after = None
        try:
            faulthandler.disable()
            if self._crash_stream is not None:
                self._crash_stream.close()
        except Exception:
            pass
        self._crash_stream = None
        try:
            super().destroy()
        except Exception:
            pass

    def _apply_app_icon(self) -> None:
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass
        icon = os.path.join(ASSETS_DIR, "icon.ico")
        if os.path.exists(icon):
            try:
                self.iconbitmap(icon)
            except Exception:
                pass

    # =====================================================================
    # Sekme seçimi
    # =====================================================================

    def select_tab(self, name: str) -> None:
        """Sekmeyi seçer, düğme durumlarını ve içerik görünürlüğünü günceller."""
        name = TAB_ALIASES.get(name, name)
        if name not in TAB_NAMES:
            for short, full in TAB_FULL_NAMES.items():
                if full == name:
                    name = short
                    break
        if name not in self._tab_frames_map:
            return
        self.current_tab = name
        for tab_name, button in self._tab_buttons.items():
            if tab_name == name:
                button.configure(fg_color=COLOR_SOLID, text_color=COLOR_ON_ACCENT,
                                 border_color=COLOR_SOLID, hover_color=COLOR_SOLID_HOVER)
            else:
                button.configure(fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
                                 border_color=COLOR_BORDER, hover_color=COLOR_SUBCARD)
        with self.perf.measure(f"sekme:{name}"):
            with self.freeze_redraw():
                self._tabs[name].ensure_built()
                self._show_tab_frame(name)
                self._on_tab_changed()
                self.update_idletasks()

    # =====================================================================
    # Yardımcılar: tema, birim, durum
    # =====================================================================

    def _on_unit_changed(self, label: str) -> None:
        new_unit = next((code for code in DISPLAY_UNITS if UNITS[code][0] == label), "mm")
        old_unit = self.unit
        if new_unit == old_unit:
            return
        for row in self._all_field_rows():
            row.change_unit(old_unit, new_unit)
        self.unit = new_unit
        self.store.unit = new_unit
        self.store.save()
        self._update_margin_preset_labels()
        self._on_field_changed()

    def _update_unit_button(self) -> None:
        """Ölçü birimi artık yalnızca Ayarlar'da (v2.3.0); Belge kartında seçici yok."""
        return

    def _all_field_rows(self) -> List[FieldRow]:
        """Kurulu sekmelerin alan satırları (kurulmamış sekme kurulurken birimi alır)."""
        return [getattr(tab, name) for tab in self._tabs.values() if tab.built
                for name in field_row_names(tab) if isinstance(getattr(tab, name), FieldRow)]

    def _on_field_changed(self) -> None:
        self._update_pipeline_summary()
        self._schedule_preview()

    def _update_safe_edge_state(self) -> None:
        self._tabs["Sayfa Düzeni"].update_safe_edge_state()

    def _on_gutter_changed(self) -> None:
        self._tabs["Sayfa Düzeni"].on_changed()

    def _toggle_gutter_fields(self) -> None:
        tab = self._tabs["Sayfa Düzeni"]
        tab.show_active(self._module_switch("gutter").get() == 1)
        self._sync_tab_enabled("gutter")
        self._update_all_modules_button()
        self._on_field_changed()

    def _on_margin_changed(self) -> None:
        self._tabs["Sayfa Düzeni"].on_margin_changed()

    def _on_margin_mode_changed(self) -> None:
        """Eski "boşluk modu" yönlendiricisi: birleşik modelde pay değişimiyle aynı."""
        self._tabs["Sayfa Düzeni"].on_margin_changed()

    def _toggle_margin_fields(self) -> None:
        tab = self._tabs["Sayfa Düzeni"]
        if tab.built:
            tab.show_margin_active(self._module_switch("margin").get() == 1)
        self._sync_tab_enabled("margin")
        self._update_all_modules_button()
        self._on_field_changed()

    def _on_number_changed(self) -> None:
        self._tabs["Sayfa Numaraları"].on_changed()

    def _on_number_position_changed(self) -> None:
        self._tabs["Sayfa Numaraları"].on_position_changed()

    def _toggle_pnum_fields(self) -> None:
        if self._tabs["Sayfa Numaraları"].built:
            self._tabs["Sayfa Numaraları"].show_active(self.switch_pnum.get() == 1)
        self._sync_tab_enabled("pnum")
        self._update_all_modules_button()
        self._on_field_changed()

    # -- Önizleme paneli: geçiş köprüsü (2.9'da kalkar) --------------------------
    preview_mode = forward("preview_panel", "mode")
    preview_page = forward("preview_panel", "page")
    _preview_gen = forward("preview_panel", "gen")
    _preview_after = forward("preview_panel", "after_id")
    _preview_signature = forward("preview_panel", "signature")
    _preview_images = forward("preview_panel", "images")
    _preview_history = forward("preview_panel", "history")
    _preview_slots = forward("preview_panel", "slots")
    preview_mode_menu = forward("preview_panel", "preview_mode_menu")
    preview_prev_btn = forward("preview_panel", "preview_prev_btn")
    preview_next_btn = forward("preview_panel", "preview_next_btn")
    preview_page_label = forward("preview_panel", "preview_page_label")
    preview_info = forward("preview_panel", "preview_info")
    preview_warning = forward("preview_panel", "preview_warning")

    def _schedule_preview(self) -> None:
        self.preview_panel.schedule()

    def _refresh_preview(self) -> None:
        self.preview_panel.refresh()

    def _refresh_preview_now(self) -> None:
        self.preview_panel.refresh_now()

    def _on_preview_mode_changed(self, value: str) -> None:
        self.preview_panel.on_mode_changed(value)

    def _preview_next(self) -> None:
        self.preview_panel.next_page()

    def _preview_previous(self) -> None:
        self.preview_panel.previous()

    def _preview_source_path(self) -> str:
        """Önizlenecek dosya: birleştirme sekmesinde seçili PDF, yoksa ana belge."""
        item = AppPreviewHost(self).merge_item()
        return str(item["path"]) if item is not None else self.input_pdf_path

    # -- Birleştirme sekmesi: geçiş köprüsü (2.9'da kalkar) ---------------------
    @property
    def merge_files(self):
        return self._tabs["Birleştirme"].files

    @property
    def selected_merge_idx(self):
        return self._tabs["Birleştirme"].selected_idx

    @selected_merge_idx.setter
    def selected_merge_idx(self, value) -> None:
        self._tabs["Birleştirme"].selected_idx = value

    @property
    def _merge_rows(self):
        return self._tabs["Birleştirme"].rows

    def _append_merge_file(self, path: str) -> None:
        self._tabs["Birleştirme"].append_file(path)

    def _refresh_merge_listbox(self) -> None:
        self._tabs["Birleştirme"].refresh_list()

    def _select_merge_item(self, index) -> None:
        self._tabs["Birleştirme"].select_item(index)

    def _rotate_selected(self, delta: int) -> None:
        self._tabs["Birleştirme"].rotate_selected(delta)

    def _rotate_all(self, delta: int) -> None:
        self._tabs["Birleştirme"].rotate_all(delta)

    def _rotate_selected_left(self) -> None:
        self._tabs["Birleştirme"].rotate_selected_left()

    def _rotate_selected_right(self) -> None:
        self._tabs["Birleştirme"].rotate_selected_right()

    def _move_merge_file_up(self) -> None:
        self._tabs["Birleştirme"].move_up()

    def _move_merge_file_down(self) -> None:
        self._tabs["Birleştirme"].move_down()

    def _remove_merge_file(self) -> None:
        self._tabs["Birleştirme"].remove_selected()

    def _clear_merge_files(self) -> None:
        self._tabs["Birleştirme"].clear()

    def _move_merge_item(self, old_index: int, new_index: int) -> None:
        self._tabs["Birleştirme"].move_item(old_index, new_index)

    def _set_status(self, text: str, color=COLOR_TEXT_SECONDARY) -> None:
        self.status_label.configure(text=text, text_color=color)

    # =====================================================================
    # Sekme değişimi
    # =====================================================================
    def _on_tab_changed(self) -> None:
        self._update_pipeline_summary()
        tab = getattr(self, "_tabs", {}).get(self.current_tab)
        if tab is not None:
            tab.on_show()
        # Birleştirme sekmesinde seçili dosya, diğer sekmelerde ana belge önizlenir.
        self._schedule_preview()

    # =====================================================================
    # Kapanış
    # =====================================================================
    def _on_close(self) -> None:
        if self._busy:
            if not messagebox.askyesno("Çıkış", "İşlem sürüyor. İptal edilip uygulama kapatılsın mı?"):
                return
            self._cancel_event.set()
        try:
            self.store.last_state = self._collect_state()
            self.store.theme = self.theme_segmented.get()
            self.store.unit = self.unit
            self.store.save()
        except Exception:
            self.log.exception("Ayarlar kaydedilemedi")
        self.log.info("Uygulama kapatıldı")
        self.destroy()


def main() -> None:
    setup_logging()
    logging.getLogger("studio").info("Uygulama başlatılıyor (Python %s)", sys.version.split()[0])
    app = ModernGutterApp()
    app.schedule_tab_prewarm()
    app.mainloop()

if __name__ == "__main__":
    main()
