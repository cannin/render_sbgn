"""Tests for the supported package-level Python API."""

import render_sbgn_py
from render_sbgn_py.renderer import draw_sbgnml, write_render_test_manifest


def test_renderer_functions_are_exported_from_package_root() -> None:
    """Expose the supported renderer entry points at the package root."""

    assert render_sbgn_py.draw_sbgnml is draw_sbgnml
    assert render_sbgn_py.write_render_test_manifest is write_render_test_manifest
    assert set(render_sbgn_py.__all__) == {
        "__version__",
        "draw_sbgnml",
        "write_render_test_manifest",
    }
