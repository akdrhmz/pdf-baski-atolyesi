"""High-DPI startup geometry must use Qt's logical screen coordinates."""

from app import ModernGutterApp
from ui.window import startup_window_sizes


def test_compact_high_dpi_screen_gets_a_fitting_window_and_relaxed_dock(monkeypatch, tmp_path):
    # 1366×768 physical pixels at 150% is about 911×512 Qt logical pixels.
    monkeypatch.setattr(ModernGutterApp, "winfo_screenwidth", lambda _self: 911)
    monkeypatch.setattr(ModernGutterApp, "winfo_screenheight", lambda _self: 512)
    app = ModernGutterApp(settings_path=tmp_path / "settings.json",
                          log_path=tmp_path / "studio.log")
    try:
        width, height, minimum_width, minimum_height, compact = app._startup_size
        assert compact
        assert width <= 911 and height <= 512
        assert minimum_width <= width and minimum_height <= height
        assert app.width() <= 911 and app.height() <= 512
        assert app.CENTER_MIN == 360
        assert app._preview_min_width == 240
        assert app.preview_panel.card.minimumWidth() == 240
    finally:
        app.destroy()


def test_standard_screen_keeps_the_regular_layout():
    width, height, minimum_width, minimum_height, compact = startup_window_sizes(1920, 1080)
    assert not compact
    assert (width, height) == (1440, 920)
    assert (minimum_width, minimum_height) == (1200, 700)
