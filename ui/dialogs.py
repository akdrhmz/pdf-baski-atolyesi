"""İletişim kutuları ve Hakkında penceresi."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Optional

from PIL import Image

from ui import qt_compat as ctk
from ui.qt_compat import filedialog, messagebox

HAS_WINDND = True

from core.settings_store import LOG_PATH
import core.page_layout_model as plm
from core.gutter_engine import UNITS, config_from_dict, config_to_dict
from core.version import APP_NAME, AUTHOR, CONTACT, VERSION
from ui.paths import ASSETS_DIR
from ui.theme import *  # noqa: F401,F403


class DialogsMixin:
    """İletişim kutuları ve Hakkında penceresi."""

    def _show_pdf_tools(self):
        if self._busy:
            return
        from ui.pdf_tools import PdfToolsWindow
        self._pdf_tools_window = PdfToolsWindow(self)

    def _show_batch_dialog(self):
        if self._busy:
            return
        from ui.batch_dialog import BatchDialog
        self._batch_dialog = BatchDialog(self)

    def _ask_clip_action(self, report) -> Optional[str]:
        """Kırpma riskinde üç seçenek sunar: 'shrink', 'clip' veya None (iptal).

        Metin diyaloğuyla aynı iskeleti kullanır (``_text_dialog_shell``): aynı pencere
        başlığı, başlık rengi ve içeriğe göre boyutlanan metin kutusu (P2-35).
        """
        result = {"value": None}
        names = plm.CHOICE_NAMES
        body = (report.summary(limit=10) + "\n\n"
                f"• {names[plm.CHOICE_SHRINK]}: içerik küçültülür, hiçbir şey kırpılmaz.\n"
                f"• {names[plm.CHOICE_CLIP]}: taşan kısım çıktıda görünmez.\n"
                "• İptal: çıktı oluşturulmaz.")
        dialog, frame, _textbox = self._text_dialog_shell(
            CLIP_DIALOG_TITLE, "Kırpma riski var", body, severity="warn")
        buttons = self._dialog_button_row(frame)

        def choose(value: Optional[str]) -> None:
            result["value"] = value
            dialog.destroy()

        self._dialog_button(
            buttons, f"{names[plm.CHOICE_SHRINK]} (önerilen)", lambda: choose("shrink"),
            column=1, primary=True, width=190)
        self._dialog_button(
            buttons, names[plm.CHOICE_CLIP], lambda: choose("clip"), column=2, width=150)
        self._dialog_button(buttons, "İptal", lambda: choose(None), column=3, width=90)
        dialog.protocol("WM_DELETE_WINDOW", lambda: choose(None))
        self.wait_window(dialog)
        return result["value"]

    # =====================================================================
    # Pencereler: bilgi, hata, hakkında
    # =====================================================================
    def _text_dialog_shell(self, title: str, heading: str, body: str,
                           severity: str = "ok"):
        """Başlık + salt-okunur metin kutusu iskeleti; ``(pencere, çerçeve, kutu)`` döner.

        Metin kutusu içeriğe göre boyutlanır (``TEXT_DIALOG_BOX_MIN_H`` ile
        ``TEXT_DIALOG_BOX_MAX_H`` arası); eskiden sabit 400-480 px yükseklikte boş kalıyordu.
        Düğme satırı 3. satırdadır (``_dialog_button_row``).
        """
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.minsize(460, 200)
        dialog.transient(self)
        dialog.grab_set()

        frame = ctk.CTkFrame(dialog, fg_color=COLOR_CARD, corner_radius=10)
        frame.put("v", fill="both", expand=True, margins=(14, 10, 14, 10))
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)

        color = {"ok": COLOR_OK, "warn": COLOR_WARN, "error": COLOR_ERROR}.get(severity, COLOR_TEXT_PRIMARY)
        ctk.CTkLabel(
            frame, text=heading, font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SUBTITLE, weight="bold"),
            text_color=color, anchor="w", justify="left", wraplength=540,
        ).place(0, 0, expand_x=True, margins=(12, 10, 12, 4))

        textbox = ctk.CTkTextbox(
            frame, fg_color=COLOR_SUBCARD, border_color=COLOR_BORDER, border_width=1,
            text_color=COLOR_TEXT_PRIMARY, font=ctk.CTkFont(family="Consolas", size=FS_SMALL),
            wrap="word",
        )
        textbox.place(1, 0, rowspan=2, valign="fill", expand_x=True, expand_y=True)
        textbox.insert("1.0", body)
        textbox.configure(state="disabled")

        doc = textbox.document()
        doc.setTextWidth(TEXT_DIALOG_W - 28 - 24 - 2 * textbox.frameWidth() - 8)
        box_h = int(doc.size().height()) + 2 * textbox.frameWidth() + 16
        box_h = max(TEXT_DIALOG_BOX_MIN_H, min(TEXT_DIALOG_BOX_MAX_H, box_h))
        textbox.setMinimumHeight(box_h)
        dialog.geometry(f"{TEXT_DIALOG_W}x{box_h + TEXT_DIALOG_CHROME_H}")
        return dialog, frame, textbox

    def _dialog_button_row(self, frame):
        """Diyalog düğme satırı: sol boşluk esner, düğmeler sağa yaslanır."""
        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.place(3, 0, expand_x=True)
        buttons.grid_columnconfigure(0, weight=1)
        # Qt bo? s?tunu esnetmeyebilir; ger?ek dolgu sa? hizay? korur.
        spacer = ctk.CTkFrame(buttons, fg_color="transparent", width=0, height=0)
        spacer.place(0, 0, expand_x=True)
        return buttons

    def _dialog_button(self, buttons, text: str, command, *, column: int,
                       primary: bool = False, width: int = 100):
        if primary:
            style = dict(fg_color=COLOR_SOLID, text_color=COLOR_ON_ACCENT,
                         hover_color=COLOR_SOLID_HOVER)
        else:
            style = dict(fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
                         border_width=1, border_color=COLOR_BORDER,
                         hover_color=COLOR_BTN_SUBTLE_HOVER)
        button = ctk.CTkButton(
            buttons, text=text, width=width, height=34, command=command,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL,
                             weight="bold" if primary else "normal"),
            **style,
        )
        button.place(0, column, align="c")
        return button

    def _show_text_dialog(self, title: str, heading: str, body: str,
                          severity: str = "ok") -> None:
        dialog, frame, _textbox = self._text_dialog_shell(title, heading, body, severity)
        buttons = self._dialog_button_row(frame)
        self._dialog_button(buttons, "Panoya kopyala", lambda: self._copy_to_clipboard(body),
                            column=1, width=140)
        self._dialog_button(buttons, "Kapat", dialog.destroy, column=2, primary=True)

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
        dialog.resizable(True, True)
        dialog.minsize(460, 320)
        dialog.transient(self)
        dialog.grab_set()

        frame = ctk.CTkScrollableFrame(dialog, fg_color=COLOR_CARD, corner_radius=12)
        frame.put("v", fill="both", expand=True, margins=(14, 10, 14, 10))
        frame.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.place(0, 0, expand_x=True, margins=(14, 10, 14, 10))
        header.grid_columnconfigure(1, weight=1)

        icon_path = os.path.join(ASSETS_DIR, "icon.png")
        if os.path.exists(icon_path):
            try:
                image = Image.open(icon_path)
                self._about_icon = ctk.CTkImage(light_image=image, dark_image=image, size=(60, 60))
                ctk.CTkLabel(header, text="", image=self._about_icon).place(
                    0, 0, rowspan=2, align="c", margins=(0, 0, 14, 0))
            except Exception:
                pass

        ctk.CTkLabel(
            header, text=APP_NAME,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TITLE, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).place(0, 1, align="w")
        ctk.CTkLabel(
            header, text=f"Sürüm {VERSION}   •   baskı ve ciltleme hazırlık aracı",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, anchor="w",
        ).place(1, 1, align="w")

        top_cards = ctk.CTkFrame(frame, fg_color="transparent")
        top_cards.place(1, 0, expand_x=True)
        top_cards.grid_columnconfigure(0, weight=1, uniform="about")
        top_cards.grid_columnconfigure(1, weight=1, uniform="about")

        dev = ctk.CTkFrame(top_cards, fg_color=COLOR_SUBCARD, corner_radius=8,
                           border_width=1, border_color=COLOR_BORDER)
        dev.place(0, 0, valign="fill", expand_x=True, expand_y=True)
        ctk.CTkLabel(
            dev, text="Geliştirici",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_ACCENT, anchor="w",
        ).put("v", margins=(12, 8, 12, 2))
        ctk.CTkLabel(
            dev, text=f"{AUTHOR}\n{CONTACT}",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_PRIMARY, justify="left", anchor="w",
        ).put("v")

        tech = ctk.CTkFrame(top_cards, fg_color=COLOR_SUBCARD, corner_radius=8,
                            border_width=1, border_color=COLOR_BORDER)
        tech.place(0, 1, valign="fill", expand_x=True, expand_y=True)
        ctk.CTkLabel(
            tech, text="Altyapı",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_ACCENT, anchor="w",
        ).put("v", margins=(12, 8, 12, 2))
        ctk.CTkLabel(
            tech, text=f"Sürüm {VERSION}\nPython {sys.version.split()[0]} • PyMuPDF vektörel motor",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_PRIMARY, justify="left", anchor="w",
        ).put("v")

        features = ctk.CTkFrame(frame, fg_color=COLOR_SUBCARD, corner_radius=8,
                                border_width=1, border_color=COLOR_BORDER)
        features.place(2, 0, expand_x=True)
        ctk.CTkLabel(
            features, text="Öne çıkanlar",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).put("v", margins=(14, 8, 14, 2))
        ctk.CTkLabel(
            features,
            text=("Tek ve çift sayfa için ayrı cilt payı; Uzat / Sığdır / Kaydır alt pay modları\n"
                  "Kırpma yerine sayfaya sığdırma; döndürülmüş ve kırpılmış sayfalar korunur\n"
                  "Kırpma riski taraması, canlı önizleme ve sonuç doğrulama raporu\n"
                  "Bağımsız sayfa dışlama listeleri, profiller, mm / cm / pt birimleri\n"
                  "Kayıpsız birleştirme, rotasyon, sürükle-bırak, yer imi ve bağlantı koruması"),
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, justify="left", anchor="w", wraplength=640,
        ).put("v")

        shortcuts = ctk.CTkFrame(frame, fg_color=COLOR_SUBCARD, corner_radius=8,
                                 border_width=1, border_color=COLOR_BORDER)
        shortcuts.place(3, 0, expand_x=True)
        ctk.CTkLabel(
            shortcuts, text="Kısayollar",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).put("v", margins=(14, 8, 14, 4))
        keys = ctk.CTkFrame(shortcuts, fg_color="transparent")
        keys.put("v", fill="x")
        keys.set_padding(0, 2, 8, 2)  # eski sezgiden türeyen boşluk, şimdi açık
        for index, (key, action) in enumerate((
                ("Ctrl+O", "PDF aç"), ("Ctrl+S", "İşlemi başlat"),
                ("Enter", "İşlemi başlat"), ("Esc", "Çalışan işlemi iptal et"))):
            ctk.CTkLabel(
                keys, text=key, width=70, height=24,
                font=ctk.CTkFont(family="Consolas", size=FS_TINY, weight="bold"),
                fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY, corner_radius=4,
            ).place(index // 2, (index % 2) * 2, align="w")
            ctk.CTkLabel(
                keys, text=action,
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
                text_color=COLOR_TEXT_SECONDARY,
            ).place(index // 2, (index % 2) * 2 + 1, align="w")

        paths = ctk.CTkFrame(frame, fg_color=COLOR_SUBCARD, corner_radius=8,
                             border_width=1, border_color=COLOR_BORDER)
        paths.place(4, 0, expand_x=True)
        paths.set_padding(14, 8, 14, 10, spacing=4)
        paths.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            paths, text="Dosyalar",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).place(0, 0, columnspan=3, align="w")
        ctk.CTkLabel(
            paths, text=f"Ayarlar: {self.store.path}\nGünlük: {LOG_PATH}",
            font=ctk.CTkFont(family="Consolas", size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, justify="left", anchor="w", wraplength=500,
        ).place(1, 0, expand_x=True)

        ctk.CTkButton(
            paths, text="Ayarlar klasörü", width=110, height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER, hover_color=COLOR_BTN_SUBTLE_HOVER,
            command=lambda: self._open_about_path(self.store.path.parent, True),
        ).place(1, 1, align="c")
        ctk.CTkButton(
            paths, text="Günlüğü aç", width=96, height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER, hover_color=COLOR_BTN_SUBTLE_HOVER,
            command=lambda: self._open_about_path(LOG_PATH, False),
        ).place(1, 2, align="c")
        ctk.CTkButton(
            paths, text="Tanılama paketi oluştur (.zip)", width=210, height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER, hover_color=COLOR_BTN_SUBTLE_HOVER,
            command=self._export_diagnostics,
        ).place(2, 0, columnspan=3, align="w")

        ctk.CTkButton(
            frame, text="Kapat", width=140, height=36,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            fg_color=COLOR_SOLID, text_color=COLOR_ON_ACCENT,
            hover_color=COLOR_SOLID_HOVER, command=dialog.destroy,
        ).place(5, 0, align="c")

    def _show_settings_dialog(self) -> None:
        """Görünüm, liste/önizleme, PDF çıktısı ve sıfırlama tercihleri."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Ayarlar - {APP_NAME}")
        dialog.geometry("560x660")
        dialog.resizable(True, True)
        dialog.minsize(500, 380)
        dialog.transient(self)
        dialog.grab_set()

        frame = ctk.CTkScrollableFrame(dialog, fg_color=COLOR_CARD, corner_radius=12)
        frame.put("v", fill="both", expand=True, margins=(14, 10, 14, 10))
        frame.grid_columnconfigure(0, weight=1)
        frame.set_padding(14, 10, 14, 2)  # eski sezgiden türeyen boşluk, şimdi açık

        def _section_title(row: int, text: str) -> None:
            ctk.CTkLabel(
                frame, text=text,
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
                text_color=COLOR_TEXT_SECONDARY, anchor="w",
            ).place(row, 0, align="w")

        # Tema için üst çubukta tek bir hızlı kontrol var; ayarlarda tekrar etmiyoruz.
        _section_title(0, "Görünüm ve birimler")
        ctk.CTkLabel(frame, text="Tema seçimi üst çubuktan yapılır.",
                     font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
                     text_color=COLOR_TEXT_SECONDARY, anchor="w").place(1, 0, align="w")

        # -- Ölçü birimi ------------------------------------------------------
        _section_title(2, "Ölçü birimi")

        def _apply_unit(label: str) -> None:
            self._on_unit_changed(label)
            try:
                self._update_unit_button()
            except Exception:
                pass

        appearance_controls = ctk.CTkFrame(frame, fg_color="transparent")
        appearance_controls.place(3, 0, align="w")
        unit_menu = ctk.CTkOptionMenu(
            appearance_controls, values=[UNITS[u][0] for u in DISPLAY_UNITS], width=150, height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            button_color=COLOR_SUBCARD, button_hover_color=COLOR_BTN_SUBTLE_HOVER,
            dropdown_fg_color=COLOR_CARD, dropdown_hover_color=COLOR_SELECTED,
            dropdown_text_color=COLOR_TEXT_PRIMARY,
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            command=_apply_unit,
        )
        unit_menu.set(UNITS[self.unit][0])
        unit_menu.put("h", margins=(0, 0, SP_M, 0))

        def _apply_language(label):
            from ui.i18n import set_language, refresh_widgets
            self.store.data["language"] = "en" if label == "English" else "tr"
            self.store.save()
            set_language(self.store.data["language"])
            refresh_widgets(self)

        language_menu = ctk.CTkOptionMenu(appearance_controls, values=["Türkçe", "English"],
                                         width=140, height=28, command=_apply_language)
        language_menu.set("English" if self.store.data.get("language") == "en" else "Türkçe")
        language_menu.setToolTip("Arayüz dili / Interface language")
        language_menu.put("h")

        # -- PDF çıktısı -----------------------------------------------------
        _section_title(9, "PDF çıktısı")
        output_boxes = {}
        for row, key, text, tooltip in (
            (10, "optimize", "Dosyayı optimize et (küçük boyut)",
             "Kullanılmayan PDF nesnelerini temizler ve akışları sıkıştırır. Görüntü çözünürlüğünü düşürmez."),
            (11, "flatten", "Açıklama ve form alanlarını sayfaya göm",
             "Not, vurgu ve doldurulmuş form alanlarının görünümünü korur; çıktıdaki bu alanlar artık düzenlenemez."),
        ):
            box = ctk.CTkCheckBox(
                frame, text=text, fg_color=COLOR_SOLID,
                text_color=COLOR_TEXT_PRIMARY, hover_color=COLOR_ACCENT,
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            )
            active = self._output_quality != "print" if key == "optimize" else self._flatten_annotations
            box.select() if active else box.deselect()
            box.setToolTip(tooltip)
            box.place(row, 0, expand_x=True)
            self._bind_wraplength(box, frame, 40)
            output_boxes[key] = box

            def toggle_output(key=key, box=box):
                if key == "optimize":
                    self._output_quality = "standard" if box.get() else "print"
                else:
                    self._flatten_annotations = bool(box.get())
                # Yalnız çıktı tercihlerini güncelle: geçersiz bir form alanı
                # nedeniyle diğer ayarları son geçerli yapılandırmayla ezme.
                state = self.store.last_state or self._collect_state()
                state["quality_mode"] = self._output_quality
                state["flatten_annotations"] = self._flatten_annotations
                self.store.last_state = state
                self.store.save()
                self._on_field_changed()

            box.configure(command=toggle_output)

        note = ctk.CTkLabel(
            frame, text="Sayfaya gömülen açıklamalar ve form alanları çıktıda düzenlenemez.",
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
        )
        note.place(12, 0, expand_x=True)
        self._bind_wraplength(note, frame, 30)

        # -- Çıktı klasörü ----------------------------------------------------
        chk_auto = ctk.CTkCheckBox(
            frame, text="İşlem bitince çıktı klasörünü otomatik aç",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_PRIMARY, hover_color=COLOR_ACCENT,
            fg_color=COLOR_SOLID,
        )
        if self.store.data.get("auto_open_output"):
            chk_auto.select()
        chk_auto.place(13, 0, align="w")
        self._bind_wraplength(chk_auto, frame, 40)

        def _toggle_auto() -> None:
            self.store.data["auto_open_output"] = bool(chk_auto.get())
            self.store.save()

        chk_auto.configure(command=_toggle_auto)

        _section_title(4, "Liste ve önizleme")
        preference_boxes = {}
        for row, key, text, tooltip in (
            (5, "merge_preview_sequence", "Önizlemede tüm birleşik belgeyi gez",
             "Dosya sınırları işaretlenir. Kapalıyken yalnız seçili dosya gösterilir. "
             "İlk açılışta geçici birleşik kopyanın hazırlanması zaman alabilir."),
            (6, "merge_handle_only", "Satırları yalnız ⠿ tutamacından sürükle",
             "Yanlışlıkla taşımayı önler; satırın diğer yerlerine tıklamak yalnızca seçer."),
        ):
            box = ctk.CTkCheckBox(
                frame, text=text,
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
                text_color=COLOR_TEXT_PRIMARY, hover_color=COLOR_ACCENT,
                fg_color=COLOR_SOLID,
            )
            box.select() if getattr(self.store, key) else box.deselect()
            box.setToolTip(tooltip)
            box.place(row, 0, expand_x=True)
            self._bind_wraplength(box, frame, 40)
            preference_boxes[key] = box

            def toggle_preference(key=key, box=box):
                setattr(self.store, key, bool(box.get()))
                self.store.save()
                # Etkin sürüklemeyi iptal et; yeni tercih bir sonraki basışta kullanılır.
                merge = self._tabs["Birleştirme"]
                if merge.built:
                    merge._end_drag()
                self._schedule_preview()

            box.configure(command=toggle_preference)

        # -- Fabrika sıfırlama + Kapat ---------------------------------------
        def _reset_to_factory() -> None:
            if not messagebox.askyesno(
                    "Fabrika ayarlarına dön",
                    "Tüm ayarlar fabrika değerlerine döner.\n"
                    "Profiller ve son durum da silinir. Devam edilsin mi?"):
                return
            self.store.reset()
            from ui.i18n import set_language, refresh_widgets
            set_language("tr")
            language_menu.set("Türkçe")
            refresh_widgets(self)
            try:
                self._apply_factory_state()  # ekrandaki alanlar da varsayılana döner
            except Exception:
                self.log.exception("Fabrika durumu alanlara uygulanamadı")
            unit_menu.set(UNITS[self.store.unit][0])
            chk_auto.deselect()
            for box in preference_boxes.values():
                box.deselect()
            output_boxes["optimize"].select() if self._output_quality != "print" else output_boxes["optimize"].deselect()
            output_boxes["flatten"].select() if self._flatten_annotations else output_boxes["flatten"].deselect()
            merge = self._tabs["Birleştirme"]
            if merge.built:
                merge._end_drag()
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

        def _export_profile_json() -> None:
            config = self._build_config(notify=True)
            if config is None:
                return
            path = filedialog.asksaveasfilename(
                title="Ayar profilini dışa aktar",
                initialfile="baski-profili.json",
                defaultextension=".json",
                filetypes=[("JSON profili", "*.json")],
            )
            if not path:
                return
            try:
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump(config_to_dict(config), handle, ensure_ascii=False, indent=2)
                self._set_status(f"Profil dışa aktarıldı: {os.path.basename(path)}", COLOR_OK)
                messagebox.showinfo("Profil dışa aktarıldı", f"Ayarlar kaydedildi:\n{path}")
            except Exception as exc:
                messagebox.showerror("Hata", f"Profil dışa aktarılamadı:\n{exc}")

        def _import_profile_json() -> None:
            path = filedialog.askopenfilename(
                title="Ayar profilini içe aktar",
                filetypes=[("JSON profili", "*.json"), ("Tüm dosyalar", "*.*")],
            )
            if not path:
                return
            try:
                with open(path, "r", encoding="utf-8-sig") as handle:
                    raw = json.load(handle)
                if isinstance(raw, dict) and isinstance(raw.get("last_state"), dict):
                    raw = raw["last_state"]
                if not isinstance(raw, dict):
                    raise ValueError("Geçerli bir JSON ayar nesnesi değil.")
                self._apply_config(config_from_dict(raw))
                unit_menu.set(UNITS[self.unit][0])
                output_boxes["optimize"].select() if self._output_quality != "print" else output_boxes["optimize"].deselect()
                output_boxes["flatten"].select() if self._flatten_annotations else output_boxes["flatten"].deselect()
                self._set_status(f"Profil içe aktarıldı: {os.path.basename(path)}", COLOR_OK)
                messagebox.showinfo("Profil içe aktarıldı", "Profil ayarları ekrana uygulandı.")
            except Exception as exc:
                messagebox.showerror("Hata", f"Profil içe aktarılamadı:\n{exc}")

        _section_title(14, "Ayar profilini paylaş / yükle (JSON)")
        profile_io = ctk.CTkFrame(frame, fg_color="transparent")
        profile_io.place(15, 0, align="w")
        ctk.CTkButton(
            profile_io, text="Dışa aktar…", width=120, height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, command=_export_profile_json,
        ).put("h", margins=(0, 0, SP_S, 0))
        ctk.CTkButton(
            profile_io, text="İçe aktar…", width=120, height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, command=_import_profile_json,
        ).put("h")

        _section_title(16, "Sıfırlama")
        actions = ctk.CTkFrame(frame, fg_color="transparent")
        actions.place(17, 0, expand_x=True)
        actions.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(
            actions, text="Fabrika değerlerine sıfırla", width=170, height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_ERROR_BG, command=_reset_to_factory,
        ).place(0, 0, align="w")
        ctk.CTkButton(
            actions, text="Kapat", width=110, height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            fg_color=COLOR_SOLID, text_color=COLOR_ON_ACCENT,
            hover_color=COLOR_SOLID_HOVER, command=dialog.destroy,
        ).place(0, 1, align="e")

    def _screen_info(self) -> dict:
        """Tanılama için ekran/DPI bilgisi (alınamazsa boş)."""
        try:
            from PySide6.QtGui import QGuiApplication
            screen = QGuiApplication.primaryScreen()
            if screen is None:
                return {}
            size = screen.size()
            return {
                "cozunurluk": f"{size.width()}x{size.height()}",
                "cihaz_piksel_orani": round(float(screen.devicePixelRatio()), 3),
                "mantiksal_dpi": round(float(screen.logicalDotsPerInch()), 1),
                "pencere": f"{self.width()}x{self.height()}",
            }
        except Exception:
            return {}

    def _export_diagnostics(self) -> None:
        """Günlük + anonim ayar + sürüm/DPI bilgisini tek .zip olarak kaydeder."""
        from core.diagnostics import build_diagnostics_zip, default_filename
        path = filedialog.asksaveasfilename(
            title="Tanılama paketini kaydet",
            initialfile=default_filename(),
            defaultextension=".zip",
            filetypes=[("ZIP arşivi", "*.zip")],
        )
        if not path:
            return
        try:
            build_diagnostics_zip(path, self.store.data, LOG_PATH, self._screen_info())
        except Exception as exc:
            self.log.exception("Tanılama paketi oluşturulamadı")
            messagebox.showerror("Tanılama paketi", f"Paket oluşturulamadı:\n{exc}")
            return
        messagebox.showinfo(
            "Tanılama paketi",
            f"Paket kaydedildi:\n{path}\n\nDosya yolları ve kullanıcı adı maskelenmiştir; "
            "göndermeden önce içeriğine bakabilirsiniz.")

    @staticmethod
    def _open_with_os(target: str) -> None:
        """Dosya veya klasörü işletim sisteminin varsayılan uygulamasıyla açar."""
        if sys.platform.startswith("win"):
            os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target], start_new_session=True)
        else:
            subprocess.Popen(["xdg-open", target], start_new_session=True)

    def _open_about_path(self, path, folder: bool) -> None:
        try:
            target = str(path)
            if folder:
                os.makedirs(target, exist_ok=True)
            elif not os.path.exists(target):
                target = os.path.dirname(target) or "."
            self._open_with_os(target)
        except Exception as exc:
            messagebox.showerror("Hata", f"Dosya/klasör açılamadı: {exc}")

    # =====================================================================
    # Çıktı işlemleri
    # =====================================================================
    def _open_output_pdf(self) -> None:
        if self.output_pdf_path and os.path.exists(self.output_pdf_path):
            try:
                self._open_with_os(self.output_pdf_path)
            except Exception as exc:
                messagebox.showerror("Hata", f"PDF açılamadı: {exc}")

    def _open_output_folder(self) -> None:
        if self.output_pdf_path and os.path.exists(self.output_pdf_path):
            try:
                self._open_with_os(os.path.dirname(os.path.abspath(self.output_pdf_path)))
            except Exception as exc:
                messagebox.showerror("Hata", f"Klasör açılamadı: {exc}")

    def _open_output_in_tools(self) -> None:
        if self._busy or not self.output_pdf_path or not os.path.exists(self.output_pdf_path):
            return
        from ui.pdf_tools import PdfToolsWindow
        win = PdfToolsWindow(self)
        win.load(self.output_pdf_path)
        self._pdf_tools_window = win
