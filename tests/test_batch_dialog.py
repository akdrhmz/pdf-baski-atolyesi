"""The batch window wires profiles, file lists and background results together."""

import time

import pymupdf
from PySide6.QtWidgets import QApplication

from app import ModernGutterApp
from ui.batch_dialog import BatchDialog


def _source(path):
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.insert_text((60, 100), "Batch source page")
        doc.save(path)


def test_batch_dialog_runs_and_reports_a_file(tmp_path):
    source = tmp_path / "source.pdf"
    _source(source)
    output = tmp_path / "output"
    app = ModernGutterApp(settings_path=tmp_path / "settings.json",
                          log_path=tmp_path / "studio.log")
    dialog = None
    try:
        app._apply_gutter_preset(15)
        dialog = BatchDialog(app)
        assert "PDF listesi boş" in dialog.file_list.item(0).text()
        dialog._add_paths([str(source)])
        dialog.output.insert(0, str(output))
        assert "Tez (üniversite)" in dialog.profile.cget("values")
        dialog.run()
        deadline = time.monotonic() + 15
        while dialog._busy and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(0.01)
        QApplication.processEvents()
        assert not dialog._busy
        assert dialog.file_list.item(0).text().startswith("Tamamlandı")
        assert list(output.glob("*.pdf"))
        with pymupdf.open(source) as doc:
            assert doc.page_count == 1
    finally:
        if dialog is not None and not dialog._busy:
            dialog.close()
        app.destroy()
