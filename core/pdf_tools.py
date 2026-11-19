"""Sayfa düzenleme, damga ve baskı montajı; kaynak dosyaları değiştirmez."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math

import pymupdf

from core.gutter_engine import (open_pdf, same_path, OutputPathError, ConfigError, ProcessCancelled,
                           _atomic_save, mm_to_pt, normalize_page_rotations, fit_matrix,
                           PageNumberSettings, resolve_number_font, sanitize_toc, unique_output_path,
                           pdf_operation, parse_page_ranges, invalid_range_tokens)


def _check_output(source, output):
    if same_path(str(source), str(output)):
        raise OutputPathError("Kaynak dosyanın üzerine yazılamaz.")


@pdf_operation
def export_pages(source, output, pages, should_cancel=None):
    """Verilen sıralı (0 tabanlı sayfa, ek döndürme) çiftlerini dışa aktarır."""
    _check_output(source, output)
    with open_pdf(str(source)) as doc:
        selected = [(int(page), int(rotation) % 360) for page, rotation in pages]
        if not selected or any(not 0 <= page < len(doc) or rotation % 90 for page, rotation in selected):
            raise ConfigError(["En az bir geçerli sayfa seçin; döndürme 90 derecenin katı olmalı."])
        toc = doc.get_toc()
        mapping = {}
        for target, (original, _) in enumerate(selected):
            mapping.setdefault(original, target)
        doc.select([page for page, _ in selected])
        for index, (_, rotation) in enumerate(selected):
            if should_cancel and should_cancel():
                raise ProcessCancelled("İşlem iptal edildi.")
            page = doc[index]
            page.set_rotation((page.rotation + rotation) % 360)
        new_toc = [[level, title, mapping[page - 1] + 1] for level, title, page in toc if page - 1 in mapping]
        doc.set_toc(sanitize_toc(new_toc))
        _atomic_save(doc, str(output), False)
    return str(output)


def split_pages(source, folder, pages, group_size=1, should_cancel=None):
    """Düzenlenen sayfaları eşit büyüklükte parçalara ayırır; son parça kısa olabilir."""
    if group_size < 1:
        raise ConfigError(["Parça başına sayfa sayısı en az 1 olmalı."])
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    outputs = []
    for index, start in enumerate(range(0, len(pages), group_size), 1):
        if should_cancel and should_cancel():
            raise ProcessCancelled(f"İptal edildi; {len(outputs)} tamamlanan parça korundu.")
        target = unique_output_path(str(folder / f"{Path(source).stem}_parca_{index:03d}.pdf"))
        outputs.append(export_pages(source, target, pages[start:start + group_size], should_cancel))
    return outputs


@dataclass
class StampOptions:
    watermark: str = ""
    opacity: float = 0.18
    angle: int = 45
    font_size: float = 40.0
    color: tuple[float, float, float] = (0.4, 0.4, 0.4)
    page_range: str = ""
    bates_prefix: str = ""
    bates_suffix: str = ""
    bates_start: int = 1
    bates_digits: int = 6
    bates_enabled: bool = False
    bates_position: str = "bottom_left"  # bottom_left, bottom_center, bottom_right, top_left, top_right


def _bates_point(rect: pymupdf.Rect, position: str, text_width: float, font_size: float) -> pymupdf.Point:
    margin_x = min(mm_to_pt(10), rect.width * 0.1)
    margin_y = min(mm_to_pt(8), rect.height * 0.1)
    if position == "bottom_right":
        return pymupdf.Point(max(margin_x, rect.width - margin_x - text_width), rect.height - margin_y)
    if position == "bottom_center":
        return pymupdf.Point(max(margin_x, (rect.width - text_width) / 2), rect.height - margin_y)
    if position == "top_left":
        return pymupdf.Point(margin_x, margin_y + font_size)
    if position == "top_right":
        return pymupdf.Point(max(margin_x, rect.width - margin_x - text_width), margin_y + font_size)
    return pymupdf.Point(margin_x, rect.height - margin_y)


def _apply_stamp_to_page(page: pymupdf.Page, index: int, options: StampOptions,
                         font_info, font_name: str, font_args: dict) -> None:
    if options.watermark:
        rect = page.rect
        text = options.watermark
        size = options.font_size
        length = (font_info[1].text_length(text, fontsize=size) if font_info else
                  pymupdf.get_text_length(text, fontsize=size))
        # Uzun damga tek sayfaya sığsın; Unicode font gerçek genişliği kullanılır.
        scale = min(1, rect.width * 0.8 / max(length, 1))
        size *= scale
        length *= scale
        center = rect.tl + (rect.br - rect.tl) * 0.5
        point = pymupdf.Point(center.x - length / 2, center.y + size / 3)
        page.insert_text(point, text, fontsize=size, fontname=font_name, **font_args,
                         color=tuple(options.color), fill_opacity=options.opacity,
                         morph=(center, pymupdf.Matrix(options.angle)), overlay=True)
    if options.bates_enabled:
        text = f"{options.bates_prefix}{options.bates_start + index:0{options.bates_digits}d}{options.bates_suffix}"
        length = (font_info[1].text_length(text, fontsize=10) if font_info else
                  pymupdf.get_text_length(text, fontsize=10))
        margin = min(mm_to_pt(10), page.rect.width * 0.1)
        size = 10 * min(1, (page.rect.width - 2 * margin) / max(length, 1))
        if size < 4:
            raise ConfigError(["Bates metni sayfaya okunabilir boyutta sığmıyor; ön/son eki kısaltın."])
        scaled_len = length * (size / 10.0)
        pt = _bates_point(page.rect, options.bates_position, scaled_len, size)
        page.insert_text(pt, text, fontsize=size, fontname=font_name, **font_args, overlay=True)


@pdf_operation
def stamp_pdf(source, output, options, should_cancel=None):
    _check_output(source, output)
    if not (0 <= options.opacity <= 1 and 4 <= options.font_size <= 200
            and 1 <= options.bates_digits <= 20 and options.bates_start >= 0):
        raise ConfigError(["Damga saydamlığı, punto veya Bates numarası geçersiz."])
    if options.page_range and invalid_range_tokens(options.page_range):
        raise ConfigError(["Sayfa aralığı geçersiz."])
    target_pages = parse_page_ranges(options.page_range) if options.page_range.strip() else None
    strings = [options.watermark, options.bates_prefix + options.bates_suffix]
    font_info = resolve_number_font(PageNumberSettings(), strings)
    if not font_info and any(ord(c) > 127 for s in strings for c in s):
        raise ConfigError(["Damga için Unicode destekli bir yazı tipi bulunamadı."])
    font_name = "STUDIOSTAMP" if font_info else "helv"
    font_args = {"fontfile": font_info[0]} if font_info else {}
    with open_pdf(str(source)) as doc:
        normalize_page_rotations(doc)
        bates_counter = 0
        for index, page in enumerate(doc):
            if should_cancel and should_cancel():
                raise ProcessCancelled("İşlem iptal edildi.")
            if target_pages is not None and (index + 1) not in target_pages:
                continue
            _apply_stamp_to_page(page, bates_counter, options, font_info, font_name, font_args)
            bates_counter += 1
        _atomic_save(doc, str(output), False)
    return str(output)


@dataclass
class PrintOptions:
    mode: str = "2up"  # 2up, 4up, booklet, marks
    width_mm: float = 297.0
    height_mm: float = 210.0
    margin_mm: float = 5.0
    gap_mm: float = 2.0
    bleed_mm: float = 0.0
    crop_marks: bool = False
    creep_mm: float = 0.0
    signature_size: int = 0   # 0 = tek forma; >0 = 4'ün katı forma boyutu (örn. 8, 16, 32)
    divider_line: bool = False
    rtl: bool = False


def booklet_order(total: int, signature_size: int = 0, rtl: bool = False):
    """Ön/arka yüzler art arda; None boş sayfadır, kısa kenardan çift taraflı baskı."""
    if total <= 0:
        return []
    sig = int(signature_size or 0)
    if sig <= 0 or sig >= total:
        chunks = [(0, total)]
    else:
        sig = max(4, ((sig + 3) // 4) * 4)
        chunks = [(start, min(start + sig, total)) for start in range(0, total, sig)]
    order = []
    for start, end in chunks:
        chunk_len = end - start
        padded = ((chunk_len + 3) // 4) * 4
        for sheet in range(padded // 4):
            front = [padded - 1 - 2 * sheet, 2 * sheet]
            back = [2 * sheet + 1, padded - 2 - 2 * sheet]
            if rtl:
                front = [front[1], front[0]]
                back = [back[1], back[0]]
            for pair in (front, back):
                order.append([start + p if p < chunk_len else None for p in pair])
    return order


def _divider_lines(page: pymupdf.Page, extra: float, margin: float,
                   cell_w: float, cell_h: float, gap: float,
                   columns: int, rows: int, width: float, height: float) -> None:
    if columns == 2:
        x = extra + margin + cell_w + gap / 2.0
        page.draw_line((x, extra + margin), (x, extra + height - margin),
                       color=(0.65, 0.65, 0.65), width=0.4, dashes="[3 3] 0")
    if rows == 2:
        y = extra + margin + cell_h + gap / 2.0
        page.draw_line((extra + margin, y), (extra + width - margin, y),
                       color=(0.65, 0.65, 0.65), width=0.4, dashes="[3 3] 0")


def _crop_marks(page, trim):
    length, gap = mm_to_pt(3), mm_to_pt(1)
    for x in (trim.x0, trim.x1):
        for y, sign in ((trim.y0, -1), (trim.y1, 1)):
            page.draw_line((x, y + sign * gap), (x, y + sign * (gap + length)), width=0.3)
    for y in (trim.y0, trim.y1):
        for x, sign in ((trim.x0, -1), (trim.x1, 1)):
            page.draw_line((x + sign * gap, y), (x + sign * (gap + length), y), width=0.3)


@pdf_operation
def impose_pdf(source, output, options, should_cancel=None):
    _check_output(source, output)
    values = (options.width_mm, options.height_mm, options.margin_mm, options.gap_mm,
              options.bleed_mm, options.creep_mm)
    if (not all(math.isfinite(value) for value in values) or min(values) < 0
            or min(options.width_mm, options.height_mm) < 10 or max(values) > 2000
            or options.mode not in ("2up", "4up", "booklet", "marks")):
        raise ConfigError(["Baskı montajı ayarları geçersiz."])
    with open_pdf(str(source)) as src, pymupdf.open() as out:
        normalize_page_rotations(src)
        page_links = [page.get_links() for page in src]
        src.bake(annots=True, widgets=True)
        total = len(src)
        columns, rows = (2, 2) if options.mode == "4up" else (2, 1)
        if options.mode == "marks":
            groups = [[i] for i in range(total)]
            columns = rows = 1
        elif options.mode == "booklet":
            if options.signature_size < 0 or (options.signature_size > 0 and options.signature_size % 4 != 0):
                raise ConfigError(["Forma boyutu 0 (tek forma) veya 4'ün katı olmalı."])
            groups = booklet_order(total, options.signature_size, options.rtl)
        else:
            size = columns * rows
            groups = [list(range(start, min(start + size, total))) for start in range(0, total, size)]
        placement = {}
        sig_sheets = max(1, options.signature_size // 4) if options.signature_size > 0 else 0
        for side, group in enumerate(groups):
            if should_cancel and should_cancel():
                raise ProcessCancelled("İşlem iptal edildi.")
            extra = mm_to_pt(options.bleed_mm + (4 if options.crop_marks else 0))
            if options.mode == "marks":
                trim = src[group[0]].rect
                width, height = trim.width, trim.height
                margin, gap = 0.0, 0.0
            else:
                width, height = mm_to_pt(options.width_mm), mm_to_pt(options.height_mm)
                margin, gap = mm_to_pt(options.margin_mm), mm_to_pt(options.gap_mm)
            cell_w = (width - 2 * margin - (columns - 1) * gap) / columns
            cell_h = (height - 2 * margin - (rows - 1) * gap) / rows
            if min(cell_w, cell_h) <= 1:
                raise ConfigError(["Kenar payı ve aralık seçilen kâğıda sığmıyor."])
            page = out.new_page(width=width + 2 * extra, height=height + 2 * extra)
            mb = page.mediabox
            trim = pymupdf.Rect(extra, extra, extra + width, extra + height) & mb
            bleed = pymupdf.Rect(
                trim.x0 - mm_to_pt(options.bleed_mm),
                trim.y0 - mm_to_pt(options.bleed_mm),
                trim.x1 + mm_to_pt(options.bleed_mm),
                trim.y1 + mm_to_pt(options.bleed_mm),
            ) & mb
            page.set_trimbox(trim)
            page.set_bleedbox(bleed)
            for slot, source_page in enumerate(group):
                if source_page is None:
                    continue
                col, row = slot % columns, slot // columns
                if options.rtl and options.mode in ("2up", "4up"):
                    col = (columns - 1) - col
                x, y = extra + margin + col * (cell_w + gap), extra + margin + row * (cell_h + gap)
                creep = 0.0
                if options.mode == "booklet":
                    sheet_idx = (side // 2) % sig_sheets if sig_sheets else (side // 2)
                    # İçteki yapraklarda içeriği sırta doğru kaydır; değer yaprak başınadır.
                    creep = mm_to_pt(options.creep_mm) * sheet_idx * (1 if col == 0 else -1)
                if abs(creep) >= cell_w / 2:
                    raise ConfigError(["Kitapçık kayma telafisi hücre genişliği için çok büyük."])
                source_rect = src[source_page].rect
                matrix = fit_matrix(source_rect.width, source_rect.height, cell_w, cell_h)
                matrix.e += x + creep
                matrix.f += y
                dest = source_rect * matrix
                # Kayma nedeniyle hücre dışında kalan içerik komşu sayfaya taşmasın.
                if dest.x0 < x or dest.x1 > x + cell_w:
                    safe_w = cell_w - 2 * abs(creep)
                    matrix = fit_matrix(source_rect.width, source_rect.height, safe_w, cell_h)
                    matrix.e += x + abs(creep) + creep
                    matrix.f += y
                    dest = source_rect * matrix
                if src[source_page].get_contents():
                    page.show_pdf_page(dest, src, source_page)
                placement[source_page] = (side, matrix)
            if options.crop_marks:
                _crop_marks(page, trim)
            if options.divider_line and options.mode in ("2up", "4up", "booklet"):
                _divider_lines(page, extra, margin, cell_w, cell_h, gap, columns, rows, width, height)
        for original, (target, matrix) in placement.items():
            for link in page_links[original]:
                item = dict(link)
                item.pop("xref", None)
                item.pop("id", None)
                item["from"] = item["from"] * matrix
                dest = item.get("page", -1)
                if item.get("kind") == pymupdf.LINK_GOTO:
                    if dest not in placement:
                        continue
                    item["page"], dest_matrix = placement[dest]
                    if isinstance(item.get("to"), pymupdf.Point):
                        item["to"] = item["to"] * dest_matrix
                out[target].insert_link(item)
        toc = [[level, title, placement[p - 1][0] + 1] for level, title, p in src.get_toc() if p - 1 in placement]
        out.set_toc(sanitize_toc(toc))
        if src.metadata:
            out.set_metadata(src.metadata)
        _atomic_save(out, str(output), False)
    return str(output)


@dataclass
class SecurityMetaOptions:
    """PDF meta veri, parola güvenliği ve görsel sıkıştırma ayarları."""
    title: str = ""
    author: str = ""
    subject: str = ""
    keywords: str = ""
    clear_metadata: bool = False
    user_password: str = ""
    owner_password: str = ""
    allow_print: bool = True
    allow_copy: bool = True
    compress_images: bool = False
    image_dpi: int = 150
    source_password: str = ""


@pdf_operation
def apply_security_and_metadata(source, output, options: SecurityMetaOptions, should_cancel=None):
    """Meta veri günceller, görselleri yeniden örnekler ve isteğe bağlı AES-256 parola uygular."""
    import os
    import tempfile

    _check_output(source, output)
    if options.compress_images and not (36 <= options.image_dpi <= 600):
        raise ConfigError(["Görsel DPI değeri 36 ile 600 arasında olmalı."])
    doc = pymupdf.open(str(source))
    try:
        if doc.needs_pass:
            if not options.source_password or not doc.authenticate(options.source_password):
                from core.gutter_engine import PdfPasswordError
                raise PdfPasswordError("Kaynak PDF parolalı; geçerli parola gerekli.")
        if should_cancel and should_cancel():
            raise ProcessCancelled("İşlem iptal edildi.")
        if options.clear_metadata:
            doc.set_metadata({})
        else:
            meta = dict(doc.metadata or {})
            for key, value in (
                ("title", options.title),
                ("author", options.author),
                ("subject", options.subject),
                ("keywords", options.keywords),
            ):
                if value.strip():
                    meta[key] = value.strip()
            doc.set_metadata(meta)
        if options.compress_images and hasattr(doc, "rewrite_images"):
            if should_cancel and should_cancel():
                raise ProcessCancelled("İşlem iptal edildi.")
            doc.rewrite_images(
                dpi_threshold=options.image_dpi + 30,
                dpi_target=options.image_dpi,
                quality=75,
            )
        save_kwargs = {"garbage": 3, "deflate": True}
        if options.user_password or options.owner_password:
            perms = pymupdf.PDF_PERM_ACCESSIBILITY
            if options.allow_print:
                perms |= pymupdf.PDF_PERM_PRINT
            if options.allow_copy:
                perms |= pymupdf.PDF_PERM_COPY
            save_kwargs["encryption"] = pymupdf.PDF_ENCRYPT_AES_256
            save_kwargs["user_pw"] = options.user_password
            save_kwargs["owner_pw"] = options.owner_password or options.user_password
            save_kwargs["permissions"] = perms
        else:
            save_kwargs["encryption"] = pymupdf.PDF_ENCRYPT_NONE
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".~sec-", suffix=".pdf", dir=str(out_path.parent))
        os.close(fd)
        try:
            doc.save(tmp, **save_kwargs)
            os.replace(tmp, str(out_path))
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
    finally:
        doc.close()
    return str(output)


@pdf_operation
def render_tool_preview(source, tool_kind: str, options, page_index: int = 0, zoom: float = 1.4) -> bytes:
    """Damga/Bates veya baskı montajının tek sayfalık hızlı PPM önizlemesini üretir."""
    with open_pdf(str(source)) as src:
        total = len(src)
        if total == 0:
            return b""
        if tool_kind == "stamp":
            idx = max(0, min(int(page_index), total - 1))
            with pymupdf.open() as tmp:
                tmp.insert_pdf(src, from_page=idx, to_page=idx)
                normalize_page_rotations(tmp)
                strings = [options.watermark, options.bates_prefix + options.bates_suffix]
                font_info = resolve_number_font(PageNumberSettings(), strings)
                font_name = "STUDIOSTAMP" if font_info else "helv"
                font_args = {"fontfile": font_info[0]} if font_info else {}
                target_pages = parse_page_ranges(options.page_range) if getattr(options, "page_range", "").strip() else None
                if target_pages is None or (idx + 1) in target_pages:
                    _apply_stamp_to_page(tmp[0], idx, options, font_info, font_name, font_args)
                pix = tmp[0].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
                return pix.tobytes("ppm")

        if tool_kind == "impose":
            normalize_page_rotations(src)
            columns, rows = (2, 2) if options.mode == "4up" else (2, 1)
            if options.mode == "marks":
                groups = [[i] for i in range(total)]
                columns = rows = 1
            elif options.mode == "booklet":
                groups = booklet_order(total, options.signature_size, options.rtl)
            else:
                size = columns * rows
                groups = [list(range(start, min(start + size, total))) for start in range(0, total, size)]
            if not groups:
                return b""
            side = max(0, min(int(page_index), len(groups) - 1))
            group = groups[side]
            sig_sheets = max(1, options.signature_size // 4) if options.signature_size > 0 else 0
            extra = mm_to_pt(options.bleed_mm + (4 if options.crop_marks else 0))
            if options.mode == "marks":
                trim = src[group[0]].rect
                width, height = trim.width, trim.height
                margin, gap = 0.0, 0.0
            else:
                width, height = mm_to_pt(options.width_mm), mm_to_pt(options.height_mm)
                margin, gap = mm_to_pt(options.margin_mm), mm_to_pt(options.gap_mm)
            cell_w = (width - 2 * margin - (columns - 1) * gap) / columns
            cell_h = (height - 2 * margin - (rows - 1) * gap) / rows
            if min(cell_w, cell_h) <= 1:
                raise ConfigError(["Kenar payı ve aralık seçilen kâğıda sığmıyor."])
            with pymupdf.open() as out:
                page = out.new_page(width=width + 2 * extra, height=height + 2 * extra)
                trim = pymupdf.Rect(extra, extra, extra + width, extra + height)
                for slot, source_page in enumerate(group):
                    if source_page is None:
                        continue
                    col, row = slot % columns, slot // columns
                    if options.rtl and options.mode in ("2up", "4up"):
                        col = (columns - 1) - col
                    x, y = extra + margin + col * (cell_w + gap), extra + margin + row * (cell_h + gap)
                    creep = 0.0
                    if options.mode == "booklet":
                        sheet_idx = (side // 2) % sig_sheets if sig_sheets else (side // 2)
                        creep = mm_to_pt(options.creep_mm) * sheet_idx * (1 if col == 0 else -1)
                    if abs(creep) >= cell_w / 2:
                        raise ConfigError(["Kitapçık kayma telafisi hücre genişliği için çok büyük."])
                    source_rect = src[source_page].rect
                    matrix = fit_matrix(source_rect.width, source_rect.height, cell_w, cell_h)
                    matrix.e += x + creep
                    matrix.f += y
                    dest = source_rect * matrix
                    if dest.x0 < x or dest.x1 > x + cell_w:
                        safe_w = cell_w - 2 * abs(creep)
                        matrix = fit_matrix(source_rect.width, source_rect.height, safe_w, cell_h)
                        matrix.e += x + abs(creep) + creep
                        matrix.f += y
                        dest = source_rect * matrix
                    if src[source_page].get_contents():
                        page.show_pdf_page(dest, src, source_page)
                if options.crop_marks:
                    _crop_marks(page, trim)
                if options.divider_line and options.mode in ("2up", "4up", "booklet"):
                    _divider_lines(page, extra, margin, cell_w, cell_h, gap, columns, rows, width, height)
                pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
                return pix.tobytes("ppm")
    return b""
