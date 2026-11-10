"""Canlı önizleme paneli: pencere öğeleri, durum, üretim iş parçacığı ve sayfa gezinmesi.

``PreviewPanel`` önizlemeyle ilgili her şeyin sahibidir (``history`` dahil); kabukla
yalnızca dar bir ``PreviewHost`` yüzeyi üzerinden konuşur: önizlenecek dosya, geçerli
ayar, arayüz iş parçacığına dönüş ve birkaç hizmet. Böylece panel gerçek pencere
olmadan sahte bir ev sahibiyle denenebilir (``tests/test_preview_panel.py``).

Kabuk ``preview_mode``, ``_preview_gen`` gibi eski adları geçiş süresince
``forward`` ile panele yönlendirir (2.9/2.8'de kalkar).
"""

from __future__ import annotations

import io
import os
import threading
from typing import Any, Callable, List, Optional, Protocol

from PIL import Image

from ui import qt_compat as ctk

from gutter_engine import (config_to_dict, format_clip_group, group_clip_lines,
                           render_plain_preview, render_preview)
from ui.preview_canvas import PreviewCanvas, fit_size  # noqa: F401  (fit_size dışa aktarılır)
from ui.theme import *  # noqa: F401,F403

# Titremeyi önlemek için son birkaç PhotoImage tutulur; 6-8 yeterlidir, fazlası büyük
# sayfalarda gereksiz bellek harcar.
PREVIEW_HISTORY_LIMIT = 8
# Üretim çözünürlüğü: panelde küçültülerek gösterildiğinde yazılar keskin kalsın.
PREVIEW_ZOOM = 2.5
from gutter_engine import PDF_LOCK
PDF_RENDER_LOCK = PDF_LOCK



_SEQ_CACHE: dict = {"key": None, "path": None}

def _drop_sequence_cache() -> None:
    path = _SEQ_CACHE.get("path")
    _SEQ_CACHE.update(key=None, path=None)
    if path:
        try:
            os.remove(path)
        except OSError:
            pass


def render_sequence_preview(items: list, counts: list, fit: Any, config: Any,
                            wanted: tuple, zoom: float = PREVIEW_ZOOM) -> list:
    """Tüm birleşik dizinin sayfalarını (dosya sınırı işaretli) çizer.

    Dosyalar döndürme ve sayfa aralığıyla geçici bir PDF'te birleştirilir; kopya, dosya
    listesi aynı kaldıkça önbellekte durur, sayfa çevirmek hızlı olur. Sonuç ayarları
    (``config``) ya da eşitleme (``fit``) birleşik belge üzerinden uygulanır; bu yüzden
    numara, cilt yönü ve "ilk/en büyük sayfa" eşitlemesi gerçek çıktıyla birebirdir.
    """
    import atexit
    import tempfile
    from gutter_engine import merge_pdfs
    key = tuple((str(i["path"]), os.stat(str(i["path"])).st_mtime_ns, int(i.get("rotation", 0)),
                 str(i.get("page_range", "") or "")) for i in items)
    if _SEQ_CACHE["key"] != key or not _SEQ_CACHE["path"] or not os.path.exists(_SEQ_CACHE["path"]):
        first_time = _SEQ_CACHE["path"] is None
        _drop_sequence_cache()
        fd, tmp = tempfile.mkstemp(prefix=".~seq-", suffix=".pdf")
        os.close(fd)
        merge_pdfs([{"path": i["path"], "rotation": int(i.get("rotation", 0)),
                     "pages": str(i.get("page_range", "") or "")} for i in items],
                   tmp, quality_mode="print")
        _SEQ_CACHE.update(key=key, path=tmp)
        if first_time:
            atexit.register(_drop_sequence_cache)
    path = _SEQ_CACHE["path"]
    if config is not None:
        pages = render_preview(path, config, pages=wanted, zoom=zoom)
    else:
        pages, _n = render_plain_preview(path, 0, "", pages=wanted, zoom=zoom, fit=fit)
    starts, total = [], 0
    for count in counts:
        starts.append(total)
        total += count
    for page in pages:
        source_index = page.page_index
        if config is not None and config.page_numbers.enabled and config.page_numbers.sections:
            from gutter_engine import numbering_sections
            blanks = numbering_sections(config)[1]
            if source_index in blanks:
                page.caption = f"{source_index + 1}. sayfa  •  Boş bölüm ayıracı"
                continue
            source_index -= sum(blank < page.page_index for blank in blanks)
        for number, (start, count) in enumerate(zip(starts, counts)):
            if start <= source_index < start + count:
                local = source_index - start + 1
                name = os.path.basename(str(items[number]["path"]))
                mark = "▶ " if local == 1 else ""
                page.caption = f"{page.page_index + 1}. sayfa  •  {mark}{name} ({local}/{count})"
                break
    return pages


def render_merge_result_preview(path: str, rotation: int, page_range: str, config: Any,
                                wanted: tuple, zoom: float = PREVIEW_ZOOM) -> list:
    """Birleştirme + aktif ayarlar seçiliyken seçili dosyanın SONUÇ önizlemesi.

    Dosya döndürme ve sayfa aralığıyla geçici bir PDF'e alınır; ayarlar (cilt, boşluk,
    numara, eşitleme) bu kopyaya uygulanarak çizilir. Numara/cilt yönü dosyanın kendi
    sayfa sırasına göredir (birleşik belgedeki konumu değil).
    """
    import tempfile
    from gutter_engine import merge_pdfs
    fd, tmp = tempfile.mkstemp(prefix=".~prev-", suffix=".pdf")
    os.close(fd)
    try:
        merge_pdfs([{"path": path, "rotation": int(rotation or 0), "pages": str(page_range or "")}],
                   tmp, quality_mode="print")
        return render_preview(tmp, config, pages=wanted, zoom=zoom)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass

class PreviewHost(Protocol):
    """Panelin pencereden beklediği her şey; ``AppPreviewHost`` ve test sahtesi sağlar."""

    log: Any

    @property
    def orig_page_count(self) -> int: ...
    def source_path(self) -> str: ...
    def build_config(self) -> Any: ...
    def run_on_ui(self, callback: Callable[[], None]) -> None: ...
    def after(self, ms: int, callback: Callable[[], None]) -> Any: ...
    def after_cancel(self, after_id: Any) -> None: ...
    def bind_wraplength(self, label: Any, container: Any, padding: int) -> None: ...
    def appearance_color(self, color: Any) -> str: ...
    def scan_for_clipping(self) -> None: ...


class AppPreviewHost:
    """Gerçek pencereye bağlı ``PreviewHost``; her okuma pencereden canlı yapılır."""

    def __init__(self, app: Any):
        self._app = app

    @property
    def log(self) -> Any:
        return self._app.log

    @property
    def orig_page_count(self) -> int:
        from gutter_engine import numbering_sections
        config = self._app._build_config(notify=False)
        blanks = numbering_sections(config)[1] if config and config.page_numbers.enabled else set()
        return self._app.orig_page_count + len(blanks)

    def source_path(self) -> str:
        return self._app._preview_source_path()

    def build_config(self) -> Any:
        return self._app._build_config(notify=False)

    def item_count(self, item: dict) -> int:
        """Dosyanın sayfa aralığı uygulanmış sayfa sayısı."""
        return self._app._tabs["Birleştirme"].item_count(item)

    def sequence_items(self) -> Optional[list]:
        """"Tüm birleşik diziyi gez" açıksa var olan dosyalar, değilse ``None``."""
        app = self._app
        if "Birleştirme" not in app.tabview.get():
            return None
        merge = app._tabs["Birleştirme"]
        config = app._build_config(notify=False) if merge.built and merge.chk_merge_apply_pipeline.get() == 1 else None
        sections_active = config is not None and config.page_numbers.enabled and bool(config.page_numbers.sections)
        if not merge.sequence_enabled() and not sections_active:
            return None
        items = merge.existing_items()
        return items or None

    def merge_item(self) -> Optional[dict]:
        """Birleştirme sekmesinde seçili dosya (yoksa ``None``).

        Dizi gezintisinde seçim olmasa da ilk dosya döner (önizleme kaynağı için).
        """
        app = self._app
        if "Birleştirme" in app.tabview.get():
            index = app.selected_merge_idx
            if index is not None and 0 <= index < len(app.merge_files):
                item = app.merge_files[index]
                if os.path.exists(str(item.get("path", "") or "")):
                    return item
            seq = self.sequence_items()
            if seq:
                return seq[0]
        return None

    @property
    def preview_page_count(self) -> int:
        seq = self.sequence_items()
        if seq:
            merge = self._app._tabs["Birleştirme"]
            total = sum(merge.item_count(entry) for entry in seq)
            if merge.chk_merge_apply_pipeline.get() == 1:
                from gutter_engine import numbering_sections
                config = self._app._build_config(notify=False)
                if config and config.page_numbers.enabled:
                    total += len(numbering_sections(config)[1])
            return total
        item = self.merge_item()
        if item is not None:
            return self._app._tabs["Birleştirme"].item_count(item)
        return self.orig_page_count

    def preview_variant(self) -> Optional[tuple]:
        item = self.merge_item()
        if item is None:
            return None
        merge = self._app._tabs["Birleştirme"]
        fit = None
        pipeline = None
        if merge.chk_merge_apply_pipeline.get() == 1:
            config = self._app._build_config(notify=False)
            if config is not None and (config.page_boxes.enabled or config.margins.enabled
                                       or config.page_numbers.enabled or config.fit_mode != "off"):
                pipeline = repr(config_to_dict(config))
        elif merge.chk_merge_fit.get() == 1:
            config = merge.merge_fit_config()
            fit = (config.fit_mode, config.fit_keep_orientation, config.fit_rotate_landscape,
                   config.fit_width_mm, config.fit_height_mm, config.fit_margin_mm)
        seq_key = None
        seq = self.sequence_items()
        if seq:
            seq_key = tuple(
                (os.path.abspath(str(e["path"])), os.stat(str(e["path"])).st_mtime_ns,
                 int(e.get("rotation", 0)), str(e.get("page_range", "") or ""))
                for e in seq)
        return (int(item.get("rotation", 0)), str(item.get("page_range", "") or ""), fit, pipeline,
                seq_key)

    def run_on_ui(self, callback: Callable[[], None]) -> None:
        self._app._ui(callback)

    def after(self, ms: int, callback: Callable[[], None]) -> Any:
        return self._app.after(ms, callback)

    def after_cancel(self, after_id: Any) -> None:
        self._app.after_cancel(after_id)

    def bind_wraplength(self, label: Any, container: Any, padding: int) -> None:
        self._app._bind_wraplength(label, container, padding)

    def appearance_color(self, color: Any) -> str:
        return self._app._apply_appearance_mode(color)

    def scan_for_clipping(self) -> None:
        self._app._scan_for_clipping()


class PreviewPanel:
    """Önizleme kartı ve önizleme üretimi."""

    def __init__(self, host: PreviewHost):
        self.host = host
        # Durum pencere öğelerinden önce de geçerlidir (sekmeler kurulurken ``schedule`` çağrılır).
        self.mode = "spread"
        self.page = 0
        self.gen = 0
        # Üretimler sıraya girer; sırası gelen eski üretim kendini iptal eder (bkz. refresh).
        self._render_lock = PDF_RENDER_LOCK
        self.after_id: Optional[Any] = None
        self.signature: Optional[Any] = None
        self.images: List[Any] = []
        self.history: List[Any] = []
        self._decoded: list = []
        self.slots: list = []
        self.image_frame: Any = None
        self.preview_mode_menu: Any = None
        self.preview_prev_btn: Any = None
        self.preview_next_btn: Any = None
        self.preview_page_label: Any = None
        self.preview_jump_entry: Any = None
        self.preview_info: Any = None
        self.preview_warning: Any = None
        # Gösterim kipi düğmeleri; kabuk işleyicileri bağlar (yerleşik/pencere/tam alan).
        self.display_handler: Optional[Callable[[str], None]] = None
        self.pin_handler: Optional[Callable[[], None]] = None
        self.display_mode = "docked"
        self.btn_full: Any = None
        self.btn_window: Any = None
        self.btn_pin: Any = None

    def _total(self) -> int:
        """Gezinilen belgenin sayfa sayısı (birleştirmede seçili dosyanınki)."""
        count = getattr(self.host, "preview_page_count", None)
        return int(count if count is not None else self.host.orig_page_count)

    def _variant(self) -> Optional[tuple]:
        """Birleştirme önizlemesinde seçili dosyanın (döndürme, sayfa aralığı) değeri."""
        getter = getattr(self.host, "preview_variant", None)
        return getter() if callable(getter) else None

    def invalidate_fit(self) -> None:
        """Panel başka bir üst öğeye taşındığında tuvaller yeniden boyanır (ölçekleme boyuta göre)."""
        for _slot, canvas, _caption in self.slots:
            canvas.update()

    def _request_display(self, target: str) -> None:
        if self.display_handler is None:
            return
        # Aynı düğme etkinken tekrar basılırsa yerleşik kipe dönülür.
        self.display_handler("docked" if self.display_mode == target else target)

    def set_display_state(self, mode: str, on_top: bool) -> None:
        """Düğme yazılarını ve 'Üstte tut' görünürlüğünü kipe göre günceller."""
        self.display_mode = mode
        if self.btn_full is None:
            return
        self.btn_full.configure(text="Küçült" if mode == "fullscreen" else "Tam ekran")
        self.btn_window.configure(text="Yerleştir" if mode == "window" else "Pencerede aç")
        if mode == "window":
            self.btn_pin.place_restore()
            self.btn_pin.configure(
                text="Üstte tut: açık" if on_top else "Üstte tut: kapalı",
                fg_color=COLOR_SELECTED if on_top else COLOR_SUBCARD)
        else:
            self.btn_pin.grid_remove()

    # -- Kabuk işleri ---------------------------------------------------------
    def cancel_pending(self) -> None:
        """Bekleyen gecikmeli yenilemeyi iptal eder (pencere kapanırken)."""
        if self.after_id is not None:
            try:
                self.host.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None

    def invalidate(self) -> None:
        """Uçuştaki üretimin sonucunu geçersiz kılar (iş başlarken)."""
        self.gen += 1

    def reset_for_new_document(self) -> None:
        self.page = 0
        self.signature = None
        self.gen += 1
        self.clear("Önizleme hazırlanıyor...")
        self.update_nav()

    def apply_theme(self) -> None:
        """Görüntü etiketlerinin düz Tk arka planını tema rengine uyarlar."""
        try:
            bg = self.host.appearance_color(COLOR_CARD)
            for _slot, image_label, _caption in self.slots:
                image_label.configure(bg=bg)
        except Exception:
            pass

    # =====================================================================
    # Canlı önizleme paneli
    # =====================================================================
    def build(self, parent) -> None:
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=8,
                        border_width=1, border_color=COLOR_BORDER)
        self.card = card
        card.place(0, 3, valign="fill", expand_x=True, expand_y=True)
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(3, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.set_padding(0, 0, 0, 0, spacing=4)
        # Kartın kenar boşluğu açık yazıldı: eskiden ilk çocuğun padx/pady değerinden türüyordu.
        head.place(0, 0, expand_x=True, margins=(12, 10, 12, 2))
        head.grid_columnconfigure(3, weight=1)
        ctk.CTkLabel(
            head, text="Canlı önizleme",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).place(0, 0, columnspan=4, align="w")

        def _head_button(text, column, command):
            button = ctk.CTkButton(
                head, text=text, height=24,
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
                fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
                border_width=1, border_color=COLOR_BORDER,
                hover_color=COLOR_BTN_SUBTLE_HOVER, corner_radius=6, command=command,
            )
            button.place(1, column, align="w")
            return button

        self.btn_full = _head_button("Tam ekran", 0, lambda: self._request_display("fullscreen"))
        self.btn_window = _head_button("Pencerede aç", 1, lambda: self._request_display("window"))
        self.btn_pin = _head_button("Üstte tut: açık", 2,
                                    lambda: self.pin_handler() if self.pin_handler else None)
        self.btn_pin.grid_remove()
        subtitle = ctk.CTkLabel(
            card, text="Çift sayfa: 1-2, 3-4 ...; cilt şeridi, paylar ve numara konumu işaretli.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=300,
        )
        subtitle.place(1, 0, expand_x=True)
        self.host.bind_wraplength(subtitle, card, 30)

        self.preview_mode_menu = ctk.CTkSegmentedButton(
            card, values=["Tek sayfa", "Çift sayfa"], height=26,
            border_width=0, fg_color=COLOR_SUBCARD, bg_color=COLOR_CARD,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_SUBCARD, unselected_hover_color=COLOR_BTN_SUBTLE_HOVER,
            text_color=COLOR_TEXT_PRIMARY, corner_radius=6,
            command=self.on_mode_changed,
        )
        self.preview_mode_menu.set("Çift sayfa")
        self.preview_mode_menu.place(2, 0, expand_x=True)

        image_frame = ctk.CTkFrame(card, fg_color="transparent")
        image_frame.place(3, 0, valign="fill", expand_x=True, expand_y=True)
        self.image_frame = image_frame
        image_frame.grid_columnconfigure(0, weight=1, uniform="preview")
        image_frame.grid_columnconfigure(1, weight=1, uniform="preview")
        image_frame.grid_rowconfigure(0, weight=1)
        self.slots = []
        for column in (0, 1):
            slot = ctk.CTkFrame(image_frame, fg_color=COLOR_CARD, corner_radius=4,
                                border_width=1, border_color=COLOR_BORDER)
            slot.place(0, column, valign="fill", expand_x=True, expand_y=True)
            slot.grid_columnconfigure(0, weight=1)
            slot.grid_rowconfigure(0, weight=1)
            # Görüntü, alanına oranlı ``paintEvent`` ile sığdırılır (bkz. ``PreviewCanvas``);
            # panel serbestçe küçülüp büyüyebilir, yeniden örnekleme beklenmez.
            image_label = PreviewCanvas(slot, bg=self.host.appearance_color(COLOR_CARD))
            image_label.place(0, 0, valign="fill", expand_x=True, expand_y=True)
            caption = ctk.CTkLabel(
                slot, text="—", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
                text_color=COLOR_TEXT_SECONDARY,
            )
            caption.place(1, 0, align="c")
            self.slots.append((slot, image_label, caption))

        nav = ctk.CTkFrame(card, fg_color="transparent")
        self.nav = nav
        nav.place(4, 0, expand_x=True)
        nav.grid_columnconfigure(1, weight=1)
        self.preview_prev_btn = ctk.CTkButton(
            nav, text="‹ Önceki", width=84, height=26,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, command=self.previous,
        )
        self.preview_prev_btn.place(0, 0, align="w")
        center = ctk.CTkFrame(nav, fg_color="transparent")
        center.place(0, 1, align="c")
        self.preview_page_label = ctk.CTkLabel(
            center, text="—", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY,
        )
        self.preview_page_label.put("h")
        self.preview_jump_entry = ctk.CTkEntry(
            center, width=48, height=24, placeholder_text="Git",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            fg_color=COLOR_CARD, border_color=COLOR_BORDER, text_color=COLOR_TEXT_PRIMARY,
        )
        self.preview_jump_entry.put("h")
        self.preview_jump_entry.bind("<Return>", lambda _e: self.jump_from_entry())
        self.preview_next_btn = ctk.CTkButton(
            nav, text="Sonraki ›", width=84, height=26,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, command=self.next_page,
        )
        self.preview_next_btn.place(0, 2, align="e")

        self.preview_info = ctk.CTkLabel(
            card, text="Belge seçildiğinde önizleme burada görünür.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=320,
        )
        self.preview_info.place(5, 0, valign="n", expand_x=True)
        self.host.bind_wraplength(self.preview_info, card, 36)

        self.preview_warning = ctk.CTkLabel(
            card, text="", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY, weight="bold"),
            text_color=COLOR_ERROR, anchor="w", justify="left", wraplength=320,
        )
        self.preview_warning.place(6, 0, expand_x=True)
        self.host.bind_wraplength(self.preview_warning, card, 36)

        legend = ctk.CTkFrame(card, fg_color="transparent")
        legend.place(7, 0, expand_x=True)
        legend._ensure_layout("pack_h").setSpacing(SP_M)
        for color, text in ((COLOR_ACCENT, "cilt payı"), (COLOR_OK, "alt/üst pay"),
                            (COLOR_ERROR, "kırpma riski")):
            # Her kutucuk kendi etiketine bitişik (kendi çerçevesinde); öğeler arası boşluk
            # çerçeveler arasındadır, fazla genişlik sağdaki esnek dolguya gider (P2-35).
            item = ctk.CTkFrame(legend, fg_color="transparent")
            item._ensure_layout("pack_h").setSpacing(SP_XS)
            ctk.CTkLabel(item, text="■", text_color=color,
                         font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL)).put("h")
            ctk.CTkLabel(item, text=text,
                         font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
                         text_color=COLOR_TEXT_SECONDARY).put("h")
            item.put("h")
        legend._ensure_layout("pack_h").addStretch(1)
        self.legend = legend

        preview_buttons = ctk.CTkFrame(card, fg_color="transparent")
        self.preview_buttons = preview_buttons
        preview_buttons.place(8, 0, expand_x=True)
        preview_buttons.grid_columnconfigure(0, weight=1)
        self.detach_images()
        preview_buttons.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(
            preview_buttons, text="Önizlemeyi yenile", height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, corner_radius=6,
            command=self.refresh_now,
        ).place(0, 0, expand_x=True)
        ctk.CTkButton(
            preview_buttons, text="Kırpma riskini tara", height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, corner_radius=6,
            command=self.host.scan_for_clipping,
        ).place(0, 1, expand_x=True)

        self.apply_layout()
        self.update_nav()

        view_tools = ctk.CTkFrame(card, fg_color="transparent")
        self.view_tools = view_tools
        view_tools.place(9, 0, expand_x=True)
        for column, (text, action) in enumerate((
            ("−", lambda canvas: canvas.zoom_by(1 / 1.25)),
            ("+", lambda canvas: canvas.zoom_by(1.25)),
            ("Döndür", lambda canvas: canvas.rotate_view()),
            ("Sığdır", lambda canvas: canvas.reset_view()),
        )):
            ctk.CTkButton(view_tools, text=text, width=54, height=26,
                          command=lambda action=action: [action(canvas) for _, canvas, _ in self.slots]
                          ).place(0, column, align="w")
        self._compare_source = False
        self.compare_menu = ctk.CTkSegmentedButton(
            view_tools, values=["Önce", "Sonra"], height=26,
            command=self._set_comparison)
        self.compare_menu.set("Sonra")
        self.compare_menu.place(1, 0, columnspan=4, expand_x=True)
        view_tools.setToolTip("Yakınlaştırma: Ctrl + fare tekerleği. Yakınlaştırınca sürükleyerek gezin. Döndür yalnız görünümü değiştirir.")
        self.view_tools.hide()

    def _set_comparison(self, value):
        self._compare_source = value == "Önce"
        self.signature = None
        self.refresh_now()

    # =====================================================================
    # Önizleme ve tarama
    # =====================================================================
    def schedule(self) -> None:
        if self.after_id is not None:
            try:
                self.host.after_cancel(self.after_id)
            except Exception:
                pass
        self.after_id = self.host.after(300, self.refresh)

    def refresh_now(self) -> None:
        if self.after_id is not None:
            try:
                self.host.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None
        path = self.host.source_path()
        if not path or not os.path.exists(path):
            self.clear("Belge seçildiğinde önizleme burada görünür.")
            return
        self.signature = None
        self.preview_info.configure(text="Önizleme yenileniyor...", text_color=COLOR_TEXT_SECONDARY)
        self.refresh()

    def refresh(self) -> None:
        self.after_id = None
        path = self.host.source_path()
        if not path or not os.path.exists(path):
            self.signature = None
            self.clear("Belge seçildiğinde önizleme burada görünür.")
            return
        variant = self._variant()
        last = getattr(self, "_last_path", None)
        self._last_path = path
        if last is not None and path != last and variant is not None:
            self.page = 0  # birleştirmede başka dosya seçildi: ilk sayfadan başla
        config = self.host.build_config() if variant is None else None
        merge_config = (self.host.build_config()
                        if variant is not None and len(variant) > 3 and variant[3] else None)
        seq_items, seq_counts = None, None
        if variant is not None and len(variant) > 4 and variant[4]:
            seq_items = [dict(e) for e in self.host.sequence_items() or []]
            seq_counts = [self.host.item_count(e) for e in seq_items]
            self.page = max(0, min(self.page, max(sum(seq_counts) - 1, 0)))
            self.normalize_page()
        elif variant is not None:
            total_now = self._total()
            if total_now > 0:           # aralık kısalınca eski sayfa sınır dışında kalmasın
                self.page = max(0, min(self.page, total_now - 1))
                self.normalize_page()
        if config is None and variant is None:
            self.preview_info.configure(text="Önizleme için ayarları düzeltin.",
                                        text_color=COLOR_WARN)
            return
        try:
            stat = os.stat(path)
            stamp = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            stamp = (0, 0)
        signature = (os.path.abspath(path), stamp,
                     self.mode, self.page, variant,
                     repr(config_to_dict(config)) if config is not None else None)
        if signature == self.signature and self.images:
            return
        self.signature = signature
        self.gen += 1
        generation = self.gen

        wanted = self.wanted_pages()
        compare_source = getattr(self, "_compare_source", False)
        zoom = self._render_zoom()

        def worker():
            with self._render_lock:
                # Beklerken yeni bir üretim istendiyse bu sonuç zaten atılacaktır: hiç başlama.
                if generation != self.gen:
                    return
                try:
                    if compare_source and variant is not None and len(variant) > 4 and variant[4]:
                        pages = render_sequence_preview(seq_items, seq_counts, None, None, wanted, zoom)
                    elif compare_source:
                        pages, _n = render_plain_preview(
                            path, variant[0] if variant else 0, variant[1] if variant else "",
                            pages=wanted, zoom=PREVIEW_ZOOM)
                    elif variant is not None and len(variant) > 4 and variant[4]:
                        pages = render_sequence_preview(
                            seq_items, seq_counts, variant[2], merge_config, wanted, zoom)
                    elif variant is not None and len(variant) > 3 and variant[3]:
                        pages = render_merge_result_preview(
                            path, variant[0], variant[1], merge_config, wanted, zoom)
                    elif variant is not None:
                        pages, _n = render_plain_preview(
                            path, variant[0], variant[1], pages=wanted, zoom=zoom,
                            fit=variant[2] if len(variant) > 2 else None)
                    else:
                        pages = render_preview(path, config, pages=wanted, zoom=zoom)
                except Exception as exc:
                    message = str(exc)
                    self.host.log.warning("Önizleme üretilemedi: %s", message)
                    self.host.run_on_ui(lambda message=message: self.show(generation, [], message))
                    return
            self.host.run_on_ui(lambda: self.show(generation, pages, None))

        threading.Thread(target=worker, daemon=True).start()

    def wanted_pages(self) -> tuple:
        """Gösterilecek sayfa indeksleri (0 tabanlı).

        Çift sayfa: (1-2), (3-4) ... ; sayfa sayısı tekse son sayfa tek başına görünür.
        ``page`` çift sayfa modunda açılımın ilk sayfasıdır (her zaman çift indeks).
        """
        if self.mode == "single":
            return (self.page,)
        total = self._total()
        if self.page + 1 < total:
            return (self.page, self.page + 1)
        return (self.page,)

    def slot_for(self, page: Any) -> int:
        """Çift sayfa modunda açılımın ilk sayfası 0. slota, ikincisi 1. slota oturur."""
        if self.mode == "single":
            return 0
        return 0 if page.page_index == self.page else 1

    def normalize_page(self) -> None:
        """Çift sayfa modunda ``page`` açılım başına (çift indeks) çekilir."""
        if self.mode == "spread" and self.page % 2 == 1:
            self.page -= 1

    def _blank_slot(self, image_label, caption) -> None:
        try:
            image_label.set_placeholder(self.mode)
        except Exception:
            pass
        try:
            caption.configure(text="—")
        except Exception:
            pass

    def detach_images(self) -> None:
        """Etiketleri boş görüntüye alır; eski görüntüler oturum boyunca saklanır."""
        for _slot, image_label, caption in self.slots:
            self._blank_slot(image_label, caption)
        self.images.clear()
        self._decoded = []

    def clear(self, message: str) -> None:
        self.detach_images()
        # Boş durumda gezinme, kip, açıklama ve eylemler görünür kalır; yalnız
        # yakınlaştırma araçları belge açılana kadar gizlenir.
        self.view_tools.hide()
        self.preview_info.configure(text=message, text_color=COLOR_TEXT_SECONDARY)
        self.preview_warning.configure(text="")

    def show(self, generation: int, pages, error: Optional[str]) -> None:
        if generation != self.gen:
            return
        if error:
            self.signature = None
            self.clear(f"Önizleme üretilemedi: {error}")
            return
        if not pages:
            self.clear("Önizleme için sayfa bulunamadı.")
            return

        self.detach_images()
        self.view_tools.show()
        decoded = []
        for page in pages[:2]:
            try:
                image = Image.open(io.BytesIO(page.png))
                image.load()
            except Exception:
                continue
            decoded.append((image, page, self.slot_for(page)))
        self._decoded = decoded
        self.fit_images()

        first = pages[0]
        info = (f"{first.width_mm:.1f} × {first.height_mm:.1f} mm  •  ölçek %{first.scale * 100:.0f}")
        if first.number_text:
            info += f"  •  numara: {first.number_text}"
        self.preview_info.configure(text=info, text_color=COLOR_TEXT_PRIMARY)

        # Aynı değerli ardışık sayfalar tek satırda aralıkla gösterilir (P2-35).
        entries = []
        for page in pages[:2]:
            if page.clipped:
                edges = ", ".join(
                    f"{name} {value:.1f} mm"
                    for name, value in zip(("sol", "sağ", "üst", "alt"), page.clip_mm)
                    if value > 0
                )
                entries.append((page.page_index + 1, edges))
        warnings = [format_clip_group(*g) + " taşıyor."
                    for g in group_clip_lines(entries)]
        if warnings:
            self.preview_warning.configure(text="Kırpma riski - " + " ".join(warnings))
        else:
            self.preview_warning.configure(text="")
        self.update_nav()

    def _render_zoom(self) -> float:
        """Görünür sayfa genişliğine göre üretim ölçeği (1,5×–2,5×).

        Küçük panelde gereksiz büyük pixmap üretilmez; geniş panelde yazı keskin kalır.
        """
        try:
            canvas = self.slots[0][1]
            width = max(int(canvas.width()), 1) * float(canvas.devicePixelRatioF())
            return max(2.0, min(PREVIEW_ZOOM, width / 595.0 * 1.6))
        except Exception:
            return 2.0

    def fit_images(self) -> None:
        """Çözülmüş sayfaları tuvallere atar; oranlı sığdırmayı tuvaller boyarken yapar.

        Adı geçmişten kalmadır: artık yeniden örnekleme yoktur, her sayfa bir kez
        ``QPixmap`` olur ve panel boyutu değişince ``PreviewCanvas`` kendini ölçekler.
        """
        items = self._decoded
        if not items:
            return
        self.images.clear()
        by_slot = {slot_index: (image, page) for image, page, slot_index in items}
        for slot_index, (_slot, image_label, caption) in enumerate(self.slots):
            if slot_index not in by_slot:
                self._blank_slot(image_label, caption)
                continue
            image, page = by_slot[slot_index]
            photo = ctk.pil_to_pixmap(image)
            self.images.append(photo)
            self.history.append(photo)
            if len(self.history) > PREVIEW_HISTORY_LIMIT:
                del self.history[:len(self.history) - PREVIEW_HISTORY_LIMIT]
            image_label.configure(image=photo, text="")
            caption.configure(text=getattr(page, "caption", None) or f"{page.page_index + 1}. sayfa")

    def on_mode_changed(self, value: str) -> None:
        self.mode = "single" if "Tek" in value else "spread"
        self.normalize_page()
        self.detach_images()
        self.apply_layout()
        self.signature = None
        self.refresh()
        self.update_nav()

    def apply_layout(self) -> None:
        """Tek sayfa modunda ikinci slotu kaldırır, ilk önizlemeyi genişletir."""
        if not self.slots:
            return
        single = self.mode == "single"
        frame = self.image_frame
        first_slot, first_label, _ = self.slots[0]
        second_slot, second_label, _ = self.slots[1]
        if single:
            frame.grid_columnconfigure(1, weight=0)
            first_slot.place(0, 0, columnspan=2, valign="fill", expand_x=True, expand_y=True)
            second_slot.grid_remove()
        else:
            frame.grid_columnconfigure(1, weight=1)
            first_slot.place(0, 0, columnspan=1, valign="fill", expand_x=True, expand_y=True)
            second_slot.place_restore()

    def _target_page(self, delta: int, total: int) -> int:
        """``delta`` (+1/-1) yönündeki sayfa/açılım başlangıcı; sınır aşılırsa mevcut sayfa."""
        stride = 1 if self.mode == "single" else 2
        candidate = self.page + delta * stride
        if candidate < 0 or candidate > total - 1:
            return self.page
        return candidate

    def step(self, delta: int) -> None:
        total = self._total()
        if total <= 0:
            return
        candidate = self._target_page(delta, total)
        if candidate == self.page:
            return
        self.page = candidate
        self.signature = None
        self.refresh()
        self.update_nav()

    def go_to(self, number: int) -> bool:
        """1 tabanlı sayfa numarasına atlar (aralık dışı sınırlandırılır); değiştiyse True."""
        total = self._total()
        if total <= 0:
            return False
        target = max(1, min(int(number), total)) - 1
        before = self.page
        self.page = target
        self.normalize_page()
        changed = self.page != before
        if changed:
            self.signature = None
            self.refresh()
        self.update_nav()
        return changed

    def jump_from_entry(self) -> None:
        """"Git" kutusuna yazılan sayfa numarasına atlar; geçersiz girdi silinir."""
        text = (self.preview_jump_entry.get() or "").strip()
        try:
            number = int(text)
        except ValueError:
            number = None
        if number is not None:
            self.go_to(number)
        self.preview_jump_entry.delete(0, "end")

    def previous(self) -> None:
        self.step(-1)

    def next_page(self) -> None:
        self.step(1)

    def update_nav(self) -> None:
        if self.preview_page_label is None:
            return
        total = self._total()
        if total <= 0:
            self.preview_page_label.configure(text="—")
            self.preview_prev_btn.configure(state="disabled")
            self.preview_next_btn.configure(state="disabled")
            return
        self.page = max(0, min(self.page, total - 1))
        self.normalize_page()
        if self.mode == "single":
            text = f"{self.page + 1} / {total}"
        else:
            end = min(self.page + 1, total - 1)
            text = (f"{self.page + 1} / {total}" if end == self.page
                    else f"{self.page + 1}–{end + 1} / {total}")
        can_prev = self.page > 0
        can_next = self._target_page(1, total) != self.page
        self.preview_page_label.configure(text=text)
        self.preview_prev_btn.configure(state="normal" if can_prev else "disabled")
        self.preview_next_btn.configure(state="normal" if can_next else "disabled")
