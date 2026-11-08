"""Windows Explorer clipboard helpers."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path


def copied_file_paths() -> list[str]:
    """Return existing files copied in Explorer (CF_HDROP), without reading clipboard text."""
    if os.name != "nt":
        return []
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    shell32.DragQueryFileW.argtypes = [
        wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT
    ]
    shell32.DragQueryFileW.restype = wintypes.UINT

    if not user32.OpenClipboard(None):
        return []
    try:
        handle = user32.GetClipboardData(15)  # CF_HDROP
        if not handle:
            return []
        count = shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
        paths = []
        for index in range(count):
            length = shell32.DragQueryFileW(handle, index, None, 0)
            buffer = ctypes.create_unicode_buffer(length + 1)
            shell32.DragQueryFileW(handle, index, buffer, length + 1)
            path = buffer.value
            if path and Path(path).is_file():
                paths.append(path)
        return paths
    except Exception as exc:
        print(f"Не удалось прочитать скопированные файлы: {exc}", flush=True)
        return []
    finally:
        user32.CloseClipboard()
