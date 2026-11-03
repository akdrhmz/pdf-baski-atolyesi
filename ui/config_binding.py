"""Ayar okuma/yazma ve profiller: arayüz alanları ↔ ``PdfProcessConfig`` köprüsü.

``app.py``'den birebir taşındı (davranış değişikliği yok). Sınıf, ``ModernGutterApp`` içinde
karışım (mixin) olarak kullanılır; alan/sekme nesneleri (``self.f_width`` vb.) ana pencerede durur.

Tembel kurulum (2.9): Kenar Boşlukları, Sayfa Numaraları ve Birleştirme sekmeleri ilk
gösterilene kadar kurulmaz. O zamana kadar ayarın o sekmeye düşen bölümü ``_pending_sections``
içinde bekler; ``_build_config`` değeri oradan okur, sekme kurulunca widget'lara yazılır.
Cilt Payı (açılış sekmesi) her zaman kuruludur.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ui import qt_compat as ctk  # noqa: F401
from ui.qt_compat import messagebox

from gutter_engine import (
    MarginSettings,
    PageBoxSettings,
    PageNumberSettings,
    PdfProcessConfig,
    config_from_dict,
    config_to_dict,
    invalid_range_tokens,
    validate_config,
)
from gutter_engine import format_measure, unit_to_mm
from settings_store import PRESETS
from ui.theme import *  # noqa: F401,F403
from ui.widgets import FieldError, FieldRow


MARGIN_TAB = "Kenar Boşlukları"
NUMBER_TAB = "Sayfa Numaraları"
MERGE_TAB = "Birleştirme"


class ConfigBindingMixin:

    # =====================================================================
    # Tembel sekmeler (2.9)
    # =====================================================================
    def __getattr__(self, name: str):
        """Kurulmamış sekmenin widget'ı eski adla istenirse (``app.f_bottom``) sekmeyi kurar.

        Yalnızca normal arama başarısız olunca çağrılır; açılış yolları bu köprüye değil
        ``_set_section`` / ``_section`` yüzeyine gider (aksi hâlde tembel kazanç kaybolur).
        """
        if not name.startswith("_"):
            tabs = self.__dict__.get("_tabs")
            if tabs:
                for tab in tabs.values():
                    if not tab.built and name in getattr(type(tab), "EXPOSED", ()):
                        tab.ensure_built()
                        return getattr(tab, name)
        return super().__getattr__(name)

    def _pending(self) -> Dict[str, Dict[str, Any]]:
        pending = self.__dict__.get("_pending_sections")
        if pending is None:
            pending = self._pending_sections = {}
        return pending

    def _tab_built(self, name: str) -> bool:
        return self._tabs[name].built

    def _section(self, name: str) -> Dict[str, Any]:
        """Kurulmamış sekmenin bekleyen ayar bölümü (yoksa widget varsayılanları)."""
        data = self._pending().get(name)
        if data is not None:
            return data
        if name == MARGIN_TAB:
            return {"margins": MarginSettings(), "pad4": False}
        if name == NUMBER_TAB:
            return {"numbers": PageNumberSettings()}
        return {"apply_pipeline": False, "bookmarks": True}

    def _set_section(self, name: str, data: Dict[str, Any]) -> None:
        """Ayar bölümünü kurulu sekmeye yazar, kurulmamışsa bekletir."""
        if self._tab_built(name):
            self._write_section(name, data)
        else:
            self._pending()[name] = data

    def _write_section(self, name: str, data: Dict[str, Any]) -> None:
        if name == MARGIN_TAB:
            margins = data["margins"]
            self.seg_bottom_mode.set(MODE_CODES.get(margins.bottom_mode, "Uzat (kırpmaz, önerilen)"))
            self.f_bottom.set_mm(margins.extra_bottom_mm)
            self.f_top.set_mm(margins.extra_top_mm)
            self.entry_exclude_margin.delete(0, "end")
            self.entry_exclude_margin.insert(0, margins.exclude_pages_str)
            self.chk_pad4.select() if data["pad4"] else self.chk_pad4.deselect()
        elif name == NUMBER_TAB:
            numbers = data["numbers"]
            self.seg_pos.set(POSITION_CODES.get(numbers.position, "Dış kenar (Tek sağ / Çift sol)"))
            self.menu_format.set(FORMAT_CODES.get(numbers.format_style, "1, 2, 3"))
            self.f_font_size.set_value(f"{numbers.font_size:g}")
            self.f_start_page.set_value(str(numbers.start_page))
            self.f_start_num.set_value(str(numbers.start_num))
            self.f_num_bottom.set_mm(numbers.bottom_margin_mm)
            self.f_num_side.set_mm(numbers.side_margin_mm)
            self.entry_skip_pages.delete(0, "end")
            self.entry_skip_pages.insert(0, numbers.skip_pages_str)
            self.entry_number_template.delete(0, "end")
            self.entry_number_template.insert(0, numbers.text_template)
            self.chk_continuous.select() if numbers.continuous_numbering else self.chk_continuous.deselect()
            # "Alt orta" konumunda yan boşluk alanı pasif, ipucu görünür (yüklenen ayarda da).
            self._tabs[NUMBER_TAB].update_side_state()
        else:
            self.chk_merge_apply_pipeline.select() if data["apply_pipeline"] else self.chk_merge_apply_pipeline.deselect()
            self.chk_merge_bookmarks.select() if data["bookmarks"] else self.chk_merge_bookmarks.deselect()

    def _on_tab_built(self, tab) -> None:
        """Sekme kurulunca: eski takma adlar, gösterim birimi, bekleyen ayar."""
        self._expose_tab_widgets(tab)
        for attr in getattr(type(tab), "EXPOSED", ()):
            row = getattr(tab, attr, None)
            if isinstance(row, FieldRow):
                row.reset_unit(self.unit)
        data = self._pending().pop(tab.name, None)
        if data is None:
            return
        self._write_section(tab.name, data)
        if tab.name == MARGIN_TAB:
            tab.on_mode_changed()
        else:
            self._on_field_changed()

    def _shown_mm(self, mm: float) -> float:
        """Değerin alanda gösterilip geri okunmuş hâli (kurulu sekmeyle aynı yuvarlama)."""
        try:
            return unit_to_mm(float(format_measure(mm, self.unit).replace(",", ".")), self.unit)
        except (TypeError, ValueError):
            return mm

    def _margin_mm(self, which: str) -> float:
        """Alt (\"bottom\") ya da üst (\"top\") pay, mm; sekme kurulmamışsa bekleyen ayardan."""
        if self._tab_built(MARGIN_TAB):
            return self._row_mm(self.f_bottom if which == "bottom" else self.f_top)
        margins = self._section(MARGIN_TAB)["margins"]
        return margins.extra_bottom_mm if which == "bottom" else margins.extra_top_mm

    def _on_margin_mode_changed(self) -> None:
        if self._tab_built(MARGIN_TAB):
            self._tabs[MARGIN_TAB].on_mode_changed()
            return
        # Kurulmamış sekmede MarginTab.on_changed ile aynı karar: pay varsa modülü aç.
        if self.switch_margin.get() != 1 and (self._margin_mm("bottom") > 0 or self._margin_mm("top") > 0):
            self.switch_margin.select()
            self._toggle_margin_fields()
            return
        self._on_field_changed()

    # =====================================================================
    # Ayar okuma / yazma (tek kaynak)
    # =====================================================================
    def _row_mm(self, row: FieldRow) -> float:
        return row.get_mm()

    def _range_entries(self) -> List[tuple]:
        """Kurulu sekmelerdeki sayfa aralığı kutuları."""
        entries = [("İşlem dışı sayfalar (cilt payı)", self.entry_exclude_pages)]
        if self._tab_built(MARGIN_TAB):
            entries.append(("İşlem dışı sayfalar (kenar boşluğu)", self.entry_exclude_margin))
        if self._tab_built(NUMBER_TAB):
            entries.append(("Numarasız sayfalar", self.entry_skip_pages))
        return entries

    def _pending_range_texts(self) -> List[tuple]:
        """Kurulmamış sekmelerin bekleyen sayfa aralığı metinleri."""
        texts = []
        if not self._tab_built(MARGIN_TAB):
            texts.append(("İşlem dışı sayfalar (kenar boşluğu)",
                          self._section(MARGIN_TAB)["margins"].exclude_pages_str))
        if not self._tab_built(NUMBER_TAB):
            texts.append(("Numarasız sayfalar", self._section(NUMBER_TAB)["numbers"].skip_pages_str))
        return texts

    def _check_range_entries(self) -> List[str]:
        """Sayfa aralığı kutularını denetler; hatalı kutunun çerçevesini kırmızı yapar."""
        problems: List[str] = []
        for label, text in self._pending_range_texts():
            bad = invalid_range_tokens(text or "")
            if bad:
                problems.append(f"{label}: anlaşılamayan değer → {', '.join(bad[:3])}")
        for label, entry in self._range_entries():
            bad = invalid_range_tokens(entry.get())
            try:
                entry.configure(border_color=COLOR_ERROR if bad else COLOR_BORDER)
            except Exception:
                pass
            if bad:
                problems.append(f"{label}: anlaşılamayan değer → {', '.join(bad[:3])}")
        return problems

    def _build_config(self, notify: bool = False) -> Optional[PdfProcessConfig]:
        """Arayüzdeki tüm alanlardan tek bir motor yapılandırması üretir."""
        margin_built = self._tab_built(MARGIN_TAB)
        number_built = self._tab_built(NUMBER_TAB)
        groups = [
            ("gutter", self.switch_gutter.get() == 1,
             [("width", self.f_width), ("height", self.f_height),
              ("safe_edge", self.f_safe_edge), ("odd_x", self.f_odd_x), ("odd_y", self.f_odd_y),
              ("even_x", self.f_even_x), ("even_y", self.f_even_y)]),
        ]
        if margin_built:
            groups.append(("margin", self.switch_margin.get() == 1,
                           [("bottom", self.f_bottom), ("top", self.f_top)]))
        if number_built:
            groups.append(("number", self.switch_pnum.get() == 1,
                           [("font_size", self.f_font_size), ("start_page", self.f_start_page),
                            ("start_num", self.f_start_num), ("num_bottom", self.f_num_bottom),
                            ("num_side", self.f_num_side)]))
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

        for problem in self._check_range_entries():
            # Kurulmamış sekmeyi odak için kurmamak adına widget yalnızca varsa verilir.
            errors.append((self.__dict__.get("entry_skip_pages"), problem))

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
            safe_edge_mm=values["safe_edge"],
            target_width_mm=values["width"],
            target_height_mm=values["height"],
            odd_x_mm=values["odd_x"],
            odd_y_mm=values["odd_y"],
            even_x_mm=values["even_x"],
            even_y_mm=values["even_y"],
            exclude_pages_str=self.entry_exclude_pages.get().strip(),
        )
        if margin_built:
            bottom_mode = self.seg_bottom_mode.get()
            margin_exclude = self.entry_exclude_margin.get().strip()
            pad4 = self.chk_pad4.get() == 1
        else:
            section = self._section(MARGIN_TAB)
            pending = section["margins"]
            values["bottom"] = self._shown_mm(pending.extra_bottom_mm)
            values["top"] = self._shown_mm(pending.extra_top_mm)
            bottom_mode = MODE_CODES.get(pending.bottom_mode, "Uzat (kırpmaz, önerilen)")
            margin_exclude = (pending.exclude_pages_str or "").strip()
            pad4 = bool(section["pad4"])
        margins = MarginSettings(
            enabled=self.switch_margin.get() == 1,
            extra_bottom_mm=values["bottom"],
            extra_top_mm=values["top"],
            bottom_mode=MODE_LABELS.get(bottom_mode, "expand"),
            exclude_pages_str=margin_exclude,
        )
        if number_built:
            position = self.seg_pos.get()
            format_label = self.menu_format.get()
            template = self.entry_number_template.get().strip()
            skip_pages = self.entry_skip_pages.get().strip()
            continuous = self.chk_continuous.get() == 1
        else:
            pending = self._section(NUMBER_TAB)["numbers"]
            values["font_size"] = float(f"{pending.font_size:g}")
            values["start_page"] = float(pending.start_page)
            values["start_num"] = float(pending.start_num)
            values["num_bottom"] = self._shown_mm(pending.bottom_margin_mm)
            values["num_side"] = self._shown_mm(pending.side_margin_mm)
            position = POSITION_CODES.get(pending.position, "Dış kenar (Tek sağ / Çift sol)")
            format_label = FORMAT_CODES.get(pending.format_style, "1, 2, 3")
            template = (pending.text_template or "").strip()
            skip_pages = (pending.skip_pages_str or "").strip()
            continuous = bool(pending.continuous_numbering)
        numbers = PageNumberSettings(
            enabled=self.switch_pnum.get() == 1,
            position=POSITION_LABELS.get(position, "outer"),
            format_style=FORMAT_LABELS.get(format_label, "number"),
            text_template=template,
            start_num=int(values["start_num"]),
            start_page=int(values["start_page"]),
            font_size=values["font_size"],
            font_color=(0.08, 0.08, 0.08),
            bottom_margin_mm=values["num_bottom"],
            side_margin_mm=values["num_side"],
            skip_pages_str=skip_pages,
            continuous_numbering=continuous,
        )
        config = PdfProcessConfig(
            page_boxes=boxes,
            margins=margins,
            page_numbers=numbers,
            quality_mode="standard" if self.chk_optimize.get() == 1 else "print",
            flatten_annotations=self.chk_flatten.get() == 1,
            pad_to_multiple=4 if pad4 else 0,
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

        self.f_width.set_mm(boxes.target_width_mm)
        self.f_height.set_mm(boxes.target_height_mm)
        self.f_safe_edge.set_mm(boxes.safe_edge_mm)
        self._update_safe_edge_state()
        self.f_odd_x.set_mm(boxes.odd_x_mm)
        self.f_odd_y.set_mm(boxes.odd_y_mm)
        self.f_even_x.set_mm(boxes.even_x_mm)
        self.f_even_y.set_mm(boxes.even_y_mm)
        self.entry_exclude_pages.delete(0, "end")
        self.entry_exclude_pages.insert(0, boxes.exclude_pages_str)
        self._set_section(MARGIN_TAB, {"margins": margins, "pad4": config.pad_to_multiple == 4})
        self._set_section(NUMBER_TAB, {"numbers": numbers})

        self.chk_optimize.select() if config.optimize else self.chk_optimize.deselect()
        self.chk_flatten.select() if config.flatten_annotations else self.chk_flatten.deselect()

        self._toggle_gutter_fields()
        self._toggle_margin_fields()
        self._toggle_pnum_fields()
        self._on_margin_mode_changed()

    def _collect_state(self) -> Dict[str, Any]:
        config = self._build_config(notify=False) or self._last_valid_config
        state = config_to_dict(config) if config else {}
        state["unit"] = self.unit
        state["theme"] = self.store.theme
        if self._tab_built(MERGE_TAB):
            state["apply_pipeline"] = self.chk_merge_apply_pipeline.get() == 1
            state["merge_bookmarks"] = self.chk_merge_bookmarks.get() == 1
        else:
            section = self._section(MERGE_TAB)
            state["apply_pipeline"] = bool(section["apply_pipeline"])
            state["merge_bookmarks"] = bool(section["bookmarks"])
        return state

    def _restore_settings(self) -> None:
        state = self.store.last_state
        self.theme_segmented.set(self.store.theme)
        ctk.set_appearance_mode({"Açık": "Light", "Koyu": "Dark"}.get(self.store.theme, "System"))

        if state:
            config = config_from_dict(state)
            self._apply_config(config)
            self._set_section(MERGE_TAB, {"apply_pipeline": bool(state.get("apply_pipeline")),
                                          "bookmarks": bool(state.get("merge_bookmarks", True))})
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
        if not hasattr(self, "profile_menu"):
            return  # profil yönetimi arayüzden kaldırıldı; ayarlar settings.json'a otomatik kaydedilir
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
        self._tabs["Cilt Payı"].apply_paper_size()

    def _apply_gutter_preset(self, gutter: float) -> None:
        self._tabs["Cilt Payı"].apply_preset(gutter)

    def _reset_gutter_to_original(self) -> None:
        self._tabs["Cilt Payı"].reset_to_original()

    def _update_margin_preset_labels(self) -> None:
        self._tabs["Kenar Boşlukları"].update_preset_labels()

