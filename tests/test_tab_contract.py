"""BaseTab sözleşmesi ve AppContext: Tk penceresi olmadan çalışan testler."""

from __future__ import annotations

import pytest

from tests.fake_context import FakeContext
from ui.context import AppContext, TabContext
from ui.tabs import BaseTab


class _Canvas:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.moved = []

    def yview_moveto(self, fraction):
        if self.fail:
            raise RuntimeError("canvas yok oldu")
        self.moved.append(fraction)


class _Child:
    def __init__(self, canvas=None):
        if canvas is not None:
            self._parent_canvas = canvas


class _Frame:
    def __init__(self, children):
        self._children = children

    def winfo_children(self):
        return list(self._children)


class _CountingTab(BaseTab):
    def __init__(self, ctx, frame=None):
        super().__init__("sayac", ctx, frame)
        self.build_calls = 0

    def build(self):
        self.build_calls += 1
        self.ctx.update_summary()


def test_base_build_must_be_implemented():
    with pytest.raises(NotImplementedError):
        BaseTab("x", FakeContext(), None).build()


def test_ensure_built_runs_build_only_once():
    ctx = FakeContext()
    tab = _CountingTab(ctx)
    assert tab.built is False
    tab.ensure_built()
    tab.ensure_built()
    assert tab.built is True and tab.build_calls == 1
    assert ctx.names() == ["update_summary"]


def test_failed_build_is_retried_not_marked_built():
    class Flaky(BaseTab):
        attempts = 0

        def build(self):
            Flaky.attempts += 1
            if Flaky.attempts == 1:
                raise RuntimeError("ilk deneme düştü")

    tab = Flaky("flaky", FakeContext(), None)
    with pytest.raises(RuntimeError):
        tab.ensure_built()
    assert tab.built is False
    tab.ensure_built()
    assert tab.built is True and Flaky.attempts == 2


def test_on_show_scrolls_scrollable_children_to_top():
    first, second = _Canvas(), _Canvas()
    frame = _Frame([_Child(first), _Child(), _Child(second)])
    _CountingTab(FakeContext(), frame).on_show()
    assert first.moved == [0.0] and second.moved == [0.0]


def test_on_show_tolerates_missing_frame_and_broken_canvas():
    _CountingTab(FakeContext(), None).on_show()
    healthy = _Canvas()
    frame = _Frame([_Child(_Canvas(fail=True)), _Child(healthy)])
    _CountingTab(FakeContext(), frame).on_show()
    assert healthy.moved == [0.0], "bozuk bir tuval diğerlerini engellememeli"


def test_apply_theme_default_is_a_no_op():
    ctx = FakeContext()
    _CountingTab(ctx).apply_theme()
    assert ctx.calls == []


def test_ensure_built_notifies_context_tab_built_hook_once():
    built_tabs = []
    ctx = FakeContext()
    ctx.tab_built = lambda t: built_tabs.append(t.name)
    tab = _CountingTab(ctx)
    tab.ensure_built()
    tab.ensure_built()
    assert built_tabs == ["sayac"]


def test_tab_can_be_built_with_fake_context_and_no_window():
    """2.2'nin amacı: sekme mantığı pencere olmadan, sahte bağlamla denenebilir."""
    ctx = FakeContext(unit="cm")

    class Probe(BaseTab):
        def build(self):
            self.ctx.set_status(f"birim {self.ctx.unit}")
            self.ctx.schedule_preview()

    Probe("probe", ctx, None).ensure_built()
    assert ctx.calls == [("set_status", ("birim cm", None)), ("schedule_preview", ())]


def test_fake_context_satisfies_the_protocol():
    assert isinstance(FakeContext(), TabContext)
    missing = [name for name in PROTOCOL_MEMBERS if not hasattr(FakeContext(), name)]
    assert missing == []


PROTOCOL_MEMBERS = (
    "store", "log", "perf", "unit", "input_pdf_path", "orig_page_count", "current_tab",
    "on_field_changed", "schedule_preview", "update_summary", "set_status",
    "select_tab", "module_enabled", "enable_module", "bind_wraplength", "run_on_ui", "after",
)


def test_app_context_exposes_every_protocol_member():
    members = PROTOCOL_MEMBERS
    missing = [name for name in members if not hasattr(AppContext, name)]
    assert missing == [], f"AppContext şu üyeleri sağlamıyor: {missing}"
