"""Modül anahtarları ve alt çubuktaki işlem hattı özeti."""

from __future__ import annotations

import os

from ui.theme import *  # noqa: F401,F403


class PipelineMixin:
    """Üç modülün topluca açılıp kapanması ve eylem çubuğunun durum özeti."""

    def _update_all_modules_button(self) -> None:
        if not hasattr(self, "btn_all_modules"):
            return
        all_off = not any(self._module_switch(key).get() == 1 for key in ("gutter", "margin", "pnum"))
        self.btn_all_modules.configure(text="Tümünü aç" if all_off else "Tümünü kapat")

    def _toggle_all_modules(self) -> None:
        target_on = not any(self._module_switch(key).get() == 1 for key in ("gutter", "margin", "pnum"))
        for key in ("gutter", "margin", "pnum"):
            switch = self._module_switch(key)
            switch.select() if target_on else switch.deselect()
        self._toggle_gutter_fields()
        self._toggle_margin_fields()
        self._toggle_pnum_fields()
        self._update_all_modules_button()

    def _disable_all_modules(self) -> None:
        for key in ("gutter", "margin", "pnum"):
            self._module_switch(key).deselect()
        self._toggle_gutter_fields()
        self._toggle_margin_fields()
        self._toggle_pnum_fields()
        self._update_all_modules_button()

    def _fit_active(self) -> bool:
        """Yalnız "Sayfaları eşitle" seçili mi? (Modül anahtarı olmadan da bir işlemdir.)"""
        try:
            if not self._tab_built("Sayfa Düzeni"):
                return False
            layout = self._tabs["Sayfa Düzeni"]
            return FIT_LABELS.get(layout.menu_fit.get(), "off") != "off"
        except Exception:
            return False

    def _sync_tab_enabled(self, key: str) -> None:
        """Modül anahtarı kapalıysa ilgili sekme içeriğini devre dışı bırakır.

        Sayfa Düzeni'nde cilt payı ve boşluk anahtarları sekmenin içindedir; bütün
        sekmeyi kilitlemek anahtarların kendisini de kilitlerdi. Yalnızca Sayfa
        Numaraları sekmesi eski davranışı korur.
        """
        if key != "pnum":
            return
        frame = self._tab_frames_map.get("Sayfa Numaraları")
        if frame is not None:
            frame.setEnabled(self._module_switch("pnum").get() == 1)

    def _update_pipeline_summary(self) -> None:
        if not hasattr(self, "pill_gutter") or not hasattr(self, "tabview"):
            return

        has_single_source = bool(self.input_pdf_path and os.path.exists(self.input_pdf_path))
        merge_count = len(self._tabs["Birleştirme"].files)
        has_any_job = has_single_source or merge_count > 0 or bool(self.output_pdf_path)
        self.btn_new_job.setVisible(has_any_job)
        output_exists = bool(self.output_pdf_path and os.path.isfile(self.output_pdf_path))
        self.btn_open_pdf.setVisible(output_exists and not self._busy)
        self.btn_open_tools.setVisible(output_exists and not self._busy)
        self.btn_open_folder.setVisible(output_exists and not self._busy)
        self.btn_cancel.setVisible(self._busy)

        if "Birleştirme" in self.tabview.get():
            apply_pipeline = self._tabs["Birleştirme"].chk_merge_apply_pipeline.get() == 1
            can_merge = merge_count >= 2
            if not can_merge:
                self.action_title_label.configure(text="Birleştirme için dosyalar bekleniyor")
                self._set_status(
                    "Birleştirmek için en az 2 PDF ekleyin."
                    if merge_count == 0 else "Birleştirmek için bir PDF daha ekleyin.")
            elif apply_pipeline:
                self.action_title_label.configure(text="Birleşik hat: birleştirme + aktif modüller")
                self._set_status("Dosyalar birleştirildikten sonra diğer sekmelerdeki ayarlar uygulanır.")
            else:
                self.action_title_label.configure(text="PDF birleştirme işlemi")
                self._set_status("Dosyalar sıraları ve rotasyonlarıyla kayıpsız birleştirilecek.")
            self.btn_main_action.configure(
                state="disabled" if (self._busy or not can_merge) else "normal",
                text=("En az 2 PDF ekleyin" if not can_merge else
                      ("Birleştir ve aktif ayarları uygula" if apply_pipeline else "PDF'leri birleştir ve kaydet")),
                command=self._start_merging,
            )
            self.btn_preflight.setVisible(can_merge and not self._busy)
            return

        has_gutter = self._module_switch("gutter").get() == 1
        if has_gutter:
            try:
                gutter = self._row_mm(self._layout_tab().f_odd_x)
                self.pill_gutter.configure(text=f" Cilt: {gutter:.1f} mm ",
                                           fg_color=("#DDF4FF", "#0C2D4A"), text_color=COLOR_ACCENT)
            except Exception:
                self.pill_gutter.configure(text=" Cilt: açık ", fg_color=COLOR_SUBCARD,
                                           text_color=COLOR_TEXT_SECONDARY)
        else:
            self.pill_gutter.configure(text=" Cilt: kapalı ", fg_color=COLOR_SUBCARD,
                                       text_color=COLOR_TEXT_SECONDARY)

        has_margin = self._module_switch("margin").get() == 1
        if has_margin:
            parts = []
            try:
                bottom = self._margin_mm("bottom")
                top = self._margin_mm("top")
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

        has_pnum = self._module_switch("pnum").get() == 1
        self.pill_pnum.configure(
            text=" Sayfa no: açık " if has_pnum else " Sayfa no: kapalı ",
            fg_color=COLOR_OK_BG if has_pnum else COLOR_SUBCARD,
            text_color=COLOR_OK if has_pnum else COLOR_TEXT_SECONDARY,
        )

        has_fit = self._fit_active()
        active_count = sum([has_gutter, has_margin, has_pnum, has_fit])
        if not has_single_source:
            self.action_title_label.configure(text="Başlamak için PDF seçin")
            self._set_status("Önce soldan PDF seçin; ardından ayarları gözden geçirip çıktı oluşturun.")
            text = "Önce PDF seçin"
        elif active_count >= 2:
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
        elif has_fit:
            self.action_title_label.configure(text="Sayfa eşitleme işlemi")
            self._set_status("Yalnızca sayfa ebatları eşitlenecek (cilt payı/boşluk/numara yok).")
            text = "Eşitlenmiş PDF oluştur"
        else:
            self.action_title_label.configure(text="İşlem durumu")
            self._set_status("Lütfen bir işlem modülünü etkinleştirin veya sayfaları eşitleyin.")
            text = "En az bir modülü etkinleştirin"

        self.btn_main_action.configure(
            state="disabled" if (self._busy or active_count == 0 or not has_single_source) else "normal",
            text=text, command=self._start_processing,
        )
        self.btn_preflight.setVisible(not self._busy and has_single_source and active_count > 0)
