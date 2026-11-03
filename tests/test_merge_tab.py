"""MergeTab tek başına: tüm uygulama olmadan, sahte bağlamla kurulup denenir (Adım 2.6)."""

from __future__ import annotations

import gc
from types import SimpleNamespace

from ui import qt_compat as ctk
import pytest

from tests.fake_context import FakeContext
from tests.pdf_factory import create_sample_a4_pdf
from ui.tabs import BaseTab
from ui.tabs.merge import MergeTab
from ui.theme import COLOR_BORDER, COLOR_ERROR, COLOR_ON_ACCENT, COLOR_WARN


@pytest.fixture(scope="module")
def root():
    window = ctk.CTk()
    window.withdraw()
    yield window
    try:
        window.destroy()
    except Exception:
        pass
    # Yok edilen köke bağlı nesneler sonraki modülün iş parçacıklarında toplanmasın.
    gc.collect()


def _make(root):
    ctx = FakeContext()
    ctx.recent = []
    ctx.store = SimpleNamespace(add_recent_file=ctx.recent.append)
    frame = ctk.CTkFrame(root)
    frame.pack(fill="both", expand=True)
    tab = MergeTab("Birleştirme", ctx, frame)
    return tab, ctx, frame


@pytest.fixture()
def built(root):
    tab, ctx, frame = _make(root)
    tab.ensure_built()
    ctx.calls.clear()
    yield tab, ctx
    frame.destroy()


@pytest.fixture()
def pdfs(tmp_path):
    paths = []
    for index, pages in enumerate((1, 2, 3), start=1):
        path = str(tmp_path / f"m{index}.pdf")
        create_sample_a4_pdf(path, pages=pages)
        paths.append(path)
    return paths


def _fill(tab, paths):
    for path in paths:
        tab.append_file(path)
    tab.refresh_list()


def _pages(tab):
    return [item["pages"] for item in tab.files]


def test_is_a_base_tab_and_exposes_all_declared_widgets(root):
    tab, _ctx, frame = _make(root)
    assert isinstance(tab, BaseTab) and not tab.built
    tab.ensure_built()
    assert tab.built
    assert [name for name in MergeTab.EXPOSED if not hasattr(tab, name)] == []
    frame.destroy()


def test_defaults_after_build(built):
    tab, _ctx = built
    assert tab.chk_merge_apply_pipeline.get() == 0
    assert tab.chk_merge_bookmarks.get() == 1
    assert tab.files == [] and tab.selected_idx is None and tab.rows == []
    assert tab.merge_summary_badge.cget("text") == "Toplam: 0 dosya | 0 sayfa"


def test_state_and_list_ops_work_before_build(root, pdfs):
    tab, ctx, frame = _make(root)
    tab.append_file(pdfs[0])
    tab.refresh_list()  # kurulmamış sekmede widget yok; sessizce atlanır
    assert not tab.built and len(tab.files) == 1 and tab.rows == []
    assert ctx.names() == []
    tab.ensure_built()
    assert len(tab.rows) == 1  # build sonunda mevcut liste çizilir
    frame.destroy()


def test_append_file_adds_dedups_and_records_recent(built, pdfs, tmp_path):
    tab, ctx = built
    tab.append_file(pdfs[1])
    tab.append_file(pdfs[1])  # aynı dosya ikinci kez eklenmez
    tab.append_file(str(tmp_path / "yok.pdf"))
    tab.append_file("")
    assert [item["pages"] for item in tab.files] == [2]
    item = tab.files[0]
    assert item["rotation"] == 0 and item["page_range"] == "" and item["name"] == "m2.pdf"
    assert ctx.recent == [pdfs[1]]


def test_append_file_warns_on_unreadable_pdf(built, tmp_path, monkeypatch):
    tab, ctx = built
    bad = tmp_path / "bozuk.pdf"
    bad.write_bytes(b"bu pdf degil")
    warnings = []
    monkeypatch.setattr("ui.tabs.merge.messagebox.showwarning",
                        lambda title, message, **kw: warnings.append((title, message)))
    tab.append_file(str(bad))
    assert tab.files == [] and ctx.recent == []
    assert len(warnings) == 1 and "bozuk.pdf" in warnings[0][1]


def test_add_files_uses_dialog_selection(built, pdfs, monkeypatch):
    tab, _ctx = built
    monkeypatch.setattr("ui.tabs.merge.filedialog.askopenfilenames",
                        lambda **kw: (pdfs[0], pdfs[2]))
    tab.add_files()
    assert _pages(tab) == [1, 3] and len(tab.rows) == 2
    monkeypatch.setattr("ui.tabs.merge.filedialog.askopenfilenames", lambda **kw: "")
    tab.add_files()  # iptal: değişmez
    assert _pages(tab) == [1, 3]


def test_refresh_list_draws_rows_summary_and_schedules_preview(built, pdfs):
    tab, ctx = built
    _fill(tab, pdfs)
    assert len(tab.rows) == 3
    assert "3 dosya | 6 sayfa" in tab.merge_summary_badge.cget("text")
    assert [int(row._number_label.cget("text")) for row in tab.rows] == [1, 2, 3]
    assert "schedule_preview" in ctx.names()
    tab.clear()
    assert tab.rows == [] and tab.merge_summary_badge.cget("text") == "Toplam: 0 dosya | 0 sayfa"


def test_rotation_without_selection_changes_nothing(built, pdfs):
    tab, ctx = built
    _fill(tab, pdfs[:1])
    tab.rotate_selected(90)
    assert tab.files[0]["rotation"] == 0
    status = [call for call in ctx.calls if call[0] == "set_status"]
    assert status and "dosya seçin" in status[-1][1][0] and status[-1][1][1] == COLOR_WARN


def test_rotation_wraps_and_rotate_all(built, pdfs):
    tab, _ctx = built
    _fill(tab, pdfs[:2])
    tab.selected_idx = 0
    tab.rotate_selected_left()
    assert [i["rotation"] for i in tab.files] == [270, 0]
    tab.rotate_selected_right()
    tab.rotate_selected_right()
    assert tab.files[0]["rotation"] == 90
    tab.rotate_all(90)
    assert [i["rotation"] for i in tab.files] == [180, 90]
    badge_texts = [c.cget("text") for c in tab.rows[0].winfo_children()
                   if isinstance(c, ctk.CTkLabel) and "°" in str(c.cget("text"))]
    assert badge_texts and "180° ters" in badge_texts[0]


def test_move_up_down_follow_selection_and_stop_at_edges(built, pdfs):
    tab, _ctx = built
    _fill(tab, pdfs)
    tab.selected_idx = 0
    tab.move_up()  # başta: değişmez
    assert _pages(tab) == [1, 2, 3] and tab.selected_idx == 0
    tab.move_down()
    assert _pages(tab) == [2, 1, 3] and tab.selected_idx == 1
    tab.selected_idx = 2
    tab.move_down()  # sonda: değişmez
    assert _pages(tab) == [2, 1, 3] and tab.selected_idx == 2
    tab.move_up()
    assert _pages(tab) == [2, 3, 1] and tab.selected_idx == 1
    assert [int(r._number_label.cget("text")) for r in tab.rows] == [1, 2, 3]


def test_remove_selected_and_clear(built, pdfs):
    tab, _ctx = built
    _fill(tab, pdfs)
    tab.remove_selected()  # seçim yok: değişmez
    assert len(tab.files) == 3
    tab.selected_idx = 1
    tab.remove_selected()
    assert _pages(tab) == [1, 3] and tab.selected_idx is None and len(tab.rows) == 2
    tab.clear()
    assert tab.files == [] and tab.rows == []


def test_select_item_marks_row_and_schedules_preview(built, pdfs):
    tab, ctx = built
    _fill(tab, pdfs[:2])
    ctx.calls.clear()
    tab.select_item(1)
    assert tab.selected_idx == 1
    assert tab.rows[1]._title_label.cget("text_color") == COLOR_ON_ACCENT
    assert tab.rows[0]._title_label.cget("text_color") != COLOR_ON_ACCENT
    assert "schedule_preview" in ctx.names()
    tab.select_item(None)
    assert tab.selected_idx is None
    assert tab.rows[1]._title_label.cget("text_color") != COLOR_ON_ACCENT


def test_item_count_respects_range_and_falls_back(built):
    tab, _ctx = built
    count = tab.item_count
    assert count({"pages": 10, "page_range": ""}) == 10
    assert count({"pages": 10, "page_range": "1-3, 7"}) == 4
    assert count({"pages": 10, "page_range": "8-20"}) == 3     # sayfa sayısıyla sınırlanır
    assert count({"pages": 10, "page_range": "50"}) == 10      # hiçbiri geçerli değil: tümü
    assert count({"pages": 10}) == 10


def test_range_entry_updates_item_border_and_totals(built, pdfs):
    tab, ctx = built
    _fill(tab, pdfs[2:])
    entry = next(c for c in tab.rows[0].winfo_children() if isinstance(c, ctk.CTkEntry))
    entry.insert(0, "1-2")
    tab.on_range_changed(tab.files[0], entry)
    assert tab.files[0]["page_range"] == "1-2"
    assert "2 sayfa" in tab.merge_summary_badge.cget("text")
    assert entry.cget("border_color") == COLOR_BORDER
    entry.delete(0, "end")
    entry.insert(0, "1-2, abc")
    tab.on_range_changed(tab.files[0], entry)
    assert entry.cget("border_color") == COLOR_ERROR
    assert tab.invalid_range_lines() == ["m3.pdf: abc"]


def test_range_entry_has_keystroke_binding(built, pdfs):
    """Pencere gizliyken tuş olayı üretilemez; bağın varlığı ve geri çağrısı ayrı sınanır."""
    tab, _ctx = built
    _fill(tab, pdfs[2:])
    entry = next(c for c in tab.rows[0].winfo_children() if isinstance(c, ctk.CTkEntry))
    assert entry._entry.bind("<KeyRelease>")


def test_move_item_keeps_files_rows_numbers_and_selection_in_sync(built, pdfs):
    tab, _ctx = built
    _fill(tab, pdfs)
    first_row = tab.rows[0]
    tab.move_item(0, 2)
    assert _pages(tab) == [2, 3, 1]
    assert tab.rows[2] is first_row
    assert [int(r._number_label.cget("text")) for r in tab.rows] == [1, 2, 3]
    assert tab.selected_idx == 2 and tab.drag_idx == 2
    tab.move_item(1, 1)           # aynı yer: değişmez
    tab.move_item(9, 0)           # geçersiz kaynak: değişmez
    assert _pages(tab) == [2, 3, 1]
    tab.move_item(2, 99)          # hedef sınırlanır
    assert _pages(tab) == [2, 3, 1]


def test_index_at_finds_row_by_screen_y(built, pdfs):
    tab, _ctx = built
    _fill(tab, pdfs[:2])
    tab.frame.update()
    row = tab.rows[1]
    assert tab.index_at(row.winfo_rooty() + 1) == 1
    assert tab.index_at(-10_000) is None


def test_worker_items_and_expected_pages(built, pdfs, tmp_path):
    tab, _ctx = built
    _fill(tab, pdfs)
    tab.files[1]["rotation"] = 90
    tab.files[2]["page_range"] = "1-2"
    assert tab.worker_items() == [
        {"path": pdfs[0], "rotation": 0, "pages": ""},
        {"path": pdfs[1], "rotation": 90, "pages": ""},
        {"path": pdfs[2], "rotation": 0, "pages": "1-2"},
    ]
    assert tab.expected_pages() == 1 + 2 + 2
    tab.files[0]["path"] = str(tmp_path / "silindi.pdf")  # diskte olmayan dosya sayılmaz
    assert tab.expected_pages() == 2 + 2


def test_pipeline_checkbox_asks_shell_to_update_summary(built):
    tab, ctx = built
    tab.chk_merge_apply_pipeline.toggle()  # CTkCheckBox.toggle komutu çağırır
    assert "update_summary" in ctx.names()
