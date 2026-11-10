"""Birleştirme işi: doğrulama, kayıt yeri, arka plan iş parçacığı, kırpma onayı, geçici dosya.

Liste ve arayüz ``ui/tabs/merge.py`` içindeki ``MergeTab``'dadır; burada yalnızca
"Birleştir" eyleminin iş akışı var (``WorkflowMixin`` ile aynı türden: ilerleme,
iptal ve sonuç kabuğun ortak yöntemleriyle yürür).
"""

from __future__ import annotations

import os
import tempfile
import threading
import traceback
from typing import List

from ui.qt_compat import filedialog, messagebox

from gutter_engine import (
    ProcessCancelled,
    FIT_MODES,
    PdfProcessConfig,
    build_fitted_pdf,
    get_pdf_info,
    merge_pdfs,
    process_pdf,
    scan_clipping,
    unique_output_path,
    verify_output,
)
from ui.theme import *  # noqa: F401,F403


class MergeJobMixin:
    """Birleştirme eylemi ve arka plan işçisi."""

    @property
    def merge_tab(self):
        return self._tabs["Birleştirme"]

    def _discard_pending_merge(self) -> None:
        """Kırpma onayı için saklanan geçici birleşik dosyayı siler."""
        pending = getattr(self, "_pending_merge", None)
        self._pending_merge = None
        if pending and pending[0] and os.path.exists(pending[0]):
            try:
                os.remove(pending[0])
            except OSError:
                pass

    def _start_merging(self) -> None:
        if self._busy:
            return
        if len(self.merge_tab.files) < 2:
            messagebox.showwarning("Uyarı", "Birleştirmek için en az 2 PDF ekleyin.")
            return

        bad_ranges = self.merge_tab.invalid_range_lines()
        if bad_ranges:
            messagebox.showerror("Sayfa aralığı geçersiz",
                                 "Şu dosyaların sayfa aralığı anlaşılamadı:\n\n"
                                 + "\n".join(f"• {line}" for line in bad_ranges[:10])
                                 + "\n\nÖrnek: 1-3, 7, 10-12")
            return
        self._discard_pending_merge()
        apply_pipeline = self.merge_tab.chk_merge_apply_pipeline.get() == 1
        if not apply_pipeline and self.merge_tab.chk_merge_fit.get() == 1 and self.merge_tab._fit_error:
            messagebox.showerror("Eşitleme ayarları", self.merge_tab._fit_error)
            return
        config = None
        if apply_pipeline:
            config = self._build_config(notify=True)
            if config is None:
                return
            if not (config.page_boxes.enabled or config.margins.enabled
                    or config.page_numbers.enabled or config.fit_mode != "off"):
                messagebox.showwarning(
                    "Uyarı", "Birleşik hat için en az bir modülü etkinleştirin ya da "
                             "\"Sayfaları eşitle\" seçin.")
                return

        first_dir = os.path.dirname(self.merge_tab.files[0]["path"])
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
        items = self.merge_tab.worker_items()
        optimize = self._output_quality != "print"
        add_bookmarks = self.merge_tab.chk_merge_bookmarks.get() == 1
        fit_plain = self.merge_tab.chk_merge_fit.get() == 1 and not apply_pipeline
        fit_config = self.merge_tab.merge_fit_config()
        fit_config.flatten_annotations = self._flatten_annotations
        expected_pages = self.merge_tab.expected_pages()
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
                    if fit_plain:
                        self._set_phase("Sayfalar eşitleniyor", 0.0)
                        fd, fitted = tempfile.mkstemp(
                            prefix=".~fit-", suffix=".pdf.tmp",
                            dir=os.path.dirname(os.path.abspath(output_path)))
                        os.close(fd)
                        try:
                            build_fitted_pdf(output_path, fitted, fit_config,
                                             should_cancel=self._cancel_event.is_set)
                            os.replace(fitted, output_path)
                        finally:
                            if os.path.exists(fitted):
                                os.remove(fitted)
                    info = get_pdf_info(output_path)
                    lines = []
                    if info["page_count"] == expected_pages:
                        lines.append(f"✔ {info['page_count']} sayfa birleştirildi")
                    else:
                        lines.append(f"✘ Beklenen {expected_pages} sayfa, çıktı {info['page_count']} sayfa")
                    lines.extend("• " + w for w in warnings)
                    self._ui(lambda: self._on_success(None, lines))
                    return

                pending, self._pending_merge = self._pending_merge, None
                if pending and not scan_first and os.path.exists(pending[0]):
                    temp_path = pending[0]       # onay sonrası ikinci birleştirme yok
                    warnings.extend(pending[1])
                else:
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
                        self._pending_merge = (temp_path, list(warnings))
                        temp_path = ""           # finally silmesin; onay bekliyor
                        self._ui(lambda: self._confirm_merge_clip(report))
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
                self._ui(lambda: self._on_success(report, warnings))
            except ProcessCancelled:
                self._ui(self._on_cancelled)
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
            self._discard_pending_merge()
            self._end_work("Birleştirme iptal edildi. Çıktı oluşturulmadı.", COLOR_WARN)
            return
        if action == "shrink" and not self._switch_to_shrink():
            self._discard_pending_merge()
            self._end_work("Kırpma önlenemedi. Ayarları kontrol edin.", COLOR_WARN)
            return
        self._begin_work("Birleştiriliyor...")
        self._start_merge_worker(scan_first=False)
