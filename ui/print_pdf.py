"""Doğrudan PDF yazdırma yardımcısı (PySide6 QPrintDialog + PyMuPDF tam ölçekli çizim)."""

from __future__ import annotations

import os
from typing import Optional

import pymupdf
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QPainter
from PySide6.QtPrintSupport import QPrintDialog, QPrinter

from core.gutter_engine import PDF_LOCK, open_pdf
from ui.i18n import tr
from ui.qt_compat import messagebox


def render_page_qimage(page: pymupdf.Page, dpi: int) -> QImage:
    """Sayfayı verilen DPI çözünürlüğünde RGB ``QImage`` olarak üretir."""
    scale = max(72, min(600, int(dpi))) / 72.0
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    qimg = QImage(
        pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888
    )
    return qimg.copy()


def compute_centered_target_rect(
    src_w: float, src_h: float, paint_w: float, paint_h: float
) -> QRectF:
    """Sayfayı yazdırılabilir alana kırpmadan ve sol-üste kaydırmadan tam ortalı sığdırır."""
    if src_w <= 0 or src_h <= 0 or paint_w <= 0 or paint_h <= 0:
        return QRectF(0.0, 0.0, max(0.0, paint_w), max(0.0, paint_h))
    scale = min(paint_w / src_w, paint_h / src_h)
    dw = src_w * scale
    dh = src_h * scale
    dx = (paint_w - dw) / 2.0
    dy = (paint_h - dh) / 2.0
    return QRectF(dx, dy, dw, dh)


def print_pdf_to_printer(pdf_path: str, printer: QPrinter, password: Optional[str] = None) -> int:
    """PDF belgesini yapılandırılmış ``QPrinter`` hedefine basar; basılan sayfa sayısını döndürür."""
    with PDF_LOCK, open_pdf(pdf_path, password=password) as doc:
        total = len(doc)
        if total == 0:
            return 0

        first_rect = doc[0].rect
        is_landscape = first_rect.width > first_rect.height
        printer.setPageOrientation(
            QPageLayout.Orientation.Landscape if is_landscape else QPageLayout.Orientation.Portrait
        )

        if printer.printRange() == QPrinter.PrintRange.PageRange:
            start_page = max(1, min(total, printer.fromPage() or 1))
            end_page = max(start_page, min(total, printer.toPage() or total))
        else:
            start_page, end_page = 1, total

        indices = list(range(start_page - 1, end_page))
        if printer.pageOrder() == QPrinter.PageOrder.LastPageFirst:
            indices.reverse()

        dpi = max(150, min(600, int(printer.resolution() or 300)))
        painter = QPainter()
        if not painter.begin(printer):
            raise RuntimeError(tr("Yazıcı başlatılamadı."))
        try:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            printed = 0
            for pos, page_idx in enumerate(indices):
                page = doc[page_idx]
                page_landscape = page.rect.width > page.rect.height
                if pos > 0:
                    printer.setPageOrientation(
                        QPageLayout.Orientation.Landscape
                        if page_landscape
                        else QPageLayout.Orientation.Portrait
                    )
                    if not printer.newPage():
                        break
                qimg = render_page_qimage(page, dpi)
                vp = painter.viewport()
                target = compute_centered_target_rect(
                    float(qimg.width()), float(qimg.height()),
                    float(vp.width()), float(vp.height()),
                )
                painter.drawImage(target, qimg)
                printed += 1
            return printed
        finally:
            painter.end()


def print_pdf_with_dialog(parent, pdf_path: str) -> bool:
    """Sistem yazdırma diyaloğunu açar ve onaylanırsa PDF'i yazdırır."""
    if not pdf_path or not os.path.isfile(pdf_path):
        messagebox.showwarning(tr("Yazdır"), tr("Yazdırılacak geçerli bir PDF dosyası bulunamadı."))
        return False

    try:
        with PDF_LOCK, open_pdf(pdf_path) as doc:
            total = len(doc)
            first_rect = doc[0].rect
    except Exception as exc:
        messagebox.showerror(tr("Yazdır"), f"{tr('PDF açılamadı')}:\n{exc}")
        return False

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setDocName(os.path.basename(pdf_path))
    printer.setFullPage(False)
    if first_rect.width > first_rect.height:
        printer.setPageOrientation(QPageLayout.Orientation.Landscape)
    else:
        printer.setPageOrientation(QPageLayout.Orientation.Portrait)
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))

    dialog = QPrintDialog(printer, parent)
    dialog.setWindowTitle(f"{tr('Yazdır')} — {os.path.basename(pdf_path)}")
    dialog.setMinMax(1, max(1, total))
    if dialog.exec() != QPrintDialog.DialogCode.Accepted:
        return False

    try:
        count = print_pdf_to_printer(pdf_path, printer)
    except Exception as exc:
        messagebox.showerror(tr("Yazdırma hatası"), str(exc))
        return False
    return count > 0
