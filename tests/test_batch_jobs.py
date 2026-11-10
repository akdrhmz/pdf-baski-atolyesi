"""Batch processing keeps sources, handles filename collisions and reports per-file errors."""

import pymupdf

from gutter_engine import PdfProcessConfig
from ui.batch_jobs import run_batch


def _pdf(path, text):
    with pymupdf.open() as doc:
        page = doc.new_page(width=300, height=420)
        page.insert_text((30, 60), text)
        doc.save(path)


def test_batch_processes_files_independently_and_resolves_name_collisions(tmp_path):
    first_dir, second_dir = tmp_path / "a", tmp_path / "b"
    first_dir.mkdir()
    second_dir.mkdir()
    first, second = first_dir / "book.pdf", second_dir / "book.pdf"
    _pdf(first, "FIRST SOURCE")
    _pdf(second, "SECOND SOURCE")
    originals = (first.read_bytes(), second.read_bytes())
    output = tmp_path / "out"
    results = run_batch([str(first), str(second)], str(output),
                        PdfProcessConfig(quality_mode="standard"))
    assert [item.state for item in results] == ["Tamamlandı", "Tamamlandı"]
    assert results[0].output != results[1].output
    assert (first.read_bytes(), second.read_bytes()) == originals
    for item in results:
        with pymupdf.open(item.output) as doc:
            assert doc.page_count == 1


def test_batch_reports_bad_files_without_stopping_following_items(tmp_path):
    good = tmp_path / "good.pdf"
    bad = tmp_path / "bad.pdf"
    _pdf(good, "GOOD")
    bad.write_text("not a PDF", encoding="utf-8")
    results = run_batch([str(bad), str(good)], str(tmp_path / "out"),
                        PdfProcessConfig(quality_mode="standard"))
    assert [item.state for item in results] == ["Hata", "Tamamlandı"]
    assert "açılamadı" in results[0].detail.lower() or "pdf" in results[0].detail.lower()
