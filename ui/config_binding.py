"""Ayar okuma/yazma ve profiller: arayüz alanları ↔ ``PdfProcessConfig`` köprüsü.

``app.py``'den birebir taşındı (davranış değişikliği yok). Sınıf, ``ModernGutterApp`` içinde
karışım (mixin) olarak kullanılır; sekme alanları (``f_width``, ``seg_pos`` vb.) ilgili sekmede durur (``_layout_tab()``, ``_number_tab()``, ``_merge_tab()``).

Tembel kurulum (2.9): Sayfa Numaraları ve Birleştirme sekmeleri ilk gösterilene kadar
kurulmaz. O zamana kadar ayarın o sekmeye düşen bölümü ``_pending_sections``
içinde bekler; ``_build_config`` değeri oradan okur, sekme kurulunca widget'lara yazılır.
Sayfa Düzeni (açılış sekmesi; cilt payı + boşluk + ebat + özel sayfalar) her zaman kuruludur.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ui import qt_compat as ctk  # noqa: F401
from ui.qt_compat import messagebox

import page_layout_model as plm
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


LAYOUT_TAB = "Sayfa Düzeni"
NUMBER_TAB = "Sayfa Numaraları"
MERGE_TAB = "Birleştirme"

#: modül anahtarı -> pencere/sekme üzerindeki anahtar widget'ı
MODULE_SWITCHES = {"gutter": "switch_gutter", "margin": "switch_margin", "pnum": "switch_pnum"}


def field_row_names(tab) -> tuple:
    """Birim değişiminde dolaşılacak alan satırı adları (sekmenin ``FIELD_ROWS`` listesi)."""
    return tuple(getattr(type(tab), "FIELD_ROWS", ()))


class ConfigBindingMixin:

    # =====================================================================
    # Tembel sekmeler (2.9)
    # =====================================================================
    def _layout_tab(self):
        """Sayfa Düzeni sekmesi (gerekirse kurulur). Üretim kodu alanlara köprü takma adı
        (``f_width`` gibi) yerine bunun üzerinden erişir (P3-16, 2. parça)."""
        tab = self._tabs[LAYOUT_TAB]
        tab.ensure_built()
        return tab

    def _number_tab(self):
        """Sayfa Numaraları sekmesi (alanları ``tab.f_font_size`` vb.); gerekirse kurulur."""
        tab = self._tabs[NUMBER_TAB]
        tab.ensure_built()
        return tab

    def _merge_tab(self):
        """Birleştirme sekmesi (``tab.chk_merge_bookmarks`` vb.); gerekirse kurulur."""
        tab = self._tabs[MERGE_TAB]
        tab.ensure_built()
        return tab

    def _module_switch(self, key: str):
        """Modül anahtarı: kabuk (yan menü) bunları kendi özniteliği olarak kurar."""
        attr = MODULE_SWITCHES[key]
        switch = self.__dict__.get(attr)
        if switch is None:
            raise AttributeError(f"Modül anahtarı bulunamadı: {attr}")
        return switch

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
        if name == NUMBER_TAB:
            return {"numbers": PageNumberSettings()}
        return {"apply_pipeline": False, "bookmarks": True}

    def _set_section(self, name: str, data: Dict[str, Any]) -> None:
        """Ayar bölümünü kurulu sekmeye yazar, kurulmamışsa bekletir."""
        if name == LAYOUT_TAB:
            return  # Sayfa Düzeni açılışta kurulur; bekleyen bölümü yoktur.
        if self._tab_built(name):
            self._write_section(name, data)
        else:
            self._pending()[name] = data

    def _write_section(self, name: str, data: Dict[str, Any]) -> None:
        if name == NUMBER_TAB:
            numbers = data["numbers"]
            nt = self._tabs[NUMBER_TAB]
            nt.seg_pos.set(POSITION_CODES.get(numbers.position, "Dış kenar (Tek sağ / Çift sol)"))
            nt.menu_format.set(FORMAT_CODES.get(numbers.format_style, "1, 2, 3"))
            nt.f_font_size.set_value(f"{numbers.font_size:g}")
            nt.f_start_page.set_value(str(numbers.start_page))
            nt.f_start_num.set_value(str(numbers.start_num))
            nt.f_num_bottom.set_mm(numbers.bottom_margin_mm)
            nt.f_num_side.set_mm(numbers.side_margin_mm)
            nt.entry_skip_pages.delete(0, "end")
            nt.entry_skip_pages.insert(0, numbers.skip_pages_str)
            nt.entry_number_template.delete(0, "end")
            nt.entry_number_template.insert(0, numbers.text_template)
            nt.chk_continuous.select() if numbers.continuous_numbering else nt.chk_continuous.deselect()
            nt.section_editor.set_sections(numbers.sections)
            # "Alt orta" konumunda yan boşluk alanı pasif, ipucu görünür (yüklenen ayarda da).
            nt.update_side_state()
        else:
            mt = self._tabs[MERGE_TAB]
            mt.chk_merge_apply_pipeline.select() if data["apply_pipeline"] else mt.chk_merge_apply_pipeline.deselect()
            mt.chk_merge_bookmarks.select() if data["bookmarks"] else mt.chk_merge_bookmarks.deselect()

    def _on_tab_built(self, tab) -> None:
        """Sekme kurulunca: gösterim birimi, bekleyen ayar."""
        for attr in field_row_names(tab):
            row = getattr(tab, attr, None)
            if isinstance(row, FieldRow):
                row.reset_unit(self.unit)
        data = self._pending().pop(tab.name, None)
        if data is None:
            return
        self._write_section(tab.name, data)
        self._on_field_changed()

    def _shown_mm(self, mm: float) -> float:
        """Değerin alanda gösterilip geri okunmuş hâli (kurulu sekmeyle aynı yuvarlama)."""
        try:
            return unit_to_mm(float(format_measure(mm, self.unit).replace(",", ".")), self.unit)
        except (TypeError, ValueError):
            return mm

    def _margin_mm(self, which: str) -> float:
        """Alt ("bottom") ya da üst ("top") pay, mm; sekme henüz kurulmadıysa 0."""
        tab = self._tabs.get(LAYOUT_TAB)
        if tab is not None and tab.built:
            return self._row_mm(tab.f_bottom if which == "bottom" else tab.f_top)
        return 0.0

    # =====================================================================
    # Ayar okuma / yazma (tek kaynak)
    # =====================================================================
    def _row_mm(self, row: FieldRow) -> float:
        return row.get_mm()

    def _range_entries(self) -> List[tuple]:
        """Kurulu sekmelerdeki sayfa aralığı kutuları."""
        entries = []
        if self._tab_built(NUMBER_TAB):
            entries.append(("Numarasız sayfalar", self._tabs[NUMBER_TAB].entry_skip_pages))
        return entries

    def _pending_range_texts(self) -> List[tuple]:
        """Kurulmamış sekmelerin bekleyen sayfa aralığı metinleri."""
        texts = []
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
        margin_built = self._tab_built(LAYOUT_TAB)
        number_built = self._tab_built(NUMBER_TAB)
        lt = self._layout_tab()
        nt = self._tabs[NUMBER_TAB]  # kurulu değilse yalnızca ``number_built`` ile okunur
        groups = [
            ("gutter", self._module_switch("gutter").get() == 1,
             [("width", lt.f_width), ("height", lt.f_height),
              ("safe_edge", lt.f_safe_edge), ("odd_x", lt.f_odd_x), ("odd_y", lt.f_odd_y),
              ("even_x", lt.f_even_x), ("even_y", lt.f_even_y)]),
        ]
        if margin_built:
            groups.append(("margin", self._module_switch("margin").get() == 1,
                           [("bottom", lt.f_bottom), ("top", lt.f_top)]))
        if number_built:
            groups.append(("number", self._module_switch("pnum").get() == 1,
                           [("font_size", nt.f_font_size), ("start_page", nt.f_start_page),
                            ("start_num", nt.f_start_num), ("num_bottom", nt.f_num_bottom),
                            ("num_side", nt.f_num_side)]))
        values: Dict[str, float] = {}
        groups.append(("fit_size", lt.menu_fit.get() == FIT_CODES["custom"],
                       [("fit_width", lt.f_fit_width), ("fit_height", lt.f_fit_height)]))
        groups.append(("fit_margin", lt.menu_fit.get() != FIT_CODES["off"],
                       [("fit_margin", lt.f_fit_margin)]))
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
            errors.append((nt.__dict__.get("entry_skip_pages"), problem))

        layout = self._tabs.get(LAYOUT_TAB)
        if layout is not None and layout.built:
            errors.extend(layout.check_rules())

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

        layout = self._tabs.get(LAYOUT_TAB)
        choice, loaded_pair = (layout.overflow_selection() if margin_built
                               else (plm.CHOICE_EXTEND, None))
        boxes = PageBoxSettings(
            binding=BINDING_LABELS.get(layout.menu_binding.get(), "left"),
            enabled=self._module_switch("gutter").get() == 1,
            size_mode=SIZE_MODE_LABELS.get(lt.seg_size_mode.get(), "fixed"),
            safe_edge_mm=values["safe_edge"],
            target_width_mm=values["width"],
            target_height_mm=values["height"],
            odd_x_mm=values["odd_x"],
            odd_y_mm=values["odd_y"],
            even_x_mm=values["even_x"],
            even_y_mm=values["even_y"],
        )
        if margin_built:
            values["bottom"] = layout.f_bottom.get_mm()
            values["top"] = layout.f_top.get_mm()
        else:
            values["bottom"] = values["top"] = 0.0
        margins = MarginSettings(
            enabled=self._module_switch("margin").get() == 1,
            extra_bottom_mm=values["bottom"],
            extra_top_mm=values["top"],
        )
        pad4 = layout.chk_pad4.get() == 1 if margin_built else False
        plm.write_unified(boxes, margins, choice,
                          layout.rules() if margin_built else [], loaded_pair)
        if number_built:
            position = nt.seg_pos.get()
            format_label = nt.menu_format.get()
            template = nt.entry_number_template.get().strip()
            skip_pages = nt.entry_skip_pages.get().strip()
            continuous = nt.chk_continuous.get() == 1
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
            sections=nt.section_editor.sections() if number_built else pending.sections,
            enabled=self._module_switch("pnum").get() == 1,
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
            quality_mode=self._output_quality,
            flatten_annotations=self._flatten_annotations,
            pad_to_multiple=4 if pad4 else 0,
            fit_mode=FIT_LABELS.get(layout.menu_fit.get(), "off") if margin_built else "off",
            fit_keep_orientation=layout.chk_fit_orient.get() == 1 if margin_built else True,
            fit_rotate_landscape=(layout.chk_fit_rotate.get() == 1) if margin_built else False,
            fit_width_mm=values["fit_width"],
            fit_height_mm=values["fit_height"],
            fit_margin_mm=values["fit_margin"],
        )

        validation = validate_config(config)
        if not validation.ok:
            if notify:
                messagebox.showerror("Ayarlar geçersiz", "• " + "\n• ".join(validation.errors))
            self._set_status(f"Ayar hatası: {validation.errors[0]}", COLOR_ERROR)
            return None
        if validation.warnings:
            self._set_status("Uyarı: " + plm.ui_warning(validation.warnings[0]), COLOR_WARN)
        self._last_valid_config = config
        return config

    def _apply_config(self, config: PdfProcessConfig) -> None:
        boxes, margins, numbers = config.page_boxes, config.margins, config.page_numbers
        self._module_switch("gutter").select() if boxes.enabled else self._module_switch("gutter").deselect()
        self._module_switch("margin").select() if margins.enabled else self._module_switch("margin").deselect()
        self._module_switch("pnum").select() if numbers.enabled else self._module_switch("pnum").deselect()

        layout = self._tabs[LAYOUT_TAB]
        layout.menu_binding.set(BINDING_CODES.get(boxes.binding, BINDING_CODES["left"]))
        layout.seg_size_mode.set(SIZE_MODE_CODES.get(boxes.size_mode, "Hedef ebat sabit"))

        layout.f_width.set_mm(boxes.target_width_mm)
        layout.f_height.set_mm(boxes.target_height_mm)
        layout.sync_paper_menu(boxes.target_width_mm, boxes.target_height_mm)
        layout.f_safe_edge.set_mm(boxes.safe_edge_mm)
        layout.f_odd_x.set_mm(boxes.odd_x_mm)
        layout.f_odd_y.set_mm(boxes.odd_y_mm)
        layout.f_even_x.set_mm(boxes.even_x_mm)
        layout.f_even_y.set_mm(boxes.even_y_mm)
        layout.f_bottom.set_mm(margins.extra_bottom_mm)
        layout.f_top.set_mm(margins.extra_top_mm)
        if config.pad_to_multiple == 4:
            layout.chk_pad4.select()
        else:
            layout.chk_pad4.deselect()
        layout.menu_fit.set(FIT_CODES.get(config.fit_mode, FIT_CODES["off"]))
        layout.f_fit_width.set_mm(config.fit_width_mm)
        layout.f_fit_height.set_mm(config.fit_height_mm)
        layout.f_fit_margin.set_mm(config.fit_margin_mm)
        if config.fit_keep_orientation:
            layout.chk_fit_orient.select()
        else:
            layout.chk_fit_orient.deselect()
        if config.fit_rotate_landscape and not config.fit_keep_orientation:
            layout.chk_fit_rotate.select()
        else:
            layout.chk_fit_rotate.deselect()
        layout.update_fit_state()
        state, rules = plm.read_unified(boxes, margins)
        layout.set_unified_state(state, rules, (boxes.overflow_mode, margins.bottom_mode))
        layout.update_preset_highlight()
        self._set_section(NUMBER_TAB, {"numbers": numbers})

        self._output_quality = config.quality_mode
        self._flatten_annotations = config.flatten_annotations

        self._toggle_gutter_fields()
        self._toggle_margin_fields()
        self._toggle_pnum_fields()

    def _collect_state(self) -> Dict[str, Any]:
        config = self._build_config(notify=False) or self._last_valid_config
        state = config_to_dict(config) if config else {}
        state["unit"] = self.unit
        state["theme"] = self.store.theme
        if self._tab_built(MERGE_TAB):
            merge = self._tabs[MERGE_TAB]
            state["apply_pipeline"] = merge.chk_merge_apply_pipeline.get() == 1
            state["merge_bookmarks"] = merge.chk_merge_bookmarks.get() == 1
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
                page_boxes=PageBoxSettings(enabled=True, target_width_mm=210.0,
                                           target_height_mm=297.0, odd_x_mm=15.0),
                margins=MarginSettings(enabled=True),
                page_numbers=PageNumberSettings(enabled=False),
            ))
            self._apply_gutter_preset(15.0)  # varsayılan: Cilt payı Standart (15 mm), açık
            self._toggle_margin_fields()
            self._toggle_pnum_fields()
        self._update_unit_button()

    def _apply_factory_state(self) -> None:
        """Fabrika sıfırlamadan sonra ekrandaki tüm alanları ve modülleri varsayılana getirir."""
        self._restore_settings()
        self._set_section(MERGE_TAB, {"apply_pipeline": False, "bookmarks": True})
        merge = self._tabs[MERGE_TAB]
        if merge.built:
            merge.chk_merge_fit.deselect()
            merge.restore_fit_preferences()
        self._update_pipeline_summary()
        self._schedule_preview()

    def _announce_restored_settings(self) -> None:
        """Önceki oturumdan açık modüller geldiyse durum çubuğunda bildirir (kullanıcı sürprizi)."""
        if not self.store.last_state:
            return
        names = [name for name, switch in (("Cilt", self._module_switch("gutter")),
                                           ("Boşluk", self._module_switch("margin")),
                                           ("Sayfa no", self._module_switch("pnum")))
                 if switch.get() == 1]
        if not names:
            return
        self._set_status(
            f"Önceki oturum ayarları yüklendi: {', '.join(names)} açık. "
            "Sıfırlamak için Ayarlar › Fabrika değerlerine sıfırla.",
            COLOR_TEXT_PRIMARY,
        )

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
        self._tabs[LAYOUT_TAB].apply_paper_size()

    def _apply_gutter_preset(self, gutter: float) -> None:
        self._tabs[LAYOUT_TAB].apply_preset(gutter)

    def _reset_gutter_to_original(self) -> None:
        self._tabs[LAYOUT_TAB].reset_to_original()

    def _update_margin_preset_labels(self) -> None:
        self._tabs[LAYOUT_TAB].update_preset_labels()

