"""PreviewPanel tek başına: tüm uygulama olmadan, sahte ev sahibiyle kurulup denenir (Adım 2.7)."""

from __future__ import annotations

import gc
import io
import time
from types import SimpleNamespace
from typing import Any, Callable, List

from ui import qt_compat as ctk
import pytest
from PIL import Image

from ui.preview import PREVIEW_HISTORY_LIMIT, PreviewHost, PreviewPanel
from ui.theme import COLOR_ERROR, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_WARN


class FakeHost:
    """``PreviewHost`` sahtesi: gecikmeli çağrıları ve arayüz kuyruğunu elle işletir."""

    def __init__(self):
        self.log = SimpleNamespace(warning=lambda *a, **k: None)
        self.orig_page_count = 0
        self.path = ""
        self.config: Any = object()
        self.ui_queue: List[Callable[[], None]] = []
        self.afters: List[tuple] = []
        self.cancelled: List[Any] = []
        self.scan_calls = 0
        self.wrap_calls = 0
        self.color = "#112233"

    def source_path(self) -> str:
        return self.path

    def build_config(self) -> Any:
        return self.config

    def run_on_ui(self, callback) -> None:
        self.ui_queue.append(callback)

    def after(self, ms, callback) -> Any:
        self.afters.append((ms, callback))
        return f"after-{len(self.afters)}"

    def after_cancel(self, after_id) -> None:
        self.cancelled.append(after_id)

    def bind_wraplength(self, label, container, padding) -> None:
        self.wrap_calls += 1

    def appearance_color(self, color) -> str:
        return self.color

    def scan_for_clipping(self) -> None:
        self.scan_calls += 1

    def pump(self, until=None, timeout=5.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            while self.ui_queue:
                self.ui_queue.pop(0)()
            if until is None or until():
                return True
            time.sleep(0.02)
        return False


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 56), "white").save(buffer, "PNG")
    return buffer.getvalue()


def _page(index=0, clipped=False):
    return SimpleNamespace(
        png=_png(), width_pt=595.0, height_pt=842.0, width_mm=210.0, height_mm=297.0,
        scale=1.0, is_odd=index % 2 == 0, page_index=index, number_text="",
        clipped=clipped, clip_mm=(0.0, 2.5, 0.0, 0.0),
    )


@pytest.fixture(scope="module")
def root():
    window = ctk.CTk()
    window.withdraw()
    yield window
    try:
        window.destroy()
    except Exception:
        pass
    gc.collect()


@pytest.fixture()
def built(root, tmp_path, monkeypatch):
    # Sahte yapılandırma nesnesi dataclass olmadığı için imza üretimi sadeleştirilir.
    monkeypatch.setattr("ui.preview.config_to_dict", lambda config: {"cfg": id(config)})
    host = FakeHost()
    panel = PreviewPanel(host)
    parent = ctk.CTkFrame(root)
    parent.pack(fill="both", expand=True)
    panel.build(parent)
    pdf = tmp_path / "belge.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    host.path = str(pdf)
    yield panel, host
    parent.destroy()
    # Yok edilen çerçevenin PhotoImage'ları, sonraki testin üretim iş parçacığında toplanıp
    # Tk'ya dokunmasın (iş parçacığından Tk çağrısı takılır); burada, ana iş parçacığında toplanır.
    panel.images.clear()
    panel.history.clear()
    gc.collect()


def test_fake_host_satisfies_the_protocol_surface():
    host = FakeHost()
    surface = ("log", "orig_page_count", "source_path", "build_config", "run_on_ui", "after",
               "after_cancel", "bind_wraplength", "appearance_color", "scan_for_clipping")
    assert [name for name in surface if not hasattr(host, name)] == []
    assert [name for name in surface if not hasattr(PreviewHost, name)
            and name not in PreviewHost.__annotations__] == []


def test_state_exists_before_widgets_and_schedule_defers(root):
    host = FakeHost()
    panel = PreviewPanel(host)
    assert (panel.mode, panel.page, panel.gen, panel.images, panel.history) == ("spread", 0, 0, [], [])
    panel.schedule()
    assert host.afters and host.afters[0][0] == 300 and panel.after_id == "after-1"
    panel.schedule()                       # ikinci çağrı öncekini iptal eder
    assert host.cancelled == ["after-1"] and panel.after_id == "after-2"
    panel.update_nav()                     # pencere öğesi yok: sessizce atlanır
    panel.apply_layout()
    panel.cancel_pending()
    assert host.cancelled[-1] == "after-2" and panel.after_id is None


def test_build_creates_widgets_and_defaults(built):
    panel, host = built
    assert panel.preview_mode_menu.get() == "Çift sayfa"
    assert len(panel.slots) == 2 and set(panel.blank_images) == {"spread", "single"}
    assert panel.preview_page_label.cget("text") == "—"
    assert panel.preview_prev_btn.cget("state") == "disabled"
    assert panel.preview_next_btn.cget("state") == "disabled"
    assert host.wrap_calls >= 4


def test_refresh_without_source_clears_and_without_config_warns(built):
    panel, host = built
    host.path = ""
    panel.refresh()
    assert "Belge seçildiğinde" in panel.preview_info.cget("text")
    host.path = __file__
    host.config = None
    panel.refresh()
    assert panel.preview_info.cget("text") == "Önizleme için ayarları düzeltin."
    assert panel.preview_info.cget("text_color") == COLOR_WARN


def _patch_render(monkeypatch, calls, pages_factory=lambda wanted: [_page(i) for i in wanted]):
    def fake_render(path, config, pages, zoom):
        calls.append(tuple(pages))
        return pages_factory(pages)
    monkeypatch.setattr("ui.preview.render_preview", fake_render)
    monkeypatch.setattr("ui.preview.config_to_dict", lambda config: {"cfg": id(config)})


def test_refresh_renders_in_background_and_caches_by_signature(built, monkeypatch):
    panel, host = built
    host.orig_page_count = 5
    calls = []
    _patch_render(monkeypatch, calls)
    panel.refresh()
    assert host.pump(lambda: len(panel.images) == 2)
    assert calls == [(0, 1)]
    assert "210.0 × 297.0 mm" in panel.preview_info.cget("text")
    assert panel.preview_info.cget("text_color") == COLOR_TEXT_PRIMARY
    gen = panel.gen
    panel.refresh()                         # aynı dosya + ayar + sayfa: yeniden üretilmez
    host.pump()
    assert panel.gen == gen and calls == [(0, 1)]
    host.config = object()                  # ayar değişti: yeniden üretilir
    panel.refresh()
    assert host.pump(lambda: len(calls) == 2) and panel.gen == gen + 1


def test_refresh_now_forces_regeneration_and_cancels_pending(built, monkeypatch):
    panel, host = built
    calls = []
    _patch_render(monkeypatch, calls)
    panel.schedule()
    panel.refresh_now()
    assert host.cancelled and panel.after_id is None
    assert host.pump(lambda: len(panel.images) == 2)
    panel.refresh_now()
    assert host.pump(lambda: len(calls) == 2)


def test_stale_generation_and_errors_are_handled(built):
    panel, host = built
    panel.gen = 5
    panel.show(4, [_page(0)], None)         # eski üretim: yok sayılır
    assert panel.images == []
    panel.signature = ("x",)
    panel.show(5, [], "bozuk")
    assert panel.signature is None
    assert panel.preview_info.cget("text") == "Önizleme üretilemedi: bozuk"
    panel.show(5, [], None)
    assert "sayfa bulunamadı" in panel.preview_info.cget("text")


def test_render_failure_is_reported_through_the_ui_queue(built, monkeypatch):
    panel, host = built
    def boom(*a, **k):
        raise RuntimeError("motor hatası")
    monkeypatch.setattr("ui.preview.render_preview", boom)
    monkeypatch.setattr("ui.preview.config_to_dict", lambda config: {})
    panel.refresh()
    assert host.pump(lambda: "motor hatası" in panel.preview_info.cget("text"))


def test_show_marks_clipping_and_history_is_capped(built):
    panel, host = built
    host.orig_page_count = 3
    panel.show(panel.gen, [_page(0, clipped=True), _page(1)], None)
    assert "Kırpma riski" in panel.preview_warning.cget("text")
    assert "Sayfa 1: sağ 2.5 mm" in panel.preview_warning.cget("text")
    assert [cap.cget("text") for _s, _l, cap in panel.slots] == ["1. sayfa • Tek (sağ)", "2. sayfa • Çift (sol)"]
    for _ in range(10):
        panel.show(panel.gen, [_page(0), _page(1)], None)
    assert len(panel.history) == PREVIEW_HISTORY_LIMIT and len(panel.images) == 2
    panel.show(panel.gen, [_page(0)], None)
    assert panel.preview_warning.cget("text") == "" and len(panel.images) == 1


def test_navigation_spread_and_single(built, monkeypatch):
    panel, host = built
    host.orig_page_count = 5
    _patch_render(monkeypatch, [])
    panel.update_nav()
    assert panel.preview_page_label.cget("text") == "1–2 / 5"
    assert panel.preview_prev_btn.cget("state") == "disabled" and panel.preview_next_btn.cget("state") == "normal"
    panel.next_page()
    panel.next_page()
    assert panel.page == 4 and panel.preview_page_label.cget("text") == "5 / 5"
    assert panel.preview_next_btn.cget("state") == "disabled"
    panel.next_page()                       # sonda: değişmez
    assert panel.page == 4
    panel.on_mode_changed("Tek sayfa")
    assert panel.mode == "single"
    panel.previous()
    assert panel.page == 3 and panel.preview_page_label.cget("text") == "4 / 5"
    panel.on_mode_changed("Çift sayfa")
    assert panel.mode == "spread"
    host.pump()


def test_single_mode_hides_second_slot_and_restores_it(built, root):
    panel, host = built
    panel.on_mode_changed("Tek sayfa")
    root.update()
    assert panel.slots[0][0].grid_info()["columnspan"] == 2
    assert panel.slots[1][0].grid_info() == {}      # grid_remove
    panel.on_mode_changed("Çift sayfa")
    root.update()
    assert panel.slots[0][0].grid_info()["columnspan"] == 1
    assert panel.slots[1][0].grid_info() != {}


def test_step_does_nothing_without_a_document(built):
    panel, host = built
    host.orig_page_count = 0
    panel.next_page()
    panel.previous()
    assert panel.page == 0 and panel.preview_page_label.cget("text") == "—"


def test_reset_invalidate_and_theme(built):
    panel, host = built
    host.orig_page_count = 4
    panel.page = 2
    panel.signature = ("eski",)
    panel.show(panel.gen, [_page(2), _page(3)], None)
    gen = panel.gen
    panel.reset_for_new_document()
    assert (panel.page, panel.signature, panel.gen) == (0, None, gen + 1)
    assert panel.images == []
    assert panel.preview_info.cget("text") == "Önizleme hazırlanıyor..."
    assert panel.preview_info.cget("text_color") == COLOR_TEXT_SECONDARY
    panel.invalidate()
    assert panel.gen == gen + 2
    host.color = "#445566"                  # tema değişti
    assert all(str(label.cget("bg")) == "#112233" for _s, label, _c in panel.slots)
    panel.apply_theme()
    assert all(str(label.cget("bg")) == "#445566" for _s, label, _c in panel.slots)


def test_buttons_route_to_panel_and_host(built, monkeypatch):
    panel, host = built
    buttons = []
    def walk(widget):
        for child in widget.winfo_children():
            if isinstance(child, ctk.CTkButton):
                buttons.append(child)
            walk(child)
    walk(panel.image_frame.master)
    texts = {button.cget("text"): button for button in buttons}
    texts["Kırpma riskini tara"].invoke()
    assert host.scan_calls == 1
    calls = []
    _patch_render(monkeypatch, calls)
    texts["Önizlemeyi yenile"].invoke()
    assert host.pump(lambda: len(calls) == 1)
