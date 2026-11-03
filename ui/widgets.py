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

        self.label = ctk.CTkLabel(
            self, text=label, font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
            width=label_width if label_width else 0,
        )
        if label:
            self.label.pack(side="left", padx=(0, 8))

        self.entry = ctk.CTkEntry(
            self, width=width, height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY),
            fg_color=COLOR_CARD, border_color=COLOR_BORDER,
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
        self.error_label.pack(side="left", padx=(6, 0))
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
            self, text=text, command=command, height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold" if bold else "normal"),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, corner_radius=6, width=width,
        )
        self._buttons.append(button)
        self.grid_columnconfigure(index, weight=1, uniform="preset")
        button.grid(row=0, column=index, sticky="ew", padx=3, pady=1)
        return button
