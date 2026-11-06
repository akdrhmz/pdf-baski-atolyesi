"""Sekmelerin uygulamayla konuştuğu dar yüzey (``AppContext``).

Sekmeler pencere nesnesine (``self``) doğrudan erişmek yerine bu bağlam
üzerinden çalışır. Böylece bir sekme, gerçek pencere olmadan sahte bir bağlamla
(``tests/fake_context.py``) kurulup denenebilir.

Yüzey bilerek küçük tutulur: yalnızca paylaşılan hizmetler, salt okunur durum
ve geri çağrılar. Yeni bir ihtiyaç çıktığında buraya eklenir; sekmeler
``ctx.app`` gibi bir kaçış kapısı bulamaz.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Protocol, runtime_checkable


@runtime_checkable
class TabContext(Protocol):
    """Bir sekmenin ihtiyaç duyduğu her şey; ``AppContext`` ve test sahtesi bunu sağlar."""

    # Paylaşılan hizmetler
    store: Any
    log: Any
    perf: Any

    # Salt okunur durum
    unit: str
    input_pdf_path: str
    orig_page_count: int
    orig_width_mm: float
    orig_height_mm: float
    current_tab: str

    # Geri çağrılar
    def on_field_changed(self) -> None: ...
    def schedule_preview(self) -> None: ...
    def update_summary(self) -> None: ...
    def set_status(self, text: str, color: Optional[Any] = None) -> None: ...
    def select_tab(self, name: str) -> None: ...
    def module_enabled(self, key: str) -> bool: ...
    def enable_module(self, key: str) -> None: ...
    def disable_module(self, key: str) -> None: ...
    def apply_named_preset(self, name: str) -> None: ...
    def bind_wraplength(self, label: Any, container: Any, padding: int) -> None: ...
    def run_on_ui(self, callback: Callable[[], None]) -> None: ...
    def gutter_exclude_text(self) -> str: ...
    def after(self, ms: int, callback: Callable[[], None]) -> Any: ...


class AppContext:
    """Gerçek pencereye bağlı ``TabContext``; her okuma pencereden canlı yapılır."""

    #: modül anahtarı -> (pencere üzerindeki onay kutusu, kabuğun durum yöntemi)
    _MODULES = {
        "gutter": ("switch_gutter", "_toggle_gutter_fields"),
        "margin": ("switch_margin", "_toggle_margin_fields"),
        "pnum": ("switch_pnum", "_toggle_pnum_fields"),
    }

    def __init__(self, app: Any):
        self._app = app

    def gutter_exclude_text(self) -> str:
        """Eski "Cilt payıyla aynı yap" köprüsü; birleşik modelde karşılığı yok."""
        return ""

    # -- Paylaşılan hizmetler ------------------------------------------------
    @property
    def store(self) -> Any:
        return self._app.store

    @property
    def log(self) -> Any:
        return self._app.log

    @property
    def perf(self) -> Any:
        return self._app.perf

    # -- Salt okunur durum ---------------------------------------------------
    @property
    def unit(self) -> str:
        return self._app.unit

    @property
    def input_pdf_path(self) -> str:
        return self._app.input_pdf_path

    @property
    def orig_page_count(self) -> int:
        return self._app.orig_page_count

    @property
    def orig_width_mm(self) -> float:
        return self._app.orig_width_mm

    @property
    def orig_height_mm(self) -> float:
        return self._app.orig_height_mm

    @property
    def current_tab(self) -> str:
        return self._app.current_tab

    # -- Geri çağrılar -------------------------------------------------------
    def on_field_changed(self) -> None:
        self._app._on_field_changed()

    def schedule_preview(self) -> None:
        self._app._schedule_preview()

    def update_summary(self) -> None:
        self._app._update_pipeline_summary()

    def set_status(self, text: str, color: Optional[Any] = None) -> None:
        if color is None:
            self._app._set_status(text)
        else:
            self._app._set_status(text, color)

    def select_tab(self, name: str) -> None:
        self._app.select_tab(name)

    def module_enabled(self, key: str) -> bool:
        """Sekmedeki modül anahtarı ("gutter", "margin", "pnum") açık mı?"""
        return self._app._module_switch(key).get() == 1

    def module_switch_widget(self, key: str) -> Any:
        """Kabuğun (yan menü) modül anahtarı widget'ı; sekme bunu paylaşır."""
        return self._app._module_switch(key)

    def enable_module(self, key: str) -> None:
        """Modül anahtarını açar ve kabuğun durum güncellemesini çalıştırır."""
        _switch_name, toggle_name = self._MODULES[key]
        self._app._module_switch(key).select()
        getattr(self._app, toggle_name)()

    def disable_module(self, key: str) -> None:
        """Modül anahtarını kapatır ve kabuğun durum güncellemesini çalıştırır."""
        _switch_name, toggle_name = self._MODULES[key]
        self._app._module_switch(key).deselect()
        getattr(self._app, toggle_name)()

    def apply_named_preset(self, name: str) -> None:
        """Hazır profili (ör. \"Standart A4\") ayarlara uygular; kabuk durum çubuğunu günceller."""
        self._app._apply_named_preset(name)

    def bind_wraplength(self, label: Any, container: Any, padding: int) -> None:
        self._app._bind_wraplength(label, container, padding)

    def run_on_ui(self, callback: Callable[[], None]) -> None:
        self._app._ui(callback)

    def after(self, ms: int, callback: Callable[[], None]) -> Any:
        return self._app.after(ms, callback)

    def tab_built(self, tab: Any) -> None:
        """Sekme (tembel) kurulunca: takma adlar, birim ve bekleyen ayar (2.9)."""
        self._app._on_tab_built(tab)
