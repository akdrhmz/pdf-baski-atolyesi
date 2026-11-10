"""Yeniden kullanılan arayüz bileşenleri."""

from __future__ import annotations

from typing import List, Optional


from ui import qt_compat as ctk

HAS_WINDND = True

from gutter_engine import (
    UNITS,
    format_measure,
    unit_to_mm,
)
from ui.theme import *  # noqa: F401,F403

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

        # Düzen: üst satır = etiket + giriş + birim; hata metni altta ayrı satırdadır
        # (komşu alanları yana itmez; boşken hiç yer kaplamaz).
        self._line = ctk.CTkFrame(self, fg_color="transparent")
        self._line.place(0, 0, align="w")
        self.grid_columnconfigure(0, weight=1)

        self.label = ctk.CTkLabel(
            self._line, text=label, font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
            width=label_width if label_width else 0,
        )
        if label:
            self.label.put("h", margins=(0, 0, 8, 0))
            self._keep_natural_width(self.label)

        self.entry = ctk.CTkEntry(
            self._line, width=width, height=26,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY),
            fg_color=COLOR_CARD, border_color=COLOR_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
        )
        self.entry.put("h")
        self.entry.insert(0, value)
        self.entry.bind("<KeyRelease>", self._on_key)
        self.entry.bind("<FocusOut>", self._on_focus_out)

        self.unit_label = ctk.CTkLabel(
            self._line, text=self._unit_text(), font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY,
        )
        self.unit_label.put("h")
        self._keep_natural_width(self.unit_label)

        self.error_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_ERROR, anchor="w", justify="left", wraplength=260,
        )
        # Yatayda yok sayılır: satırın asgari/tercih genişliğini şişirmez, komşu alanları
        # itmez; hücreyi (= giriş satırının genişliğini) doldurur ve metin orada sarılır.
        # (Eskiden ``grid()`` bu politikayı sessizce ``Preferred`` yapıp 220 px asgari
        # genişlik dayatıyordu.)
        sp = self.error_label.sizePolicy()
        sp.setHorizontalPolicy(ctk.QSizePolicy.Policy.Ignored)
        self.error_label.setSizePolicy(sp)
        self.error_label.place(1, 0, valign="n")
        self.error_label.hide()
        self._set_default(value)

    @staticmethod
    def _keep_natural_width(widget) -> None:
        """Etiketi metin genişliğinin altına sıkıştırılamaz yapar (P2-33).

        Üst kapsayıcılar daralınca eskiden birim etiketi (\"mm\") 2-6 px'e eziliyor,
        sabit genişlikli giriş kutusu ise yerinde kaldığı için yazı kutunun üstüne
        biniyordu. ``Fixed`` politikada sıkışan satır etiketi ezmez; taşan kısım kırpılır.
        """
        sp = widget.sizePolicy()
        sp.setHorizontalPolicy(ctk.QSizePolicy.Policy.Fixed)
        widget.setSizePolicy(sp)

    def _refresh_unit_label(self) -> None:
        self.unit_label.configure(text=self._unit_text())
        self.unit_label.adjustSize()
        self.unit_label.updateGeometry()

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
        self.error_label.setVisible(bool(message))
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
        self._refresh_unit_label()
        # Görüntü yuvarlanır ama mm değeri korunur; birime geri dönüş kayıpsızdır.
        self.set_value(format_measure(self._canonical_mm, new_unit),
                       canonical_mm=self._canonical_mm)

    def reset_unit(self, unit: str) -> None:
        """Gösterim birimini dönüştürmeden ayarlar (başlangıçta kayıtlı birim)."""
        if not self.convert:
            return
        self.unit = unit
        self._refresh_unit_label()
        self.set_value(format_measure(self._canonical_mm, unit),
                       canonical_mm=self._canonical_mm)


class WrapButtonRow(ctk.CTkFrame):
    """Düğme grubu: sığmayan düğmeler alt satıra sarar (sabit genişlik korunur).

    Sarma gerçek yeniden ızgaradır: genişlik değişince düğmeler satırlara dağıtılır.
    Böylece içerik alanı daraldığında grup yatay taşmaz (P3 13e).
    """

    def __init__(self, master, stretch: bool = False, wrap: bool = True, gap: int = SP_S, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._buttons: List[ctk.CTkButton] = []
        self._row_count = 1
        self._stretch = bool(stretch)
        self._wrap = bool(wrap)
        self._gap = gap
        # Satır sonundaki esnek dolgu: artan genişlik düğmelere değil bu sütuna gider.
        self._tail = ctk.CTkFrame(self, fg_color="transparent", width=1)
        self._tail_col = 0
        self._last_width = -1
        self._reflowing = False
        self.set_padding(0, 0, 0, 0, spacing=self._gap)

    def add_button(self, text: str, command, width: int = BTN_W,
                   bold: bool = False) -> ctk.CTkButton:
        btn_w = width if (width and not self._stretch) else 0
        button = ctk.CTkButton(
            self, text=text, command=command, width=btn_w, height=BTN_H,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold" if bold else "normal"),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, corner_radius=6,
        )
        if width:
            button.setMinimumWidth(min(width, 36))
            if not self._stretch and not self._wrap:
                button.setFixedWidth(width)
        else:
            # Sabit genişlik yok: düğme metni kadar yer alır, yazı kırpılmaz.
            button.setMinimumWidth(button.fontMetrics().horizontalAdvance(text) + 16)
        self._buttons.append(button)
        self._reflow()
        return button

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.width() != self._last_width:
            self._last_width = self.width()
            self._reflow()

    def _reflow(self) -> None:
        """Düğmeleri geçerli genişliğe göre satırlara dağıtır."""
        if not self._buttons or self._reflowing:
            return
        self._reflowing = True
        try:
            self._place_buttons()
        finally:
            self._reflowing = False

    def _place_buttons(self) -> None:
        if not self._buttons:
            return
        available = max(1, self.width())
        gap = self._gap
        placements = []
        if not self._wrap:
            rows = 1
            for col, _ in enumerate(self._buttons):
                placements.append((0, col))
        else:
            rows, columns, x = 1, 0, 0
            for button in self._buttons:
                width = self._min_button_width(button)
                if columns and x + width > available:
                    rows, columns, x = rows + 1, 0, 0
                placements.append((rows - 1, columns))
                x += width + gap
                columns += 1
        max_col = max(c for _, c in placements)
        if self._stretch:
            for column in range(max_col + 1):
                self.grid_columnconfigure(column, weight=1)
        else:
            for column in range(max_col + 1):
                self.grid_columnconfigure(column, weight=0)
        for button, (row, column) in zip(self._buttons, placements):
            button.place(row, column, align="" if self._stretch else "w",
                         expand_x=self._stretch)
            if self._stretch:
                # ``place(expand_x=True)`` asgari genişliği sıfırlar; uzun metin
                # ("Sıcak tutkal cilt") kırpılmasın diye metne göre geri verilir.
                button.setMinimumWidth(self._min_button_width(button))
        tail_col = max_col + 1
        self.grid_columnconfigure(self._tail_col, weight=0)
        self.grid_columnconfigure(tail_col, weight=0 if self._stretch else 1)
        self._tail_col = tail_col
        self._tail.place(0, tail_col, expand_x=True)
        self._row_count = rows
        self.updateGeometry()

    def add_widget(self, widget) -> None:
        """Düğme olmayan bir ögeyi (ör. ``FieldRow``) aynı sarma düzenine ekler."""
        self._buttons.append(widget)
        self._reflow()

    @staticmethod
    def _min_button_width(button) -> int:
        """Ögenin asgari genişliği: düğmede metne göre (kendi genişliğinden bağımsız),
        diğer ögelerde ``sizeHint`` genişliği."""
        if isinstance(button, ctk.CTkButton):
            return button.fontMetrics().horizontalAdvance(button.text()) + 26
        return button.sizeHint().width()

    def _one_row_height(self) -> int:
        return max((b.sizeHint().height() for b in self._buttons), default=BTN_H)

    def sizeHint(self):  # noqa: N802 (Qt adı)
        width = sum(self._min_button_width(b) for b in self._buttons) + SP_M * (len(self._buttons) + 1)
        return ctk.QSize(min(width, CONTENT_MAX_W), self._row_count * (self._one_row_height() + SP_M))

    def minimumSizeHint(self):  # noqa: N802 (Qt adı)
        width = max((self._min_button_width(b) for b in self._buttons), default=0) + SP_M
        return ctk.QSize(width, self._row_count * (self._one_row_height() + SP_M))
