"""Tanılama paketi: anonimleştirme, içerik, atomik yazma."""

import json
import zipfile

from core.diagnostics import (PATH_MASK, anonymize_settings, build_diagnostics_zip, collect_info,
                         scrub_text)


def test_anonymize_drops_recent_files_and_masks_paths():
    data = {
        "unit": "mm",
        "recent_files": ["C:\\Users\\Ali\\gizli.pdf"],
        "last_state": {"output_dir": "D:/Belgeler/cikti", "unc": "\\\\sunucu\\paylasim",
                       "nested": [{"p": "/home/ali/x.pdf", "n": 5}]},
        "preview_width": 480,
    }
    out = anonymize_settings(data)
    assert "recent_files" not in out
    assert out["last_state"]["output_dir"] == PATH_MASK
    assert out["last_state"]["unc"] == PATH_MASK
    assert out["last_state"]["nested"] == [{"p": PATH_MASK, "n": 5}]
    assert out["unit"] == "mm" and out["preview_width"] == 480
    assert "recent_files" in data  # özgün veri değişmez


def test_scrub_text_masks_home_and_user():
    text = "Açıldı: C:\\Users\\hamza\\Belgeler\\a.pdf kullanıcı hamza"
    out = scrub_text(text, home="C:\\Users\\hamza", user="hamza")
    assert "hamza" not in out.lower()
    assert "~" in out and "<kullanici>" in out


def test_scrub_text_ignores_tiny_user_names():
    assert scrub_text("ab abc", home="", user="ab") == "ab abc"


def test_build_zip_contents_and_no_leftover_part(tmp_path):
    log = tmp_path / "studio.log"
    log.write_text("2026 | INFO | C:\\Users\\hamza\\x.pdf işlendi\n", encoding="utf-8")
    (tmp_path / "studio.log.1").write_text("eski", encoding="utf-8")
    dest = tmp_path / "paket.zip"
    out = build_diagnostics_zip(
        dest, {"recent_files": ["C:\\a.pdf"], "unit": "mm"}, log,
        {"mantiksal_dpi": 120.0})
    assert out == dest and dest.exists()
    assert not (tmp_path / "paket.zip.part").exists()
    with zipfile.ZipFile(dest) as bundle:
        names = set(bundle.namelist())
        assert {"bilgi.json", "ayarlar_anonim.json", "OKU.txt",
                "gunluk/studio.log", "gunluk/studio.log.1"} <= names
        info = json.loads(bundle.read("bilgi.json"))
        assert info["ekran"]["mantiksal_dpi"] == 120.0 and info["surum"]
        assert "recent_files" not in json.loads(bundle.read("ayarlar_anonim.json"))


def test_build_zip_without_log_still_works(tmp_path):
    dest = tmp_path / "p.zip"
    build_diagnostics_zip(dest, {}, tmp_path / "yok.log")
    with zipfile.ZipFile(dest) as bundle:
        assert "bilgi.json" in bundle.namelist()
        assert not [n for n in bundle.namelist() if n.startswith("gunluk/")]


def test_build_zip_failure_cleans_part(tmp_path, monkeypatch):
    import core.diagnostics as diagnostics

    def boom(*_a, **_k):
        raise RuntimeError("x")
    monkeypatch.setattr(diagnostics, "collect_info", boom)
    dest = tmp_path / "p.zip"
    try:
        build_diagnostics_zip(dest, {}, tmp_path / "yok.log")
    except RuntimeError:
        pass
    assert not dest.exists() and not (tmp_path / "p.zip.part").exists()


def test_collect_info_has_versions():
    info = collect_info()
    assert info["surum"] and info["python"] and "PySide6" in info
