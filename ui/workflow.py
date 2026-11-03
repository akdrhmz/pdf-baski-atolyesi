"""İşleme, tarama, ilerleme ve sonuç akışı."""

from __future__ import annotations

import os
import threading
import traceback
from typing import List

from ui.qt_compat import filedialog, messagebox

HAS_WINDND = True

from gutter_engine import (
    ProcessCancelled,
    process_pdf,
    scan_clipping,
    unique_output_path,
    verify_output,
)
from ui.theme import *  # noqa: F401,F403


class WorkflowMixin:
    """İşleme, tarama, ilerleme ve sonuç akışı."""

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
            self._update_safe_edge_state()
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

    def _begin_work(self, message: str) -> None:
        self._busy = True
        self._cancel_event.clear()
        self.preview_panel.invalidate()
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
