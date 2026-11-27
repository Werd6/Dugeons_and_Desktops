"""WinWindowSource filtering (ctypes mocked; runnable on any host OS)."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from dungeons_desktops.core.geometry import Rect
from dungeons_desktops.desktop.windows import WinWindowSource, WindowRecord, WindowSourceError


def test_win_window_source_rejects_non_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    with pytest.raises(WindowSourceError, match="Windows"):
        WinWindowSource()


def test_win_window_source_keeps_visible_app_windows_only(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("os.getpid", lambda: 42)

    user32 = MagicMock()
    dpi_fn = MagicMock(return_value=96)
    dpi_fn.restype = None
    dpi_fn.argtypes = None
    user32.GetDpiForWindow = dpi_fn

    class RECT:
        def __init__(self):
            self.left = self.top = self.right = self.bottom = 0

    class DWORD:
        def __init__(self, value=0):
            self.value = value

    fake_ctypes = types.ModuleType("ctypes")
    fake_ctypes.c_bool = bool
    fake_ctypes.windll = types.SimpleNamespace(user32=user32)
    fake_ctypes.wintypes = types.SimpleNamespace(HWND=int, LPARAM=int, UINT=int, DWORD=DWORD, RECT=RECT)
    fake_ctypes.byref = lambda obj: obj

    def winfunctype(*_a, **_k):
        def deco(fn):
            return fn

        return deco

    fake_ctypes.WINFUNCTYPE = winfunctype
    monkeypatch.setitem(sys.modules, "ctypes", fake_ctypes)

    # Enumerate: good, toolwindow, owned, own-pid, invisible, tiny.
    windows = [10, 11, 12, 13, 14, 15]

    def enum_windows(callback, _lparam):
        for hwnd in windows:
            callback(hwnd, 0)
        return True

    user32.EnumWindows.side_effect = enum_windows
    user32.IsWindowVisible.side_effect = lambda hwnd: hwnd != 14
    user32.IsIconic.return_value = False
    user32.GetWindow.side_effect = lambda hwnd, _gw: 99 if hwnd == 12 else 0
    user32.GetWindowLongW.side_effect = lambda hwnd, _idx: 0x80 if hwnd == 11 else 0

    def get_pid(hwnd, pid_ref):
        pid_ref.value = 42 if hwnd == 13 else 7
        return 0

    user32.GetWindowThreadProcessId.side_effect = get_pid

    def get_rect(hwnd, rect):
        sizes = {
            10: (0, 0, 400, 300),
            11: (0, 0, 400, 300),
            12: (0, 0, 400, 300),
            13: (0, 0, 400, 300),
            15: (0, 0, 4, 4),
        }
        left, top, right, bottom = sizes.get(hwnd, (0, 0, 0, 0))
        rect.left, rect.top, rect.right, rect.bottom = left, top, right, bottom
        return 1

    user32.GetWindowRect.side_effect = get_rect

    source = WinWindowSource()
    records = source.snapshot()
    assert records == [WindowRecord(10, Rect(0.0, 0.0, 400.0, 300.0))]
