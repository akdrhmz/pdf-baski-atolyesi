"""İletişim kutuları ve Hakkında penceresi."""

from __future__ import annotations

import os
import sys
from typing import Optional

from PIL import Image

from ui import qt_compat as ctk
from ui.qt_compat import messagebox

HAS_WINDND = True

from settings_store import LOG_PATH
from gutter_engine import UNITS
from version import APP_NAME, AUTHOR, CONTACT, VERSION
from ui.paths import ASSETS_DIR
from ui.theme import *  # noqa: F401,F403


class DialogsMixin:
    """İletişim kutuları ve Hakkında penceresi."""

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
        dialog.geometry("720x600")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        frame = ctk.CTkFrame(dialog, fg_color=COLOR_CARD, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=16, pady=16)
        frame.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 10))
        header.grid_columnconfigure(1, weight=1)

        icon_path = os.path.join(ASSETS_DIR, "icon.png")
        if os.path.exists(icon_path):
            try:
                image = Image.open(icon_path)
                self._about_icon = ctk.CTkImage(light_image=image, dark_image=image, size=(60, 60))
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
        paths.set_padding(14, 8, 14, 10, spacing=4)
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
        ).grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))

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

    def _show_settings_dialog(self) -> None:
        """Ayarlar penceresi: tema, ölçü birimi, çıktı klasörü açma ve fabrika sıfırlama."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Ayarlar - {APP_NAME}")
        dialog.geometry("460x340")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        frame = ctk.CTkFrame(dialog, fg_color=COLOR_CARD, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=14, pady=14)
        frame.grid_columnconfigure(0, weight=1)

        def _section_title(row: int, text: str) -> None:
            ctk.CTkLabel(
                frame, text=text,
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
                text_color=COLOR_TEXT_SECONDARY, anchor="w",
            ).grid(row=row, column=0, sticky="w", padx=16, pady=(10, 2))

        # -- Tema -------------------------------------------------------------
        _section_title(0, "Tema")

        def _apply_theme(choice: str) -> None:
            try:
                self.theme_segmented.set(choice)
            except Exception:
                pass
            self._on_theme_changed(choice)

        theme_seg = ctk.CTkSegmentedButton(
            frame, values=["Açık", "Koyu", "Sistem"], height=28,
            border_width=0, fg_color=COLOR_SUBCARD, bg_color=COLOR_CARD,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_SUBCARD, unselected_hover_color=COLOR_BTN_SUBTLE_HOVER,
            text_color=COLOR_TEXT_PRIMARY, corner_radius=6,
            command=_apply_theme,
        )
        theme_seg.set(self.store.theme)
        theme_seg.grid(row=1, column=0, sticky="w", padx=16)

        # -- Ölçü birimi ------------------------------------------------------
        _section_title(2, "Ölçü birimi")

        def _apply_unit(label: str) -> None:
            self._on_unit_changed(label)
            try:
                self._update_unit_button()
            except Exception:
                pass

        unit_menu = ctk.CTkOptionMenu(
            frame, values=[UNITS[u][0] for u in DISPLAY_UNITS], width=150, height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            button_color=COLOR_SUBCARD, button_hover_color=COLOR_BTN_SUBTLE_HOVER,
            dropdown_fg_color=COLOR_CARD, dropdown_hover_color=COLOR_SELECTED,
            dropdown_text_color=COLOR_TEXT_PRIMARY,
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            command=_apply_unit,
        )
        unit_menu.set(UNITS[self.unit][0])
        unit_menu.grid(row=3, column=0, sticky="w", padx=16)

        # -- Çıktı klasörü ----------------------------------------------------
        chk_auto = ctk.CTkCheckBox(
            frame, text="İşlem bitince çıktı klasörünü otomatik aç",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_PRIMARY, hover_color=COLOR_ACCENT,
            fg_color=COLOR_SOLID,
        )
        if self.store.data.get("auto_open_output"):
            chk_auto.select()
        chk_auto.grid(row=5, column=0, sticky="w", padx=16, pady=(14, 2))

        def _toggle_auto() -> None:
            self.store.data["auto_open_output"] = bool(chk_auto.get())
            self.store.save()

        chk_auto.configure(command=_toggle_auto)

        # -- Fabrika sıfırlama + Kapat ---------------------------------------
        def _reset_to_factory() -> None:
            if not messagebox.askyesno(
                    "Fabrika ayarlarına dön",
                    "Tüm ayarlar fabrika değerlerine döner.\n"
                    "Profiller ve son durum da silinir. Devam edilsin mi?"):
                return
            self.store.reset()
            theme_seg.set(self.store.theme)
            unit_menu.set(UNITS[self.store.unit][0])
            chk_auto.deselect()
            try:
                self._on_unit_changed(UNITS["mm"][0])  # alanlar da yeni birime döner
                self._update_unit_button()
            except Exception:
                self.log.exception("Fabrika birimine geçilemedi")
            try:
                self.theme_segmented.set("Sistem")
                self._on_theme_changed("Sistem")
            except Exception:
                self.log.exception("Fabrika teması uygulanamadı")

        actions = ctk.CTkFrame(frame, fg_color="transparent")
        actions.grid(row=6, column=0, sticky="ew", padx=16, pady=(16, 14))
        actions.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(
            actions, text="Fabrika değerlerine sıfırla", width=170, height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_ERROR_BG, command=_reset_to_factory,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            actions, text="Kapat", width=110, height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            fg_color=COLOR_SOLID, text_color=COLOR_ON_ACCENT,
            hover_color=COLOR_SOLID_HOVER, command=dialog.destroy,
        ).grid(row=0, column=1, sticky="e")

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
