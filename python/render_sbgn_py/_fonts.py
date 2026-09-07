"""Register the bundled renderer font with the host text stack."""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import sys
import threading
from pathlib import Path

FONT_FAMILIES = (
    "Liberation Sans",
    "Arial",
    "DejaVu Sans",
    "Helvetica",
    "sans-serif",
)
BUNDLED_FONT_PATH = Path(__file__).with_name("fonts") / "LiberationSans-Regular.ttf"
_FONT_REGISTRATION_LOCK = threading.Lock()
_FONT_REGISTERED = False


def _register_with_fontconfig(font_path: Path) -> bool:
    """Register a private font with the active Unix fontconfig instance."""
    library_name = ctypes.util.find_library("fontconfig")
    if library_name is None:
        return False
    library = ctypes.CDLL(library_name)
    library.FcConfigGetCurrent.argtypes = []
    library.FcConfigGetCurrent.restype = ctypes.c_void_p
    library.FcConfigAppFontAddFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    library.FcConfigAppFontAddFile.restype = ctypes.c_int
    config = library.FcConfigGetCurrent()
    return bool(config and library.FcConfigAppFontAddFile(config, os.fsencode(font_path)))


def _register_with_windows(font_path: Path) -> bool:
    """Register a private font with the Windows graphics subsystem."""
    add_font = getattr(ctypes, "windll").gdi32.AddFontResourceExW
    add_font.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
    add_font.restype = ctypes.c_int
    return bool(add_font(str(font_path), 0x10, None))


def _register_with_core_text(font_path: Path) -> bool:
    """Register a private font with macOS Core Text."""
    core_foundation_name = ctypes.util.find_library("CoreFoundation")
    core_text_name = ctypes.util.find_library("CoreText")
    if core_foundation_name is None or core_text_name is None:
        return False
    core_foundation = ctypes.CDLL(core_foundation_name)
    core_text = ctypes.CDLL(core_text_name)
    core_foundation.CFURLCreateFromFileSystemRepresentation.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_long,
        ctypes.c_bool,
    ]
    core_foundation.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
    core_foundation.CFRelease.argtypes = [ctypes.c_void_p]
    core_text.CTFontManagerRegisterFontsForURL.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_void_p,
    ]
    core_text.CTFontManagerRegisterFontsForURL.restype = ctypes.c_bool
    encoded_path = os.fsencode(font_path)
    url = core_foundation.CFURLCreateFromFileSystemRepresentation(
        None, encoded_path, len(encoded_path), False
    )
    if not url:
        return False
    try:
        return bool(core_text.CTFontManagerRegisterFontsForURL(url, 1, None))
    finally:
        core_foundation.CFRelease(url)


def register_bundled_font() -> None:
    """Register bundled Liberation Sans once for the current process."""
    global _FONT_REGISTERED

    if _FONT_REGISTERED:
        return
    with _FONT_REGISTRATION_LOCK:
        if _FONT_REGISTERED:
            return
        if not BUNDLED_FONT_PATH.is_file():
            raise RuntimeError(f"bundled font is missing: {BUNDLED_FONT_PATH}")
        if sys.platform == "win32":
            registered = _register_with_windows(BUNDLED_FONT_PATH)
        elif sys.platform == "darwin":
            registered = _register_with_core_text(BUNDLED_FONT_PATH)
        else:
            registered = _register_with_fontconfig(BUNDLED_FONT_PATH)
        if not registered:
            fallbacks = " -> ".join(FONT_FAMILIES)
            raise RuntimeError(
                "could not register bundled Liberation Sans; "
                f"font fallback order is {fallbacks}"
            )
        _FONT_REGISTERED = True
