"""Pencere olmadan sekme denemek için ``TabContext`` sahtesi (çağrıları kaydeder)."""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Tuple


class FakeContext:
    def __init__(self, unit: str = "mm"):
        self.store = object()
        self.log = _NullLog()
        self.perf = object()
        self.unit = unit
        self.input_pdf_path = ""
        self.orig_page_count = 0
        self.orig_width_mm = 210.0
        self.orig_height_mm = 297.0
        self.current_tab = ""
        self.modules = {"gutter": False, "margin": False, "pnum": False}
        self.calls: List[Tuple[str, tuple]] = []

    def _record(self, name: str, *args: Any) -> None:
        self.calls.append((name, args))

    def on_field_changed(self) -> None:
        self._record("on_field_changed")

    def schedule_preview(self) -> None:
        self._record("schedule_preview")

    def update_summary(self) -> None:
        self._record("update_summary")

    def set_status(self, text: str, color: Optional[Any] = None) -> None:
        self._record("set_status", text, color)

    def select_tab(self, name: str) -> None:
        self._record("select_tab", name)

    def module_enabled(self, key: str) -> bool:
        return self.modules[key]

    def enable_module(self, key: str) -> None:
        self._record("enable_module", key)
        self.modules[key] = True

    def disable_module(self, key: str) -> None:
        self._record("disable_module", key)
        self.modules[key] = False

    def apply_named_preset(self, name: str) -> None:
        self._record("apply_named_preset", name)

    def bind_wraplength(self, label: Any, container: Any, padding: int) -> None:
        self._record("bind_wraplength", padding)

    def run_on_ui(self, callback: Callable[[], None]) -> None:
        self._record("run_on_ui")
        callback()

    def after(self, ms: int, callback: Callable[[], None]) -> Any:
        self._record("after", ms)
        callback()
        return "after-id"

    def names(self) -> List[str]:
        return [name for name, _ in self.calls]


class _NullLog:
    def __getattr__(self, _name: str):
        return lambda *a, **k: None
