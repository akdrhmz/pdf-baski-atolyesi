"""Modül anahtarları ve alt çubuktaki işlem hattı özeti."""

from __future__ import annotations

from ui.theme import *  # noqa: F401,F403


class PipelineMixin:
    """Üç modülün topluca açılıp kapanması ve eylem çubuğunun durum özeti."""

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

    def _sync_tab_enabled(self, key: str) -> None:
        """Modül anahtarı kapalıysa ilgili sekme içeriğini devre dışı bırakır."""
        switch, tab_name = {
            "gutter": (self.switch_gutter, "Cilt Payı"),
            "margin": (self.switch_margin, "Kenar Boşlukları"),
            "pnum": (self.switch_pnum, "Sayfa Numaraları"),
        }[key]
        frame = self._tab_frames_map.get(tab_name)
        if frame is not None:
            frame.setEnabled(switch.get() == 1)

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
