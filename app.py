"""
PDF Baskı & Cilt Stüdyosu - Masaüstü arayüzü

Kayıpsız duplex cilt payı, sabit alt/üst boşluk, kesintisiz sayfa
numaralandırma, kırpma taraması, sonuç doğrulama ve PDF birleştirme.

Arayüz tek bir ``build_config`` üzerinden motora bağlanır: önizleme, tarama,
işleme ve birleştirme aynı ayarları kullanır; kopya kod yoktur.
"""

from __future__ import annotations

import faulthandler
import io
import logging
import os
import queue
import sys
import tempfile
import threading
import tkinter as tk
import traceback
from typing import Any, Dict, List, Optional

from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageTk

try:
    import windnd
    HAS_WINDND = True
except ImportError:
    HAS_WINDND = False

from gutter_engine import (
    UNITS,
    MarginSettings,
    PageBoxSettings,
    PageNumberSettings,
    PdfProcessConfig,
    ProcessCancelled,
    config_from_dict,
    config_to_dict,
    format_measure,
    get_pdf_info,
    merge_pdfs,
    parse_page_ranges,
    process_pdf,
    render_preview,
    scan_clipping,
    unit_to_mm,
    unique_output_path,
    validate_config,
    verify_output,
)
from settings_store import LOG_PATH, PRESETS, SettingsStore, setup_logging
from version import APP_ID, APP_NAME, AUTHOR, CONTACT, VERSION

# ---------------------------------------------------------------------------
# Tasarım ölçüleri (tek kaynak: tüm yazı boyutları buradan gelir)
# ---------------------------------------------------------------------------
FONT_FAMILY = "Segoe UI"
FS_TITLE = 22
FS_SUBTITLE = 15
FS_BODY = 14
FS_SMALL = 12
FS_TINY = 11
BODY_MIN_PX = 12

# Açık / koyu tema renk çiftleri
COLOR_BG = ("#F6F8FA", "#0D1117")
COLOR_CARD = ("#FFFFFF", "#161B22")
COLOR_SUBCARD = ("#F6F8FA", "#1F242C")
COLOR_BORDER = ("#D0D7DE", "#30363D")
COLOR_TEXT_PRIMARY = ("#1F2328", "#F0F6FC")
COLOR_TEXT_SECONDARY = ("#656D76", "#8B949E")
COLOR_ACCENT = ("#0969DA", "#58A6FF")
COLOR_ACCENT_HOVER = ("#0854C4", "#79B8FF")
COLOR_SOLID = ("#0969DA", "#1F6FEB")
COLOR_SOLID_HOVER = ("#0854C4", "#1857B8")
COLOR_ON_ACCENT = ("#FFFFFF", "#FFFFFF")
COLOR_SELECTED = ("#B7DCFF", "#17456E")
COLOR_SELECTED_HOVER = ("#9FCDF8", "#1D527F")
COLOR_BTN_SUBTLE = ("#F3F4F6", "#21262D")
COLOR_BTN_SUBTLE_HOVER = ("#E5E7EB", "#30363D")
COLOR_OK = ("#1A7F37", "#3FB950")
COLOR_OK_BG = ("#DAFBE1", "#133E1D")
COLOR_WARN = ("#9A6700", "#D29922")
COLOR_WARN_BG = ("#FFF8C5", "#3D2C00")
COLOR_ERROR = ("#CF222E", "#FF7B72")
COLOR_ERROR_BG = ("#FFEBE9", "#3D1A1C")

POSITION_LABELS = {
    "Dış kenar (Tek sağ / Çift sol)": "outer",
    "Alt orta": "center",
    "İç kenar": "inner",
}
POSITION_CODES = {v: k for k, v in POSITION_LABELS.items()}
FORMAT_LABELS = {
    "1, 2, 3": "number",
    "- 1 -": "dash",
    "1 / Toplam": "total",
    "Sayfa 1": "label",
    "i, ii, iii": "roman",
    "I, II, III": "roman_upper",
}
FORMAT_CODES = {v: k for k, v in FORMAT_LABELS.items()}
MODE_LABELS = {
    "Uzat (kırpmaz, önerilen)": "expand",
    "Sığdır (orantılı küçült)": "fit",
    "Kaydır (kırpabilir)": "shift",
}
MODE_CODES = {v: k for k, v in MODE_LABELS.items()}
SIZE_MODE_LABELS = {
    "Hedef ebat sabit": "fixed",
    "Kaynak ebat + cilt payı": "auto",
}
SIZE_MODE_CODES = {v: k for k, v in SIZE_MODE_LABELS.items()}
OVERFLOW_LABELS = {
    "Kırp": "clip",
    "Sayfaya sığdır": "shrink",
}
OVERFLOW_CODES = {v: k for k, v in OVERFLOW_LABELS.items()}
MARGIN_PRESETS_MM = (10.0, 15.0, 20.0, 25.0)
PAPER_SIZES = {
    "A4 (210 × 297)": (210.0, 297.0),
    "A5 (148 × 210)": (148.0, 210.0),
    "B5 (176 × 250)": (176.0, 250.0),
    "Letter (8.5 × 11 inç)": (215.9, 279.4),
}
# İnç şimdilik arayüzde kapalı; motor desteği ileride açılmak üzere duruyor.
DISPLAY_UNITS = ("mm", "cm", "pt")


class FieldError(Exception):
    """Alan doğrulama hatası; mesajı kullanıcıya gösterilir."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class FieldRow(ctk.CTkFrame):
    """
    Etiket + giriş kutusu + birim + hata satırı.
    Hatalı kutu kırmızıya döner ve altında kısa açıklama görünür.
    """

    def __init__(
        self,
        master,
        label: str,
        value: str,
        unit: str = "mm",
        convert: bool = True,
        width: int = 78,
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
        integer: bool = False,
        allow_negative: bool = False,
        on_change=None,
        suffix: Optional[str] = None,
        label_width: int = 0,
    ):
        super().__init__(master, fg_color="transparent")
        self.label_text = label
        self.unit = unit
        self.convert = convert
        self.minimum = minimum
        self.maximum = maximum
        self.integer = integer
        self.allow_negative = allow_negative
        self.on_change = on_change
        self.suffix = suffix
        self.last_valid: float = 0.0
        self._canonical_mm: float = 0.0

        self.label = ctk.CTkLabel(
            self, text=label, font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
            width=label_width if label_width else 0,
        )
        self.label.pack(side="left", padx=(0, 6))

        self.entry = ctk.CTkEntry(
            self, width=width, height=32,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY),
            fg_color=COLOR_SUBCARD, border_color=COLOR_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
        )
        self.entry.pack(side="left")
        self.entry.insert(0, value)
        self.entry.bind("<KeyRelease>", self._on_key)
        self.entry.bind("<FocusOut>", self._on_focus_out)

        self.unit_label = ctk.CTkLabel(
            self, text=self._unit_text(), font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY,
        )
        self.unit_label.pack(side="left", padx=(4, 0))

        self.error_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_ERROR, anchor="w", justify="left", wraplength=230,
        )
        self.error_label.pack(anchor="w", pady=(1, 0))
        self._set_default(value)

    # -- değer -------------------------------------------------------------
    def _unit_text(self) -> str:
        if self.suffix is not None:
            return self.suffix
        if not self.convert:
            return "pt"
        return UNITS.get(self.unit, UNITS["mm"])[0]

    def _set_default(self, text: str) -> None:
        try:
            self.last_valid = float(str(text).replace(",", "."))
        except (TypeError, ValueError):
            self.last_valid = 0.0
        if self.convert:
            self._canonical_mm = unit_to_mm(self.last_valid, self.unit)

    def _replace_text(self, text: str) -> None:
        previous_state = self.entry.cget("state")
        if previous_state == "disabled":
            self.entry.configure(state="normal")
        self.entry.delete(0, "end")
        self.entry.insert(0, text)
        if previous_state == "disabled":
            self.entry.configure(state="disabled")
        self.set_error("")

    def set_value(self, text: str, canonical_mm: Optional[float] = None) -> None:
        self._replace_text(text)
        if canonical_mm is not None:
            self._canonical_mm = float(canonical_mm)
            self.last_valid = unit_to_mm(float(canonical_mm), self.unit) if self.convert else float(canonical_mm)
        else:
            self._set_default(text)

    def set_mm(self, mm: float) -> None:
        if self.convert:
            self.set_value(format_measure(mm, self.unit), canonical_mm=mm)
        else:
            self.set_value(f"{mm:g}")

    def get_value(self) -> float:
        text = self.entry.get().strip().replace(" ", "").replace(",", ".")
        if not text:
            raise FieldError("Değer girin.")
        try:
            number = float(text)
        except ValueError:
            raise FieldError("Sayı girin (örn. 15 veya 2,5).")
        if self.integer:
            if abs(number - round(number)) > 1e-6:
                raise FieldError("Tam sayı girin.")
            number = int(round(number))
        if not self.allow_negative and number < 0:
            raise FieldError("Negatif olamaz.")
        if self.minimum is not None and number < self.minimum:
            raise FieldError(f"En az {self._fmt_limit(self.minimum)} olmalı.")
        if self.maximum is not None and number > self.maximum:
            raise FieldError(f"En fazla {self._fmt_limit(self.maximum)} olmalı.")
        self.last_valid = float(number)
        if self.convert:
            self._canonical_mm = unit_to_mm(self.last_valid, self.unit)
        return float(number)

    def _fmt_limit(self, value: float) -> str:
        return f"{value:g}"

    def get_mm(self) -> float:
        self.get_value()
        return self._canonical_mm if self.convert else self.last_valid

    def _on_key(self, _event=None) -> None:
        try:
            self.get_value()
        except FieldError:
            pass
        else:
            self.set_error("")
        if self.on_change:
            self.on_change()

    def _on_focus_out(self, _event=None) -> None:
        try:
            self.get_value()
        except FieldError as exc:
            self.set_error(exc.message)

    def set_error(self, message: str) -> None:
        self.error_label.configure(text=message)
        if message:
            self.entry.configure(border_color=COLOR_ERROR, border_width=2)
        else:
            self.entry.configure(border_color=COLOR_BORDER, border_width=1)

    def set_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.entry.configure(state=state)

    def change_unit(self, old_unit: str, new_unit: str) -> None:
        if not self.convert or old_unit == new_unit:
            return
        try:
            value = float(self.entry.get().strip().replace(",", "."))
        except ValueError:
            value = None
        if value is not None:
            self._canonical_mm = unit_to_mm(value, old_unit)
        self.unit = new_unit
        self.unit_label.configure(text=self._unit_text())
        # Görüntü yuvarlanır ama mm değeri korunur; birime geri dönüş kayıpsızdır.
        self.set_value(format_measure(self._canonical_mm, new_unit),
                       canonical_mm=self._canonical_mm)

    def reset_unit(self, unit: str) -> None:
        """Gösterim birimini dönüştürmeden ayarlar (başlangıçta kayıtlı birim)."""
        if not self.convert:
            return
        self.unit = unit
        self.unit_label.configure(text=self._unit_text())
        self.set_value(format_measure(self._canonical_mm, unit),
                       canonical_mm=self._canonical_mm)


class WrapButtonRow(ctk.CTkFrame):
    """Eşit genişlikte, tek satırlık düğme grubu (yeniden yerleşim titremesi yok)."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._buttons: List[ctk.CTkButton] = []

    def add_button(self, text: str, command, width: int = 90, bold: bool = False) -> ctk.CTkButton:
        index = len(self._buttons)
        button = ctk.CTkButton(
            self, text=text, command=command, height=32,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold" if bold else "normal"),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, corner_radius=6, width=width,
        )
        self._buttons.append(button)
        self.grid_columnconfigure(index, weight=1, uniform="preset")
        button.grid(row=0, column=index, sticky="ew", padx=2, pady=2)
        return button


class TabNav:
    """``CTkTabview`` yerine daha okunur, büyük düğmeli sekme denetleyicisi."""

    def __init__(self, app: "ModernGutterApp"):
        self.app = app

    def get(self) -> str:
        return self.app.current_tab

    def set(self, name: str) -> None:
        self.app.select_tab(name)


TAB_NAMES = ["Cilt Payı", "Kenar Boşlukları", "Sayfa Numaraları", "Birleştirme"]
TAB_FULL_NAMES = {
    "Cilt Payı": "Cilt Payı",
    "Kenar Boşlukları": "Kenar Boşlukları",
    "Sayfa Numaraları": "Sayfa Numaralandırma",
    "Birleştirme": "PDF Birleştirme",
}


class StudioWindow(ctk.CTk):
    """
    CustomTkinter penceresi; başlık çubuğu rengini pencereyi gizlemeden değiştirir.

    CTk 6.0.0'ın ``_windows_set_titlebar_color`` yöntemi pencereyi önce
    ``withdraw()`` ile gizler, sonra ``deiconify()`` ile geri açar. Windows'ta bu
    geçiş sırasında pencere boş görünür ve titrer; ayrıca koşulu hatalı yazıldığı
    (``!= "iconic" or != "withdrawn"`` her zaman doğru) için her tema değişiminde
    çalışır. Burada yalnızca DWM özniteliği güncellenir; pencere hiç gizlenmez.
    """

    def _windows_set_titlebar_color(self, color_mode: str) -> None:
        if not sys.platform.startswith("win"):
            return
        if getattr(self, "_deactivate_windows_window_header_manipulation", False):
            return
        try:
            import ctypes

            value = ctypes.c_int(1 if str(color_mode).lower() == "dark" else 0)
            user32 = ctypes.windll.user32
            user32.GetParent.restype = ctypes.c_void_p
            user32.GetParent.argtypes = [ctypes.c_void_p]
            hwnd = user32.GetParent(self.winfo_id())
            if not hwnd:
                return
            # 20 yeni, 19 eski Windows sürümlerinde karanlık başlık özniteliğidir.
            for attribute in (20, 19):
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        ctypes.c_void_p(hwnd), attribute,
                        ctypes.byref(value), ctypes.sizeof(value)) == 0:
                    break
        except Exception:
            pass


class ModernGutterApp(StudioWindow):
    def __init__(self, settings_path=None, log_path=None):
        super().__init__()
        self._closing = False

        self.log = setup_logging(log_path)
        # Doğal olmayan kapanmalarda (ctypes geri çağrısı, erişim ihlali) Python
        # yığın izi günlüğe düşsün; "uygulama sessizce kapandı" tanısı kolaylaşır.
        try:
            self._crash_stream = open(log_path or LOG_PATH, "a", encoding="utf-8")
            faulthandler.enable(file=self._crash_stream)
        except Exception:
            self._crash_stream = None
        self.store = SettingsStore(settings_path)
        self.log.info("%s %s başlatıldı", APP_NAME, VERSION)

        self.title(f"{APP_NAME} {VERSION}")
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self._apply_app_icon()
        self.configure(fg_color=COLOR_BG)

        # Belge durumu
        self.input_pdf_path = ""
        self.output_pdf_path = ""
        self.orig_width_mm = 210.0
        self.orig_height_mm = 297.0
        self.orig_page_count = 0

        # Birleştirme listesi
        self.merge_files: List[Dict[str, Any]] = []
        self.selected_merge_idx: Optional[int] = None
        self._merge_rows: List[ctk.CTkFrame] = []
        self._drag_idx: Optional[int] = None
        self.current_tab = TAB_NAMES[0]

        # Çalışma durumu
        self._cancel_event = threading.Event()
        self._busy = False
        self._work_config: Optional[PdfProcessConfig] = None
        self._work_paths = ("", "")
        self._preview_gen = 0
        self._preview_after = None
        self._preview_signature = None
        self._queue_after = None
        self._preview_history: List[Any] = []
        self._blank_images: Dict[str, Any] = {}
        self.preview_mode = "spread"
        self.preview_page = 0
        self._preview_images: List[Any] = []
        self._last_valid_config: Optional[PdfProcessConfig] = None
        self.unit = self.store.unit if self.store.unit in DISPLAY_UNITS else "mm"
        self._ui_queue: "queue.Queue" = queue.Queue()

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
        self._schedule_preview()
        self._queue_after = self.after(50, self._drain_ui_queue)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.update_idletasks()
        # CTk geometry/minsize değerlerini pencere ölçeğiyle çarpar; ekran ölçüsü
        # ise fiziksel pikseldir. İkisini aynı birime (mantıksal piksel) getir.
        screen_scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        screen_w = self.winfo_screenwidth() / screen_scale
        screen_h = self.winfo_screenheight() / screen_scale
        available_w = max(1060, screen_w - 120)
        available_h = max(660, screen_h - 140)
        self.geometry(f"{min(1240, available_w):.0f}x{min(900, available_h):.0f}")
        self.minsize(min(1060, available_w), min(700, available_h))

    # =====================================================================
    # Genel pencere kurulumu
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
        self._closing = True
        try:
            self._cancel_event.set()
        except Exception:
            pass
        if self._preview_after is not None:
            try:
                self.after_cancel(self._preview_after)
            except Exception:
                pass
            self._preview_after = None
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
        icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.ico")
        if os.path.exists(icon):
            try:
                self.iconbitmap(icon)
            except Exception:
                pass

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-o>", lambda e: self._choose_file())
        self.bind("<Control-O>", lambda e: self._choose_file())
        # Ctrl+S "işle" anlamına geliyordu; asıl eylem Ctrl+Enter oldu.
        self.bind("<Control-Return>", lambda e: self._invoke_main_action())
        self.bind("<Return>", self._on_enter_key)
        self.bind("<Escape>", lambda e: self._on_escape())
        self.bind("<Delete>", self._on_merge_delete)
        self.bind("<Alt-Up>", lambda e: self._on_merge_move(-1))
        self.bind("<Alt-Down>", lambda e: self._on_merge_move(1))

    def _list_shortcuts_active(self) -> bool:
        """Liste kısayolları yalnızca birleştirme sekmesinde ve metin alanı dışında çalışır."""
        if "Birleştirme" not in self.tabview.get():
            return False
        focus = self.focus_get()
        return not isinstance(focus, (tk.Entry, tk.Text, ctk.CTkEntry, ctk.CTkTextbox))

    def _on_merge_delete(self, _event=None):
        if not self._list_shortcuts_active() or self._busy:
            return None
        self._remove_merge_file()
        return "break"

    def _on_merge_move(self, delta: int):
        if not self._list_shortcuts_active() or self._busy:
            return None
        if delta < 0:
            self._move_merge_file_up()
        else:
            self._move_merge_file_down()
        return "break"

    def _on_enter_key(self, _event=None):
        focus = self.focus_get()
        if isinstance(focus, (tk.Entry, tk.Text, ctk.CTkEntry, ctk.CTkTextbox)):
            return
        self._invoke_main_action()

    def _on_escape(self) -> None:
        if self._busy:
            self._cancel_work()

    def _invoke_main_action(self) -> None:
        if self._busy:
            return
        if "Birleştirme" in self.tabview.get():
            self._start_merging()
        else:
            self._start_processing()

    def _init_drag_and_drop(self) -> None:
        if not HAS_WINDND:
            self.log.info("windnd bulunamadı; sürükle-bırak devre dışı.")
            return
        try:
            # force_unicode: windnd aksi hâlde ANSI bayt döndürür ve Türkçe
            # karakterli yollar çözülemez (UnicodeDecodeError).
            windnd.hook_dropfiles(self, func=self._on_drop_files, force_unicode=True)
        except Exception:
            self.log.exception("Sürükle-bırak kancası kurulamadı")

    def _on_drop_files(self, files) -> None:
        """windnd bu geri çağrıyı pencere yordamı içinden çalıştırır.

        Burada Tk'ye hiç dokunulmaz: pencere yordamı içinden Tcl çağırmak
        (``after`` dahil) yeniden girişe ve uygulamanın sessizce kapanmasına yol
        açabiliyor. İş, ana döngüde çalıştırılmak üzere kuyruğa bırakılır.
        """
        try:
            paths = list(files)
        except Exception:
            self.log.exception("Sürükle-bırak verisi okunamadı")
            return
        try:
            self._ui_queue.put(lambda: self._handle_dropped_files(paths))
        except Exception:
            self.log.exception("Sürükle-bırak kuyruğa alınamadı")

    @staticmethod
    def _decode_dropped(item) -> str:
        """Bırakılan yolu metne çevirir; ANSI (mbcs) ve UTF-8 baytlarını destekler."""
        if isinstance(item, str):
            return item
        if isinstance(item, bytes):
            for encoding in ("utf-8", "mbcs"):
                try:
                    return item.decode(encoding)
                except (UnicodeDecodeError, LookupError):
                    continue
            return item.decode("latin-1", "replace")
        return str(item)

    def _handle_dropped_files(self, files) -> None:
        """Bırakılan dosyaları sekmeye göre açar veya birleştirme listesine ekler."""
        try:
            paths = [self._decode_dropped(item).strip().strip('"') for item in files]
            paths = [p for p in paths if p]
            pdfs = [p for p in paths
                    if p.lower().endswith(".pdf") and os.path.isfile(p)]
            if not pdfs:
                messagebox.showinfo(
                    "Sürükle-bırak",
                    "Bırakılan öğeler arasında PDF dosyası yok.\n"
                    "Klasör yerine doğrudan PDF dosyalarını bırakın.",
                )
                return

            if "Birleştirme" in self.tabview.get():
                before = len(self.merge_files)
                for path in pdfs:
                    self._append_merge_file(path)
                self._refresh_merge_listbox()
                added = len(self.merge_files) - before
                skipped = len(pdfs) - added
                text = f"{added} PDF birleştirme listesine eklendi."
                if skipped:
                    text += f" {skipped} dosya listede zaten vardı veya açılamadı."
                self._set_status(text, COLOR_TEXT_PRIMARY)
                return

            self._load_file(pdfs[0])
            if len(pdfs) > 1:
                self._set_status(
                    f"{len(pdfs)} PDF bırakıldı; ilki açıldı. Hepsini birleştirmek için "
                    "Birleştirme sekmesine bırakın.",
                    COLOR_TEXT_PRIMARY,
                )
            elif len(paths) > 1:
                self._set_status("PDF dışı öğeler yok sayıldı.", COLOR_TEXT_SECONDARY)
        except Exception:
            self.log.exception("Sürükle-bırak işlenemedi")
            messagebox.showerror("Sürükle-bırak",
                                 "Bırakılan dosyalar işlenemedi. Ayrıntılar günlükte.")

    # =====================================================================
    # Üst çubuk, dosya çubuğu, sekmeler
    # =====================================================================
    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._build_header()
        self._build_file_bar()
        self._build_workspace()
        self._build_action_bar()

    def _build_header(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=COLOR_CARD, corner_radius=8,
                           border_width=1, border_color=COLOR_BORDER)
        bar.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 5))

        left = ctk.CTkFrame(bar, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True, padx=12, pady=7)

        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.png")
        if os.path.exists(icon_path):
            try:
                image = Image.open(icon_path)
                self._header_icon = ctk.CTkImage(light_image=image, dark_image=image, size=(34, 34))
                ctk.CTkLabel(left, text="", image=self._header_icon).pack(side="left", padx=(0, 10))
            except Exception:
                pass

        title_box = ctk.CTkFrame(left, fg_color="transparent")
        title_box.pack(side="left")
        ctk.CTkLabel(
            title_box, text=APP_NAME,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TITLE, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_box, text=f"Sürüm {VERSION} • kayıpsız vektörel baskı hazırlığı",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY,
        ).pack(anchor="w")

        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.pack(side="right", padx=12)

        ctk.CTkButton(
            right, text="Hakkında", width=90, height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, corner_radius=6,
            command=self._show_about_dialog,
        ).pack(side="left", padx=(0, 8))

        self.theme_segmented = ctk.CTkSegmentedButton(
            right, values=["Açık", "Koyu", "Sistem"], width=200, height=34,
            border_width=0, fg_color=COLOR_SUBCARD, bg_color=COLOR_CARD,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            command=self._on_theme_changed,
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_SUBCARD, unselected_hover_color=COLOR_BTN_SUBTLE,
            text_color=COLOR_TEXT_PRIMARY, corner_radius=6,
        )
        self.theme_segmented.pack(side="left")

    def _build_file_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=COLOR_CARD, corner_radius=8,
                           border_width=1, border_color=COLOR_BORDER)
        bar.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 5))

        row = ctk.CTkFrame(bar, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(7, 3))

        ctk.CTkLabel(
            row, text="Belge:", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(side="left", padx=(0, 8))

        self.path_entry = ctk.CTkEntry(
            row, placeholder_text="PDF dosyası seçin veya pencereye sürükleyin...",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY), height=34,
            border_color=COLOR_BORDER, fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
        )
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.path_entry.bind("<Return>", lambda e: self._load_from_entry())

        ctk.CTkButton(
            row, text="Gözat...", width=88, height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY, weight="bold"),
            fg_color=COLOR_SOLID, text_color=COLOR_ON_ACCENT,
            hover_color=COLOR_SOLID_HOVER,
            command=self._choose_file,
        ).pack(side="left")

        row2 = ctk.CTkFrame(bar, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=(0, 7))

        self.info_badge = ctk.CTkLabel(
            row2, text="Henüz belge seçilmedi.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=460,
        )
        self.info_badge.pack(side="left", fill="x", expand=True)

        controls = ctk.CTkFrame(row2, fg_color="transparent")
        controls.pack(side="right")

        ctk.CTkLabel(
            controls, text="Birim:", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY,
        ).pack(side="left", padx=(0, 4))
        self.unit_menu = ctk.CTkOptionMenu(
            controls, values=[UNITS[u][0] for u in DISPLAY_UNITS], width=74, height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            button_color=COLOR_SUBCARD, button_hover_color=COLOR_BTN_SUBTLE_HOVER,
            dropdown_fg_color=COLOR_CARD, dropdown_hover_color=COLOR_SELECTED,
            dropdown_text_color=COLOR_TEXT_PRIMARY,
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            command=self._on_unit_changed,
        )
        self.unit_menu.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(
            controls, text="Profil:", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY,
        ).pack(side="left", padx=(0, 4))
        self.profile_menu = ctk.CTkOptionMenu(
            controls, values=["(profil seçin)"], width=170, height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            button_color=COLOR_SUBCARD, button_hover_color=COLOR_BTN_SUBTLE_HOVER,
            dropdown_fg_color=COLOR_CARD, dropdown_hover_color=COLOR_SELECTED,
            dropdown_text_color=COLOR_TEXT_PRIMARY,
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
        )
        self.profile_menu.pack(side="left", padx=(0, 4))

        icon_button = {
            "width": 30, "height": 26, "font": ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            "fg_color": COLOR_SUBCARD, "text_color": COLOR_TEXT_PRIMARY,
            "border_width": 1, "border_color": COLOR_BORDER,
            "hover_color": COLOR_BTN_SUBTLE_HOVER, "corner_radius": 5,
        }
        ctk.CTkButton(controls, text="Yükle", **icon_button).pack(side="left", padx=(0, 3))
        ctk.CTkButton(controls, text="Kaydet", **{**icon_button, "width": 56}).pack(side="left", padx=(0, 3))
        ctk.CTkButton(controls, text="Sil", **{**icon_button, "width": 40}).pack(side="left")

        row2.bind("<Configure>", lambda e: self.info_badge.configure(
            wraplength=max(180, e.width - controls.winfo_reqwidth() - 24)), add="+")

    def _build_workspace(self) -> None:
        workspace = ctk.CTkFrame(self, fg_color="transparent")
        workspace.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 6))
        self._workspace = workspace
        workspace.grid_columnconfigure(0, weight=1)
        workspace.grid_columnconfigure(1, weight=0, minsize=380)
        workspace.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(workspace, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(2, weight=1)

        self._build_module_bar(left)

        nav = ctk.CTkFrame(left, fg_color="transparent")
        nav.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        self._tab_buttons: Dict[str, ctk.CTkButton] = {}
        for index, name in enumerate(TAB_NAMES):
            nav.grid_columnconfigure(index, weight=1, uniform="tab")
            button = ctk.CTkButton(
                nav, text=f"{index + 1}   {name}", height=46,
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY, weight="bold"),
                fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
                border_width=1, border_color=COLOR_BORDER,
                hover_color=COLOR_SUBCARD, corner_radius=8,
                command=lambda n=name: self.select_tab(n),
            )
            button.grid(row=0, column=index, sticky="ew", padx=3)
            self._tab_buttons[name] = button

        content = ctk.CTkFrame(left, fg_color=COLOR_CARD, corner_radius=10,
                               border_width=1, border_color=COLOR_BORDER)
        content.grid(row=2, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)

        self.tab_gutter = ctk.CTkFrame(content, fg_color=COLOR_CARD)
        self.tab_margin = ctk.CTkFrame(content, fg_color=COLOR_CARD)
        self.tab_number = ctk.CTkFrame(content, fg_color=COLOR_CARD)
        self.tab_merge = ctk.CTkFrame(content, fg_color=COLOR_CARD)
        self._tab_frames = [self.tab_gutter, self.tab_margin, self.tab_number, self.tab_merge]
        self._tab_frames_map = {
            "Cilt Payı": self.tab_gutter,
            "Kenar Boşlukları": self.tab_margin,
            "Sayfa Numaraları": self.tab_number,
            "Birleştirme": self.tab_merge,
        }
        for frame in self._tab_frames:
            frame.grid(row=0, column=0, sticky="nsew")

        self._build_tab_gutter()
        self._build_tab_margin()
        self._build_tab_number()
        self._build_tab_merge()
        self._build_preview_panel(workspace)

        self.tabview = TabNav(self)
        self.select_tab(self.current_tab)

    def _build_module_bar(self, parent) -> None:
        """Üç modülün tek yerden açılıp kapatıldığı üst şerit."""
        bar = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10,
                           border_width=1, border_color=COLOR_BORDER)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        bar.grid_columnconfigure(0, weight=1)

        labels = ctk.CTkFrame(bar, fg_color="transparent")
        labels.grid(row=0, column=0, sticky="w", padx=(12, 8), pady=7)
        ctk.CTkLabel(
            labels, text="Uygulanacak işlemler",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            labels, text="İşaretlediğiniz modüller tek geçişte uygulanır.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w",
        ).pack(anchor="w")

        checks = ctk.CTkFrame(bar, fg_color="transparent")
        checks.grid(row=0, column=1, sticky="e", padx=(0, 6), pady=7)

        check_font = ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold")
        self.switch_gutter = ctk.CTkCheckBox(
            checks, text="Cilt payı", font=check_font,
            text_color=COLOR_TEXT_PRIMARY, hover_color=COLOR_ACCENT,
            fg_color=COLOR_SOLID, border_color=COLOR_BORDER,
            command=self._toggle_gutter_fields,
        )
        self.switch_gutter.pack(side="left", padx=(0, 14))

        self.switch_margin = ctk.CTkCheckBox(
            checks, text="Kenar boşluğu", font=check_font,
            text_color=COLOR_TEXT_PRIMARY, hover_color=COLOR_ACCENT,
            fg_color=COLOR_SOLID, border_color=COLOR_BORDER,
            command=self._toggle_margin_fields,
        )
        self.switch_margin.pack(side="left", padx=(0, 14))

        self.switch_pnum = ctk.CTkCheckBox(
            checks, text="Sayfa numarası", font=check_font,
            text_color=COLOR_TEXT_PRIMARY, hover_color=COLOR_ACCENT,
            fg_color=COLOR_SOLID, border_color=COLOR_BORDER,
            command=self._toggle_pnum_fields,
        )
        self.switch_pnum.pack(side="left")

        self.btn_all_modules = ctk.CTkButton(
            bar, text="Tümünü aç", width=110, height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, corner_radius=6,
            command=self._toggle_all_modules,
        )
        self.btn_all_modules.grid(row=0, column=2, sticky="e", padx=12)

    def _update_all_modules_button(self) -> None:
        if not hasattr(self, "btn_all_modules"):
            return
        all_off = not any(switch.get() == 1 for switch in
                          (self.switch_gutter, self.switch_margin, self.switch_pnum))
        self.btn_all_modules.configure(text="Tümünü aç" if all_off else "Tümünü kapat")

    def _toggle_all_modules(self) -> None:
        target_on = not any(switch.get() == 1 for switch in
                            (self.switch_gutter, self.switch_margin, self.switch_pnum))
        for switch in (self.switch_gutter, self.switch_margin, self.switch_pnum):
            if target_on:
                switch.select()
            else:
                switch.deselect()
        self._toggle_gutter_fields()
        self._toggle_margin_fields()
        self._toggle_pnum_fields()
        self._update_all_modules_button()

    def _disable_all_modules(self) -> None:
        self.switch_gutter.deselect()
        self.switch_margin.deselect()
        self.switch_pnum.deselect()
        self._toggle_gutter_fields()
        self._toggle_margin_fields()
        self._toggle_pnum_fields()
        self._update_all_modules_button()

    def select_tab(self, name: str) -> None:
        """Sekmeyi seçer, düğme durumlarını ve içerik görünürlüğünü günceller."""
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
        self._tab_frames_map[name].tkraise()
        self._on_tab_changed()

    # =====================================================================
    # SEKME 1: Cilt Payı
    # =====================================================================
    def _build_tab_gutter(self) -> None:
        scroll = ctk.CTkScrollableFrame(self.tab_gutter, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=8, pady=(4, 10))
        container = scroll
        container.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(container, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", pady=(2, 6))
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            top, text="Cilt payı ayarları",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SUBTITLE, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self.lbl_gutter_status = ctk.CTkLabel(
            top, text="Devre dışı: üstteki 'Cilt payı' onay kutusundan açın",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=520,
        )
        self.lbl_gutter_status.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self._bind_wraplength(self.lbl_gutter_status, top, 24)

        presets = ctk.CTkFrame(container, fg_color="transparent")
        presets.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self._gutter_preset_row = WrapButtonRow(presets)
        self._gutter_preset_row.pack(fill="x")
        self._gutter_preset_row.add_button("10 mm duplex", lambda: self._apply_gutter_preset(10.0))
        self._gutter_preset_row.add_button("15 mm duplex (standart)", lambda: self._apply_gutter_preset(15.0), bold=True)
        self._gutter_preset_row.add_button("20 mm duplex (geniş)", lambda: self._apply_gutter_preset(20.0))
        self._gutter_preset_row.add_button("Sıfırla / kapat", self._reset_gutter_to_original)

        profile_row = ctk.CTkFrame(container, fg_color="transparent")
        profile_row.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        ctk.CTkLabel(
            profile_row, text="Hazır profil:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(side="left", padx=(0, 6))
        self._preset_row = WrapButtonRow(profile_row)
        self._preset_row.pack(side="left", fill="x", expand=True)
        for preset_name in PRESETS:
            short = preset_name.split(" (")[0]
            self._preset_row.add_button(
                short, lambda name=preset_name: self._apply_named_preset(name), width=96,
            )

        mode_card = ctk.CTkFrame(container, fg_color=COLOR_SUBCARD, corner_radius=6,
                                 border_width=1, border_color=COLOR_BORDER)
        mode_card.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        mode_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            mode_card, text="Sayfa ebadı",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(7, 2))

        self.seg_size_mode = ctk.CTkSegmentedButton(
            mode_card, values=list(SIZE_MODE_LABELS.keys()), height=36,
            border_width=0, fg_color=COLOR_SUBCARD, bg_color=COLOR_SUBCARD,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_CARD, unselected_hover_color=COLOR_SUBCARD,
            text_color=COLOR_TEXT_PRIMARY, command=lambda _v: self._on_gutter_changed(),
        )
        self.seg_size_mode.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 4))

        ctk.CTkLabel(
            mode_card,
            text="Sabit: hedef ebatı siz belirlersiniz. Kaynak + cilt: her sayfa kendi ebadını korur; "
                 "karışık ebatlı belgelerde kırpma olmaz.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=560,
        ).grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 7))

        overflow_row = ctk.CTkFrame(mode_card, fg_color="transparent")
        overflow_row.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 8))
        ctk.CTkLabel(
            overflow_row, text="Hedefe sığmayan içerik:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(side="left", padx=(0, 8))
        self.seg_overflow = ctk.CTkSegmentedButton(
            overflow_row, values=list(OVERFLOW_LABELS.keys()), width=180, height=30,
            border_width=0, fg_color=COLOR_SUBCARD, bg_color=COLOR_SUBCARD,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_CARD, unselected_hover_color=COLOR_SUBCARD,
            text_color=COLOR_TEXT_PRIMARY, command=lambda _v: self._on_gutter_changed(),
        )
        self.seg_overflow.set(list(OVERFLOW_LABELS.keys())[0])
        self.seg_overflow.pack(side="left")
        ctk.CTkLabel(
            overflow_row, text="Sığdır: küçültür, kırpmaz",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY,
        ).pack(side="left", padx=(8, 0))

        paper_row = ctk.CTkFrame(mode_card, fg_color="transparent")
        paper_row.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 8))
        ctk.CTkLabel(
            paper_row, text="Kağıt:", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(side="left", padx=(0, 5))
        self.paper_menu = ctk.CTkOptionMenu(
            paper_row, values=list(PAPER_SIZES.keys()), width=180, height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
            button_color=COLOR_SUBCARD, button_hover_color=COLOR_BTN_SUBTLE_HOVER,
            dropdown_fg_color=COLOR_CARD, dropdown_hover_color=COLOR_SELECTED,
            dropdown_text_color=COLOR_TEXT_PRIMARY,
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
        )
        self.paper_menu.set(list(PAPER_SIZES.keys())[0])
        self.paper_menu.pack(side="left", padx=(0, 6))
        self.orientation_menu = ctk.CTkSegmentedButton(
            paper_row, values=["Dikey", "Yatay"], width=120, height=32,
            border_width=0, fg_color=COLOR_SUBCARD, bg_color=COLOR_SUBCARD,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_CARD, unselected_hover_color=COLOR_SUBCARD,
            text_color=COLOR_TEXT_PRIMARY,
        )
        self.orientation_menu.set("Dikey")
        self.orientation_menu.pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            paper_row, text="Uygula", width=74, height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY, weight="bold"),
            fg_color=COLOR_SOLID, text_color=COLOR_ON_ACCENT,
            hover_color=COLOR_SOLID_HOVER,
            command=self._apply_paper_size,
        ).pack(side="left")

        sizes = ctk.CTkFrame(container, fg_color="transparent")
        sizes.grid(row=5, column=0, sticky="ew", pady=(0, 8))
        sizes.grid_columnconfigure(1, weight=1)

        self.f_width = FieldRow(
            sizes, "Hedef genişlik", "210", width=86, minimum=1, maximum=5000,
            on_change=self._on_gutter_changed,
        )
        self.f_width.grid(row=0, column=0, sticky="w", padx=(0, 18))
        self.f_height = FieldRow(
            sizes, "Hedef yükseklik", "297", width=86, minimum=1, maximum=5000,
            on_change=self._on_gutter_changed,
        )
        self.f_height.grid(row=0, column=1, sticky="w")

        cols = ctk.CTkFrame(container, fg_color="transparent")
        cols.grid(row=6, column=0, sticky="ew", pady=(0, 4))
        cols.grid_columnconfigure(0, weight=1, uniform="col")
        cols.grid_columnconfigure(1, weight=1, uniform="col")

        odd = ctk.CTkFrame(cols, fg_color=COLOR_SUBCARD, corner_radius=6,
                           border_width=1, border_color=COLOR_BORDER)
        odd.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        even = ctk.CTkFrame(cols, fg_color=COLOR_SUBCARD, corner_radius=6,
                            border_width=1, border_color=COLOR_BORDER)
        even.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        ctk.CTkLabel(
            odd, text="Tek sayfalar (1, 3, 5... sağ sayfa)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_ACCENT, anchor="w", wraplength=240, justify="left",
        ).pack(anchor="w", padx=10, pady=(7, 0))
        ctk.CTkLabel(
            odd, text="Cilt payı sol kenarda açılır",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w",
        ).pack(anchor="w", padx=10, pady=(0, 4))
        self.f_odd_x = FieldRow(odd, "X ofseti", "0", width=64, minimum=-5000, maximum=5000,
                                allow_negative=True, on_change=self._on_gutter_changed)
        self.f_odd_x.pack(fill="x", padx=10, pady=2)
        self.f_odd_y = FieldRow(odd, "Y ofseti", "0", width=64, minimum=-5000, maximum=5000,
                                allow_negative=True, on_change=self._on_gutter_changed)
        self.f_odd_y.pack(fill="x", padx=10, pady=(2, 8))

        ctk.CTkLabel(
            even, text="Çift sayfalar (2, 4, 6... sol sayfa)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_ACCENT, anchor="w", wraplength=240, justify="left",
        ).pack(anchor="w", padx=10, pady=(7, 0))
        ctk.CTkLabel(
            even, text="Cilt payı sağ kenarda açılır",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w",
        ).pack(anchor="w", padx=10, pady=(0, 4))
        self.f_even_x = FieldRow(even, "X ofseti", "0", width=64, minimum=-5000, maximum=5000,
                                 allow_negative=True, on_change=self._on_gutter_changed)
        self.f_even_x.pack(fill="x", padx=10, pady=2)
        self.f_even_y = FieldRow(even, "Y ofseti", "0", width=64, minimum=-5000, maximum=5000,
                                 allow_negative=True, on_change=self._on_gutter_changed)
        self.f_even_y.pack(fill="x", padx=10, pady=(2, 8))

        ctk.CTkFrame(container, fg_color="transparent", height=12).grid(row=7, column=0, sticky="ew")

        exclude_card = ctk.CTkFrame(container, fg_color=COLOR_SUBCARD, corner_radius=6,
                                    border_width=1, border_color=COLOR_BORDER)
        exclude_card.grid(row=3, column=0, sticky="ew", pady=(4, 8))
        ctk.CTkLabel(
            exclude_card, text="İşlem dışı sayfalar (ara kapaklar)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).pack(anchor="w", padx=10, pady=(7, 2))
        self.entry_exclude_pages = ctk.CTkEntry(
            exclude_card, placeholder_text="Örn: 1, 5, 9-10", height=32,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY),
            fg_color=COLOR_CARD, border_color=COLOR_BORDER, text_color=COLOR_TEXT_PRIMARY,
        )
        self.entry_exclude_pages.pack(fill="x", padx=10)
        self.entry_exclude_pages.bind("<KeyRelease>", lambda e: self._on_field_changed())
        ctk.CTkLabel(
            exclude_card,
            text="Bu sayfalara yalnızca cilt payı uygulanmaz; kenar boşluğu ayarları etkilenmez. "
                 "Örn: 1, 5, 9-10",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=560,
        ).pack(anchor="w", padx=10, pady=(2, 7))

        self._toggle_gutter_fields()

    def _toggle_gutter_fields(self) -> None:
        active = self.switch_gutter.get() == 1
        if active:
            self.lbl_gutter_status.configure(
                text="Etkin: tek ve çift sayfalara cilt payı uygulanacak", text_color=COLOR_OK)
        else:
            self.lbl_gutter_status.configure(
                text="Devre dışı: üstteki 'Cilt payı' onay kutusundan açın",
                text_color=COLOR_TEXT_SECONDARY)
        self._update_all_modules_button()
        self._on_field_changed()

    # =====================================================================
    # SEKME 2: Kenar boşlukları
    # =====================================================================
    def _build_tab_margin(self) -> None:
        scroll = ctk.CTkScrollableFrame(self.tab_margin, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=8, pady=(4, 10))
        container = scroll
        container.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(container, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", pady=(2, 6))
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            top, text="Kenar boşluğu ayarları",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SUBTITLE, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self.lbl_margin_status = ctk.CTkLabel(
            top, text="Devre dışı: üstteki 'Kenar boşluğu' onay kutusundan açın",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=520,
        )
        self.lbl_margin_status.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self._bind_wraplength(self.lbl_margin_status, top, 24)

        card = ctk.CTkFrame(container, fg_color=COLOR_SUBCARD, corner_radius=6,
                            border_width=1, border_color=COLOR_BORDER)
        card.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text="Alt pay modu",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(7, 2))

        self.seg_bottom_mode = ctk.CTkSegmentedButton(
            card, values=list(MODE_LABELS.keys()), height=36,
            border_width=0, fg_color=COLOR_SUBCARD, bg_color=COLOR_SUBCARD,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_CARD, unselected_hover_color=COLOR_SUBCARD,
            text_color=COLOR_TEXT_PRIMARY, command=lambda _v: self._on_margin_mode_changed(),
        )
        self.seg_bottom_mode.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 4))

        self.lbl_mode_warning = ctk.CTkLabel(
            card, text="", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY, weight="bold"),
            text_color=COLOR_WARN, anchor="w", justify="left", wraplength=540,
        )
        self.lbl_mode_warning.grid(row=2, column=0, sticky="ew", padx=10)

        bottom_row = ctk.CTkFrame(card, fg_color="transparent")
        bottom_row.grid(row=3, column=0, sticky="ew", padx=10, pady=(5, 3))
        self.f_bottom = FieldRow(bottom_row, "Alt pay", "0", width=64, minimum=0, maximum=5000,
                                 on_change=self._on_margin_changed)
        self.f_bottom.pack(side="left", padx=(0, 8))
        self._bottom_preset_row = WrapButtonRow(bottom_row)
        self._bottom_preset_row.pack(side="left", fill="x", expand=True)
        for value in MARGIN_PRESETS_MM:
            self._bottom_preset_row.add_button(
                self._margin_preset_label(value),
                lambda v=value: self._set_bottom_margin(v), width=52)
        self._bottom_preset_row.add_button("Sıfırla", lambda: self._set_bottom_margin(0.0), width=56)

        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.grid(row=4, column=0, sticky="ew", padx=10, pady=(3, 8))
        self.f_top = FieldRow(top_row, "Üst pay", "0", width=64, minimum=0, maximum=5000,
                              on_change=self._on_margin_changed)
        self.f_top.pack(side="left", padx=(0, 8))
        self._top_preset_row = WrapButtonRow(top_row)
        self._top_preset_row.pack(side="left", fill="x", expand=True)
        for value in MARGIN_PRESETS_MM:
            self._top_preset_row.add_button(
                self._margin_preset_label(value),
                lambda v=value: self._set_top_margin(v), width=52)
        self._top_preset_row.add_button("Sıfırla", lambda: self._set_top_margin(0.0), width=56)
        self._margin_preset_rows = (self._bottom_preset_row, self._top_preset_row)

        self.chk_pad4 = ctk.CTkCheckBox(
            card,
            text="Sayfa sayısını 4'ün katına tamamla (sona boş sayfa ekle)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_PRIMARY, hover_color=COLOR_ACCENT,
            fg_color=COLOR_SOLID, command=self._on_field_changed,
        )
        self.chk_pad4.grid(row=5, column=0, sticky="w", padx=10, pady=(2, 8))

        note = ctk.CTkLabel(
            container,
            text="Uzat: sayfa yüksekliğine pay eklenir, içerik %100 ölçekte kalır (önerilen). "
                 "Sığdır: ebat sabit kalır, içerik orantılı küçülür. Kaydır: içerik kaydırılır, "
                 "sayfa dışına taşan kısım kırpılır.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=560,
        )
        note.grid(row=3, column=0, sticky="ew", padx=2, pady=(0, 6))
        self._bind_wraplength(note, container, 30)

        ctk.CTkFrame(container, fg_color="transparent", height=12).grid(row=4, column=0, sticky="ew")

        exclude_card = ctk.CTkFrame(container, fg_color=COLOR_SUBCARD, corner_radius=6,
                                    border_width=1, border_color=COLOR_BORDER)
        exclude_card.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        ctk.CTkLabel(
            exclude_card, text="İşlem dışı sayfalar (ara kapaklar)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).pack(anchor="w", padx=10, pady=(7, 2))
        self.entry_exclude_margin = ctk.CTkEntry(
            exclude_card, placeholder_text="Örn: 1, 5, 9-10", height=32,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY),
            fg_color=COLOR_CARD, border_color=COLOR_BORDER, text_color=COLOR_TEXT_PRIMARY,
        )
        self.entry_exclude_margin.pack(fill="x", padx=10)
        self.entry_exclude_margin.bind("<KeyRelease>", lambda e: self._on_field_changed())
        ctk.CTkLabel(
            exclude_card,
            text="Bu sayfalara yalnızca alt/üst pay uygulanmaz; cilt payı etkilenmez. "
                 "Örn: 1, 5, 9-10",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=560,
        ).pack(anchor="w", padx=10, pady=(2, 7))

        self._toggle_margin_fields()

    def _toggle_margin_fields(self) -> None:
        active = self.switch_margin.get() == 1
        if active:
            self.lbl_margin_status.configure(
                text="Etkin: belirtilen alt/üst pay uygulanacak", text_color=COLOR_OK)
        else:
            self.lbl_margin_status.configure(
                text="Devre dışı: üstteki 'Kenar boşluğu' onay kutusundan açın",
                text_color=COLOR_TEXT_SECONDARY)
        self._update_all_modules_button()
        self._on_field_changed()

    def _on_margin_mode_changed(self) -> None:
        mode = MODE_LABELS.get(self.seg_bottom_mode.get(), "expand")
        if mode == "shift":
            self.lbl_mode_warning.configure(
                text="Uyarı: Kaydır modu sayfa dışına taşan içeriği kırpar. Önizlemede kırmızı çerçeve ile gösterilir.",
                text_color=COLOR_ERROR)
        elif mode == "fit":
            self.lbl_mode_warning.configure(
                text="Sığdır modu içeriği orantılı küçültür; hiçbir içerik kırpılmaz.",
                text_color=COLOR_TEXT_SECONDARY)
        else:
            self.lbl_mode_warning.configure(
                text="Uzat modu içeriği %100 ölçekte korur; kırpma olmaz.",
                text_color=COLOR_TEXT_SECONDARY)
        self._on_margin_changed()

    # =====================================================================
    # SEKME 3: Sayfa numaralandırma
    # =====================================================================
    def _build_tab_number(self) -> None:
        scroll = ctk.CTkScrollableFrame(self.tab_number, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=8, pady=(4, 10))
        container = scroll
        container.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(container, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", pady=(2, 6))
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            top, text="Sayfa numaralandırma ayarları",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SUBTITLE, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self.lbl_pnum_status = ctk.CTkLabel(
            top, text="Devre dışı: üstteki 'Sayfa numarası' onay kutusundan açın",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=520,
        )
        self.lbl_pnum_status.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self._bind_wraplength(self.lbl_pnum_status, top, 24)

        card = ctk.CTkFrame(container, fg_color=COLOR_SUBCARD, corner_radius=6,
                            border_width=1, border_color=COLOR_BORDER)
        card.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text="Numara konumu",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(7, 2))
        self.seg_pos = ctk.CTkSegmentedButton(
            card, values=list(POSITION_LABELS.keys()), height=36,
            border_width=0, fg_color=COLOR_SUBCARD, bg_color=COLOR_SUBCARD,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_CARD, unselected_hover_color=COLOR_SUBCARD,
            text_color=COLOR_TEXT_PRIMARY, command=lambda _v: self._on_number_position_changed(),
        )
        self.seg_pos.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))

        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 4))
        grid.grid_columnconfigure(1, weight=1)
        grid.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(
            grid, text="Biçim:", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w", padx=(0, 4), pady=3)
        self.menu_format = ctk.CTkOptionMenu(
            grid, values=list(FORMAT_LABELS.keys()), width=120, height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            button_color=COLOR_SUBCARD, button_hover_color=COLOR_BTN_SUBTLE_HOVER,
            dropdown_fg_color=COLOR_CARD, dropdown_hover_color=COLOR_SELECTED,
            dropdown_text_color=COLOR_TEXT_PRIMARY,
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            command=lambda _v: self._on_number_changed(),
        )
        self.menu_format.set("1, 2, 3")
        self.menu_format.grid(row=0, column=1, sticky="w", padx=(0, 12), pady=3)

        ctk.CTkLabel(
            grid, text="Punto:", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_PRIMARY,
        ).grid(row=0, column=2, sticky="w", padx=(0, 4), pady=3)
        self.f_font_size = FieldRow(grid, "", "10", unit="pt", convert=False, width=54,
                                    minimum=1, maximum=72, on_change=self._on_number_changed)
        self.f_font_size.grid(row=0, column=3, sticky="w", pady=3)

        self.f_start_page = FieldRow(grid, "Başlangıç sayfası", "1", convert=False, width=54,
                                     minimum=1, maximum=100000, integer=True,
                                     suffix="", label_width=126, on_change=self._on_number_changed)
        self.f_start_page.grid(row=1, column=0, columnspan=2, sticky="w", pady=3)
        self.f_start_num = FieldRow(grid, "İlk numara", "1", convert=False, width=54,
                                    minimum=0, maximum=100000, integer=True,
                                    suffix="", label_width=126, on_change=self._on_number_changed)
        self.f_start_num.grid(row=1, column=2, columnspan=2, sticky="w", pady=3)

        self.f_num_bottom = FieldRow(grid, "Tabandan uzaklık", "12", width=60, minimum=0, maximum=5000, label_width=126,
                                     on_change=self._on_number_changed)
        self.f_num_bottom.grid(row=2, column=0, columnspan=2, sticky="w", pady=3)
        self.f_num_side = FieldRow(grid, "Yan boşluk", "15", width=60, minimum=0, maximum=5000, label_width=126,
                                   on_change=self._on_number_changed)
        self.f_num_side.grid(row=2, column=2, columnspan=2, sticky="w", pady=3)

        self.lbl_side_hint = ctk.CTkLabel(
            grid, text="", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w",
        )
        self.lbl_side_hint.grid(row=3, column=2, columnspan=2, sticky="w")

        template_row = ctk.CTkFrame(card, fg_color="transparent")
        template_row.grid(row=3, column=0, sticky="ew", padx=10, pady=(3, 3))
        ctk.CTkLabel(
            template_row, text="Özel metin:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(side="left", padx=(0, 8))
        self.entry_number_template = ctk.CTkEntry(
            template_row, placeholder_text="Örn: {n} / {N}  •  {roman}  •  Sayfa {n}",
            height=32, font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY),
            fg_color=COLOR_CARD, border_color=COLOR_BORDER, text_color=COLOR_TEXT_PRIMARY,
        )
        self.entry_number_template.pack(side="left", fill="x", expand=True)
        self.entry_number_template.bind("<KeyRelease>", lambda e: self._on_number_changed())
        ctk.CTkLabel(
            card,
            text="Boş bırakılırsa biçim kullanılır. Değişkenler: {n} numara, {N} toplam, "
                 "{roman}/{ROMAN}, {label}. Türkçe karakterler için Unicode yazı tipi otomatik gömülür.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=600,
        ).grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 3))
        self._bind_wraplength(card.winfo_children()[-1], card, 24)

        skip_row = ctk.CTkFrame(card, fg_color="transparent")
        skip_row.grid(row=5, column=0, sticky="ew", padx=10, pady=(5, 3))
        ctk.CTkLabel(
            skip_row, text="Numarasız sayfalar:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(side="left", padx=(0, 8))
        self.entry_skip_pages = ctk.CTkEntry(
            skip_row, placeholder_text="Örn: 1, 2, 15, 24-26", height=32,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY),
            fg_color=COLOR_CARD, border_color=COLOR_BORDER, text_color=COLOR_TEXT_PRIMARY,
        )
        self.entry_skip_pages.pack(side="left", fill="x", expand=True)
        self.entry_skip_pages.bind("<KeyRelease>", lambda e: self._on_number_changed())

        self.chk_continuous = ctk.CTkCheckBox(
            card,
            text="Kapak sayfalarında numarayı dondur (ardışık: 90 → kapak → 91)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_PRIMARY, hover_color=COLOR_ACCENT_HOVER,
            fg_color=COLOR_ACCENT, command=self._on_number_changed,
        )
        self.chk_continuous.select()
        self.chk_continuous.grid(row=6, column=0, sticky="w", padx=10, pady=(3, 8))

        ctk.CTkFrame(container, fg_color="transparent", height=12).grid(row=2, column=0, sticky="ew")

        self._toggle_pnum_fields()

    def _toggle_pnum_fields(self) -> None:
        active = self.switch_pnum.get() == 1
        if active:
            self.lbl_pnum_status.configure(
                text="Etkin: sayfa numaraları belgeye eklenecek", text_color=COLOR_OK)
        else:
            self.lbl_pnum_status.configure(
                text="Devre dışı: üstteki 'Sayfa numarası' onay kutusundan açın",
                text_color=COLOR_TEXT_SECONDARY)
        self._update_all_modules_button()
        self._on_field_changed()

    # =====================================================================
    # SEKME 4: PDF Birleştirme
    # =====================================================================
    def _build_tab_merge(self) -> None:
        container = ctk.CTkFrame(self.tab_merge, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=6, pady=4)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(2, weight=1)

        top = WrapButtonRow(container)
        top.grid(row=0, column=0, sticky="ew", pady=(2, 4))
        top.add_button("+ Dosya ekle...", self._add_merge_files, width=110, bold=True)
        top.add_button("90° sola", self._rotate_selected_left)
        top.add_button("90° sağa", self._rotate_selected_right)
        top.add_button("Tümünü döndür", lambda: self._rotate_all(90), width=110)
        top.add_button("Yukarı", self._move_merge_file_up, width=70)
        top.add_button("Aşağı", self._move_merge_file_down, width=70)
        top.add_button("Kaldır", self._remove_merge_file, width=64)
        top.add_button("Temizle", self._clear_merge_files, width=70)

        hint = ctk.CTkLabel(
            container, text="Satırları sürükleyerek sıralayın. Sıralama ve rotasyonlar birleştirmeye aynen uygulanır. "
                            "Kısayollar: Del (kaldır), Alt+↑/↓ (sırala).",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=560,
        )
        hint.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        self._bind_wraplength(hint, container, 24)

        self.merge_list_frame = ctk.CTkScrollableFrame(
            container, fg_color=COLOR_SUBCARD, border_width=1,
            border_color=COLOR_BORDER, corner_radius=6,
        )
        self.merge_list_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 6))
        self.merge_list_frame.grid_columnconfigure(0, weight=1)

        bot = ctk.CTkFrame(container, fg_color="transparent")
        bot.grid(row=3, column=0, sticky="ew")
        bot.grid_columnconfigure(0, weight=1)

        self.merge_summary_badge = ctk.CTkLabel(
            bot, text="Toplam: 0 dosya | 0 sayfa",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY, anchor="w",
        )
        self.merge_summary_badge.grid(row=0, column=0, sticky="w")

        self.chk_merge_apply_pipeline = ctk.CTkCheckBox(
            bot, text="Birleştirdikten sonra diğer sekmelerdeki aktif ayarları uygula",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, hover_color=COLOR_ACCENT_HOVER,
            fg_color=COLOR_ACCENT, command=self._update_pipeline_summary,
        )
        self.chk_merge_apply_pipeline.deselect()
        self.chk_merge_apply_pipeline.grid(row=1, column=0, sticky="w", pady=(3, 0))

        self.chk_merge_bookmarks = ctk.CTkCheckBox(
            bot, text="Her dosya için dosya adından yer imi ekle",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, hover_color=COLOR_ACCENT_HOVER,
            fg_color=COLOR_ACCENT,
        )
        self.chk_merge_bookmarks.select()
        self.chk_merge_bookmarks.grid(row=2, column=0, sticky="w", pady=(3, 0))

        self._refresh_merge_listbox()

    def _append_merge_file(self, path: str) -> None:
        if not path or not os.path.exists(path):
            return
        if any(os.path.normcase(item["path"]) == os.path.normcase(path) for item in self.merge_files):
            return
        try:
            info = get_pdf_info(path)
        except Exception as exc:
            messagebox.showwarning("Dosya eklenemedi", f"{os.path.basename(path)}\n\n{exc}")
            return
        self.merge_files.append({
            "path": path,
            "name": os.path.basename(path),
            "pages": info["page_count"],
            "size_mb": info["file_size_mb"],
            "rotation": 0,
            "page_range": "",
        })
        self.store.add_recent_file(path)

    def _add_merge_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Birleştirilecek PDF dosyalarını seçin",
            filetypes=[("PDF belgeleri", "*.pdf")],
        )
        for path in paths or ():
            self._append_merge_file(path)
        self._refresh_merge_listbox()

    def _rotate_selected(self, delta: int) -> None:
        if not self.merge_files:
            return
        index = self.selected_merge_idx
        if index is None or not (0 <= index < len(self.merge_files)):
            self._set_status("Döndürmek için listeden bir dosya seçin.", COLOR_WARN)
            return
        item = self.merge_files[index]
        item["rotation"] = (int(item.get("rotation", 0)) + delta) % 360
        self._refresh_merge_listbox()

    def _rotate_all(self, delta: int) -> None:
        if not self.merge_files:
            return
        for item in self.merge_files:
            item["rotation"] = (int(item.get("rotation", 0)) + delta) % 360
        self._refresh_merge_listbox()

    def _rotate_selected_left(self) -> None:
        self._rotate_selected(-90)

    def _rotate_selected_right(self) -> None:
        self._rotate_selected(90)

    def _move_merge_file_up(self) -> None:
        index = self.selected_merge_idx
        if index is not None and index > 0:
            self.merge_files[index - 1], self.merge_files[index] = (
                self.merge_files[index], self.merge_files[index - 1])
            self.selected_merge_idx = index - 1
            self._refresh_merge_listbox()

    def _move_merge_file_down(self) -> None:
        index = self.selected_merge_idx
        if index is not None and index < len(self.merge_files) - 1:
            self.merge_files[index + 1], self.merge_files[index] = (
                self.merge_files[index], self.merge_files[index + 1])
            self.selected_merge_idx = index + 1
            self._refresh_merge_listbox()

    def _remove_merge_file(self) -> None:
        index = self.selected_merge_idx
        if index is not None and 0 <= index < len(self.merge_files):
            self.merge_files.pop(index)
            self.selected_merge_idx = None
            self._refresh_merge_listbox()

    def _clear_merge_files(self) -> None:
        self.merge_files.clear()
        self.selected_merge_idx = None
        self._refresh_merge_listbox()

    def _select_merge_item(self, index: int) -> None:
        self.selected_merge_idx = index
        self._refresh_merge_selection()
        self._schedule_preview()

    def _refresh_merge_selection(self) -> None:
        for idx, row in enumerate(self._merge_rows):
            selected = idx == self.selected_merge_idx
            row.configure(fg_color=COLOR_SOLID if selected else COLOR_CARD,
                          border_color=COLOR_SOLID if selected else COLOR_BORDER)
            # Yalnızca sıra numarası ve dosya adı seçim rengine uyar; döndürme
            # rozeti kendi kontrastını korur (seçiliyken okunmaz hâle gelmesin).
            try:
                row._title_label.configure(
                    text_color=COLOR_ON_ACCENT if selected else COLOR_TEXT_PRIMARY)
            except Exception:
                pass
            try:
                row._number_label.configure(
                    text_color=COLOR_ON_ACCENT if selected else COLOR_TEXT_SECONDARY)
            except Exception:
                pass

    def _refresh_merge_listbox(self) -> None:
        for row in self._merge_rows:
            row.destroy()
        self._merge_rows.clear()

        if not self.merge_files:
            self.merge_summary_badge.configure(text="Toplam: 0 dosya | 0 sayfa",
                                               text_color=COLOR_TEXT_SECONDARY)
            ctk.CTkLabel(
                self.merge_list_frame,
                text="Liste boş. Dosya ekleyin veya PDF'leri bu sekmeye sürükleyin.",
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
                text_color=COLOR_TEXT_SECONDARY,
            ).grid(row=0, column=0, pady=18)
            return

        total_pages = sum(self._merge_item_count(item) for item in self.merge_files)
        total_size = sum(item["size_mb"] for item in self.merge_files)
        self.merge_summary_badge.configure(
            text=f"Toplam: {len(self.merge_files)} dosya | {total_pages} sayfa | ~{total_size:.1f} MB",
            text_color=COLOR_TEXT_PRIMARY,
        )

        for index, item in enumerate(self.merge_files):
            row = ctk.CTkFrame(self.merge_list_frame, fg_color=COLOR_CARD,
                               corner_radius=5, border_width=1, border_color=COLOR_BORDER)
            row.grid(row=index, column=0, sticky="ew", padx=4, pady=2)
            row.grid_columnconfigure(2, weight=1)

            handle = ctk.CTkLabel(
                row, text="⠿", width=18,
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
                text_color=COLOR_TEXT_SECONDARY, cursor="fleur",
            )
            handle.grid(row=0, column=0, padx=(6, 0), pady=5)

            number = ctk.CTkLabel(
                row, text=f"{index + 1:>2}", width=26,
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
                text_color=COLOR_TEXT_SECONDARY,
            )
            number.grid(row=0, column=1, padx=(2, 2), pady=5)

            title = ctk.CTkLabel(
                row, text=f"{item['name']}  •  {item['pages']} sayfa  •  {item['size_mb']} MB",
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
                text_color=COLOR_TEXT_PRIMARY, anchor="w",
            )
            title.grid(row=0, column=2, sticky="ew", padx=4, pady=5)

            ctk.CTkLabel(
                row, text="Sayfa:", width=40,
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
                text_color=COLOR_TEXT_SECONDARY, anchor="e",
            ).grid(row=0, column=3, padx=(4, 2), pady=5)

            range_entry = ctk.CTkEntry(
                row, width=88, height=28, placeholder_text="Tümü",
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
                fg_color=COLOR_SUBCARD, border_color=COLOR_BORDER,
                text_color=COLOR_TEXT_PRIMARY,
            )
            range_entry.insert(0, item.get("page_range", ""))
            range_entry.grid(row=0, column=4, padx=4, pady=5)
            range_entry.bind(
                "<KeyRelease>",
                lambda event, current=item, entry=range_entry: self._on_merge_range_changed(current, entry),
            )

            rotation = int(item.get("rotation", 0))
            rotation_text = {0: "0° düz", 90: "90° sağa", 180: "180° ters", 270: "90° sola"}.get(
                rotation, f"{rotation}°")
            badge = ctk.CTkLabel(
                row, text=f" {rotation_text} ",
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY, weight="bold"),
                fg_color=COLOR_WARN_BG, text_color=COLOR_WARN, corner_radius=4,
            )
            badge.grid(row=0, column=5, padx=(4, 8), pady=5)

            row._number_label = number  # type: ignore[attr-defined]
            row._title_label = title  # type: ignore[attr-defined]
            self._bind_row_drag(row, index)
            self._merge_rows.append(row)

        self._refresh_merge_selection()
        self._schedule_preview()

    def _merge_item_count(self, item: Dict[str, Any]) -> int:
        total = int(item.get("pages", 0))
        text = str(item.get("page_range", "") or "").strip()
        if not text:
            return total
        selected = {page for page in parse_page_ranges(text) if 1 <= page <= total}
        return len(selected) if selected else total

    def _on_merge_range_changed(self, item: Dict[str, Any], entry: ctk.CTkEntry) -> None:
        item["page_range"] = entry.get().strip()
        total_pages = sum(self._merge_item_count(current) for current in self.merge_files)
        total_size = sum(current["size_mb"] for current in self.merge_files)
        self.merge_summary_badge.configure(
            text=f"Toplam: {len(self.merge_files)} dosya | {total_pages} sayfa | ~{total_size:.1f} MB",
            text_color=COLOR_TEXT_PRIMARY,
        )

    def _bind_row_drag(self, row: ctk.CTkFrame, index: int) -> None:
        widgets = [row] + [child for child in row.winfo_children()
                           if not isinstance(child, ctk.CTkEntry)]

        def on_press(_event, idx=index):
            self._drag_idx = idx
            self._select_merge_item(idx)

        def on_motion(event):
            if self._drag_idx is None:
                return
            target = self._merge_index_at(event.y_root)
            if target is not None and target != self._drag_idx:
                self._move_merge_item(self._drag_idx, target)

        def on_release(_event):
            self._drag_idx = None

        for widget in widgets:
            widget.bind("<Button-1>", on_press, add="+")
            widget.bind("<B1-Motion>", on_motion, add="+")
            widget.bind("<ButtonRelease-1>", on_release, add="+")

    def _move_merge_item(self, old_index: int, new_index: int) -> None:
        """Liste ve satır nesnelerini birlikte taşır; görsel sıra veriyle eşleşir."""
        if old_index == new_index or not (0 <= old_index < len(self.merge_files)):
            return
        new_index = max(0, min(new_index, len(self.merge_files) - 1))
        item = self.merge_files.pop(old_index)
        self.merge_files.insert(new_index, item)
        if 0 <= old_index < len(self._merge_rows):
            row = self._merge_rows.pop(old_index)
            self._merge_rows.insert(new_index, row)
        self._drag_idx = new_index
        self.selected_merge_idx = new_index
        self._reorder_merge_rows()

    def _merge_index_at(self, y_root: int) -> Optional[int]:
        for idx, row in enumerate(self._merge_rows):
            top = row.winfo_rooty()
            if top <= y_root <= top + row.winfo_height():
                return idx
        return None

    def _reorder_merge_rows(self) -> None:
        """Satırları yeniden oluşturmadan taşır: titremesiz sürükleme."""
        for idx, row in enumerate(self._merge_rows):
            row.grid_configure(row=idx)
            number = getattr(row, "_number_label", None)
            if number is not None:
                number.configure(text=f"{idx + 1:>2}")
        self._refresh_merge_selection()

    # =====================================================================
    # Canlı önizleme paneli
    # =====================================================================
    def _build_preview_panel(self, parent) -> None:
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=8,
                            border_width=1, border_color=COLOR_BORDER, width=380)
        card.grid(row=0, column=1, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            card, text="Canlı önizleme",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        subtitle = ctk.CTkLabel(
            card, text="İlk sayfa ve karşı sayfa; cilt şeridi, paylar ve numara konumu işaretli.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=300,
        )
        subtitle.grid(row=1, column=0, sticky="ew", padx=12)
        self._bind_wraplength(subtitle, card, 30)

        self.preview_mode_menu = ctk.CTkSegmentedButton(
            card, values=["Tek sayfa", "Çift sayfa"], height=30,
            border_width=0, fg_color=COLOR_SUBCARD, bg_color=COLOR_CARD,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_SUBCARD, unselected_hover_color=COLOR_BTN_SUBTLE_HOVER,
            text_color=COLOR_TEXT_PRIMARY, corner_radius=6,
            command=self._on_preview_mode_changed,
        )
        self.preview_mode_menu.set("Çift sayfa")
        self.preview_mode_menu.grid(row=2, column=0, sticky="ew", padx=12, pady=(5, 2))

        image_frame = ctk.CTkFrame(card, fg_color="transparent")
        image_frame.grid(row=3, column=0, sticky="nsew", padx=8, pady=(6, 3))
        self._preview_image_frame = image_frame
        image_frame.grid_columnconfigure(0, weight=1, uniform="preview")
        image_frame.grid_columnconfigure(1, weight=1, uniform="preview")
        image_frame.grid_rowconfigure(0, weight=1)
        self._preview_slots = []
        for column in (0, 1):
            slot = ctk.CTkFrame(image_frame, fg_color=COLOR_CARD, corner_radius=4,
                                border_width=1, border_color=COLOR_BORDER)
            slot.grid(row=0, column=column, padx=2)
            slot.grid_columnconfigure(0, weight=1)
            image_label = tk.Label(
                slot, text="", bd=0, highlightthickness=0,
                bg=self._apply_appearance_mode(COLOR_CARD),
            )
            image_label.grid(row=0, column=0, padx=3, pady=(3, 0))
            caption = ctk.CTkLabel(
                slot, text="—", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
                text_color=COLOR_TEXT_SECONDARY,
            )
            caption.grid(row=1, column=0, padx=3, pady=(0, 3))
            self._preview_slots.append((slot, image_label, caption))

        try:
            blank_small = Image.new("RGBA", (168, 240), (0, 0, 0, 0))
            blank_large = Image.new("RGBA", (260, 368), (0, 0, 0, 0))
            self._blank_images = {
                "spread": ImageTk.PhotoImage(blank_small),
                "single": ImageTk.PhotoImage(blank_large),
            }
        except Exception:
            self._blank_images = {}

        nav = ctk.CTkFrame(card, fg_color="transparent")
        nav.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 2))
        nav.grid_columnconfigure(1, weight=1)
        self.preview_prev_btn = ctk.CTkButton(
            nav, text="‹ Önceki", width=84, height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, command=self._preview_previous,
        )
        self.preview_prev_btn.grid(row=0, column=0, sticky="w")
        self.preview_page_label = ctk.CTkLabel(
            nav, text="—", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY,
        )
        self.preview_page_label.grid(row=0, column=1)
        self.preview_next_btn = ctk.CTkButton(
            nav, text="Sonraki ›", width=84, height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, command=self._preview_next,
        )
        self.preview_next_btn.grid(row=0, column=2, sticky="e")

        self.preview_info = ctk.CTkLabel(
            card, text="Belge seçildiğinde önizleme burada görünür.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=320,
        )
        self.preview_info.grid(row=5, column=0, sticky="new", padx=12, pady=(2, 4))
        self._bind_wraplength(self.preview_info, card, 36)

        self.preview_warning = ctk.CTkLabel(
            card, text="", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY, weight="bold"),
            text_color=COLOR_ERROR, anchor="w", justify="left", wraplength=320,
        )
        self.preview_warning.grid(row=6, column=0, sticky="ew", padx=12)
        self._bind_wraplength(self.preview_warning, card, 36)

        legend = ctk.CTkLabel(
            card, text="Mavi: cilt payı   •   Yeşil: alt/üst pay   •   Kırmızı çerçeve: kırpma riski",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=320,
        )
        legend.grid(row=7, column=0, sticky="ew", padx=12, pady=(2, 6))
        self._bind_wraplength(legend, card, 24)

        preview_buttons = ctk.CTkFrame(card, fg_color="transparent")
        preview_buttons.grid(row=8, column=0, sticky="ew", padx=8, pady=(0, 10))
        preview_buttons.grid_columnconfigure(0, weight=1)
        preview_buttons.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(
            preview_buttons, text="Önizlemeyi yenile", height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, corner_radius=6,
            command=self._refresh_preview_now,
        ).grid(row=0, column=0, sticky="ew", padx=(4, 3))
        ctk.CTkButton(
            preview_buttons, text="Kırpma riskini tara", height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, corner_radius=6,
            command=self._scan_for_clipping,
        ).grid(row=0, column=1, sticky="ew", padx=(3, 4))

        self._apply_preview_layout()
        self._update_preview_nav()

    # =====================================================================
    # Alt eylem çubuğu
    # =====================================================================
    def _build_action_bar(self) -> None:
        card = ctk.CTkFrame(self, fg_color=COLOR_CARD, corner_radius=8,
                            border_width=1, border_color=COLOR_BORDER)
        card.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=12, pady=(7, 2))
        head.grid_columnconfigure(0, weight=1)
        self.action_title_label = ctk.CTkLabel(
            head, text="İşlem durumu",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        )
        self.action_title_label.grid(row=0, column=0, sticky="w")

        self.pipeline_frame = ctk.CTkFrame(head, fg_color="transparent")
        self.pipeline_frame.grid(row=0, column=1, sticky="e")
        self.pill_gutter = self._make_pill("Cilt: kapalı")
        self.pill_margin = self._make_pill("Boşluk: kapalı")
        self.pill_pnum = self._make_pill("Sayfa no: kapalı")

        self.progress_bar = ctk.CTkProgressBar(card, height=4, progress_color=COLOR_ACCENT)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=12, pady=3)

        self.status_label = ctk.CTkLabel(
            card, text="Hazır. En az bir modülü etkinleştirin.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=780,
        )
        self.status_label.grid(row=2, column=0, sticky="ew", padx=12)
        self._bind_wraplength(self.status_label, card, 40)

        options = ctk.CTkFrame(card, fg_color="transparent")
        options.grid(row=3, column=0, sticky="ew", padx=12, pady=(4, 2))
        self.chk_optimize = ctk.CTkCheckBox(
            options, text="Dosyayı optimize et (daha küçük dosya, görünüm aynı)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, hover_color=COLOR_ACCENT_HOVER,
            fg_color=COLOR_ACCENT,
        )
        self.chk_optimize.pack(side="left", padx=(0, 14))
        self.chk_flatten = ctk.CTkCheckBox(
            options, text="Açıklamaları ve form alanlarını sayfaya göm",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, hover_color=COLOR_ACCENT_HOVER,
            fg_color=COLOR_ACCENT,
        )
        self.chk_flatten.select()
        self.chk_flatten.pack(side="left")

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.grid(row=4, column=0, sticky="ew", padx=12, pady=(3, 9))
        for column in range(4):
            buttons.grid_columnconfigure(column, weight=1)

        self.btn_open_folder = ctk.CTkButton(
            buttons, text="Klasörde göster", height=36, state="disabled",
            fg_color=COLOR_BTN_SUBTLE, text_color=COLOR_TEXT_PRIMARY,
            hover_color=COLOR_BTN_SUBTLE_HOVER, command=self._open_output_folder,
        )
        self.btn_open_folder.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.btn_open_pdf = ctk.CTkButton(
            buttons, text="PDF'i aç", height=36, state="disabled",
            fg_color=COLOR_BTN_SUBTLE, text_color=COLOR_TEXT_PRIMARY,
            hover_color=COLOR_BTN_SUBTLE_HOVER, command=self._open_output_pdf,
        )
        self.btn_open_pdf.grid(row=0, column=1, sticky="ew", padx=4)
        self.btn_cancel = ctk.CTkButton(
            buttons, text="İptal", height=36, state="disabled",
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_SECONDARY,
            hover_color=COLOR_ERROR_BG, command=self._cancel_work,
        )
        self.btn_cancel.grid(row=0, column=2, sticky="ew", padx=4)
        self.btn_main_action = ctk.CTkButton(
            buttons, text="PDF'i işle ve kaydet", height=38,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY, weight="bold"),
            fg_color=COLOR_SOLID, hover_color=COLOR_SOLID_HOVER,
            text_color=COLOR_ON_ACCENT,
            command=self._start_processing,
        )
        self.btn_main_action.grid(row=0, column=3, sticky="ew", padx=(4, 0))

    def _make_pill(self, text: str) -> ctk.CTkLabel:
        pill = ctk.CTkLabel(
            self.pipeline_frame, text=f" {text} ",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY, weight="bold"),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_SECONDARY, corner_radius=4,
        )
        pill.pack(side="left", padx=2)
        return pill

    # =====================================================================
    # Yardımcılar: wraplength, birim, durum
    # =====================================================================
    def _bind_wraplength(self, label, container, padding: int) -> None:
        state = {"width": None, "job": None}

        def apply_width():
            if state["width"] is None:
                return
            try:
                label.configure(wraplength=state["width"])
            except Exception:
                pass

        def on_configure(event, pad=padding):
            width = max(120, event.width - pad)
            if state["width"] is not None and abs(state["width"] - width) < 4:
                return
            state["width"] = width
            if state["job"] is not None:
                try:
                    container.after_cancel(state["job"])
                except Exception:
                    pass
            state["job"] = container.after(80, apply_width)
        container.bind("<Configure>", on_configure, add="+")

    def _on_theme_changed(self, choice: str) -> None:
        mode = {"Açık": "Light", "Koyu": "Dark"}.get(choice, "System")
        ctk.set_appearance_mode(mode)
        self.store.theme = choice
        try:
            bg = self._apply_appearance_mode(COLOR_CARD)
            for _slot, image_label, _caption in self._preview_slots:
                image_label.configure(bg=bg)
        except Exception:
            pass

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
        code = self.unit if self.unit in DISPLAY_UNITS else "mm"
        self.unit_menu.set(UNITS[code][0])

    def _all_field_rows(self) -> List[FieldRow]:
        return [self.f_width, self.f_height, self.f_odd_x, self.f_odd_y,
                self.f_even_x, self.f_even_y, self.f_bottom, self.f_top,
                self.f_font_size, self.f_start_page, self.f_start_num,
                self.f_num_bottom, self.f_num_side]

    def _on_field_changed(self) -> None:
        self._update_pipeline_summary()
        self._schedule_preview()

    def _on_gutter_changed(self) -> None:
        if self.switch_gutter.get() != 1:
            self.switch_gutter.select()
            self._toggle_gutter_fields()
        else:
            self._on_field_changed()

    def _on_margin_changed(self) -> None:
        if self.switch_margin.get() != 1:
            has_pay = False
            for row in (self.f_bottom, self.f_top):
                try:
                    has_pay = has_pay or row.get_mm() > 0
                except FieldError:
                    continue
            if has_pay:
                self.switch_margin.select()
                self._toggle_margin_fields()
                return
        self._on_field_changed()

    def _on_number_changed(self) -> None:
        if self.switch_pnum.get() != 1:
            self.switch_pnum.select()
            self._toggle_pnum_fields()
        else:
            self._on_field_changed()

    def _on_number_position_changed(self) -> None:
        self._update_number_side_state()
        self._on_number_changed()

    def _update_number_side_state(self) -> None:
        """Alt orta konumunda yan boşluk kullanılmaz; alanı pasif gösterir."""
        if not hasattr(self, "seg_pos") or not hasattr(self, "f_num_side"):
            return
        center = POSITION_LABELS.get(self.seg_pos.get()) == "center"
        self.f_num_side.set_enabled(not center)
        self.f_num_side.label.configure(
            text_color=COLOR_TEXT_SECONDARY if center else COLOR_TEXT_PRIMARY)
        if hasattr(self, "lbl_side_hint"):
            self.lbl_side_hint.configure(
                text="Alt orta konumunda yan boşluk kullanılmaz." if center else "")

    def _set_status(self, text: str, color=COLOR_TEXT_SECONDARY) -> None:
        self.status_label.configure(text=text, text_color=color)

    # =====================================================================
    # Ayar okuma / yazma (tek kaynak)
    # =====================================================================
    def _row_mm(self, row: FieldRow) -> float:
        return row.get_mm()

    def _build_config(self, notify: bool = False) -> Optional[PdfProcessConfig]:
        """Arayüzdeki tüm alanlardan tek bir motor yapılandırması üretir."""
        groups = [
            ("gutter", self.switch_gutter.get() == 1,
             [("width", self.f_width), ("height", self.f_height),
              ("odd_x", self.f_odd_x), ("odd_y", self.f_odd_y),
              ("even_x", self.f_even_x), ("even_y", self.f_even_y)]),
            ("margin", self.switch_margin.get() == 1,
             [("bottom", self.f_bottom), ("top", self.f_top)]),
            ("number", self.switch_pnum.get() == 1,
             [("font_size", self.f_font_size), ("start_page", self.f_start_page),
              ("start_num", self.f_start_num), ("num_bottom", self.f_num_bottom),
              ("num_side", self.f_num_side)]),
        ]
        values: Dict[str, float] = {}
        errors: List[tuple] = []
        for _group, active, rows in groups:
            for key, row in rows:
                try:
                    values[key] = row.get_mm() if row.convert else row.get_value()
                    row.set_error("")
                except FieldError as exc:
                    if active:
                        row.set_error(exc.message)
                        errors.append((row, f"{row.label_text or 'Değer'}: {exc.message}"))
                    else:
                        values[key] = row._canonical_mm if row.convert else row.last_valid

        if errors:
            if notify:
                messagebox.showerror(
                    "Ayarlar geçersiz",
                    "Aşağıdaki alanları düzeltin:\n\n" +
                    "\n".join(f"• {message}" for _row, message in errors[:10]),
                )
            self._set_status(f"Ayar hatası: {errors[0][1]}", COLOR_ERROR)
            try:
                errors[0][0].entry.focus_set()
            except Exception:
                pass
            return None

        boxes = PageBoxSettings(
            enabled=self.switch_gutter.get() == 1,
            size_mode=SIZE_MODE_LABELS.get(self.seg_size_mode.get(), "fixed"),
            overflow_mode=OVERFLOW_LABELS.get(self.seg_overflow.get(), "clip"),
            target_width_mm=values["width"],
            target_height_mm=values["height"],
            odd_x_mm=values["odd_x"],
            odd_y_mm=values["odd_y"],
            even_x_mm=values["even_x"],
            even_y_mm=values["even_y"],
            exclude_pages_str=self.entry_exclude_pages.get().strip(),
        )
        margins = MarginSettings(
            enabled=self.switch_margin.get() == 1,
            extra_bottom_mm=values["bottom"],
            extra_top_mm=values["top"],
            bottom_mode=MODE_LABELS.get(self.seg_bottom_mode.get(), "expand"),
            exclude_pages_str=self.entry_exclude_margin.get().strip(),
        )
        numbers = PageNumberSettings(
            enabled=self.switch_pnum.get() == 1,
            position=POSITION_LABELS.get(self.seg_pos.get(), "outer"),
            format_style=FORMAT_LABELS.get(self.menu_format.get(), "number"),
            text_template=self.entry_number_template.get().strip(),
            start_num=int(values["start_num"]),
            start_page=int(values["start_page"]),
            font_size=values["font_size"],
            font_color=(0.08, 0.08, 0.08),
            bottom_margin_mm=values["num_bottom"],
            side_margin_mm=values["num_side"],
            skip_pages_str=self.entry_skip_pages.get().strip(),
            continuous_numbering=self.chk_continuous.get() == 1,
        )
        config = PdfProcessConfig(
            page_boxes=boxes,
            margins=margins,
            page_numbers=numbers,
            quality_mode="standard" if self.chk_optimize.get() == 1 else "print",
            flatten_annotations=self.chk_flatten.get() == 1,
            pad_to_multiple=4 if self.chk_pad4.get() == 1 else 0,
        )

        validation = validate_config(config)
        if not validation.ok:
            if notify:
                messagebox.showerror("Ayarlar geçersiz", "• " + "\n• ".join(validation.errors))
            self._set_status(f"Ayar hatası: {validation.errors[0]}", COLOR_ERROR)
            return None
        if validation.warnings:
            self._set_status("Uyarı: " + validation.warnings[0], COLOR_WARN)
        self._last_valid_config = config
        return config

    def _apply_config(self, config: PdfProcessConfig) -> None:
        boxes, margins, numbers = config.page_boxes, config.margins, config.page_numbers
        self.switch_gutter.select() if boxes.enabled else self.switch_gutter.deselect()
        self.switch_margin.select() if margins.enabled else self.switch_margin.deselect()
        self.switch_pnum.select() if numbers.enabled else self.switch_pnum.deselect()

        self.seg_size_mode.set(SIZE_MODE_CODES.get(boxes.size_mode, "Hedef ebat sabit"))
        self.seg_overflow.set(OVERFLOW_CODES.get(boxes.overflow_mode, "Kırp"))
        self.seg_bottom_mode.set(MODE_CODES.get(margins.bottom_mode, "Uzat (kırpmaz, önerilen)"))
        self.seg_pos.set(POSITION_CODES.get(numbers.position, "Dış kenar (Tek sağ / Çift sol)"))
        self.menu_format.set(FORMAT_CODES.get(numbers.format_style, "1, 2, 3"))

        self.f_width.set_mm(boxes.target_width_mm)
        self.f_height.set_mm(boxes.target_height_mm)
        self.f_odd_x.set_mm(boxes.odd_x_mm)
        self.f_odd_y.set_mm(boxes.odd_y_mm)
        self.f_even_x.set_mm(boxes.even_x_mm)
        self.f_even_y.set_mm(boxes.even_y_mm)
        self.f_bottom.set_mm(margins.extra_bottom_mm)
        self.f_top.set_mm(margins.extra_top_mm)
        self.f_font_size.set_value(f"{numbers.font_size:g}")
        self.f_start_page.set_value(str(numbers.start_page))
        self.f_start_num.set_value(str(numbers.start_num))
        self.f_num_bottom.set_mm(numbers.bottom_margin_mm)
        self.f_num_side.set_mm(numbers.side_margin_mm)
        self.entry_skip_pages.delete(0, "end")
        self.entry_skip_pages.insert(0, numbers.skip_pages_str)
        self.entry_number_template.delete(0, "end")
        self.entry_number_template.insert(0, numbers.text_template)
        self.entry_exclude_pages.delete(0, "end")
        self.entry_exclude_pages.insert(0, boxes.exclude_pages_str)
        self.entry_exclude_margin.delete(0, "end")
        self.entry_exclude_margin.insert(0, margins.exclude_pages_str)
        self.chk_continuous.select() if numbers.continuous_numbering else self.chk_continuous.deselect()

        self.chk_optimize.select() if config.optimize else self.chk_optimize.deselect()
        self.chk_flatten.select() if config.flatten_annotations else self.chk_flatten.deselect()
        self.chk_pad4.select() if config.pad_to_multiple == 4 else self.chk_pad4.deselect()

        self._toggle_gutter_fields()
        self._toggle_margin_fields()
        self._toggle_pnum_fields()
        self._on_margin_mode_changed()

    def _collect_state(self) -> Dict[str, Any]:
        config = self._build_config(notify=False) or self._last_valid_config
        state = config_to_dict(config) if config else {}
        state["unit"] = self.unit
        state["theme"] = self.store.theme
        state["apply_pipeline"] = self.chk_merge_apply_pipeline.get() == 1
        state["merge_bookmarks"] = self.chk_merge_bookmarks.get() == 1
        return state

    def _restore_settings(self) -> None:
        state = self.store.last_state
        self.theme_segmented.set(self.store.theme)
        ctk.set_appearance_mode({"Açık": "Light", "Koyu": "Dark"}.get(self.store.theme, "System"))

        if state:
            config = config_from_dict(state)
            self._apply_config(config)
            if state.get("apply_pipeline"):
                self.chk_merge_apply_pipeline.select()
            else:
                self.chk_merge_apply_pipeline.deselect()
            if state.get("merge_bookmarks", True):
                self.chk_merge_bookmarks.select()
            else:
                self.chk_merge_bookmarks.deselect()
        else:
            self._apply_config(PdfProcessConfig(
                page_boxes=PageBoxSettings(enabled=False, target_width_mm=210.0,
                                           target_height_mm=297.0, odd_x_mm=15.0),
                margins=MarginSettings(enabled=False),
                page_numbers=PageNumberSettings(enabled=False),
            ))
            self._apply_gutter_preset(15.0)
            self._reset_gutter_to_original()
            self._toggle_margin_fields()
            self._toggle_pnum_fields()
        self._update_unit_button()

    # =====================================================================
    # Profiller, kağıt şablonları, hazır cilt payları
    # =====================================================================
    def _refresh_profile_menu(self) -> None:
        names = self.store.profile_names()
        values = ["(profil seçin)"] + names
        self.profile_menu.configure(values=values)
        if self.profile_menu.get() not in values:
            self.profile_menu.set(values[0])

    def _load_profile(self) -> None:
        name = self.profile_menu.get()
        if name.startswith("("):
            messagebox.showinfo("Profil", "Önce kayıtlı bir profil seçin.")
            return
        data = self.store.get_profile(name)
        if not data:
            messagebox.showwarning("Profil", f"'{name}' profili bulunamadı.")
            return
        self._apply_config(config_from_dict(data))
        self._set_status(f"'{name}' profili yüklendi.", COLOR_TEXT_PRIMARY)

    def _save_profile(self) -> None:
        config = self._build_config(notify=True)
        if config is None:
            return
        dialog = ctk.CTkInputDialog(title="Profili kaydet", text="Profil adı:")
        name = (dialog.get_input() or "").strip()
        if not name:
            return
        try:
            self.store.save_profile(name, config)
        except Exception as exc:
            messagebox.showerror("Profil", f"Profil kaydedilemedi:\n{exc}")
            return
        self._refresh_profile_menu()
        self.profile_menu.set(name)
        self._set_status(f"'{name}' profili kaydedildi.", COLOR_OK)

    def _delete_profile(self) -> None:
        name = self.profile_menu.get()
        if name.startswith("("):
            return
        if not messagebox.askyesno("Profili sil", f"'{name}' profili silinsin mi?"):
            return
        self.store.delete_profile(name)
        self._refresh_profile_menu()

    def _apply_named_preset(self, name: str) -> None:
        data = PRESETS.get(name)
        if not data:
            return
        self._apply_config(config_from_dict(data))
        self._set_status(
            f"'{name}' öneri profili uygulandı; değerleri gerektiği gibi düzenleyebilirsiniz.",
            COLOR_TEXT_PRIMARY,
        )

    def _apply_paper_size(self) -> None:
        width, height = PAPER_SIZES.get(self.paper_menu.get(), PAPER_SIZES["A4 (210 × 297)"])
        if self.orientation_menu.get() == "Yatay":
            width, height = height, width
        self.seg_size_mode.set(SIZE_MODE_CODES["fixed"])
        self.f_width.set_mm(width)
        self.f_height.set_mm(height)
        self.switch_gutter.select()
        self._toggle_gutter_fields()
        self._set_status(f"Kağıt boyutu {width:g} × {height:g} mm olarak ayarlandı.", COLOR_TEXT_PRIMARY)

    def _apply_gutter_preset(self, gutter: float) -> None:
        self.switch_gutter.select()
        self.seg_size_mode.set(SIZE_MODE_CODES["fixed"])
        self.f_width.set_mm(self.orig_width_mm + gutter)
        self.f_height.set_mm(self.orig_height_mm)
        self.f_odd_x.set_mm(gutter)
        self.f_odd_y.set_mm(0.0)
        self.f_even_x.set_mm(0.0)
        self.f_even_y.set_mm(0.0)
        self._toggle_gutter_fields()

    def _reset_gutter_to_original(self) -> None:
        self.switch_gutter.deselect()
        self.f_width.set_mm(self.orig_width_mm)
        self.f_height.set_mm(self.orig_height_mm)
        for row in (self.f_odd_x, self.f_odd_y, self.f_even_x, self.f_even_y):
            row.set_mm(0.0)
        self._toggle_gutter_fields()

    def _set_bottom_margin(self, value: float) -> None:
        if value > 0:
            self.switch_margin.select()
        self.f_bottom.set_mm(value)
        self._toggle_margin_fields()

    def _set_top_margin(self, value: float) -> None:
        if value > 0:
            self.switch_margin.select()
        self.f_top.set_mm(value)
        self._toggle_margin_fields()

    def _margin_preset_label(self, mm: float) -> str:
        """Ön ayar düğmesi etiketi: değer seçili birimde yazılır (mm/cm/pt)."""
        return "+" + format_measure(mm, self.unit)

    def _update_margin_preset_labels(self) -> None:
        for row in getattr(self, "_margin_preset_rows", ()):
            for button, value in zip(row._buttons, MARGIN_PRESETS_MM):
                try:
                    button.configure(text=self._margin_preset_label(value))
                except Exception:
                    pass

    # =====================================================================
    # Belge yükleme
    # =====================================================================
    def _choose_file(self) -> None:
        path = filedialog.askopenfilename(
            title="İşlenecek PDF dosyasını seçin",
            filetypes=[("PDF belgeleri", "*.pdf")],
        )
        if path:
            self._load_file(path)

    def _load_from_entry(self) -> None:
        path = self.path_entry.get().strip().strip('"')
        if path:
            self._load_file(path)

    def _load_file(self, path: str) -> None:
        path = (path or "").strip().strip('"')
        if not path or not os.path.exists(path):
            self.info_badge.configure(text=f"Dosya bulunamadı: {path or '(boş)'}",
                                      text_color=COLOR_ERROR)
            return
        try:
            info = get_pdf_info(path)
        except Exception as exc:
            self.log.warning("PDF okunamadı: %s (%s)", path, exc)
            self.info_badge.configure(text=f"PDF okunamadı: {exc}", text_color=COLOR_ERROR)
            self._set_status(f"PDF okunamadı: {exc}", COLOR_ERROR)
            return

        self.input_pdf_path = path
        self.path_entry.delete(0, "end")
        self.path_entry.insert(0, path)
        self.orig_width_mm = info["width_mm"]
        self.orig_height_mm = info["height_mm"]
        self.orig_page_count = info["page_count"]
        self.store.add_recent_file(path)

        mixed = " • karışık ebatlı" if info.get("mixed_sizes") else ""
        self.info_badge.configure(
            text=(f"{os.path.basename(path)}  •  {info['width_mm']:.1f} × {info['height_mm']:.1f} mm  •  "
                  f"{info['page_count']} sayfa{mixed}  •  {info['file_size_mb']} MB"),
            text_color=COLOR_TEXT_PRIMARY,
        )
        if self.switch_gutter.get() == 1 and SIZE_MODE_LABELS.get(self.seg_size_mode.get()) == "fixed":
            # Yeni belgeye geçerken hedef ebat, kaynak + mevcut cilt payı olarak güncellenir.
            try:
                extra_x = max(self._row_mm(self.f_odd_x), self._row_mm(self.f_even_x), 0.0)
                extra_y = max(self._row_mm(self.f_odd_y), self._row_mm(self.f_even_y), 0.0)
                self.f_width.set_mm(self.orig_width_mm + extra_x)
                self.f_height.set_mm(self.orig_height_mm + extra_y)
            except Exception:
                pass
        else:
            self.f_width.set_mm(self.orig_width_mm)
            self.f_height.set_mm(self.orig_height_mm)
        self._set_status(f"'{os.path.basename(path)}' yüklendi.", COLOR_TEXT_PRIMARY)
        self.preview_page = 0
        self._preview_signature = None
        self._preview_gen += 1
        self._clear_preview("Önizleme hazırlanıyor...")
        self._update_preview_nav()
        self._update_pipeline_summary()
        self._schedule_preview()

    # =====================================================================
    # Önizleme ve tarama
    # =====================================================================
    def _schedule_preview(self) -> None:
        if self._preview_after is not None:
            try:
                self.after_cancel(self._preview_after)
            except Exception:
                pass
        self._preview_after = self.after(300, self._refresh_preview)

    def _preview_source_path(self) -> str:
        """Önizlenecek dosya: birleştirme sekmesinde seçili PDF, yoksa ana belge."""
        if "Birleştirme" in self.tabview.get():
            index = self.selected_merge_idx
            if index is not None and 0 <= index < len(self.merge_files):
                path = str(self.merge_files[index].get("path", "") or "")
                if path and os.path.exists(path):
                    return path
        return self.input_pdf_path

    def _refresh_preview_now(self) -> None:
        if self._preview_after is not None:
            try:
                self.after_cancel(self._preview_after)
            except Exception:
                pass
            self._preview_after = None
        path = self._preview_source_path()
        if not path or not os.path.exists(path):
            self._clear_preview("Belge seçildiğinde önizleme burada görünür.")
            return
        self._preview_signature = None
        self.preview_info.configure(text="Önizleme yenileniyor...", text_color=COLOR_TEXT_SECONDARY)
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        self._preview_after = None
        path = self._preview_source_path()
        if not path or not os.path.exists(path):
            self._preview_signature = None
            self._clear_preview("Belge seçildiğinde önizleme burada görünür.")
            return
        config = self._build_config(notify=False)
        if config is None:
            self.preview_info.configure(text="Önizleme için ayarları düzeltin.",
                                        text_color=COLOR_WARN)
            return
        try:
            stat = os.stat(path)
            stamp = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            stamp = (0, 0)
        signature = (os.path.abspath(path), stamp,
                     self.preview_mode, self.preview_page, repr(config_to_dict(config)))
        if signature == self._preview_signature and self._preview_images:
            return
        self._preview_signature = signature
        self._preview_gen += 1
        generation = self._preview_gen

        def worker():
            try:
                if self.preview_mode == "single":
                    wanted = (self.preview_page,)
                else:
                    wanted = (self.preview_page, self.preview_page + 1)
                pages = render_preview(path, config, pages=wanted, zoom=1.2)
            except Exception as exc:
                message = str(exc)
                self.log.warning("Önizleme üretilemedi: %s", message)
                self._ui(lambda message=message: self._show_preview(generation, [], message))
                return
            self._ui(lambda: self._show_preview(generation, pages, None))

        threading.Thread(target=worker, daemon=True).start()

    def _blank_preview_slot(self, image_label, caption) -> None:
        try:
            blank = self._blank_images.get(self.preview_mode)
            image_label.configure(image=blank if blank is not None else "", text="")
        except Exception:
            pass
        try:
            caption.configure(text="—")
        except Exception:
            pass

    def _detach_preview_images(self) -> None:
        """Etiketleri boş görüntüye alır; eski görüntüler oturum boyunca saklanır."""
        for _slot, image_label, caption in self._preview_slots:
            self._blank_preview_slot(image_label, caption)
        self._preview_images.clear()

    def _clear_preview(self, message: str) -> None:
        self._detach_preview_images()
        self.preview_info.configure(text=message, text_color=COLOR_TEXT_SECONDARY)
        self.preview_warning.configure(text="")

    def _show_preview(self, generation: int, pages, error: Optional[str]) -> None:
        if generation != self._preview_gen:
            return
        if error:
            self._preview_signature = None
            self._clear_preview(f"Önizleme üretilemedi: {error}")
            return
        if not pages:
            self._clear_preview("Önizleme için sayfa bulunamadı.")
            return

        self._detach_preview_images()
        count = min(len(pages), 2)
        max_width = 260 if self.preview_mode == "single" else 168
        for slot_index, (slot, image_label, caption) in enumerate(self._preview_slots):
            if slot_index >= count:
                continue
            page = pages[slot_index]
            try:
                image = Image.open(io.BytesIO(page.png))
                image.load()
            except Exception:
                continue
            ratio = page.height_pt / page.width_pt if page.width_pt else 1.414
            display_w = max_width
            display_h = max(60, min(380, round(max_width * ratio)))
            preview_image = image.resize((display_w, display_h), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(preview_image)
            self._preview_images.append(photo)
            self._preview_history.append(photo)
            if len(self._preview_history) > 40:
                del self._preview_history[:len(self._preview_history) - 40]
            image_label.configure(image=photo, text="")
            side = "Tek (sağ)" if page.is_odd else "Çift (sol)"
            caption.configure(text=f"{page.page_index + 1}. sayfa • {side}")

        first = pages[0]
        info = (f"{first.width_mm:.1f} × {first.height_mm:.1f} mm  •  ölçek %{first.scale * 100:.0f}")
        if first.number_text:
            info += f"  •  numara: {first.number_text}"
        self.preview_info.configure(text=info, text_color=COLOR_TEXT_PRIMARY)

        warnings = []
        for page in pages[:2]:
            if page.clipped:
                edges = ", ".join(
                    f"{name} {value:.1f} mm"
                    for name, value in zip(("sol", "sağ", "üst", "alt"), page.clip_mm)
                    if value > 0
                )
                warnings.append(f"Sayfa {page.page_index + 1}: {edges} taşıyor.")
        if warnings:
            self.preview_warning.configure(text="Kırpma riski - " + " ".join(warnings))
        else:
            self.preview_warning.configure(text="")
        self._update_preview_nav()

    def _on_preview_mode_changed(self, value: str) -> None:
        self.preview_mode = "single" if "Tek" in value else "spread"
        self._detach_preview_images()
        self._apply_preview_layout()
        self._preview_signature = None
        self._refresh_preview()
        self._update_preview_nav()

    def _apply_preview_layout(self) -> None:
        """Tek sayfa modunda ikinci slotu kaldırır, ilk önizlemeyi genişletir."""
        if not hasattr(self, "_preview_slots"):
            return
        single = self.preview_mode == "single"
        frame = self._preview_image_frame
        first_slot, first_label, _ = self._preview_slots[0]
        second_slot, second_label, _ = self._preview_slots[1]
        if single:
            frame.grid_columnconfigure(1, weight=0)
            first_slot.grid_configure(columnspan=2)
            second_slot.grid_remove()
        else:
            frame.grid_columnconfigure(1, weight=1)
            first_slot.grid_configure(columnspan=1)
            second_slot.grid()

    def _preview_step(self, delta: int) -> None:
        total = self.orig_page_count
        if total <= 0:
            return
        step = 1 if self.preview_mode == "single" else 2
        candidate = self.preview_page + delta * step
        candidate = max(0, min(candidate, total - 1))
        if candidate == self.preview_page:
            return
        self.preview_page = candidate
        self._preview_signature = None
        self._refresh_preview()
        self._update_preview_nav()

    def _preview_previous(self) -> None:
        self._preview_step(-1)

    def _preview_next(self) -> None:
        self._preview_step(1)

    def _update_preview_nav(self) -> None:
        if not hasattr(self, "preview_page_label"):
            return
        total = self.orig_page_count
        if total <= 0:
            self.preview_page_label.configure(text="—")
            self.preview_prev_btn.configure(state="disabled")
            self.preview_next_btn.configure(state="disabled")
            return
        self.preview_page = max(0, min(self.preview_page, total - 1))
        if self.preview_mode == "single":
            text = f"{self.preview_page + 1} / {total}"
            can_prev = self.preview_page > 0
            can_next = self.preview_page < total - 1
        else:
            end = min(self.preview_page + 1, total - 1)
            text = (f"{self.preview_page + 1} / {total}" if end == self.preview_page
                    else f"{self.preview_page + 1}–{end + 1} / {total}")
            can_prev = self.preview_page > 0
            can_next = self.preview_page + 2 < total
        self.preview_page_label.configure(text=text)
        self.preview_prev_btn.configure(state="normal" if can_prev else "disabled")
        self.preview_next_btn.configure(state="normal" if can_next else "disabled")

    def _scan_for_clipping(self) -> None:
        if not self.input_pdf_path or not os.path.exists(self.input_pdf_path):
            messagebox.showwarning("Tarama", "Önce bir PDF dosyası seçin.")
            return
        if self._busy:
            return
        config = self._build_config(notify=True)
        if config is None:
            return
        path = self.input_pdf_path
        self._set_status("Kırpma riski taranıyor...", COLOR_ACCENT)
        self.progress_bar.set(0)

        def report_progress(cur: int, total: int) -> None:
            self._ui( lambda: self._update_progress(cur, total, "taranıyor"))

        def worker():
            try:
                report = scan_clipping(path, config, progress_callback=report_progress)
            except Exception as exc:
                details = traceback.format_exc()
                message = str(exc)
                self.log.exception("Kırpma taraması başarısız")
                self._ui(lambda message=message, details=details:
                         self._on_error("Kırpma taraması", message, details))
                return
            self._ui( lambda: self._show_scan_report(report))

        threading.Thread(target=worker, daemon=True).start()

    def _show_scan_report(self, report) -> None:
        self.progress_bar.set(0)
        self._set_status(report.summary(3).replace("\n", " "), 
                         COLOR_WARN if report.has_issues else COLOR_OK)
        body = report.summary(limit=50)
        if report.blank_pages:
            body += f"\n\nBoş sayfa: {report.blank_pages}"
        self._show_text_dialog(
            "Kırpma riski taraması",
            "Kırpma riski var" if report.has_issues else "Kırpma riski yok",
            body,
            severity="error" if report.has_issues else "ok",
        )

    # =====================================================================
    # İşleme ve birleştirme
    # =====================================================================
    def _suggest_output_path(self, tags: List[str]) -> str:
        directory, filename = os.path.split(self.input_pdf_path)
        name, extension = os.path.splitext(filename)
        suffix = "_" + "_".join(tags) if tags else "_islenmis"
        return unique_output_path(os.path.join(directory, f"{name}{suffix}{extension or '.pdf'}"))

    def _start_processing(self) -> None:
        if self._busy:
            return
        if not self.input_pdf_path or not os.path.exists(self.input_pdf_path):
            messagebox.showwarning("Uyarı", "Lütfen önce geçerli bir PDF dosyası seçin.")
            return
        if not (self.switch_gutter.get() or self.switch_margin.get() or self.switch_pnum.get()):
            messagebox.showwarning(
                "Uyarı", "En az bir modülü (cilt payı, boşluk veya sayfa numarası) etkinleştirin.")
            return

        config = self._build_config(notify=True)
        if config is None:
            return

        tags = []
        if config.page_boxes.enabled:
            tags.append("cilt_payli")
        if config.margins.enabled:
            tags.append("bosluklu")
        if config.page_numbers.enabled:
            tags.append("numarali")
        default_path = self._suggest_output_path(tags)
        output_path = filedialog.asksaveasfilename(
            title="İşlenmiş PDF'i kaydet",
            initialdir=os.path.dirname(default_path),
            initialfile=os.path.basename(default_path),
            defaultextension=".pdf",
            filetypes=[("PDF belgeleri", "*.pdf")],
        )
        if not output_path:
            return
        output_path = unique_output_path(output_path)
        if os.path.normcase(os.path.realpath(output_path)) == os.path.normcase(os.path.realpath(self.input_pdf_path)):
            messagebox.showerror("Hata", "Çıktı dosyası kaynakla aynı olamaz.")
            return

        self.output_pdf_path = output_path
        self._work_config = config
        self._work_paths = (self.input_pdf_path, output_path)
        self._begin_work("İşleniyor...")
        self._start_process_worker(scan_first=True)

    def _thread_progress(self, verb: str):
        """Arka plandan gelen ilerlemeyi Tk ana iş parçacığına güvenle taşır."""
        def callback(current: int, total: int) -> None:
            self._ui( lambda c=current, t=total: self._update_progress(c, t, verb))
        return callback

    def _start_process_worker(self, scan_first: bool) -> None:
        input_path, output_path = self._work_paths
        config = self._work_config
        self._cancel_event.clear()

        def worker():
            try:
                if scan_first:
                    self._set_phase("Kırpma riski taranıyor", 0.0)
                    report = scan_clipping(
                        input_path, config,
                        progress_callback=self._thread_progress("taranıyor"),
                        should_cancel=self._cancel_event.is_set,
                    )
                    if report.has_issues:
                        self._ui( lambda: self._confirm_clip_risk(report))
                        return

                self._set_phase("Sayfalar işleniyor", 0.0)
                process_pdf(
                    input_path, output_path, config,
                    progress_callback=self._thread_progress("işleniyor"),
                    should_cancel=self._cancel_event.is_set,
                )
                self._set_phase("Sonuç doğrulanıyor", 0.0)
                report = verify_output(
                    input_path, output_path, config,
                    progress_callback=self._thread_progress("doğrulanıyor"),
                    should_cancel=self._cancel_event.is_set,
                )
                self._ui( lambda: self._on_success(report, []))
            except ProcessCancelled:
                self._ui( self._on_cancelled)
            except Exception as exc:
                details = traceback.format_exc()
                message = str(exc)
                self.log.exception("İşleme hatası")
                self._ui(lambda message=message, details=details:
                         self._on_error("İşlem hatası", message, details))

        threading.Thread(target=worker, daemon=True).start()

    def _confirm_clip_risk(self, report) -> None:
        self._set_phase("Onay bekleniyor", 0.0)
        action = self._ask_clip_action(report)
        if action is None:
            self._end_work("İşlem iptal edildi. Çıktı oluşturulmadı.", COLOR_WARN)
            return
        if action == "shrink" and not self._switch_to_shrink():
            self._end_work("Kırpma önlenemedi. Ayarları kontrol edin.", COLOR_WARN)
            return
        self._begin_work("İşleniyor...")
        self._start_process_worker(scan_first=False)

    def _switch_to_shrink(self) -> bool:
        """Taşan içeriği kırpmak yerine küçültecek ayarı seçer; başarılıysa True."""
        if self.switch_gutter.get() == 1:
            self.seg_overflow.set(OVERFLOW_CODES["shrink"])
        elif self.switch_margin.get() == 1:
            self.seg_bottom_mode.set(MODE_CODES["fit"])
        else:
            return False
        self.update_idletasks()
        config = self._build_config(notify=False)
        if config is None:
            return False
        self._work_config = config
        return True

    def _ask_clip_action(self, report) -> Optional[str]:
        """Kırpma riskinde üç seçenek sunar: 'shrink', 'clip' veya None (iptal)."""
        result = {"value": None}
        dialog = ctk.CTkToplevel(self)
        dialog.title("Kırpma riski")
        dialog.geometry("600x400")
        dialog.minsize(480, 320)
        dialog.transient(self)
        dialog.grab_set()

        frame = ctk.CTkFrame(dialog, fg_color=COLOR_CARD, corner_radius=10)
        frame.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkLabel(
            frame, text="Kırpma riski",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SUBTITLE, weight="bold"),
            text_color=COLOR_WARN, anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 4))
        body = ctk.CTkTextbox(
            frame, fg_color=COLOR_SUBCARD, border_color=COLOR_BORDER, border_width=1,
            text_color=COLOR_TEXT_PRIMARY, font=ctk.CTkFont(family="Consolas", size=FS_SMALL),
            wrap="word",
        )
        body.pack(fill="both", expand=True, padx=12, pady=4)
        body.insert("1.0", report.summary(limit=10) + "\n\n"
                    "• Sayfaya sığdır: içerik küçültülür, hiçbir şey kırpılmaz.\n"
                    "• Kırp ve devam et: taşan kısım çıktıda görünmez.\n"
                    "• İptal: çıktı oluşturulmaz.")
        body.configure(state="disabled")

        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.pack(fill="x", padx=12, pady=(6, 10))

        def choose(value: Optional[str]) -> None:
            result["value"] = value
            dialog.destroy()

        ctk.CTkButton(
            buttons, text="Sayfaya sığdır (önerilen)", height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            fg_color=COLOR_SOLID, text_color=COLOR_ON_ACCENT,
            hover_color=COLOR_SOLID_HOVER, command=lambda: choose("shrink"),
        ).pack(side="left")
        ctk.CTkButton(
            buttons, text="Kırp ve devam et", height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, command=lambda: choose("clip"),
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            buttons, text="İptal", width=90, height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, command=lambda: choose(None),
        ).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", lambda: choose(None))
        self.wait_window(dialog)
        return result["value"]

    def _start_merging(self) -> None:
        if self._busy:
            return
        if len(self.merge_files) < 2:
            messagebox.showwarning("Uyarı", "Birleştirmek için en az 2 PDF ekleyin.")
            return

        apply_pipeline = self.chk_merge_apply_pipeline.get() == 1
        config = None
        if apply_pipeline:
            config = self._build_config(notify=True)
            if config is None:
                return
            if not (config.page_boxes.enabled or config.margins.enabled or config.page_numbers.enabled):
                messagebox.showwarning("Uyarı", "Birleşik hat için en az bir modülü etkinleştirin.")
                return

        first_dir = os.path.dirname(self.merge_files[0]["path"])
        default_path = unique_output_path(os.path.join(first_dir, "Birlestirilmis_Belge.pdf"))
        output_path = filedialog.asksaveasfilename(
            title="Birleştirilmiş PDF'i kaydet",
            initialdir=first_dir,
            initialfile=os.path.basename(default_path),
            defaultextension=".pdf",
            filetypes=[("PDF belgeleri", "*.pdf")],
        )
        if not output_path:
            return
        output_path = unique_output_path(output_path)

        self.output_pdf_path = output_path
        self._work_config = config
        self._work_paths = ("", output_path)
        self._begin_work("Birleştiriliyor...")
        self._start_merge_worker(scan_first=True)

    def _start_merge_worker(self, scan_first: bool) -> None:
        output_path = self._work_paths[1]
        config = self._work_config
        apply_pipeline = config is not None
        items = [{
            "path": item["path"],
            "rotation": int(item.get("rotation", 0)),
            "pages": str(item.get("page_range", "") or ""),
        } for item in self.merge_files]
        optimize = self.chk_optimize.get() == 1
        add_bookmarks = self.chk_merge_bookmarks.get() == 1
        expected_pages = sum(self._merge_item_count(item) for item in self.merge_files
                             if os.path.exists(item.get("path", "")))
        self._cancel_event.clear()

        def worker():
            warnings: List[str] = []
            temp_path = ""
            try:
                if not apply_pipeline:
                    self._set_phase("Dosyalar birleştiriliyor", 0.0)
                    merge_pdfs(
                        items, output_path,
                        progress_callback=self._thread_progress("birleştiriliyor"),
                        quality_mode="standard" if optimize else "print",
                        should_cancel=self._cancel_event.is_set,
                        warnings=warnings,
                        add_bookmarks=add_bookmarks,
                    )
                    info = get_pdf_info(output_path)
                    lines = []
                    if info["page_count"] == expected_pages:
                        lines.append(f"✔ {info['page_count']} sayfa birleştirildi")
                    else:
                        lines.append(f"✘ Beklenen {expected_pages} sayfa, çıktı {info['page_count']} sayfa")
                    lines.extend("• " + w for w in warnings)
                    self._ui( lambda: self._on_success(None, lines))
                    return

                fd, temp_path = tempfile.mkstemp(
                    prefix=".~merge-", suffix=".pdf.tmp",
                    dir=os.path.dirname(os.path.abspath(output_path)))
                os.close(fd)
                self._set_phase("Dosyalar birleştiriliyor", 0.0)
                merge_pdfs(
                    items, temp_path,
                    progress_callback=self._thread_progress("birleştiriliyor"),
                    quality_mode="print",
                    should_cancel=self._cancel_event.is_set,
                    warnings=warnings,
                    add_bookmarks=add_bookmarks,
                )

                if scan_first:
                    self._set_phase("Kırpma riski taranıyor", 0.0)
                    report = scan_clipping(
                        temp_path, config,
                        progress_callback=self._thread_progress("taranıyor"),
                        should_cancel=self._cancel_event.is_set,
                    )
                    if report.has_issues:
                        self._ui( lambda: self._confirm_merge_clip(report))
                        return

                self._set_phase("Aktif ayarlar uygulanıyor", 0.0)
                process_pdf(
                    temp_path, output_path, config,
                    progress_callback=self._thread_progress("işleniyor"),
                    should_cancel=self._cancel_event.is_set,
                )
                self._set_phase("Sonuç doğrulanıyor", 0.0)
                report = verify_output(
                    temp_path, output_path, config,
                    progress_callback=self._thread_progress("doğrulanıyor"),
                    should_cancel=self._cancel_event.is_set,
                )
                self._ui( lambda: self._on_success(report, warnings))
            except ProcessCancelled:
                self._ui( self._on_cancelled)
            except Exception as exc:
                details = traceback.format_exc()
                message = str(exc)
                self.log.exception("Birleştirme hatası")
                self._ui(lambda message=message, details=details:
                         self._on_error("Birleştirme hatası", message, details))
            finally:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass

        threading.Thread(target=worker, daemon=True).start()

    def _confirm_merge_clip(self, report) -> None:
        self._set_phase("Onay bekleniyor", 0.0)
        action = self._ask_clip_action(report)
        if action is None:
            self._end_work("Birleştirme iptal edildi. Çıktı oluşturulmadı.", COLOR_WARN)
            return
        if action == "shrink" and not self._switch_to_shrink():
            self._end_work("Kırpma önlenemedi. Ayarları kontrol edin.", COLOR_WARN)
            return
        self._begin_work("Birleştiriliyor...")
        self._start_merge_worker(scan_first=False)

    def _begin_work(self, message: str) -> None:
        self._busy = True
        self._cancel_event.clear()
        self._preview_gen += 1
        self.btn_main_action.configure(state="disabled", text="İşleniyor...")
        self.btn_cancel.configure(state="normal", fg_color=COLOR_ERROR_BG,
                                  text_color=COLOR_ERROR)
        self.btn_open_pdf.configure(state="disabled")
        self.btn_open_folder.configure(state="disabled")
        self.progress_bar.set(0)
        self._set_status(message, COLOR_ACCENT)

    def _reset_cancel_button(self) -> None:
        self.btn_cancel.configure(state="disabled", fg_color=COLOR_SUBCARD,
                                  text_color=COLOR_TEXT_SECONDARY)

    def _end_work(self, message: str, color=COLOR_TEXT_PRIMARY) -> None:
        self._busy = False
        self.progress_bar.set(0)
        self._reset_cancel_button()
        self._update_pipeline_summary()
        self._set_status(message, color)

    def _set_phase(self, message: str, progress: float) -> None:
        self._ui( lambda: self._set_status(message + "...", COLOR_ACCENT))
        self._ui( lambda: self.progress_bar.set(progress))

    def _update_progress(self, current: int, total: int, verb: str = "işleniyor") -> None:
        progress = current / total if total else 0.0
        self.progress_bar.set(progress)
        self._set_status(f"{verb.capitalize()}: {current} / {total} sayfa (%{int(progress * 100)})",
                         COLOR_ACCENT)

    def _cancel_work(self) -> None:
        if not self._busy:
            return
        self._cancel_event.set()
        self.btn_cancel.configure(state="disabled")
        self._set_status("İptal isteniyor...", COLOR_WARN)

    def _on_cancelled(self) -> None:
        self._end_work("İptal edildi. Çıktı dosyası oluşturulmadı.", COLOR_WARN)

    def _on_success(self, report, warnings: List[str]) -> None:
        self._busy = False
        self.progress_bar.set(1.0)
        self._reset_cancel_button()
        self.btn_open_pdf.configure(state="normal")
        self.btn_open_folder.configure(state="normal")
        self._update_pipeline_summary()
        self._schedule_preview()

        lines = report.lines() if report is not None else []
        lines.extend("• " + warning for warning in warnings)
        ok = report.ok if report is not None else True
        self._set_status(
            f"Tamamlandı: {os.path.basename(self.output_pdf_path)}",
            COLOR_OK if ok else COLOR_WARN,
        )
        self.log.info("Çıktı yazıldı: %s (doğrulama: %s)", self.output_pdf_path, ok)
        self.store.last_state = self._collect_state()
        self.store.save()

        body = f"{self.output_pdf_path}\n\n" + ("\n".join(lines) if lines else "")
        self._show_text_dialog(
            "İşlem tamamlandı",
            "PDF oluşturuldu" if ok else "PDF oluşturuldu, ancak doğrulama uyarı verdi",
            body,
            severity="ok" if ok else "warn",
        )

    def _on_error(self, title: str, exc: Exception, details: str = "") -> None:
        self._busy = False
        self.progress_bar.set(0)
        self._reset_cancel_button()
        self._update_pipeline_summary()
        message = str(exc)
        self._set_status(f"Hata: {message}", COLOR_ERROR)
        self.log.error("%s: %s", title, message)
        self._show_error_dialog(title, message, details or traceback.format_exc())

    # =====================================================================
    # Pencereler: bilgi, hata, hakkında
    # =====================================================================
    def _show_text_dialog(self, title: str, heading: str, body: str,
                          severity: str = "ok") -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.geometry("620x480")
        dialog.minsize(460, 320)
        dialog.transient(self)
        dialog.grab_set()

        frame = ctk.CTkFrame(dialog, fg_color=COLOR_CARD, corner_radius=10)
        frame.pack(fill="both", expand=True, padx=14, pady=14)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)

        color = {"ok": COLOR_OK, "warn": COLOR_WARN, "error": COLOR_ERROR}.get(severity, COLOR_TEXT_PRIMARY)
        ctk.CTkLabel(
            frame, text=heading, font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SUBTITLE, weight="bold"),
            text_color=color, anchor="w", justify="left", wraplength=540,
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))

        textbox = ctk.CTkTextbox(
            frame, fg_color=COLOR_SUBCARD, border_color=COLOR_BORDER, border_width=1,
            text_color=COLOR_TEXT_PRIMARY, font=ctk.CTkFont(family="Consolas", size=FS_SMALL),
            wrap="word",
        )
        textbox.grid(row=1, column=0, rowspan=2, sticky="nsew", padx=12, pady=4)
        textbox.insert("1.0", body)
        textbox.configure(state="disabled")

        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.grid(row=3, column=0, sticky="ew", padx=12, pady=(4, 8))
        buttons.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            buttons, text="Panoya kopyala", width=140, height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER,
            command=lambda: self._copy_to_clipboard(body),
        ).grid(row=0, column=1, padx=(0, 6))
        ctk.CTkButton(
            buttons, text="Kapat", width=100, height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            fg_color=COLOR_SOLID, text_color=COLOR_ON_ACCENT,
            hover_color=COLOR_SOLID_HOVER, command=dialog.destroy,
        ).grid(row=0, column=2)

    def _show_error_dialog(self, title: str, message: str, details: str) -> None:
        self._show_text_dialog(
            title, message, details + "\n\nGünlük dosyası: " + str(LOG_PATH),
            severity="error",
        )

    def _copy_to_clipboard(self, text: str) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update_idletasks()
        except Exception:
            pass

    def _show_about_dialog(self) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Hakkında - {APP_NAME}")
        dialog.geometry("860x700")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        frame = ctk.CTkFrame(dialog, fg_color=COLOR_CARD, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=16, pady=16)
        frame.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 10))
        header.grid_columnconfigure(1, weight=1)

        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.png")
        if os.path.exists(icon_path):
            try:
                image = Image.open(icon_path)
                self._about_icon = ctk.CTkImage(light_image=image, dark_image=image, size=(76, 76))
                ctk.CTkLabel(header, text="", image=self._about_icon).grid(
                    row=0, column=0, rowspan=2, padx=(0, 14))
            except Exception:
                pass

        ctk.CTkLabel(
            header, text=APP_NAME,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TITLE, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(
            header, text=f"Sürüm {VERSION}   •   baskı ve ciltleme hazırlık aracı",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, anchor="w",
        ).grid(row=1, column=1, sticky="w", pady=(2, 0))

        top_cards = ctk.CTkFrame(frame, fg_color="transparent")
        top_cards.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 8))
        top_cards.grid_columnconfigure(0, weight=1, uniform="about")
        top_cards.grid_columnconfigure(1, weight=1, uniform="about")

        dev = ctk.CTkFrame(top_cards, fg_color=COLOR_SUBCARD, corner_radius=8,
                           border_width=1, border_color=COLOR_BORDER)
        dev.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        ctk.CTkLabel(
            dev, text="Geliştirici",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_ACCENT, anchor="w",
        ).pack(anchor="w", padx=12, pady=(8, 2))
        ctk.CTkLabel(
            dev, text=f"{AUTHOR}\n{CONTACT}",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_PRIMARY, justify="left", anchor="w",
        ).pack(anchor="w", padx=12, pady=(0, 9))

        tech = ctk.CTkFrame(top_cards, fg_color=COLOR_SUBCARD, corner_radius=8,
                            border_width=1, border_color=COLOR_BORDER)
        tech.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        ctk.CTkLabel(
            tech, text="Altyapı",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_ACCENT, anchor="w",
        ).pack(anchor="w", padx=12, pady=(8, 2))
        ctk.CTkLabel(
            tech, text=f"Sürüm {VERSION}\nPython {sys.version.split()[0]} • PyMuPDF vektörel motor",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_PRIMARY, justify="left", anchor="w",
        ).pack(anchor="w", padx=12, pady=(0, 9))

        features = ctk.CTkFrame(frame, fg_color=COLOR_SUBCARD, corner_radius=8,
                                border_width=1, border_color=COLOR_BORDER)
        features.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 8))
        ctk.CTkLabel(
            features, text="Öne çıkanlar",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).pack(anchor="w", padx=14, pady=(8, 2))
        ctk.CTkLabel(
            features,
            text=("Tek ve çift sayfa için ayrı cilt payı; Uzat / Sığdır / Kaydır alt pay modları\n"
                  "Kırpma yerine sayfaya sığdırma; döndürülmüş ve kırpılmış sayfalar korunur\n"
                  "Kırpma riski taraması, canlı önizleme ve sonuç doğrulama raporu\n"
                  "Bağımsız sayfa dışlama listeleri, profiller, mm / cm / pt birimleri\n"
                  "Kayıpsız birleştirme, rotasyon, sürükle-bırak, yer imi ve bağlantı koruması"),
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, justify="left", anchor="w", wraplength=640,
        ).pack(anchor="w", padx=14, pady=(0, 9))

        shortcuts = ctk.CTkFrame(frame, fg_color=COLOR_SUBCARD, corner_radius=8,
                                 border_width=1, border_color=COLOR_BORDER)
        shortcuts.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 8))
        ctk.CTkLabel(
            shortcuts, text="Kısayollar",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).pack(anchor="w", padx=14, pady=(8, 4))
        grid = ctk.CTkFrame(shortcuts, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=(0, 8))
        for index, (key, action) in enumerate((
                ("Ctrl+O", "PDF aç"), ("Ctrl+S", "İşlemi başlat"),
                ("Enter", "İşlemi başlat"), ("Esc", "Çalışan işlemi iptal et"))):
            ctk.CTkLabel(
                grid, text=key, width=70, height=24,
                font=ctk.CTkFont(family="Consolas", size=FS_TINY, weight="bold"),
                fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY, corner_radius=4,
            ).grid(row=index // 2, column=(index % 2) * 2, sticky="w", padx=(0, 8), pady=2)
            ctk.CTkLabel(
                grid, text=action,
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
                text_color=COLOR_TEXT_SECONDARY,
            ).grid(row=index // 2, column=(index % 2) * 2 + 1, sticky="w", padx=(0, 26), pady=2)

        paths = ctk.CTkFrame(frame, fg_color=COLOR_SUBCARD, corner_radius=8,
                             border_width=1, border_color=COLOR_BORDER)
        paths.grid(row=4, column=0, sticky="ew", padx=18, pady=(0, 10))
        paths.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            paths, text="Dosyalar",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=14, pady=(8, 2))
        ctk.CTkLabel(
            paths, text=f"Ayarlar: {self.store.path}\nGünlük: {LOG_PATH}",
            font=ctk.CTkFont(family="Consolas", size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, justify="left", anchor="w", wraplength=500,
        ).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 8))

        ctk.CTkButton(
            paths, text="Ayarlar klasörü", width=110, height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER, hover_color=COLOR_BTN_SUBTLE_HOVER,
            command=lambda: self._open_about_path(self.store.path.parent, True),
        ).grid(row=1, column=1, padx=(6, 4), pady=(0, 8))
        ctk.CTkButton(
            paths, text="Günlüğü aç", width=96, height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER, hover_color=COLOR_BTN_SUBTLE_HOVER,
            command=lambda: self._open_about_path(LOG_PATH, False),
        ).grid(row=1, column=2, padx=(0, 14), pady=(0, 8))

        ctk.CTkButton(
            frame, text="Kapat", width=140, height=36,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            fg_color=COLOR_SOLID, text_color=COLOR_ON_ACCENT,
            hover_color=COLOR_SOLID_HOVER, command=dialog.destroy,
        ).grid(row=5, column=0, pady=(0, 10))

    def _open_about_path(self, path, folder: bool) -> None:
        try:
            target = str(path)
            if folder:
                os.makedirs(target, exist_ok=True)
            elif not os.path.exists(target):
                target = os.path.dirname(target) or "."
            os.startfile(target)
        except Exception as exc:
            messagebox.showerror("Hata", f"Dosya/klasör açılamadı: {exc}")

    # =====================================================================
    # Çıktı işlemleri
    # =====================================================================
    def _open_output_pdf(self) -> None:
        if self.output_pdf_path and os.path.exists(self.output_pdf_path):
            try:
                os.startfile(self.output_pdf_path)
            except Exception as exc:
                messagebox.showerror("Hata", f"PDF açılamadı: {exc}")

    def _open_output_folder(self) -> None:
        if self.output_pdf_path and os.path.exists(self.output_pdf_path):
            try:
                os.startfile(os.path.dirname(os.path.abspath(self.output_pdf_path)))
            except Exception as exc:
                messagebox.showerror("Hata", f"Klasör açılamadı: {exc}")

    # =====================================================================
    # Durum özeti
    # =====================================================================
    def _on_tab_changed(self) -> None:
        self._update_pipeline_summary()
        self._scroll_active_tab_to_top()
        # Birleştirme sekmesinde seçili dosya, diğer sekmelerde ana belge önizlenir.
        self._schedule_preview()

    def _scroll_active_tab_to_top(self) -> None:
        frame = self._tab_frames_map.get(self.current_tab)
        if frame is None:
            return
        for child in frame.winfo_children():
            if isinstance(child, ctk.CTkScrollableFrame):
                try:
                    child._parent_canvas.yview_moveto(0.0)
                except Exception:
                    pass

    def _update_pipeline_summary(self) -> None:
        if not hasattr(self, "pill_gutter") or not hasattr(self, "tabview"):
            return

        if "Birleştirme" in self.tabview.get():
            apply_pipeline = self.chk_merge_apply_pipeline.get() == 1
            if apply_pipeline:
                self.action_title_label.configure(text="Birleşik hat: birleştirme + aktif modüller")
                self._set_status("Dosyalar birleştirildikten sonra diğer sekmelerdeki ayarlar uygulanır.")
            else:
                self.action_title_label.configure(text="PDF birleştirme işlemi")
                self._set_status("Dosyalar sıraları ve rotasyonlarıyla kayıpsız birleştirilecek.")
            self.btn_main_action.configure(
                state="disabled" if self._busy else "normal",
                text="Birleştir ve aktif ayarları uygula" if apply_pipeline else "PDF'leri birleştir ve kaydet",
                command=self._start_merging,
            )
            return

        has_gutter = self.switch_gutter.get() == 1
        if has_gutter:
            try:
                gutter = self._row_mm(self.f_odd_x)
                self.pill_gutter.configure(text=f" Cilt: {gutter:.1f} mm ",
                                           fg_color=("#DDF4FF", "#0C2D4A"), text_color=COLOR_ACCENT)
            except Exception:
                self.pill_gutter.configure(text=" Cilt: açık ", fg_color=COLOR_SUBCARD,
                                           text_color=COLOR_TEXT_SECONDARY)
        else:
            self.pill_gutter.configure(text=" Cilt: kapalı ", fg_color=COLOR_SUBCARD,
                                       text_color=COLOR_TEXT_SECONDARY)

        has_margin = self.switch_margin.get() == 1
        if has_margin:
            parts = []
            try:
                bottom = self._row_mm(self.f_bottom)
                top = self._row_mm(self.f_top)
                if bottom > 0:
                    parts.append(f"alt +{bottom:.0f}")
                if top > 0:
                    parts.append(f"üst +{top:.0f}")
            except Exception:
                pass
            self.pill_margin.configure(
                text=(" Boşluk: " + ", ".join(parts) + " mm ") if parts else " Boşluk: 0 mm ",
                fg_color=("#DDF4FF", "#0C2D4A"), text_color=COLOR_ACCENT,
            )
        else:
            self.pill_margin.configure(text=" Boşluk: kapalı ", fg_color=COLOR_SUBCARD,
                                       text_color=COLOR_TEXT_SECONDARY)

        has_pnum = self.switch_pnum.get() == 1
        self.pill_pnum.configure(
            text=" Sayfa no: açık " if has_pnum else " Sayfa no: kapalı ",
            fg_color=COLOR_OK_BG if has_pnum else COLOR_SUBCARD,
            text_color=COLOR_OK if has_pnum else COLOR_TEXT_SECONDARY,
        )

        active_count = sum([has_gutter, has_margin, has_pnum])
        if active_count >= 2:
            self.action_title_label.configure(text="Birleşik işlem hattı")
            self._set_status("Tüm aktif modüller tek bir kayıpsız geçişte uygulanacak.")
            text = "Tüm aktif ayarlarla PDF oluştur"
        elif has_gutter:
            self.action_title_label.configure(text="Cilt payı işlemi")
            self._set_status("Yalnızca cilt payı uygulanacak.")
            text = "Cilt paylı PDF oluştur"
        elif has_margin:
            self.action_title_label.configure(text="Kenar boşluğu işlemi")
            self._set_status("Yalnızca alt/üst pay uygulanacak.")
            text = "Boşluklu PDF oluştur"
        elif has_pnum:
            self.action_title_label.configure(text="Sayfa numaralandırma işlemi")
            self._set_status("Sayfa boyutları korunarak yalnızca numara basılacak.")
            text = "Numaralandırılmış PDF oluştur"
        else:
            self.action_title_label.configure(text="İşlem durumu")
            self._set_status("Lütfen en az bir işlem modülünü etkinleştirin.")
            text = "En az bir modülü etkinleştirin"

        self.btn_main_action.configure(
            state="disabled" if (self._busy or active_count == 0) else "normal",
            text=text, command=self._start_processing,
        )

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
    app.mainloop()


if __name__ == "__main__":
    main()
