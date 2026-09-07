"""Tests for bundled renderer fonts."""

from pathlib import Path

from render_sbgn_py import renderer
from render_sbgn_py._fonts import BUNDLED_FONT_PATH


def test_bundled_font_and_fallback_order() -> None:
    """Ship Liberation Sans and preserve the documented fallback order."""

    assert renderer.FONT_FAMILIES == (
        "Liberation Sans",
        "Arial",
        "DejaVu Sans",
        "Helvetica",
        "sans-serif",
    )
    assert Path(BUNDLED_FONT_PATH).is_file()
    assert Path(BUNDLED_FONT_PATH).stat().st_size > 0


def test_bundled_font_registers() -> None:
    """Register the package-local font with the active platform backend."""

    renderer.register_bundled_font()
