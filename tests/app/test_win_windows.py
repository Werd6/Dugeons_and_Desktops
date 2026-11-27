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


def _install_fake_ctypes(monkeypatch, user32, *, dwmapi=None):
    class RECT:
        def __init__(self):
            self.left = self.top = self.right = self.bottom = 0

    class DWORD:
        def __init__(self, value=0):
            self.value = value

    fake_ctypes = types.ModuleType("ctypes")
    fake_ctypes.c_bool = bool
    fake_ctypes.windll = types.SimpleNamespace(user32=user32, dwmapi=dwmapi)
    fake_ctypes.wintypes = types.SimpleNamespace(
        HWND=int, LPARAM=int, UINT=int, DWORD=DWORD, RECT=RECT
    )
    fake_ctypes.byref = lambda obj: obj
    fake_ctypes.sizeof = lambda obj: 4
    fake_ctypes.create_unicode_buffer = lambda n: types.SimpleNamespace(value="")

    def winfunctype(*_a, **_k):
        def deco(fn):
            return fn

        return deco

    fake_ctypes.WINFUNCTYPE = winfunctype
    monkeypatch.setitem(sys.modules, "ctypes", fake_ctypes)
    return fake_ctypes


def test_win_window_source_keeps_visible_app_windows_only(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("os.getpid", lambda: 42)

    user32 = MagicMock()
    dpi_fn = MagicMock(return_value=96)
    dpi_fn.restype = None
    dpi_fn.argtypes = None
    user32.GetDpiForWindow = dpi_fn
    fake_ctypes = _install_fake_ctypes(monkeypatch, user32)

    # Enumerate: good, toolwindow, owned, own-pid, invisible, tiny, shell WorkerW.
    windows = [10, 11, 12, 13, 14, 15, 16]
    class_names = {16: "WorkerW"}

    def enum_windows(callback, _lparam):
        for hwnd in windows:
            callback(hwnd, 0)
        return True

    user32.EnumWindows.side_effect = enum_windows
    user32.IsWindowVisible.side_effect = lambda hwnd: hwnd != 14
    user32.IsIconic.return_value = False
    user32.GetWindow.side_effect = lambda hwnd, _gw: 99 if hwnd == 12 else 0
    user32.GetWindowLongW.side_effect = lambda hwnd, _idx: 0x80 if hwnd == 11 else 0

    def get_class(hwnd, buf, _n):
        buf.value = class_names.get(hwnd, "Chrome_WidgetWin_1")
        return len(buf.value)

    user32.GetClassNameW.side_effect = get_class
    # Rebind create_unicode_buffer so GetClassNameW can assign .value
    def make_buf(n):
        return types.SimpleNamespace(value="")

    fake_ctypes.create_unicode_buffer = make_buf

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
            16: (0, 0, 1920, 1080),
        }
        left, top, right, bottom = sizes.get(hwnd, (0, 0, 0, 0))
        rect.left, rect.top, rect.right, rect.bottom = left, top, right, bottom
        return 1

    user32.GetWindowRect.side_effect = get_rect

    source = WinWindowSource()
    records = source.snapshot()
    assert records == [WindowRecord(10, Rect(0.0, 0.0, 400.0, 300.0))]


def test_win_window_source_skips_cloaked_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("os.getpid", lambda: 1)

    user32 = MagicMock()
    dwmapi = MagicMock()
    user32.GetDpiForWindow = MagicMock(return_value=96)
    fake_ctypes = _install_fake_ctypes(monkeypatch, user32, dwmapi=dwmapi)

    def make_buf(_n):
        return types.SimpleNamespace(value="")

    fake_ctypes.create_unicode_buffer = make_buf
    user32.GetClassNameW.side_effect = lambda hwnd, buf, _n: setattr(buf, "value", "AppWindow") or 9

    def enum_windows(callback, _lparam):
        callback(20, 0)
        callback(21, 0)
        return True

    user32.EnumWindows.side_effect = enum_windows
    user32.IsWindowVisible.return_value = True
    user32.IsIconic.return_value = False
    user32.GetWindow.return_value = 0
    user32.GetWindowLongW.return_value = 0
    user32.GetWindowThreadProcessId.side_effect = lambda hwnd, pid_ref: setattr(
        pid_ref, "value", 9
    )

    def get_rect(hwnd, rect):
        rect.left, rect.top, rect.right, rect.bottom = 0, 0, 500, 400
        return 1

    user32.GetWindowRect.side_effect = get_rect

    def cloak_attr(hwnd, _attr, cloaked_ref, _size):
        cloaked_ref.value = 1 if hwnd == 20 else 0
        return 0

    dwmapi.DwmGetWindowAttribute.side_effect = cloak_attr

    source = WinWindowSource()
    assert source.snapshot() == [WindowRecord(21, Rect(0.0, 0.0, 500.0, 400.0))]
