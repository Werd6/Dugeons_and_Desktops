"""Traversable surfaces extracted from solid rectangles (future: desktop windows).

Each box contributes a walkable top and two climbable sides; the floor is
walkable. Any part of a surface that another box would put the character inside
is clipped away.

Surfaces describe where the character's *contact point* can be: the feet on a
walkable surface, the feet level on a climbable side. A climbable side extends
below the wall's real bottom by a hang reach, because a climber can hang with
hands on the wall and feet dangling below it. It also stops `mantle_depth`
below the wall top: that is where the hands reach the lip, and a mantle carries
the body the rest of the way up.

With a `hang_depth`, box bottoms (and the screen top, given a `ceiling`) are
CEILING surfaces: the character hangs from them by its hands and goes along
hand over hand. A ceiling surface runs left to right at feet level, `hang_depth`
below the line the hands grip (`grip`), wherever the hanging body fits.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum

from dungeons_desktops.core.geometry import Rect, Vec2, clamp

EPSILON = 0.5
MIN_PIECE = 4.0


class SurfaceKind(Enum):
    FLOOR = "floor"
    TOP = "top"
    LEFT = "left"
    RIGHT = "right"
    CEILING = "ceiling"


@dataclass(frozen=True)
class Surface:
    """Walkable surfaces and ceilings run left to right; climbable sides run top to
    bottom. For a side, `wall_top`/`wall_bottom` are the wall's real extent; for a
    ceiling both are the line the hands grip."""

    id: int
    kind: SurfaceKind
    start: Vec2
    end: Vec2
    box: int | None
    wall_top: float = 0.0
    wall_bottom: float = 0.0

    @property
    def walkable(self) -> bool:
        return self.kind in (SurfaceKind.FLOOR, SurfaceKind.TOP)

    @property
    def wall(self) -> bool:
        """A climbable side."""
        return self.kind in (SurfaceKind.LEFT, SurfaceKind.RIGHT)

    @property
    def hanging(self) -> bool:
        return self.kind is SurfaceKind.CEILING

    @property
    def horizontal(self) -> bool:
        return not self.wall

    @property
    def grip(self) -> float:
        """The height a ceiling's hands hold."""
        return self.wall_top

    @property
    def normal(self) -> Vec2:
        """Direction from the surface toward the side the character occupies."""
        if self.kind is SurfaceKind.LEFT:
            return Vec2(-1.0, 0.0)
        if self.kind is SurfaceKind.RIGHT:
            return Vec2(1.0, 0.0)
        if self.kind is SurfaceKind.CEILING:
            return Vec2(0.0, 1.0)
        return Vec2(0.0, -1.0)

    @property
    def facing(self) -> int:
        """+1 when a climber faces +x (wall on its right)."""
        return -1 if self.kind is SurfaceKind.RIGHT else 1

    def coord(self, point: Vec2) -> float:
        return point.x if self.horizontal else point.y

    def point_at(self, coord: float) -> Vec2:
        return Vec2(coord, self.start.y) if self.horizontal else Vec2(self.start.x, coord)

    @property
    def low(self) -> float:
        return self.coord(self.start)

    @property
    def high(self) -> float:
        return self.coord(self.end)

    @property
    def length(self) -> float:
        return self.high - self.low

    @property
    def lip(self) -> Vec2:
        """Top corner of a climbable side's wall."""
        return Vec2(self.start.x, self.wall_top)

    def closest_point(self, point: Vec2) -> Vec2:
        return self.point_at(clamp(self.coord(point), self.low, self.high))

    def contains(self, point: Vec2, tolerance: float = 1.0) -> bool:
        across = point.y - self.start.y if self.horizontal else point.x - self.start.x
        along = self.coord(point)
        return abs(across) <= tolerance and self.low - tolerance <= along <= self.high + tolerance


@dataclass(frozen=True)
class TerrainChange:
    """How the boxes changed between two terrain builds.

    `moves` maps an old box index to how far that box moved. `remap` maps old box
    indices to new ones (None: the box is gone); without it indices are unchanged.
    `shift` moves everything at once.
    """

    moves: Mapping[int, Vec2] = field(default_factory=dict)
    remap: Mapping[int, int | None] | None = None
    shift: Vec2 | None = None

    def delta_for(self, box: int | None) -> Vec2 | None:
        """How far something resting on `box` is carried, or None if it stays put."""
        if self.shift is not None:
            return self.shift
        return None if box is None else self.moves.get(box)

    def new_index(self, box: int | None) -> int | None:
        if box is None or self.remap is None:
            return box
        return self.remap.get(box)

    def removed(self, box: int | None) -> bool:
        return box is not None and self.remap is not None and self.remap.get(box) is None


def _overlap(a: Rect, b: Rect) -> bool:
    return a.left < b.right and b.left < a.right and a.top < b.bottom and b.top < a.bottom


def _subtract(low: float, high: float, blocks: Sequence[tuple[float, float]]) -> list[tuple]:
    pieces = [(low, high)]
    for block_low, block_high in blocks:
        remaining = []
        for piece_low, piece_high in pieces:
            if block_high <= piece_low or block_low >= piece_high:
                remaining.append((piece_low, piece_high))
                continue
            if block_low > piece_low:
                remaining.append((piece_low, block_low))
            if block_high < piece_high:
                remaining.append((block_high, piece_high))
        pieces = remaining
    return [(a, b) for a, b in pieces if b - a >= MIN_PIECE]


class Terrain:
    def __init__(
        self,
        boxes: Sequence[Rect],
        floor_y: float,
        left: float,
        right: float,
        hang_reach: float = 45.0,
        mantle_depth: float = 70.0,
        ceiling: float | None = None,
        hang_depth: float | None = None,
        clearance: float = 0.0,
        headroom: float = 0.0,
        wall_clearance: float | None = None,
        floor_headroom: bool = False,
    ) -> None:
        """With a `ceiling`, the left and right bounds are climbable walls (screen edges)
        from `mantle_depth` below the ceiling down to the floor, wherever no box covers them.
        With a `hang_depth` (hands to feet when hanging), box bottoms and the ceiling can
        be hung from. A `clearance` drops the parts of surfaces where another box comes
        closer than that to the surface, on the side the character is (room for a body
        that lies along the surface, like a crawler's). A `headroom` does the same above
        the walkable surfaces only (room for a tall body standing on them), but leaves the
        screen floor whole unless `floor_headroom`. A
        `wall_clearance` replaces `clearance` for the sides (0 keeps them whole: a body
        that may clip into the window beside a narrow slot as it climbs)."""
        self.boxes = tuple(boxes)
        self.floor_y = floor_y
        self.left = left
        self.right = right
        self.hang_reach = hang_reach
        self.mantle_depth = mantle_depth
        self.ceiling = ceiling
        self.hang_depth = hang_depth
        self.clearance = clearance
        self.headroom = headroom
        self.wall_clearance = wall_clearance
        self.floor_headroom = floor_headroom
        surfaces = self._extract()
        if clearance > 0.0 or headroom > 0.0:
            surfaces = self._clear(surfaces)
        self.surfaces: tuple[Surface, ...] = tuple(surfaces)

    def column_clear(self, x: float, y_top: float, y_bottom: float) -> bool:
        """True if a vertical line at x between the two heights passes through no box."""
        for box in self.boxes:
            if (
                box.left < x < box.right
                and box.top < y_bottom - EPSILON
                and box.bottom > y_top + EPSILON
            ):
                return False
        return True

    def _extract(self) -> list[Surface]:
        surfaces: list[Surface] = []

        def add(kind, start, end, box, wall_top=0.0, wall_bottom=0.0):
            surfaces.append(Surface(len(surfaces), kind, start, end, box, wall_top, wall_bottom))

        for low, high in self._horizontal(self.floor_y, self.left, self.right):
            add(SurfaceKind.FLOOR, Vec2(low, self.floor_y), Vec2(high, self.floor_y), None)

        for index, box in enumerate(self.boxes):
            if box.top >= self.floor_y:
                continue
            low, high = max(box.left, self.left), min(box.right, self.right)
            for a, b in self._horizontal(box.top, low, high):
                add(SurfaceKind.TOP, Vec2(a, box.top), Vec2(b, box.top), index)

            for kind, x, probe in (
                (SurfaceKind.LEFT, box.left, box.left - EPSILON),
                (SurfaceKind.RIGHT, box.right, box.right + EPSILON),
            ):
                if not self.left <= probe <= self.right:
                    continue
                blocks = [(b.top, b.bottom) for b in self.boxes if b.left < probe < b.right]
                bottom = min(box.bottom, self.floor_y)
                for top, piece_bottom in _subtract(box.top, bottom, blocks):
                    reach = self._hang_extension(probe, piece_bottom)
                    highest = min(top + self.mantle_depth, reach)
                    add(kind, Vec2(x, highest), Vec2(x, reach), index, top, piece_bottom)

        if self.ceiling is not None:
            for kind, x, probe in (
                (SurfaceKind.RIGHT, self.left, self.left + EPSILON),
                (SurfaceKind.LEFT, self.right, self.right - EPSILON),
            ):
                blocks = [(b.top, b.bottom) for b in self.boxes if b.left < probe < b.right]
                for top, bottom in _subtract(self.ceiling, self.floor_y, blocks):
                    highest = top + self.mantle_depth
                    if bottom - highest >= MIN_PIECE:
                        add(kind, Vec2(x, highest), Vec2(x, bottom), None, top, bottom)

        if self.hang_depth is not None:
            grips: list[tuple[float, int | None]] = [
                (b.bottom, i) for i, b in enumerate(self.boxes)
            ]
            if self.ceiling is not None:
                grips.append((self.ceiling, None))
            for grip, index in grips:
                feet = grip + self.hang_depth
                if feet >= self.floor_y or (self.ceiling is not None and grip < self.ceiling):
                    continue
                box = self.boxes[index] if index is not None else None
                low = self.left if box is None else max(box.left, self.left)
                high = self.right if box is None else min(box.right, self.right)
                blocks = [
                    (b.left, b.right)
                    for b in self.boxes
                    if b.top < feet and b.bottom > grip + EPSILON
                ]
                for a, b in _subtract(low, high, blocks):
                    add(SurfaceKind.CEILING, Vec2(a, feet), Vec2(b, feet), index, grip, grip)
        return surfaces

    def _clear(self, surfaces: list[Surface]) -> list[Surface]:
        """Each surface cut down to where no other box is within `clearance` of it. A cut
        side's wall ends where it was cut, so it only mantles or swings round a corner
        it still reaches."""
        far = 1e6
        top = self.ceiling if self.ceiling is not None else -far
        # The band above the screen isn't a ceiling he has to fit under. He's too tall
        # for the gap under the menu bar, so he walks those tops anyway.
        overhead = top - self.headroom
        outside = [
            Rect(-far, -far, 3 * far, overhead + far),
            Rect(-far, self.floor_y, 3 * far, far),
            Rect(-far, -far, self.left + far, 3 * far),
            Rect(self.right, -far, far, 3 * far),
        ]
        result: list[Surface] = []
        for surface in surfaces:
            normal = surface.normal
            # The screen floor stays whole. He's too tall for the lane above it, so a
            # window hanging over that edge is not a wall he has to route around.
            room = self.clearance
            if surface.wall and self.wall_clearance is not None:
                room = self.wall_clearance
            if surface.walkable and (surface.kind is not SurfaceKind.FLOOR or self.floor_headroom):
                room = max(room, self.headroom)
            if room <= 0.0:
                result.append(surface)
                continue
            corners = [
                end + normal * offset
                for end in (surface.start, surface.end)
                for offset in (EPSILON, room)
            ]
            xs, ys = [p.x for p in corners], [p.y for p in corners]
            slab = Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
            blocks = []
            others = [(i, box) for i, box in enumerate(self.boxes) if i != surface.box]
            if surface.box is not None:
                others += [(None, box) for box in outside]
            for _, box in others:
                if not _overlap(slab, box):
                    continue
                if surface.horizontal:
                    blocks.append((box.left, box.right))
                else:
                    blocks.append((box.top, box.bottom))
            for low, high in _subtract(surface.low, surface.high, blocks):
                start, end = surface.point_at(low), surface.point_at(high)
                wall_top, wall_bottom = surface.wall_top, surface.wall_bottom
                if surface.wall:
                    if low > surface.low:
                        wall_top = low - self.mantle_depth
                    if high < surface.high:
                        wall_bottom = high
                result.append(
                    Surface(
                        len(result), surface.kind, start, end, surface.box, wall_top, wall_bottom
                    )
                )
        return result

    def _horizontal(self, y: float, low: float, high: float) -> list[tuple[float, float]]:
        blocks = [
            (b.left, b.right) for b in self.boxes if b.top < y - EPSILON and b.bottom > y - EPSILON
        ]
        return _subtract(low, high, blocks)

    def _hang_extension(self, probe_x: float, wall_bottom: float) -> float:
        """How far below the wall the feet can hang, stopping at the floor or a box top."""
        reach = min(wall_bottom + self.hang_reach, self.floor_y)
        for box in self.boxes:
            if box.left < probe_x < box.right and wall_bottom - EPSILON <= box.top < reach:
                reach = box.top
        return reach
