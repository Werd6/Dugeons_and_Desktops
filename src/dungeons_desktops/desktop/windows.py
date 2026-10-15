"""Read-only snapshots of the desktop's app windows, and diffs between snapshots.

A `WindowSource` lists visible app windows front to back as plain rectangles in
global logical points (top-left origin, y down - the same frame Qt uses for
screen geometry). Nothing here moves, focuses or otherwise touches a window, and
no titles or contents are read.

`WindowTracker` turns successive snapshots into the box list the simulation
uses: boxes keep a stable index while their window exists, and each update says
which boxes moved, by how much, and which disappeared.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.navigation.terrain import TerrainChange

MIN_WIDTH = 120.0
MIN_HEIGHT = 60.0
TOLERANCE = 1.0


@dataclass(frozen=True)
class WindowRecord:
    id: int
    rect: Rect


class WindowSource(Protocol):
    def snapshot(self) -> list[WindowRecord]:
        """Visible app windows, frontmost first."""
        ...


class WindowSourceError(RuntimeError):
    pass


class MacWindowSource:
    """Window bounds from Quartz `CGWindowListCopyWindowInfo` (needs no permissions)."""

    def __init__(self) -> None:
        try:
            import Quartz
        except ImportError as error:
            raise WindowSourceError(
                "pyobjc-framework-Quartz is not installed; run pip install -e '.[dev]'"
            ) from error
        self._quartz = Quartz
        self._pid = os.getpid()

    def snapshot(self) -> list[WindowRecord]:
        q = self._quartz
        options = q.kCGWindowListOptionOnScreenOnly | q.kCGWindowListExcludeDesktopElements
        info = q.CGWindowListCopyWindowInfo(options, q.kCGNullWindowID)
        if info is None:
            raise WindowSourceError("the window server returned no window list")
        records = []
        for window in info:
            if window.get("kCGWindowLayer", -1) != 0:
                continue
            if window.get("kCGWindowAlpha", 1.0) <= 0.0:
                continue
            if window.get("kCGWindowOwnerPID") == self._pid:
                continue
            bounds = window.get("kCGWindowBounds")
            if bounds is None:
                continue
            rect = Rect(
                float(bounds["X"]),
                float(bounds["Y"]),
                float(bounds["Width"]),
                float(bounds["Height"]),
            )
            records.append(WindowRecord(int(window["kCGWindowNumber"]), rect))
        return records


class FakeWindowSource:
    """Scripted windows for tests and `--mock-desktop`; edit `records` to move them."""

    def __init__(self, records: Sequence[WindowRecord] = ()) -> None:
        self.records = list(records)

    def snapshot(self) -> list[WindowRecord]:
        return list(self.records)

    def move(self, window_id: int, dx: float, dy: float) -> None:
        self.records = [
            WindowRecord(r.id, r.rect.moved(dx, dy)) if r.id == window_id else r
            for r in self.records
        ]

    def remove(self, window_id: int) -> None:
        self.records = [r for r in self.records if r.id != window_id]


def demo_windows(area: Rect) -> list[WindowRecord]:
    """A few made-up windows laid out inside `area`, for `--mock-desktop`."""
    x, y, w, h = area.x, area.y, area.width, area.height
    return [
        WindowRecord(1, Rect(x + w * 0.08, y + h * 0.55, w * 0.22, h * 0.45)),
        WindowRecord(2, Rect(x + w * 0.38, y + h * 0.40, w * 0.26, h * 0.35)),
        WindowRecord(3, Rect(x + w * 0.72, y + h * 0.62, w * 0.20, h * 0.30)),
    ]


def clip(rect: Rect, area: Rect) -> Rect | None:
    left, right = max(rect.left, area.left), min(rect.right, area.right)
    top, bottom = max(rect.top, area.top), min(rect.bottom, area.bottom)
    if right - left < 1.0 or bottom - top < 1.0:
        return None
    return Rect(left, top, right - left, bottom - top)


def _same(a: Rect, b: Rect) -> bool:
    return (
        abs(a.x - b.x) <= TOLERANCE
        and abs(a.y - b.y) <= TOLERANCE
        and abs(a.width - b.width) <= TOLERANCE
        and abs(a.height - b.height) <= TOLERANCE
    )


@dataclass(frozen=True)
class WindowUpdate:
    boxes: list[Rect]
    change: TerrainChange
    front_to_back: list[int]
    """Box indices, frontmost window first."""


class WindowTracker:
    """Diffs snapshots by window id. Windows are clipped to `area` (the usable screen)."""

    def __init__(self, area: Rect) -> None:
        self.area = area
        self.ids: list[int] = []
        self.rects: dict[int, Rect] = {}
        self.order: list[int] = []

    @property
    def boxes(self) -> list[Rect]:
        return [self.rects[i] for i in self.ids]

    @property
    def front_to_back(self) -> list[int]:
        index = {window_id: n for n, window_id in enumerate(self.ids)}
        return [index[i] for i in self.order]

    def update(self, records: Sequence[WindowRecord]) -> WindowUpdate | None:
        """Take a snapshot; returns what changed, or None if nothing did."""
        visible: dict[int, Rect] = {}
        order: list[int] = []
        for record in records:
            rect = clip(record.rect, self.area)
            if rect is None or rect.width < MIN_WIDTH or rect.height < MIN_HEIGHT:
                continue
            if record.id in visible:
                continue
            visible[record.id] = rect
            order.append(record.id)

        moves: dict[int, Vec2] = {}
        remap: dict[int, int | None] = {}
        new_ids: list[int] = []
        new_rects: dict[int, Rect] = {}
        changed = order != self.order
        for old_index, window_id in enumerate(self.ids):
            rect = visible.get(window_id)
            if rect is None:
                remap[old_index] = None
                changed = True
                continue
            old = self.rects[window_id]
            if _same(old, rect):
                rect = old
            else:
                changed = True
                delta = Vec2(rect.x - old.x, rect.y - old.y)
                if delta.length_sq() > 0.0:
                    moves[old_index] = delta
            remap[old_index] = len(new_ids)
            new_ids.append(window_id)
            new_rects[window_id] = rect
        for window_id in order:
            if window_id not in new_rects:
                changed = True
                new_ids.append(window_id)
                new_rects[window_id] = visible[window_id]

        if not changed:
            return None
        self.ids, self.rects, self.order = new_ids, new_rects, order
        return WindowUpdate(self.boxes, TerrainChange(moves, remap), self.front_to_back)
