"""PySide6 (Qt 6) temel bileşen ve pencere altyapısı.

Uygulama düzeyinde tek bir merkezi QSS ve doğal ``QPainter``/``QPalette`` çizimi
kullanır; hiçbir alt bileşende bireysel ``setStyleSheet`` derlemesi yapmaz.
Bu sayede Açık/Koyu tema değişimi, sekme geçişi ve düğme tıklamaları < 5 ms
içinde anında yanıt verir.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image
from PySide6.QtCore import QEvent, QObject, QPoint, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.theme import (
    COLOR_ACCENT,
    COLOR_BG,
    COLOR_BORDER,
    COLOR_BTN_SUBTLE,
    COLOR_BTN_SUBTLE_HOVER,
    COLOR_CARD,
    COLOR_ERROR,
    COLOR_ON_ACCENT,
    COLOR_SELECTED,
    COLOR_SELECTED_HOVER,
    COLOR_SOLID,
    COLOR_SOLID_HOVER,
    COLOR_SUBCARD,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    FONT_FAMILY,
    FS_BODY,
    FS_SMALL,
)

# ---------------------------------------------------------------------------
# QApplication tekil örnek ve Görünüm (Açık / Koyu / Sistem) yöneticisi
# ---------------------------------------------------------------------------
_APPEARANCE_MODE: str = "Light"  # "Light" | "Dark"
_APPEARANCE_CHOICE: str = "System"  # "Light" | "Dark" | "System"
_THEME_LISTENERS: List[Callable[[], None]] = []


def ensure_qapp() -> QApplication:
    """Çalışan bir ``QApplication`` örneği döndürür; yoksa oluşturur."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv if sys.argv else ["studio"])
        font = QFont(FONT_FAMILY)
        font.setPixelSize(FS_BODY)
        app.setFont(font)
        _apply_global_theme(app, _APPEARANCE_MODE)
    return app  # type: ignore[return-value]


def _detect_system_mode() -> str:
    """Windows / Qt sistem temasını ('Light' veya 'Dark') algılar."""
    if sys.platform.startswith("win"):
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return "Light" if int(val) != 0 else "Dark"
        except Exception:
            pass
    try:
        app = ensure_qapp()
        if app.styleHints().colorScheme() == Qt.ColorScheme.Dark:
            return "Dark"
    except Exception:
        pass
    return "Light"


def get_appearance_mode() -> str:
    return _APPEARANCE_MODE


def resolve_color(color: Any, mode: Optional[str] = None) -> str:
    """``(acik, koyu)`` renk çiftini veya tek renk dizgesini aktif temaya göre çözer."""
    if color is None or color == "" or color == "transparent":
        return "transparent"
    m = mode or _APPEARANCE_MODE
    if isinstance(color, (tuple, list)) and len(color) >= 2:
        return str(color[1] if m == "Dark" else color[0])
    return str(color)


def _apply_global_theme(app: QApplication, mode: str) -> None:
    """Tüm uygulama için anında ``QPalette`` uygular (< 1 ms, sıfır QSS yeniden derlemesi)."""
    bg = resolve_color(COLOR_BG, mode)
    card = resolve_color(COLOR_CARD, mode)
    subcard = resolve_color(COLOR_SUBCARD, mode)
    border = resolve_color(COLOR_BORDER, mode)
    text = resolve_color(COLOR_TEXT_PRIMARY, mode)
    text_sec = resolve_color(COLOR_TEXT_SECONDARY, mode)
    accent = resolve_color(COLOR_ACCENT, mode)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(bg))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(text))
    palette.setColor(QPalette.ColorRole.Base, QColor(card))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(subcard))
    palette.setColor(QPalette.ColorRole.Text, QColor(text))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(text_sec))
    palette.setColor(QPalette.ColorRole.Button, QColor(card))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(text))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(accent))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Mid, QColor(border))
    app.setPalette(palette)


def set_appearance_mode(mode_str: str) -> None:
    """Görünüm modunu ('Light', 'Dark', 'System') tüm pencerelere anında uygular."""
    global _APPEARANCE_CHOICE, _APPEARANCE_MODE
    norm = str(mode_str or "System").strip().capitalize()
    if norm not in ("Light", "Dark", "System"):
        norm = "System"
    _APPEARANCE_CHOICE = norm
    _APPEARANCE_MODE = _detect_system_mode() if norm == "System" else norm
    app = ensure_qapp()
    _apply_global_theme(app, _APPEARANCE_MODE)
    for listener in list(_THEME_LISTENERS):
        owner = getattr(listener, "__self__", None)
        if owner is not None and getattr(owner, "_defer_theme_refresh", False):
            owner._theme_dirty = True
            continue
        try:
            listener()
        except Exception:
            pass


def set_default_color_theme(_theme: str = "blue") -> None:
    """Uyumluluk kancası."""


def register_theme_listener(cb: Callable[[], None]) -> None:
    if cb not in _THEME_LISTENERS:
        _THEME_LISTENERS.append(cb)


def unregister_theme_listener(cb: Callable[[], None]) -> None:
    try:
        _THEME_LISTENERS.remove(cb)
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# Yazı tipi ve Görsel kapsayıcıları
# ---------------------------------------------------------------------------
class QtFont(QFont):
    """``family``, ``size`` (piksel), ``weight`` parametreleriyle ``QFont`` üretir."""

    def __init__(self, family: str = FONT_FAMILY, size: int = FS_BODY, weight: str = "normal"):
        super().__init__(family)
        self.setPixelSize(max(8, int(size)))
        if str(weight).lower() == "bold":
            self.setBold(True)


class QtImage:
    """PIL ``Image`` nesnesini istenen boyutta ``QPixmap``'e dönüştürür."""

    def __init__(
        self,
        light_image: Optional[Image.Image] = None,
        dark_image: Optional[Image.Image] = None,
        size: Tuple[int, int] = (32, 32),
    ):
        self.light_image = light_image
        self.dark_image = dark_image or light_image
        self.size = size
        self._pixmap_cache: Dict[Tuple[str, Tuple[int, int]], QPixmap] = {}

    def pixmap(self, mode: Optional[str] = None) -> QPixmap:
        ensure_qapp()
        m = mode or _APPEARANCE_MODE
        key = (m, self.size)
        if key in self._pixmap_cache:
            return self._pixmap_cache[key]
        src = self.dark_image if m == "Dark" and self.dark_image is not None else self.light_image
        if src is None:
            pm = QPixmap(self.size[0], self.size[1])
            pm.fill(Qt.GlobalColor.transparent)
            return pm
        rgba = src.convert("RGBA").resize(self.size, Image.Resampling.LANCZOS)
        data = rgba.tobytes("raw", "RGBA")
        qimg = QImage(
            data, rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888
        ).copy()
        pm = QPixmap.fromImage(qimg)
        self._pixmap_cache[key] = pm
        return pm


def pil_to_pixmap(image: Image.Image) -> QPixmap:
    """PIL görüntüsünü doğrudan ``QPixmap`` olarak döndürür."""
    ensure_qapp()
    rgba = image.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimg = QImage(
        data, rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888
    ).copy()
    return QPixmap.fromImage(qimg)


# ---------------------------------------------------------------------------
# Ortak Widget & Yerleşim Davranışı (QtWidgetMixin)
# ---------------------------------------------------------------------------
class _EventFilter(QObject):
    """Widget üzerindeki fare/klavye/boyut olaylarını bağlı Python geri çağrılarına iletir."""

    def __init__(self, owner: "QtWidgetMixin"):
        super().__init__(owner)  # type: ignore[arg-type]
        self._owner = owner

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        owner = self._owner
        etype = event.type()
        if etype == QEvent.Type.Resize:
            cbs = owner._bindings.get("<Configure>", [])
            if cbs:
                ev = SimpleNamespace(
                    widget=owner,
                    width=owner.width(),
                    height=owner.height(),
                )
                for cb in list(cbs):
                    try:
                        cb(ev)
                    except Exception:
                        pass
        elif etype == QEvent.Type.KeyRelease:
            key = event.key()  # type: ignore[attr-defined]
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                for cb in list(owner._bindings.get("<Return>", [])):
                    try:
                        cb(SimpleNamespace(widget=owner))
                    except Exception:
                        pass
            for cb in list(owner._bindings.get("<KeyRelease>", [])):
                try:
                    cb(SimpleNamespace(widget=owner))
                except Exception:
                    pass
        elif etype == QEvent.Type.FocusOut:
            for cb in list(owner._bindings.get("<FocusOut>", [])):
                try:
                    cb(SimpleNamespace(widget=owner))
                except Exception:
                    pass
        elif etype == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:  # type: ignore[attr-defined]
                gpos = event.globalPosition().toPoint()  # type: ignore[attr-defined]
                ev = SimpleNamespace(widget=owner, x_root=gpos.x(), y_root=gpos.y())
                for cb in list(owner._bindings.get("<Button-1>", [])):
                    try:
                        cb(ev)
                    except Exception:
                        pass
        elif etype == QEvent.Type.MouseMove:
            if event.buttons() & Qt.MouseButton.LeftButton:  # type: ignore[attr-defined]
                gpos = event.globalPosition().toPoint()  # type: ignore[attr-defined]
                ev = SimpleNamespace(widget=owner, x_root=gpos.x(), y_root=gpos.y())
                for cb in list(owner._bindings.get("<B1-Motion>", [])):
                    try:
                        cb(ev)
                    except Exception:
                        pass
        elif etype == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:  # type: ignore[attr-defined]
                gpos = event.globalPosition().toPoint()  # type: ignore[attr-defined]
                ev = SimpleNamespace(widget=owner, x_root=gpos.x(), y_root=gpos.y())
                for cb in list(owner._bindings.get("<ButtonRelease-1>", [])):
                    try:
                        cb(ev)
                    except Exception:
                        pass
        return False


def _pad_pair(val: Any) -> Tuple[int, int]:
    if isinstance(val, (tuple, list)) and len(val) >= 2:
        return int(val[0]), int(val[1])
    v = int(val or 0)
    return v, v


class QtWidgetMixin:
    """Qt bileşenlerine ortak yerleşim (grid/pack), olay bağlama ve tema yetenekleri kazandırır."""

    def _init_mixin(self, master: Optional[QWidget] = None) -> None:
        self.master = master
        self._props: Dict[str, Any] = {}
        self._bindings: Dict[str, List[Callable]] = {}
        self._shortcuts: List[QShortcut] = []
        self._grid_meta: Dict[str, Any] = {}
        self._pack_meta: Dict[str, Any] = {}
        self._col_weights: Dict[int, int] = {}
        self._col_minsizes: Dict[int, int] = {}
        self._col_uniforms: Dict[int, str] = {}
        self._row_weights: Dict[int, int] = {}
        self._ev_filter: Optional[_EventFilter] = None
        if master is not None and hasattr(master, "_register_child"):
            master._register_child(self)
        register_theme_listener(self._refresh_style)

    def _register_child(self, child: Any) -> None:
        if not hasattr(self, "_child_widgets"):
            self._child_widgets: List[Any] = []
        if child not in self._child_widgets:
            self._child_widgets.append(child)

    def _ensure_layout(self, kind: str = "grid") -> QLayout:
        target = self._content_host()
        lay = target.layout()
        if lay is not None:
            return lay
        if kind == "pack_h":
            lay = QHBoxLayout(target)
        elif kind == "pack_v":
            lay = QVBoxLayout(target)
        else:
            lay = QGridLayout(target)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        return lay

    def set_padding(self, left: int = 0, top: int = 0, right: int = 0, bottom: int = 0, spacing: int = 6) -> None:
        lay = self._ensure_layout("grid")
        lay.setContentsMargins(left, top, right, bottom)
        lay.setSpacing(spacing)

    def _content_host(self) -> QWidget:
        return self  # type: ignore[return-value]

    # -- Grid / Pack yerleşim yöneticisi ------------------------------------
    def grid_columnconfigure(
        self, index: int, weight: int = 0, minsize: int = 0, uniform: str = ""
    ) -> None:
        self._col_weights[index] = weight
        if minsize:
            self._col_minsizes[index] = minsize
        if uniform:
            self._col_uniforms[index] = uniform
        lay = self._ensure_layout("grid")
        if isinstance(lay, QGridLayout):
            lay.setColumnStretch(index, weight)
            if minsize:
                lay.setColumnMinimumWidth(index, minsize)

    def grid_rowconfigure(self, index: int, weight: int = 0, minsize: int = 0) -> None:
        self._row_weights[index] = weight
        lay = self._ensure_layout("grid")
        if isinstance(lay, QGridLayout):
            lay.setRowStretch(index, weight)
            if minsize:
                lay.setRowMinimumHeight(index, minsize)

    def grid(
        self,
        row: Optional[int] = None,
        column: Optional[int] = None,
        rowspan: int = 1,
        columnspan: int = 1,
        sticky: str = "",
        padx: Any = 0,
        pady: Any = 0,
    ) -> None:
        if row is None and self._grid_meta:
            row = self._grid_meta.get("row", 0)
            column = self._grid_meta.get("column", 0)
            rowspan = self._grid_meta.get("rowspan", 1)
            columnspan = self._grid_meta.get("columnspan", 1)
            sticky = self._grid_meta.get("sticky", "")
            padx = self._grid_meta.get("padx", 0)
            pady = self._grid_meta.get("pady", 0)
        row = 0 if row is None else int(row)
        column = 0 if column is None else int(column)
        self._grid_meta = {
            "row": row,
            "column": column,
            "rowspan": rowspan,
            "columnspan": columnspan,
            "sticky": sticky,
            "padx": padx,
            "pady": pady,
            "mapped": True,
        }
        parent = self.master
        if parent is None:
            self.setVisible(True)  # type: ignore[attr-defined]
            return
        lay = parent._ensure_layout("grid")
        if not isinstance(lay, QGridLayout):
            lay.addWidget(self)  # type: ignore[arg-type]
            self.setVisible(True)  # type: ignore[attr-defined]
            return
        for c, w in getattr(parent, "_col_weights", {}).items():
            lay.setColumnStretch(c, w)
        for c, m in getattr(parent, "_col_minsizes", {}).items():
            lay.setColumnMinimumWidth(c, m)
        for r, w in getattr(parent, "_row_weights", {}).items():
            lay.setRowStretch(r, w)

        st = str(sticky or "").lower()
        h_expand = "e" in st and "w" in st
        v_expand = "n" in st and "s" in st
        sp = self.sizePolicy()  # type: ignore[attr-defined]
        fixed_w = getattr(self, "_has_fixed_w", False)
        if h_expand:
            self._has_fixed_w = False
            self.setMinimumWidth(0)  # type: ignore[attr-defined]
            self.setMaximumWidth(16777215)  # type: ignore[attr-defined]
        sp.setHorizontalPolicy(
            QSizePolicy.Policy.Expanding
            if h_expand
            else (QSizePolicy.Policy.Fixed if fixed_w else QSizePolicy.Policy.Preferred)
        )
        sp.setVerticalPolicy(
            QSizePolicy.Policy.Expanding if v_expand else QSizePolicy.Policy.Preferred
        )
        self.setSizePolicy(sp)  # type: ignore[attr-defined]

        align = Qt.AlignmentFlag(0)
        if not h_expand:
            if "w" in st:
                align |= Qt.AlignmentFlag.AlignLeft
            elif "e" in st:
                align |= Qt.AlignmentFlag.AlignRight
            else:
                align |= Qt.AlignmentFlag.AlignHCenter
        if not v_expand:
            if "n" in st:
                align |= Qt.AlignmentFlag.AlignTop
            elif "s" in st:
                align |= Qt.AlignmentFlag.AlignBottom
            else:
                align |= Qt.AlignmentFlag.AlignVCenter

        lay.removeWidget(self)  # type: ignore[arg-type]
        px_l, px_r = _pad_pair(padx)
        py_t, py_b = _pad_pair(pady)
        if (px_l >= 8 or px_r >= 8 or py_t >= 6 or py_b >= 6) and lay.contentsMargins().isNull():
            lay.setContentsMargins(
                min(14, px_l), min(10, py_t), min(14, px_r), min(10, py_b)
            )
        if align:
            lay.addWidget(self, row, column, rowspan, columnspan, align)  # type: ignore[arg-type]
        else:
            if h_expand:
                self.setMaximumWidth(16777215)  # type: ignore[attr-defined]
            lay.addWidget(self, row, column, rowspan, columnspan)  # type: ignore[arg-type]
        self.setVisible(True)  # type: ignore[attr-defined]

    def grid_configure(self, **kwargs: Any) -> None:
        if not self._grid_meta:
            self._grid_meta = {
                "row": 0,
                "column": 0,
                "rowspan": 1,
                "columnspan": 1,
                "sticky": "",
                "padx": 0,
                "pady": 0,
            }
        self._grid_meta.update(kwargs)
        self.grid(
            row=self._grid_meta["row"],
            column=self._grid_meta["column"],
            rowspan=self._grid_meta["rowspan"],
            columnspan=self._grid_meta["columnspan"],
            sticky=self._grid_meta["sticky"],
            padx=self._grid_meta["padx"],
            pady=self._grid_meta["pady"],
        )

    def grid_remove(self) -> None:
        if self._grid_meta:
            self._grid_meta["mapped"] = False
        self.setVisible(False)  # type: ignore[attr-defined]

    def grid_info(self) -> Dict[str, Any]:
        if not self._grid_meta or not self._grid_meta.get("mapped", False):
            return {}
        return dict(self._grid_meta)

    def pack(
        self,
        side: str = "top",
        fill: str = "none",
        expand: bool = False,
        anchor: str = "",
        padx: Any = 0,
        pady: Any = 0,
    ) -> None:
        self._pack_meta = {
            "side": side,
            "fill": fill,
            "expand": bool(expand),
            "anchor": anchor,
            "padx": padx,
            "pady": pady,
            "mapped": True,
        }
        parent = self.master
        if parent is None:
            self.setVisible(True)  # type: ignore[attr-defined]
            return
        s = str(side or "top").lower()
        kind = "pack_h" if s in ("left", "right") else "pack_v"
        lay = parent._ensure_layout(kind)
        f = str(fill or "none").lower()
        sp = self.sizePolicy()  # type: ignore[attr-defined]
        fixed_w = getattr(self, "_has_fixed_w", False)
        if f in ("x", "both") or (expand and kind == "pack_h"):
            self._has_fixed_w = False
            self.setMaximumWidth(16777215)  # type: ignore[attr-defined]
            sp.setHorizontalPolicy(QSizePolicy.Policy.Expanding)
        elif fixed_w:
            sp.setHorizontalPolicy(QSizePolicy.Policy.Fixed)
        if f in ("y", "both") or (expand and kind == "pack_v"):
            sp.setVerticalPolicy(QSizePolicy.Policy.Expanding)
        self.setSizePolicy(sp)  # type: ignore[attr-defined]

        stretch = 1 if expand else 0
        px_l, px_r = _pad_pair(padx)
        py_t, py_b = _pad_pair(pady)
        if isinstance(lay, (QHBoxLayout, QVBoxLayout)):
            if lay.count() == 0 and (px_l >= 8 or px_r >= 8 or py_t >= 6 or py_b >= 6) and lay.contentsMargins().isNull():
                lay.setContentsMargins(
                    min(14, px_l), min(10, py_t), min(14, px_r), min(10, py_b)
                )
            lay.addWidget(self, stretch)  # type: ignore[arg-type]
        elif isinstance(lay, QGridLayout):
            r = lay.rowCount()
            if (px_l >= 8 or px_r >= 8 or py_t >= 6 or py_b >= 6) and lay.contentsMargins().isNull():
                lay.setContentsMargins(
                    min(14, px_l), min(10, py_t), min(14, px_r), min(10, py_b)
                )
            if f in ("x", "both") or expand:
                lay.setColumnStretch(0, 1)
                lay.addWidget(self, r, 0)  # type: ignore[arg-type]
            else:
                anc = str(anchor or "").lower()
                align = Qt.AlignmentFlag.AlignVCenter
                if "w" in anc:
                    align |= Qt.AlignmentFlag.AlignLeft
                elif "e" in anc:
                    align |= Qt.AlignmentFlag.AlignRight
                else:
                    align |= Qt.AlignmentFlag.AlignLeft
                lay.addWidget(self, r, 0, align)  # type: ignore[arg-type]
        self.setVisible(True)  # type: ignore[attr-defined]

    def tkraise(self) -> None:
        self.raise_()  # type: ignore[attr-defined]

    # -- Olaylar ve Sorgular ------------------------------------------------
    def bind(self, sequence: str, func: Optional[Callable] = None, add: Optional[str] = None) -> Any:
        if func is None:
            return bool(self._bindings.get(sequence))
        if self._ev_filter is None:
            self._ev_filter = _EventFilter(self)
            self.installEventFilter(self._ev_filter)  # type: ignore[attr-defined]
        if add != "+":
            self._bindings[sequence] = [func]
        else:
            self._bindings.setdefault(sequence, []).append(func)

        key_map = {
            "<Control-o>": "Ctrl+O",
            "<Control-O>": "Ctrl+Shift+O",
            "<Control-Return>": "Ctrl+Return",
            "<Escape>": "Esc",
            "<Delete>": "Del",
            "<Alt-Up>": "Alt+Up",
            "<Alt-Down>": "Alt+Down",
        }
        if sequence in key_map and isinstance(self, QMainWindow):
            sc = QShortcut(QKeySequence(key_map[sequence]), self)
            sc.activated.connect(lambda cb=func: cb(SimpleNamespace(widget=self)))
            self._shortcuts.append(sc)
        return sequence

    def event_generate(self, sequence: str, **_kwargs: Any) -> None:
        ev = SimpleNamespace(
            widget=self, width=self.width(), height=self.height(), x_root=0, y_root=0  # type: ignore[attr-defined]
        )
        for cb in list(self._bindings.get(sequence, [])):
            cb(ev)

    def cget(self, key: str) -> Any:
        if key in self._props:
            return self._props[key]
        if key == "text" and hasattr(self, "text"):
            return self.text()  # type: ignore[attr-defined]
        if key == "state":
            return "normal" if self.isEnabled() else "disabled"  # type: ignore[attr-defined]
        return None

    def configure(self, **kwargs: Any) -> None:
        self._props.update(kwargs)
        if "state" in kwargs:
            self.setEnabled(kwargs["state"] != "disabled")  # type: ignore[attr-defined]
        if "text" in kwargs and hasattr(self, "setText"):
            self.setText(str(kwargs["text"]))  # type: ignore[attr-defined]
        if "width" in kwargs and kwargs["width"]:
            w = int(kwargs["width"])
            if w > 0:
                self.setMinimumWidth(w)  # type: ignore[attr-defined]
        if "height" in kwargs and kwargs["height"]:
            h = int(kwargs["height"])
            if h > 0:
                self.setFixedHeight(h)  # type: ignore[attr-defined]
        if "cursor" in kwargs:
            c = str(kwargs["cursor"])
            if c == "fleur":
                self.setCursor(Qt.CursorShape.SizeAllCursor)  # type: ignore[attr-defined]
        self._refresh_style()

    def _refresh_style(self) -> None:
        self.update()  # type: ignore[misc]

    # -- winfo_* uyumluluk metotları ----------------------------------------
    def winfo_children(self) -> List[Any]:
        return [
            w for w in getattr(self, "_child_widgets", []) if not getattr(w, "_destroyed", False)
        ]

    def winfo_ismapped(self) -> bool:
        if self._grid_meta and not self._grid_meta.get("mapped", True):
            return False
        return not self.isHidden()  # type: ignore[attr-defined]

    def winfo_width(self) -> int:
        w = self.width()  # type: ignore[attr-defined]
        try:
            top = self.window() if hasattr(self, "window") else None  # type: ignore[attr-defined]
            if top is not None and top is not self:
                max_right = top.mapToGlobal(QPoint(0, 0)).x() + top.width()
                rx = self.winfo_rootx()
                if rx + w > max_right:
                    return max(1, max_right - rx)
        except Exception:
            pass
        return max(1, w)

    def winfo_height(self) -> int:
        h = self.height()  # type: ignore[attr-defined]
        if h <= 1 or not self.isVisible():  # type: ignore[attr-defined]
            sh = self.sizeHint().height()  # type: ignore[attr-defined]
            if sh > 0:
                return sh
        return max(1, h)

    def winfo_reqwidth(self) -> int:
        return max(1, self.sizeHint().width())  # type: ignore[attr-defined]

    def winfo_reqheight(self) -> int:
        return max(1, self.sizeHint().height())  # type: ignore[attr-defined]

    def winfo_rootx(self) -> int:
        try:
            return self.mapToGlobal(QPoint(0, 0)).x()  # type: ignore[attr-defined]
        except Exception:
            return 0

    def winfo_rooty(self) -> int:
        try:
            if not self.isVisible() and self._grid_meta and self.master is not None:  # type: ignore[attr-defined]
                row_idx = int(self._grid_meta.get("row", 0))
                h = self.winfo_height()
                return self.master.winfo_rooty() + row_idx * (h + 4)
            return self.mapToGlobal(QPoint(0, 0)).y()  # type: ignore[attr-defined]
        except Exception:
            return 0

    def winfo_class(self) -> str:
        return type(self).__name__

    def winfo_exists(self) -> bool:
        return not getattr(self, "_destroyed", False)

    def focus_set(self) -> None:
        try:
            root = self.window() if hasattr(self, "window") else None  # type: ignore[attr-defined]
            if root is not None:
                root._explicit_focus = self
            self.setFocus()  # type: ignore[attr-defined]
        except Exception:
            pass

    def focus_force(self) -> None:
        try:
            root = self.window() if hasattr(self, "window") else None  # type: ignore[attr-defined]
            if root is not None:
                root._explicit_focus = self
            self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)  # type: ignore[attr-defined]
        except Exception:
            pass

    def update(self, *args: Any) -> None:
        super().update(*args)  # type: ignore[misc]

    def update_idletasks(self) -> None:
        """Hafif kuyruk boşaltma; ağır tam-ağaç geometri taraması yapmaz."""
        try:
            drain = getattr(self, "_drain_ui_queue", None)
            if callable(drain) and not getattr(self, "_draining_queue", False):
                self._draining_queue = True
                try:
                    drain()
                finally:
                    self._draining_queue = False
        except Exception:
            pass

    def destroy(self) -> None:
        self._destroyed = True
        unregister_theme_listener(self._refresh_style)
        for child in list(getattr(self, "_child_widgets", [])):
            try:
                child.destroy()
            except Exception:
                pass
        if self.master is not None and hasattr(self.master, "_child_widgets"):
            try:
                self.master._child_widgets.remove(self)
            except ValueError:
                pass
        try:
            self.setParent(None)  # type: ignore[attr-defined]
            self.deleteLater()  # type: ignore[attr-defined]
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Somut PySide6 Bileşen Sınıfları (QPainter / QPalette tabanlı, 0 QSS gecikmesi)
# ---------------------------------------------------------------------------
class QtFrame(QFrame, QtWidgetMixin):
    """Doğal ``QPainter`` ile çizilen kart / çerçeve bileşeni (bireysel QSS derlemesi yok)."""

    def __init__(
        self,
        master: Optional[QWidget] = None,
        fg_color: Any = "transparent",
        corner_radius: int = 0,
        border_width: int = 0,
        border_color: Any = COLOR_BORDER,
        width: int = 0,
        height: int = 0,
        **_kwargs: Any,
    ):
        ensure_qapp()
        parent = master._content_host() if hasattr(master, "_content_host") else master
        super().__init__(parent)
        self._init_mixin(master)
        self._props.update(
            fg_color=fg_color,
            corner_radius=corner_radius,
            border_width=border_width,
            border_color=border_color,
        )
        if width > 0:
            self.setMinimumWidth(width)
        if height > 0:
            self.setFixedHeight(height)

    def paintEvent(self, event) -> None:
        bg = resolve_color(self._props.get("fg_color", "transparent"))
        bw = int(self._props.get("border_width", 0) or 0)
        if bg == "transparent" and bw <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cr = float(self._props.get("corner_radius", 0) or 0)
        half = bw / 2.0 if bw > 0 else 0.0
        rect = QRectF(self.rect()).adjusted(half, half, -half, -half)
        if bg != "transparent":
            painter.setBrush(QColor(bg))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        if bw > 0:
            bc = resolve_color(self._props.get("border_color", COLOR_BORDER))
            painter.setPen(QPen(QColor(bc), bw))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        if cr > 0:
            painter.drawRoundedRect(rect, cr, cr)
        else:
            painter.drawRect(rect)


class QtScrollableFrame(QScrollArea, QtWidgetMixin):
    """Kaydırılabilir çerçeve (``QScrollArea`` + iç ``QtFrame``)."""

    def __init__(
        self,
        master: Optional[QWidget] = None,
        fg_color: Any = "transparent",
        corner_radius: int = 0,
        border_width: int = 0,
        border_color: Any = COLOR_BORDER,
        **_kwargs: Any,
    ):
        ensure_qapp()
        parent = master._content_host() if hasattr(master, "_content_host") else master
        super().__init__(parent)
        self._init_mixin(master)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._inner = QtFrame(
            None,
            fg_color=fg_color if fg_color != "transparent" else COLOR_CARD,
            corner_radius=corner_radius,
            border_width=border_width,
            border_color=border_color,
        )
        self.setWidget(self._inner)
        self._register_child(self._inner)
        self._props.update(
            fg_color=fg_color,
            corner_radius=corner_radius,
            border_width=border_width,
            border_color=border_color,
        )
        self._parent_canvas = self

    def _refresh_style(self) -> None:
        fg = self._props.get("fg_color", "transparent")
        self._inner._props["fg_color"] = fg if fg != "transparent" else COLOR_CARD
        self._inner._refresh_style()
        self.viewport().update()
        self.update()

    def _content_host(self) -> QWidget:
        return self._inner

    def yview_moveto(self, fraction: float) -> None:
        bar = self.verticalScrollBar()
        if bar is not None:
            bar.setValue(int(round(float(fraction) * bar.maximum())))


class QtLabel(QLabel, QtWidgetMixin):
    """Doğal ``QPalette`` + ``QPainter`` tabanlı etiket."""

    def __init__(
        self,
        master: Optional[QWidget] = None,
        text: str = "",
        font: Optional[QFont] = None,
        text_color: Any = COLOR_TEXT_PRIMARY,
        fg_color: Any = "transparent",
        bg: Any = None,
        corner_radius: int = 0,
        anchor: str = "center",
        justify: str = "left",
        wraplength: int = 0,
        width: int = 0,
        height: int = 0,
        image: Any = None,
        cursor: str = "",
        **_kwargs: Any,
    ):
        ensure_qapp()
        parent = master._content_host() if hasattr(master, "_content_host") else master
        super().__init__(str(text), parent)
        self._init_mixin(master)
        if font is not None:
            self.setFont(font)
        if wraplength and int(wraplength) > 0:
            self.setWordWrap(True)
        anc = str(anchor or "").lower()
        align = Qt.AlignmentFlag.AlignVCenter
        if "w" in anc or justify == "left":
            align |= Qt.AlignmentFlag.AlignLeft
        elif "e" in anc or justify == "right":
            align |= Qt.AlignmentFlag.AlignRight
        else:
            align |= Qt.AlignmentFlag.AlignHCenter
        self.setAlignment(align)
        if width and int(width) > 0:
            self._has_fixed_w = True
            self.setFixedWidth(int(width))
        if height and int(height) > 0:
            self.setFixedHeight(int(height))
        if cursor == "fleur":
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        eff_bg = bg if bg is not None else fg_color
        self._props.update(
            text=str(text),
            text_color=text_color,
            fg_color=eff_bg,
            bg=eff_bg,
            corner_radius=corner_radius,
            wraplength=wraplength,
            image=image,
        )
        if image is not None:
            self._apply_image(image)
        self._refresh_style()

    def _apply_image(self, img: Any) -> None:
        if isinstance(img, QtImage):
            self.setPixmap(img.pixmap())
        elif isinstance(img, QPixmap):
            self.setPixmap(img)
        elif img == "" or img is None:
            self.clear()

    def configure(self, **kwargs: Any) -> None:
        if "bg" in kwargs:
            kwargs["fg_color"] = kwargs["bg"]
        if "wraplength" in kwargs:
            self.setWordWrap(bool(kwargs["wraplength"] and int(kwargs["wraplength"]) > 0))
        if "image" in kwargs:
            self._apply_image(kwargs["image"])
        super().configure(**kwargs)

    def _refresh_style(self) -> None:
        img = self._props.get("image")
        if isinstance(img, QtImage):
            self.setPixmap(img.pixmap())
        raw = resolve_color(self._props.get("text_color", COLOR_TEXT_PRIMARY))
        tc = QColor(raw)
        if not self.isEnabled():
            tc.setAlpha(110)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.WindowText, tc)
        self.setPalette(pal)
        self.update()  # type: ignore[misc]

    def paintEvent(self, event) -> None:
        bg = resolve_color(self._props.get("fg_color", "transparent"))
        if bg != "transparent":
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            cr = float(self._props.get("corner_radius", 0) or 0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(bg))
            if cr > 0:
                painter.drawRoundedRect(QRectF(self.rect()), cr, cr)
            else:
                painter.drawRect(self.rect())
            painter.end()
        super().paintEvent(event)

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.EnabledChange:
            self._refresh_style()
        super().changeEvent(event)


class QtButton(QPushButton, QtWidgetMixin):
    """Doğal ``QPainter`` ile çizilen hızlı düğme bileşeni (QSS yeniden derlemesi yapmaz)."""

    def __init__(
        self,
        master: Optional[QWidget] = None,
        text: str = "",
        command: Optional[Callable[[], None]] = None,
        width: int = 0,
        height: int = 32,
        font: Optional[QFont] = None,
        fg_color: Any = COLOR_SOLID,
        text_color: Any = COLOR_ON_ACCENT,
        hover_color: Any = COLOR_SOLID_HOVER,
        border_width: int = 0,
        border_color: Any = COLOR_BORDER,
        corner_radius: int = 6,
        state: str = "normal",
        **_kwargs: Any,
    ):
        ensure_qapp()
        parent = master._content_host() if hasattr(master, "_content_host") else master
        super().__init__(str(text), parent)
        self._init_mixin(master)
        if font is not None:
            self.setFont(font)
        if width and int(width) > 0:
            self._has_fixed_w = True
            self.setFixedWidth(int(width))
        if height and int(height) > 0:
            self.setFixedHeight(int(height))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._hovered = False
        self._command = command
        self.clicked.connect(self._on_clicked)
        self._props.update(
            text=str(text),
            command=command,
            fg_color=fg_color,
            text_color=text_color,
            hover_color=hover_color,
            border_width=border_width,
            border_color=border_color,
            corner_radius=corner_radius,
            state=state,
        )
        self.setEnabled(state != "disabled")

    def enterEvent(self, event) -> None:
        self._hovered = True
        super().update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        super().update()
        super().leaveEvent(event)

    def _on_clicked(self) -> None:
        if self._command is not None:
            self._command()

    def invoke(self) -> Any:
        if self._command is not None:
            return self._command()
        return None

    def configure(self, **kwargs: Any) -> None:
        if "command" in kwargs:
            self._command = kwargs["command"]
        super().configure(**kwargs)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        enabled = self.isEnabled()
        if not enabled:
            painter.setOpacity(0.55)
        bg_raw = (
            self._props.get("hover_color", COLOR_SOLID_HOVER)
            if (self._hovered and enabled)
            else self._props.get("fg_color", COLOR_SOLID)
        )
        bg = resolve_color(bg_raw)
        tc = resolve_color(self._props.get("text_color", COLOR_ON_ACCENT))
        bw = int(self._props.get("border_width", 0) or 0)
        cr = float(self._props.get("corner_radius", 6) or 0)
        half = bw / 2.0 if bw > 0 else 0.0
        rect = QRectF(self.rect()).adjusted(half, half, -half, -half)
        if bg != "transparent":
            painter.setBrush(QColor(bg))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        if bw > 0:
            bc = resolve_color(self._props.get("border_color", COLOR_BORDER))
            painter.setPen(QPen(QColor(bc), bw))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, cr, cr)
        painter.setPen(QColor(tc))
        painter.setFont(self.font())
        painter.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), self.text())


class QtEntry(QLineEdit, QtWidgetMixin):
    """Tek satırlık metin giriş kutusu (``QLineEdit``; ``QPainter``/``QPalette`` ile çizilir)."""

    def __init__(
        self,
        master: Optional[QWidget] = None,
        placeholder_text: str = "",
        width: int = 0,
        height: int = 32,
        font: Optional[QFont] = None,
        fg_color: Any = COLOR_SUBCARD,
        border_color: Any = COLOR_BORDER,
        border_width: int = 1,
        text_color: Any = COLOR_TEXT_PRIMARY,
        state: str = "normal",
        **_kwargs: Any,
    ):
        ensure_qapp()
        parent = master._content_host() if hasattr(master, "_content_host") else master
        super().__init__(parent)
        self._init_mixin(master)
        self.setFrame(False)
        self.setTextMargins(6, 2, 6, 2)
        if placeholder_text:
            self.setPlaceholderText(str(placeholder_text))
        if font is not None:
            self.setFont(font)
        if width and int(width) > 0:
            self._has_fixed_w = True
            self.setFixedWidth(int(width))
        if height and int(height) > 0:
            self.setFixedHeight(int(height))
        self._entry = self
        self._props.update(
            fg_color=fg_color,
            border_color=border_color,
            border_width=border_width,
            text_color=text_color,
            state=state,
        )
        self.setEnabled(state != "disabled")
        self._refresh_style()

    def _refresh_style(self) -> None:
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(0, 0, 0, 0))
        tc = resolve_color(
            COLOR_TEXT_SECONDARY
            if not self.isEnabled()
            else self._props.get("text_color", COLOR_TEXT_PRIMARY)
        )
        pal.setColor(QPalette.ColorRole.Text, QColor(tc))
        pal.setColor(
            QPalette.ColorRole.PlaceholderText, QColor(resolve_color(COLOR_TEXT_SECONDARY))
        )
        self.setPalette(pal)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if not self.isEnabled():
            painter.setOpacity(0.55)
        bg = resolve_color(
            COLOR_SUBCARD
            if not self.isEnabled()
            else self._props.get("fg_color", COLOR_CARD)
        )
        is_err = self._props.get("border_color") == COLOR_ERROR
        bw = 2 if is_err else (1 if self.hasFocus() else int(self._props.get("border_width", 1) or 1))
        bc = resolve_color(
            COLOR_ERROR
            if is_err
            else (COLOR_ACCENT if self.hasFocus() else self._props.get("border_color", COLOR_BORDER))
        )
        half = bw / 2.0
        rect = QRectF(self.rect()).adjusted(half, half, -half, -half)
        painter.setBrush(QColor(bg))
        painter.setPen(QPen(QColor(bc), bw))
        painter.drawRoundedRect(rect, 6.0, 6.0)
        painter.end()
        super().paintEvent(event)

    def get(self) -> str:
        return self.text()

    def delete(self, first: Any = 0, last: Any = "end") -> None:
        if first == 0 and last in ("end", "END"):
            self.clear()
        else:
            txt = self.text()
            s = int(first) if isinstance(first, int) else 0
            e = len(txt) if last in ("end", "END") else int(last)
            self.setText(txt[:s] + txt[e:])

    def insert(self, index: Any, text: str) -> None:
        cur = self.text()
        pos = len(cur) if index in ("end", "END") else int(index)
        self.setText(cur[:pos] + str(text) + cur[pos:])

    def configure(self, **kwargs: Any) -> None:
        super().configure(**kwargs)
        self._refresh_style()


class QtSwitch(QWidget, QtWidgetMixin):
    """Açık/Kapalı anahtar düğmesi (yunus çubuklu ``QPainter`` çizimi).

    Yerleşim uyumluluğu için ``CTkCheckBox`` arayüzünü sağlar: ``get()``,
    ``select()``, ``deselect()``; değişim ``command`` geri çağrısını tetikler.
    """

    def __init__(
        self,
        master: Optional[QWidget] = None,
        command: Optional[Callable[[], None]] = None,
        checked: bool = True,
        width: int = 40,
        height: int = 22,
        **_kwargs: Any,
    ):
        ensure_qapp()
        parent = master._content_host() if hasattr(master, "_content_host") else master
        super().__init__(parent)
        self._init_mixin(master)
        if width and int(width) > 0:
            self._has_fixed_w = True
            self.setFixedWidth(int(width))
        if height and int(height) > 0:
            self.setFixedHeight(int(height))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._checked = bool(checked)
        self._command = command
        self._props.update(command=command, checked=self._checked)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if not self.isEnabled():
            painter.setOpacity(0.45)
        track = QColor(resolve_color(COLOR_SOLID if self._checked else COLOR_BTN_SUBTLE))
        w, h = self.width(), self.height()
        r = h / 2.0
        painter.setPen(QPen(QColor(resolve_color(COLOR_BORDER if not self._checked else COLOR_SOLID)), 1))
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(1.0, 1.0, w - 2, h - 2), r, r)
        knob = h - 8.0
        x = (w - knob - 5.0) if self._checked else 5.0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(resolve_color(COLOR_ON_ACCENT)))
        painter.drawEllipse(QRectF(x, 4.0, knob, knob))

    def mousePressEvent(self, event) -> None:
        self.setChecked(not self._checked)
        if self._command is not None:
            self._command()

    def setChecked(self, value: bool) -> None:  # noqa: N802 (Qt adı)
        changed = value != self._checked
        self._checked = bool(value)
        self._props["checked"] = self._checked
        if changed:
            self.update()

    def get(self) -> int:
        return 1 if self._checked else 0

    def select(self) -> None:
        self.setChecked(True)

    def deselect(self) -> None:
        self.setChecked(False)


class QtCheckBox(QCheckBox, QtWidgetMixin):
    """Onay kutusu (``QCheckBox``; ``QPainter`` ile çizilir)."""

    def __init__(
        self,
        master: Optional[QWidget] = None,
        text: str = "",
        font: Optional[QFont] = None,
        text_color: Any = COLOR_TEXT_PRIMARY,
        fg_color: Any = COLOR_SOLID,
        hover_color: Any = COLOR_ACCENT,
        border_color: Any = COLOR_BORDER,
        command: Optional[Callable[[], None]] = None,
        **_kwargs: Any,
    ):
        ensure_qapp()
        parent = master._content_host() if hasattr(master, "_content_host") else master
        super().__init__(str(text), parent)
        self._init_mixin(master)
        if font is not None:
            self.setFont(font)
        self.setMinimumHeight(24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._command = command
        self.clicked.connect(self._on_user_click)
        self._props.update(
            text=str(text),
            text_color=text_color,
            fg_color=fg_color,
            hover_color=hover_color,
            border_color=border_color,
            command=command,
        )

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if not self.isEnabled():
            painter.setOpacity(0.55)
        box_y = (self.height() - 18) / 2.0
        box_rect = QRectF(1.0, box_y, 18.0, 18.0)
        if self.isChecked():
            fill = resolve_color(self._props.get("fg_color", COLOR_SOLID))
            painter.setBrush(QColor(fill))
            painter.setPen(QPen(QColor(fill), 1))
            painter.drawRoundedRect(box_rect, 4.0, 4.0)
            painter.setPen(QPen(QColor("#FFFFFF"), 2.0))
            painter.drawLine(int(5), int(box_y + 9), int(8), int(box_y + 13))
            painter.drawLine(int(8), int(box_y + 13), int(15), int(box_y + 5))
        else:
            bg = resolve_color(COLOR_CARD)
            bc = resolve_color(self._props.get("border_color", COLOR_BORDER))
            painter.setBrush(QColor(bg))
            painter.setPen(QPen(QColor(bc), 1))
            painter.drawRoundedRect(box_rect, 4.0, 4.0)
        tc = resolve_color(self._props.get("text_color", COLOR_TEXT_PRIMARY))
        painter.setPen(QColor(tc))
        painter.setFont(self.font())
        text_rect = self.rect().adjusted(26, 0, 0, 0)
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self.text(),
        )

    def _on_user_click(self) -> None:
        if self._command is not None:
            self._command()

    def get(self) -> int:
        return 1 if self.isChecked() else 0

    def select(self) -> None:
        self.setChecked(True)

    def deselect(self) -> None:
        self.setChecked(False)

    def toggle(self) -> None:
        self.setChecked(not self.isChecked())
        if self._command is not None:
            self._command()

    def configure(self, **kwargs: Any) -> None:
        if "command" in kwargs:
            self._command = kwargs["command"]
        super().configure(**kwargs)


class QtOptionMenu(QComboBox, QtWidgetMixin):
    """Açılır seçim kutusu (``QComboBox``; ``QPainter`` ile çizilir)."""

    def __init__(
        self,
        master: Optional[QWidget] = None,
        values: Optional[List[str]] = None,
        width: int = 120,
        height: int = 30,
        font: Optional[QFont] = None,
        fg_color: Any = COLOR_SUBCARD,
        text_color: Any = COLOR_TEXT_PRIMARY,
        command: Optional[Callable[[str], None]] = None,
        **_kwargs: Any,
    ):
        ensure_qapp()
        parent = master._content_host() if hasattr(master, "_content_host") else master
        super().__init__(parent)
        self._init_mixin(master)
        if font is not None:
            self.setFont(font)
        if width and int(width) > 0:
            self._has_fixed_w = True
            self.setFixedWidth(int(width))
        if height and int(height) > 0:
            self.setFixedHeight(int(height))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._command = command
        self._suppress = False
        self._values = list(values or [])
        if self._values:
            self.addItems(self._values)
        self.currentTextChanged.connect(self._on_text_changed)
        self._canvas = self
        self._props.update(
            values=self._values,
            fg_color=fg_color,
            text_color=text_color,
            command=command,
        )
        self._refresh_style()

    def _refresh_style(self) -> None:
        try:
            v = self.view()
            if v is not None:
                pal = v.palette()
                pal.setColor(QPalette.ColorRole.Base, QColor(resolve_color(COLOR_CARD)))
                pal.setColor(QPalette.ColorRole.Text, QColor(resolve_color(COLOR_TEXT_PRIMARY)))
                pal.setColor(QPalette.ColorRole.Highlight, QColor(resolve_color(COLOR_SELECTED)))
                pal.setColor(QPalette.ColorRole.HighlightedText, QColor(resolve_color(COLOR_TEXT_PRIMARY)))
                v.setPalette(pal)
        except Exception:
            pass
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if not self.isEnabled():
            painter.setOpacity(0.55)
        bg = resolve_color(self._props.get("fg_color", COLOR_CARD))
        tc = resolve_color(self._props.get("text_color", COLOR_TEXT_PRIMARY))
        bc = resolve_color(COLOR_BORDER)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setBrush(QColor(bg))
        painter.setPen(QPen(QColor(bc), 1))
        painter.drawRoundedRect(rect, 6.0, 6.0)
        painter.setPen(QColor(tc))
        painter.setFont(self.font())
        text_rect = self.rect().adjusted(10, 0, -24, 0)
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self.currentText(),
        )
        painter.drawText(
            self.rect().adjusted(0, 0, -8, 0),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            "▾",
        )

    def _on_text_changed(self, value: str) -> None:
        if not self._suppress and self._command is not None:
            self._command(value)

    def get(self) -> str:
        return self.currentText()

    def set(self, value: str) -> None:
        self._suppress = True
        try:
            idx = self.findText(str(value))
            if idx >= 0:
                self.setCurrentIndex(idx)
            else:
                self.addItem(str(value))
                self.setCurrentIndex(self.count() - 1)
        finally:
            self._suppress = False

    def configure(self, **kwargs: Any) -> None:
        if "values" in kwargs:
            cur = self.get()
            self._values = list(kwargs["values"] or [])
            self._suppress = True
            try:
                self.clear()
                self.addItems(self._values)
                if cur in self._values:
                    self.setCurrentIndex(self._values.index(cur))
            finally:
                self._suppress = False
        if "command" in kwargs:
            self._command = kwargs["command"]
        super().configure(**kwargs)


class QtSegmentedButton(QtFrame):
    """Segmentli seçim düğmesi grubu (``QtButton`` tabanlı, 0 QSS gecikmesi)."""

    def __init__(
        self,
        master: Optional[QWidget] = None,
        values: Optional[List[str]] = None,
        width: int = 0,
        height: int = 34,
        font: Optional[QFont] = None,
        fg_color: Any = COLOR_SUBCARD,
        selected_color: Any = COLOR_SELECTED,
        selected_hover_color: Any = COLOR_SELECTED_HOVER,
        unselected_color: Any = COLOR_SUBCARD,
        unselected_hover_color: Any = COLOR_BTN_SUBTLE,
        text_color: Any = COLOR_TEXT_PRIMARY,
        corner_radius: int = 6,
        command: Optional[Callable[[str], None]] = None,
        **_kwargs: Any,
    ):
        super().__init__(
            master,
            fg_color=fg_color,
            corner_radius=corner_radius,
            border_width=1,
            border_color=COLOR_BORDER,
            width=width,
            height=height,
        )
        if width and int(width) > 0:
            self.setMaximumWidth(max(int(width) + 40, int(width)))
        self._values: List[str] = list(values or [])
        self._current: str = self._values[0] if self._values else ""
        self._command = command
        self._font = font or QtFont(FONT_FAMILY, FS_SMALL)
        self._bold_font = QtFont(FONT_FAMILY, self._font.pixelSize(), weight="bold")
        self._selected_color = selected_color
        self._selected_hover_color = selected_hover_color
        self._unselected_color = unselected_color
        self._unselected_hover_color = unselected_hover_color
        self._text_color = text_color
        self._seg_buttons: Dict[str, QtButton] = {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(3)
        for val in self._values:
            btn = QtButton(
                self,
                text=str(val),
                height=max(22, height - 6),
                font=self._font,
                fg_color=unselected_color,
                hover_color=unselected_hover_color,
                text_color=text_color,
                corner_radius=max(4, corner_radius - 2),
                command=lambda v=val: self._on_seg_click(v),
            )
            lay.addWidget(btn, 1)
            self._seg_buttons[val] = btn
        self._sync_segments()

    def _on_seg_click(self, value: str) -> None:
        self._current = value
        self._sync_segments()
        if self._command is not None:
            self._command(value)

    def get(self) -> str:
        return self._current

    def set(self, value: str) -> None:
        self._current = str(value)
        self._sync_segments()

    def _sync_segments(self) -> None:
        if not hasattr(self, "_seg_buttons"):
            return
        for val, btn in self._seg_buttons.items():
            sel = val == self._current
            btn.setFont(self._bold_font if sel else self._font)
            btn._props["fg_color"] = self._selected_color if sel else self._unselected_color
            btn._props["hover_color"] = (
                self._selected_hover_color if sel else self._unselected_hover_color
            )
            btn.update()

    def _refresh_style(self) -> None:
        self._sync_segments()
        super()._refresh_style()


class QtProgressBar(QProgressBar, QtWidgetMixin):
    """İlerleme çubuğu (0.0 – 1.0 aralığı; ``QPainter`` ile çizilir)."""

    def __init__(
        self,
        master: Optional[QWidget] = None,
        height: int = 6,
        progress_color: Any = COLOR_ACCENT,
        **_kwargs: Any,
    ):
        ensure_qapp()
        parent = master._content_host() if hasattr(master, "_content_host") else master
        super().__init__(parent)
        self._init_mixin(master)
        self.setRange(0, 1000)
        self.setValue(0)
        self.setTextVisible(False)
        self.setFixedHeight(max(4, int(height)))
        self._props["progress_color"] = progress_color

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bg = resolve_color(COLOR_SUBCARD)
        fg = resolve_color(self._props.get("progress_color", COLOR_ACCENT))
        rect = QRectF(self.rect())
        r = rect.height() / 2.0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(bg))
        painter.drawRoundedRect(rect, r, r)
        ratio = max(0.0, min(1.0, self.value() / 1000.0))
        if ratio > 0.0:
            chunk = QRectF(0.0, 0.0, max(rect.height(), rect.width() * ratio), rect.height())
            painter.setBrush(QColor(fg))
            painter.drawRoundedRect(chunk, r, r)

    def set(self, value: float) -> None:
        v = max(0.0, min(1.0, float(value or 0.0)))
        self.setValue(int(round(v * 1000)))

    def get(self) -> float:
        return self.value() / 1000.0


class QtTextbox(QTextEdit, QtWidgetMixin):
    """Çok satırlı salt-okunur/düzenlenebilir metin alanı (``QTextEdit``)."""

    def __init__(
        self,
        master: Optional[QWidget] = None,
        fg_color: Any = COLOR_SUBCARD,
        border_color: Any = COLOR_BORDER,
        border_width: int = 1,
        text_color: Any = COLOR_TEXT_PRIMARY,
        font: Optional[QFont] = None,
        wrap: str = "word",
        **_kwargs: Any,
    ):
        ensure_qapp()
        parent = master._content_host() if hasattr(master, "_content_host") else master
        super().__init__(parent)
        self._init_mixin(master)
        if font is not None:
            self.setFont(font)
        if wrap == "none":
            self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        else:
            self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self._props.update(
            fg_color=fg_color,
            border_color=border_color,
            border_width=border_width,
            text_color=text_color,
        )

    def insert(self, _index: Any, text: str) -> None:
        self.insertPlainText(str(text))

    def get(self, _start: Any = "1.0", _end: Any = "end") -> str:
        return self.toPlainText()

    def delete(self, _start: Any = "1.0", _end: Any = "end") -> None:
        self.clear()

    def configure(self, **kwargs: Any) -> None:
        if "state" in kwargs:
            self.setReadOnly(kwargs.pop("state") == "disabled")
        super().configure(**kwargs)


# ---------------------------------------------------------------------------
# Üst Düzey İletişim Pencereleri (QtToplevel, QtInputDialog)
# ---------------------------------------------------------------------------
class QtToplevel(QDialog, QtWidgetMixin):
    """İkincil iletişim penceresi (Hakkında, Rapor, Kırpma Onayı)."""

    def __init__(self, master: Optional[QWidget] = None, **_kwargs: Any):
        ensure_qapp()
        super().__init__(master)
        self._init_mixin(master)
        self._close_cb: Optional[Callable[[], None]] = None

    def title(self, text: Optional[str] = None) -> str:
        if text is not None:
            self.setWindowTitle(str(text))
        return self.windowTitle()

    def geometry(self, spec: Optional[str] = None) -> str:
        if spec:
            parts = str(spec).split("+")[0].split("x")
            if len(parts) == 2:
                self.resize(int(parts[0]), int(parts[1]))
        return f"{self.width()}x{self.height()}"

    def minsize(self, width: int, height: int) -> None:
        self.setMinimumSize(int(width), int(height))

    def resizable(self, width: bool, height: bool) -> None:
        if not width and not height:
            self.setFixedSize(self.size())

    def transient(self, _master: Any = None) -> None:
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

    def grab_set(self) -> None:
        self.show()

    def grab_release(self) -> None:
        pass

    def protocol(self, name: str, func: Callable[[], None]) -> None:
        if name == "WM_DELETE_WINDOW":
            self._close_cb = func

    def closeEvent(self, event) -> None:
        if self._close_cb is not None:
            self._close_cb()
        super().closeEvent(event)

    def update(self, *args: Any) -> None:
        if args:
            super().update(*args)
            return
        try:
            QApplication.sendPostedEvents()
            QApplication.processEvents()
            super().update()
        except Exception:
            pass


class QtInputDialog:
    """Metin giriş iletişim kutusu (profil kaydetme vb.)."""

    def __init__(self, title: str = "", text: str = "", master: Optional[QWidget] = None):
        self._title = title
        self._text = text
        self._master = master

    def get_input(self) -> Optional[str]:
        ensure_qapp()
        val, ok = QInputDialog.getText(self._master, self._title, self._text)
        return val if ok else None


# ---------------------------------------------------------------------------
# Ana Uygulama Penceresi (QtMainWindow)
# ---------------------------------------------------------------------------
class QtMainWindow(QMainWindow, QtWidgetMixin):
    """Tek yüzeyli (``QBackingStore``) çift tamponlu ana uygulama penceresi."""

    def __init__(self) -> None:
        ensure_qapp()
        super().__init__()
        self._central = QtFrame(None, fg_color=COLOR_BG)
        self.setCentralWidget(self._central)
        self._init_mixin(None)
        self._register_child(self._central)
        self._timers: Dict[str, QTimer] = {}
        self._timer_seq = 0
        self._close_protocol: Optional[Callable[[], None]] = None
        self._drop_callback: Optional[Callable[[List[str]], None]] = None
        self._wm_state = "normal"
        self.setAcceptDrops(True)

    def _content_host(self) -> QWidget:
        return self._central

    def _apply_appearance_mode(self, color: Any) -> str:
        return resolve_color(color)

    def _get_appearance_mode(self) -> str:
        return get_appearance_mode().lower()

    # -- Pencere yönetimi ---------------------------------------------------
    def title(self, text: Optional[str] = None) -> str:
        if text is not None:
            self.setWindowTitle(str(text))
        return self.windowTitle()

    def iconbitmap(self, path: str) -> None:
        if path and os.path.exists(path):
            self.setWindowIcon(QIcon(path))

    def geometry(self, spec: Optional[str] = None) -> str:
        if spec:
            size_part = str(spec).split("+")[0]
            if "x" in size_part:
                w_str, h_str = size_part.split("x", 1)
                w, h = int(float(w_str)), int(float(h_str))
                self.resize(w, h)
                self._central.setGeometry(0, 0, w, h)
        return f"{self.width()}x{self.height()}+{self.x()}+{self.y()}"

    def minsize(self, width: int, height: int) -> None:
        self.setMinimumSize(int(width), int(height))

    def state(self, newstate: Optional[str] = None) -> str:
        if newstate is None:
            if self.isMaximized():
                return "zoomed"
            if self.isMinimized():
                return "iconic"
            return self._wm_state
        st = str(newstate).lower()
        self._wm_state = st
        if st == "zoomed":
            self.showMaximized()
        elif st == "iconic":
            self.showMinimized()
        elif st == "withdrawn":
            self.hide()
        else:
            self._wm_state = "normal"
            if self.isMaximized() or self.isMinimized():
                self.showNormal()
        return self._wm_state

    def withdraw(self) -> None:
        self._wm_state = "withdrawn"
        self.hide()

    def deiconify(self) -> None:
        self._wm_state = "normal"
        self.show()

    def attributes(self, name: str, value: Any = None) -> Any:
        if name == "-alpha":
            if value is not None:
                self.setWindowOpacity(float(value))
            return self.windowOpacity()
        return None

    def protocol(self, name: str, func: Callable[[], None]) -> None:
        if name == "WM_DELETE_WINDOW":
            self._close_protocol = func

    def closeEvent(self, event) -> None:
        if self._close_protocol is not None and not getattr(self, "_closing", False):
            event.ignore()
            self._close_protocol()
            return
        super().closeEvent(event)

    def winfo_id(self) -> int:
        return int(self.winId())

    def update(self, *args: Any) -> None:
        if args:
            super().update(*args)
            return
        try:
            drain = getattr(self, "_drain_ui_queue", None)
            if callable(drain) and not getattr(self, "_draining_queue", False):
                self._draining_queue = True
                try:
                    drain()
                finally:
                    self._draining_queue = False
            QApplication.sendPostedEvents()
            QApplication.processEvents()
            super().update()
        except Exception:
            pass

    def winfo_screenwidth(self) -> int:
        screen = QApplication.primaryScreen()
        return screen.availableGeometry().width() if screen else 1920

    def winfo_screenheight(self) -> int:
        screen = QApplication.primaryScreen()
        return screen.availableGeometry().height() if screen else 1080

    def winfo_fpixels(self, spec: str) -> float:
        if spec == "1i":
            return 96.0
        return 1.0

    # -- Zamanlayıcılar (after / after_idle / after_cancel) -----------------
    def after(self, ms: int, func: Optional[Callable] = None, *args: Any) -> str:
        if func is None:
            return ""
        self._timer_seq += 1
        tid = f"qt_timer_{self._timer_seq}"
        timer = QTimer(self)
        timer.setSingleShot(True)

        def _fire() -> None:
            self._timers.pop(tid, None)
            if not getattr(self, "_closing", False):
                func(*args)

        timer.timeout.connect(_fire)
        self._timers[tid] = timer
        timer.start(max(0, int(ms)))
        return tid

    def after_idle(self, func: Callable, *args: Any) -> str:
        return self.after(0, func, *args)

    def after_cancel(self, tid: Any) -> None:
        timer = self._timers.pop(str(tid), None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()

    # -- Güncelleme / Kuyruk Boşaltma (QtMainWindow) ------------------------
    def update(self, *args: Any) -> None:
        if args:
            super().update(*args)
            return
        try:
            drain = getattr(self, "_drain_ui_queue", None)
            if callable(drain) and not getattr(self, "_draining_queue", False):
                self._draining_queue = True
                try:
                    drain()
                finally:
                    self._draining_queue = False
            QApplication.sendPostedEvents()
            QApplication.processEvents()
            super().update()
        except Exception:
            pass

    def update_idletasks(self) -> None:
        try:
            drain = getattr(self, "_drain_ui_queue", None)
            if callable(drain) and not getattr(self, "_draining_queue", False):
                self._draining_queue = True
                try:
                    drain()
                finally:
                    self._draining_queue = False
        except Exception:
            pass

    # -- Odak, Pano ve İkincil Pencere Bekleme ------------------------------
    def focus_get(self) -> Optional[QWidget]:
        w = QApplication.focusWidget()
        if w is not None:
            return w
        return getattr(self, "_explicit_focus", None)

    def clipboard_clear(self) -> None:
        cb = QApplication.clipboard()
        if cb is not None:
            cb.clear()

    def clipboard_append(self, text: str) -> None:
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(str(text))

    def wait_window(self, dialog: QDialog) -> None:
        dialog.exec()

    def mainloop(self) -> None:
        self.show()
        app = ensure_qapp()
        app.exec()

    # -- Doğal Qt 6 Unicode Sürükle-Bırak (Drag & Drop) ---------------------
    def set_drop_callback(self, callback: Callable[[List[str]], None]) -> None:
        self._drop_callback = callback

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        if self._drop_callback is None or not event.mimeData().hasUrls():
            return
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self._drop_callback(paths)


# ---------------------------------------------------------------------------
# Dosya ve Mesaj Kutusu Sarmalayıcıları (filedialog & messagebox)
# ---------------------------------------------------------------------------
class _QtMessageBoxNamespace:
    @staticmethod
    def showinfo(title: str, message: str, **_kwargs: Any) -> str:
        ensure_qapp()
        QMessageBox.information(None, str(title), str(message))
        return "ok"

    @staticmethod
    def showwarning(title: str, message: str, **_kwargs: Any) -> str:
        ensure_qapp()
        QMessageBox.warning(None, str(title), str(message))
        return "ok"

    @staticmethod
    def showerror(title: str, message: str, **_kwargs: Any) -> str:
        ensure_qapp()
        QMessageBox.critical(None, str(title), str(message))
        return "ok"

    @staticmethod
    def askyesno(title: str, message: str, **_kwargs: Any) -> bool:
        ensure_qapp()
        res = QMessageBox.question(
            None,
            str(title),
            str(message),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return res == QMessageBox.StandardButton.Yes


class _QtFileDialogNamespace:
    @staticmethod
    def _filter_str(filetypes: Optional[List[Tuple[str, str]]]) -> str:
        if not filetypes:
            return "Tüm Dosyalar (*.*)"
        return ";;".join(f"{label} ({pattern})" for label, pattern in filetypes)

    @classmethod
    def askopenfilename(
        cls,
        title: str = "",
        initialdir: str = "",
        filetypes: Optional[List[Tuple[str, str]]] = None,
        **_kwargs: Any,
    ) -> str:
        ensure_qapp()
        path, _ = QFileDialog.getOpenFileName(
            None, str(title), str(initialdir or ""), cls._filter_str(filetypes)
        )
        return path or ""

    @classmethod
    def askopenfilenames(
        cls,
        title: str = "",
        initialdir: str = "",
        filetypes: Optional[List[Tuple[str, str]]] = None,
        **_kwargs: Any,
    ) -> Tuple[str, ...]:
        ensure_qapp()
        paths, _ = QFileDialog.getOpenFileNames(
            None, str(title), str(initialdir or ""), cls._filter_str(filetypes)
        )
        return tuple(paths or ())

    @classmethod
    def asksaveasfilename(
        cls,
        title: str = "",
        initialdir: str = "",
        initialfile: str = "",
        defaultextension: str = ".pdf",
        filetypes: Optional[List[Tuple[str, str]]] = None,
        **_kwargs: Any,
    ) -> str:
        ensure_qapp()
        start = (
            os.path.join(initialdir, initialfile)
            if initialdir and initialfile
            else (initialdir or initialfile or "")
        )
        path, _ = QFileDialog.getSaveFileName(
            None, str(title), start, cls._filter_str(filetypes)
        )
        if path and defaultextension and not os.path.splitext(path)[1]:
            path += defaultextension
        return path or ""


messagebox = _QtMessageBoxNamespace()
filedialog = _QtFileDialogNamespace()

# ---------------------------------------------------------------------------
# Dışa Aktarılan Standart Bileşen İsimleri
# ---------------------------------------------------------------------------
CTk = QtMainWindow
CTkToplevel = QtToplevel
CTkFrame = QtFrame
CTkScrollableFrame = QtScrollableFrame
CTkLabel = QtLabel
CTkButton = QtButton
CTkEntry = QtEntry
CTkCheckBox = QtCheckBox
CTkSwitch = QtSwitch
CTkOptionMenu = QtOptionMenu
CTkSegmentedButton = QtSegmentedButton
CTkProgressBar = QtProgressBar
CTkTextbox = QtTextbox
CTkInputDialog = QtInputDialog
CTkFont = QtFont
CTkImage = QtImage
