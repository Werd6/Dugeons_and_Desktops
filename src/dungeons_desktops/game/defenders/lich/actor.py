"""The lich: a tall, gaunt skeleton king in a ragged black robe and a gold crown.

He walks the floor and window tops on his own terrain (`world.lich_terrain`, tall
enough to need `HEADROOM`), slowly and smoothly: he eases into and out of every step
(`ACCELERATION`) and turns round through a three-quarter view toward the viewer
(`Lich.yaw`, sprung, never snapped). He walks with his right hand held out before him,
palm up, a green flame floating over it. He never climbs or jumps: to get to another
surface he **levitates** along a path round the windows (`Flight`), rising or sinking
in a clear column beside them and gliding on or off at the level of the surface,
slowing at every corner.

He keeps his distance: he hunts the nearest free adventurer (sticking with him
`FOE_COMMIT`), and looks for a spot `CAST_MIN`..`CAST_MAX` from him (ideally
`CAST_IDEAL`) and clear of everyone else (`CROWD`), on his own surface if one will do,
else on another he floats to. Anyone coming close, he backs away from, still facing
his foe. Whenever a foe is within `CAST_RANGE` he casts, still walking or floating
on toward his spot: the gesture is laid over his arms and jaw only.

Spells: `spells` is his spell queue and every cast is the next one in it
(`next_spell`), whoever the foe; after each he waits that spell's `SPELL_DELAY`.

With `LICH_HP` gone he crumbles: the robe collapses, skull, crown and bones tumble
down, the flame gutters out, and the heap fades.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.game.actors.mortal import Mortal
from dungeons_desktops.game.defenders.lich.spells import SPELLS
from dungeons_desktops.navigation.terrain import Surface, TerrainChange

if TYPE_CHECKING:
    from dungeons_desktops.game.adventurers.actor import Stickman
    from dungeons_desktops.game.world.simulation import SimWorld

LICH_HP = 6

HEIGHT = 44.0
"""Feet to the top of his skull (the crown stands above that)."""
HEADROOM = 40.0
"""Window tops with another window lower than this above them are left out."""
BODY_HALF = 9.0
"""Half his width, kept clear of windows when he levitates and off surface ends."""
LEG_ROOM = 16.0
"""The height of the part of him (hem and feet) a levitation path must keep clear."""
HOVER = 4.0
"""How high he lifts off a surface to levitate."""
HIP_Y = -12.0
CHEST_Y = -27.0
SKULL = Vec2(1.6, -39.0)
"""His skull in his own frame (forward, up = -y), feet at the origin."""
SKULL_RADIUS = 5.2
BODY_RADIUS = 7.5
SHOULDER_Y = -32.0
SHOULDER_HALF = 4.2
UPPER_ARM = 9.5
FOREARM = 9.5
REST_YAW = 0.35
"""Standing, he's turned this far (radians) from side-on toward the viewer."""

WALK_SPEED = 30.0
BACK_SPEED = 20.0
ACCELERATION = 45.0
STRIDE = 26.0
"""Ground covered in one gait cycle (two steps)."""
TURN_RATE = 7.0
"""Spring rate of his turn: about half a second to turn round."""
FLOAT_SPEED = 50.0
FLOAT_ACCELERATION = 60.0
CORNER_SPEED = 6.0
"""The speed he slows to at each corner of a levitation path."""
SURFACE_MATCH = 12.0

FOE_COMMIT = 1.5
FOE_SWITCH = 0.6
CLUSTER_RADIUS = 300.0
"""Adventurers this close to one another count as one group (for his doors)."""
CLUSTER_DOOR = 3
CLUSTER_GROWTH = 2
"""A group of at least `CLUSTER_DOOR`, `CLUSTER_GROWTH` bigger than his foe's (and
without him in it), is worth a dimension door even with his foe close by."""
STRANDED_AFTER = 1.5  # a foe he can't get in range of (nor door to) for this long...
SHUN_TIME = 4.0  # ...is passed over this long for one he can reach
TOO_CLOSE = 60.0  # he never picks a spot this near an adventurer
CAST_MIN = 180.0
CAST_IDEAL = 220.0
CAST_MAX = 260.0
CAST_SLACK = 40.0
"""How far outside `CAST_MIN`..`CAST_MAX` he still casts from."""
CROWD = 150.0
DOOR_CROWD = 100.0
"""A door comes out at least this far from every free adventurer."""
"""He keeps at least this far from every free adventurer."""
REPLAN_EVERY = 0.6
HOLD = 12.0
"""A spot must score this much better than where he stands for him to move."""
LEVITATE_COST = 80.0
LEVEL_REACH = 30.0
"""He never walks past an adventurer this close to his own height: he floats over."""
HOP = HEIGHT + 22.0
"""How high he floats over the heads of adventurers in his way."""
WANDER_WAIT = (2.5, 5.0)
WANDER_LEVITATE = 0.3

CAST_TIME = 0.9
CAST_RELEASE = 0.5
"""The spell leaves his hand this far through the cast (0.45 s in)."""
CAST_RANGE = 420.0
"""He casts at a foe this close, wherever he is and whether or not he's moving."""
SPELLBOOK = SPELLS
"""His queue, in order: every cast is the next one."""
SPELL_DELAY = {
    "magic_missiles": 0.9,
    "chain_lightning": 1.2,
    "fireball": 1.4,
    "black_tentacles": 1.6,
    "power_word_kill": 2.2,
}
"""How long after casting each spell before he starts the next."""
CAST_DELAY = 1.4
"""After a spell missing from `SPELL_DELAY`."""

GRAVITY = 900.0
COLLAPSE_TIME = 0.7
FLAME_OUT = 0.6

DOOR_COOLDOWN = 20.0
DOOR_FIRST = 4.0
"""Seconds after he appears before his first dimension door is ready."""
DOOR_PATIENCE = 2.0
"""A far foe, and his door ready within this: he waits for it rather than set off."""
DOOR_RANGE = 400.0
DOOR_ROUTE_TIME = 4.0
"""He opens a door to a foe farther than `DOOR_RANGE`, or one whose casting spots he
couldn't reach in `DOOR_ROUTE_TIME`."""
DOOR_FADE = 0.45
"""Into his door: he traces it, it opens, and from here he dissolves into it..."""
DOOR_SWAP = 0.78
"""...and at this point (unseen) he's at the other door..."""
DOOR_EMERGE = 0.8
"""...from where he steps out of it..."""
DOOR_TIME = 1.35
"""...and both doors have closed and faded."""
DOOR_STEP_OUT = 0.3
DOOR_MIN_JUMP = 60.0
SIGHT_STEP = 6.0


class Eased:
    """A value that follows its target on a critically damped spring: no pops."""

    def __init__(self, value: float = 0.0) -> None:
        self.value = value
        self.rate = 0.0

    def update(self, target: float, omega: float, dt: float) -> float:
        accel = omega * omega * (target - self.value) - 2.0 * omega * self.rate
        self.rate += accel * dt
        self.value += self.rate * dt
        return self.value


@dataclass
class Flight:
    """Levitating along `points` (the rest of the path) to land on `surface`."""

    points: list[Vec2]
    surface: Surface
    speed: float = 0.0


@dataclass
class Door:
    """A dimension door from `origin` (feet, on `origin_surface`) to `target` on
    `surface`, `time` seconds in."""

    origin: Vec2
    origin_surface: Surface | None
    target: Vec2
    surface: Surface
    time: float = 0.0
    moved: bool = False


@dataclass
class Bit:
    """A piece of him tumbling down as he crumbles: skull, crown or bone."""

    kind: str
    position: Vec2
    velocity: Vec2
    angle: float = 0.0
    spin: float = 0.0
    radius: float = 2.0
    resting: bool = False


@dataclass
class Joints:
    """His pose in world points, worked out once per frame."""

    root: Vec2
    skull: Vec2
    tilt: float
    shoulders: tuple[Vec2, Vec2]
    elbows: tuple[Vec2, Vec2]
    hands: tuple[Vec2, Vec2]
    flame: Vec2
    flame_front: bool
    """The flame arm is on the viewer's side of his body."""
    finger: float = 0.0
    """How far his other hand points a bony finger (power word kill)."""
    jaw: float = 0.0
    """How far his jaw drops as he speaks."""
    crackle: float = 0.0
    """Lightning crackling between his fingers (chain lightning)."""


Key = tuple[float, tuple[float, float], tuple[float, float]]
REST_F = (11.5, -24.5)
REST_O = (1.0, -17.5)
GESTURES: dict[str, tuple[Key, ...]] = {
    # (cast progress, flame hand, other hand), as (forward, up) from his root
    "fireball": (
        (0.0, REST_F, REST_O),
        (0.3, (-8.0, -27.0), (6.0, -21.0)),
        (0.5, (14.0, -36.0), (2.0, -19.0)),
        (0.7, (13.0, -31.0), (1.5, -18.5)),
        (1.0, REST_F, REST_O),
    ),
    "power_word_kill": (
        (0.0, REST_F, REST_O),
        (0.25, (8.0, -23.0), (14.0, -29.0)),
        (0.8, (8.0, -23.0), (15.0, -30.0)),
        (1.0, REST_F, REST_O),
    ),
    "magic_missiles": (
        (0.0, REST_F, REST_O),
        (0.35, (5.0, -27.0), (2.0, -18.0)),
        (0.5, (17.0, -28.5), (2.0, -18.0)),
        (0.75, (16.0, -28.0), (1.5, -18.0)),
        (1.0, REST_F, REST_O),
    ),
    "chain_lightning": (
        (0.0, REST_F, REST_O),
        (0.35, (14.5, -28.0), (13.5, -26.0)),
        (0.55, (16.0, -28.5), (15.0, -26.5)),
        (0.8, (15.0, -28.0), (14.0, -26.0)),
        (1.0, REST_F, REST_O),
    ),
    "black_tentacles": (
        (0.0, REST_F, REST_O),
        (0.35, (8.0, -46.0), (12.0, -43.0)),
        (0.5, (13.0, -16.0), (11.0, -15.0)),
        (0.75, (12.5, -16.5), (10.5, -15.5)),
        (1.0, REST_F, REST_O),
    ),
}
"""How he casts each spell: his hands through the cast, released at `CAST_RELEASE`."""


def _keyframe(keys: tuple[Key, ...], p: float) -> tuple[Vec2, Vec2]:
    for (p0, f0, o0), (p1, f1, o1) in zip(keys, keys[1:], strict=False):
        if p <= p1:
            u = smoothstep(clamp((p - p0) / max(1e-6, p1 - p0), 0.0, 1.0))
            return Vec2(*f0).lerp(Vec2(*f1), u), Vec2(*o0).lerp(Vec2(*o1), u)
    return Vec2(*keys[-1][1]), Vec2(*keys[-1][2])


def _window(p: float, start: float, end: float) -> float:
    """1 between `start` and `end` of the cast, easing in and out."""
    rise = smoothstep(clamp((p - start) / 0.1, 0.0, 1.0))
    return rise * (1.0 - smoothstep(clamp((p - end) / 0.1, 0.0, 1.0)))


def _approach(value: float, target: float, step: float) -> float:
    if value < target:
        return min(target, value + step)
    return max(target, value - step)


def _sign(value: float) -> int:
    return 1 if value >= 0.0 else -1


def _segment_distance(point: Vec2, a: Vec2, b: Vec2) -> float:
    ab = b - a
    length_sq = ab.x * ab.x + ab.y * ab.y
    t = (
        0.0
        if length_sq <= 1e-9
        else clamp(((point - a).x * ab.x + (point - a).y * ab.y) / length_sq, 0.0, 1.0)
    )
    return point.distance_to(a + ab * t)


def _ik(root: Vec2, target: Vec2, upper: float, lower: float, bend: float) -> Vec2:
    """The joint of a two-bone limb from `root` reaching for `target`."""
    offset = target - root
    distance = clamp(offset.length(), 1e-3, upper + lower - 1e-3)
    cos_a = clamp(
        (upper * upper + distance * distance - lower * lower) / (2 * upper * distance), -1, 1
    )
    return root + Vec2.from_angle(offset.angle() + bend * math.acos(cos_a), upper)


class Lich(Mortal):
    max_hp = LICH_HP
    linger = 3.0

    def __init__(self, world: SimWorld, surface: Surface, point: Vec2, heading: int = 1) -> None:
        self.world = world
        self.surface: Surface | None = surface
        self.position = point
        self.speed = 0.0
        self.velocity = Vec2(0.0, 0.0)
        self.flight: Flight | None = None
        self.goal: tuple[Surface, float] | None = None
        self.foe: Stickman | None = None
        self._foe_since = 0.0
        self._stranded_since: float | None = None
        self._shunned: dict[int, float] = {}
        self.time = 0.0
        self.heading = heading
        self.yaw = Eased(self._rest_yaw(heading))
        self.gait = Eased()
        self.phase = 0.0
        self.lift = Eased()
        self.drag = Eased()
        self.raised = Eased()
        self.gesture = Eased()
        self.cast_spell: str | None = None
        """The spell he's casting (or last cast), which shapes the gesture."""
        self.flare = Eased()
        self.cast_left = 0.0
        self.cast_wait = 1.0
        self.casts = 0
        self.last_cast: tuple[str, Stickman] | None = None
        self._released = False
        self.spells: list[str] = list(SPELLBOOK)
        self.spell_index = 0
        self._replan_wait = 0.0
        self._wander_wait = world.random.uniform(*WANDER_WAIT)
        self.door: Door | None = None
        self.door_wait = DOOR_FIRST
        self.doors = 0
        self.door_groups: list[int] = []
        """The size of the group each of his doors was aimed at."""
        self.bits: list[Bit] = []
        self.slump = 0.0
        self.flame = 1.0
        self.fall_speed = 0.0

    # ----- the spell hook ----------------------------------------------------------

    @property
    def spell(self) -> str:
        """The spell he's casting, or else the one he'll cast next."""
        if self.casting and self.cast_spell is not None:
            return self.cast_spell
        return self.spells[self.spell_index % len(self.spells)]

    def next_spell(self) -> str:
        """The next spell in his queue (and move the queue on)."""
        spell = self.spells[self.spell_index % len(self.spells)]
        self.spell_index = (self.spell_index + 1) % len(self.spells)
        return spell

    def _cast(self, foe: Stickman) -> None:
        """Let the spell he's casting fly at `foe` from the flame in his palm."""
        spell = self.cast_spell or self.spell
        self.casts += 1
        self.last_cast = (spell, foe)
        self.world.necromancy.cast(spell, self, self.flame_point(), foe)

    def flame_point(self) -> Vec2:
        return self.joints().flame

    # ----- where he is ---------------------------------------------------------------

    @staticmethod
    def _rest_yaw(heading: int) -> float:
        return REST_YAW if heading > 0 else math.pi - REST_YAW

    @property
    def facing(self) -> int:
        return 1 if self.yaw.value < math.pi / 2 else -1

    @property
    def turning(self) -> bool:
        return abs(self.yaw.value - self._rest_yaw(self.heading)) > 0.25

    @property
    def grounded(self) -> bool:
        return self.surface is not None and self.flight is None

    @property
    def levitating(self) -> bool:
        return self.flight is not None

    @property
    def visibility(self) -> float:
        """1 normally; fades to 0 as he goes into a dimension door and back out of the other."""
        door = self.door
        if door is None or door.time < DOOR_FADE:
            return 1.0
        if door.time < DOOR_SWAP:
            return 1.0 - smoothstep((door.time - DOOR_FADE) / (DOOR_SWAP - DOOR_FADE))
        if door.time < DOOR_EMERGE:
            return 0.0
        return smoothstep(min(1.0, (door.time - DOOR_EMERGE) / DOOR_STEP_OUT))

    @property
    def phased(self) -> bool:
        """Mostly gone into a dimension door: nothing can see or hit him."""
        return self.door is not None and self.visibility < 0.5

    @property
    def casting(self) -> bool:
        return self.cast_left > 0.0

    def root(self) -> Vec2:
        """Where his frame stands: his feet, with the idle sway and levitation bob."""
        if self.dead:
            return self.position
        idle = 1.0 - smoothstep(self.gait.value)
        sway = 0.6 * math.sin(self.time * 1.3) * idle
        hover = self.lift.value * 1.4 * math.sin(self.time * 2.2)
        return self.position + Vec2(sway, hover)

    def lean(self) -> float:
        return 0.05 + 0.07 * self.gait.value - 0.04 * self.lift.value

    def project(self, forward: float, right: float, y: float, root: Vec2 | None = None) -> Vec2:
        """A point in his own frame (`forward`, `right` toward the viewer when he faces
        +x, y down from his feet) on the screen."""
        if y < HIP_Y:
            forward += (HIP_Y - y) * self.lean()
        yaw = self.yaw.value
        x = forward * math.cos(yaw) - right * math.sin(yaw)
        return (root or self.root()) + Vec2(x, y)

    def depth(self, forward: float, right: float) -> float:
        """How far toward the viewer a point of his frame is."""
        yaw = self.yaw.value
        return forward * math.sin(yaw) + right * math.cos(yaw)

    def joints(self) -> Joints:
        root = self.root()
        t = self.time
        gait = smoothstep(clamp(self.gait.value, 0.0, 1.0))
        lift = clamp(self.lift.value, 0.0, 1.0)
        raised = clamp(self.raised.value, 0.0, 1.2)
        swing = math.sin(2.0 * math.pi * self.phase)
        tilt = 0.08 * math.sin(t * 0.9) * (1.0 - gait) - 0.05 * raised
        skull = self.project(SKULL.x, 0.0, SKULL.y, root)
        # Flame arm: out before him, palm up; raised high to cast.
        rest = Vec2(
            11.5 + 0.6 * math.sin(t * 1.1), -24.5 - 0.5 * math.sin(t * 1.7) + 0.4 * gait * swing
        )
        high = Vec2(9.0, -39.0)
        hand_f = rest.lerp(high, raised)
        finger = jaw = crackle = 0.0
        gesture = clamp(self.gesture.value, 0.0, 1.0)
        keys = GESTURES.get(self.cast_spell or "")
        shoulder_f = Vec2(0.5, SHOULDER_Y)
        elbow_f = _ik(shoulder_f, hand_f, UPPER_ARM, FOREARM, 1.0)
        right = (SHOULDER_HALF, SHOULDER_HALF * 0.75, SHOULDER_HALF * 0.6)
        # Other arm: hanging at his side, holding the robe, swinging a little.
        other_hand = Vec2(1.0 - 0.6 * gait * swing - 1.0 * lift, -17.5 + 1.5 * lift)
        if gesture > 0.0 and keys is not None:
            p = 1.0 - self.cast_left / CAST_TIME if self.casting else 1.0
            key_f, key_o = _keyframe(keys, p)
            hand_f = hand_f.lerp(key_f, gesture)
            other_hand = other_hand.lerp(key_o, gesture)
            if self.cast_spell == "power_word_kill":
                finger = gesture * _window(p, 0.15, 0.85)
                jaw = gesture * _window(p, 0.3, 0.7) * (0.5 + 0.5 * math.sin(t * 24.0))
            elif self.cast_spell == "chain_lightning":
                crackle = gesture * _window(p, 0.25, 0.8)
        other_shoulder = Vec2(0.0, SHOULDER_Y)
        other_elbow = _ik(other_shoulder, other_hand, UPPER_ARM * 0.85, FOREARM * 0.85, 1.0)
        left = (-SHOULDER_HALF, -SHOULDER_HALF * 0.9, -SHOULDER_HALF * 1.1)
        hand = self.project(hand_f.x, right[2], hand_f.y, root)
        flame_front = self.depth(hand_f.x, right[2]) > 0.0
        return Joints(
            root=root,
            skull=skull,
            tilt=tilt,
            shoulders=(
                self.project(shoulder_f.x, right[0], shoulder_f.y, root),
                self.project(other_shoulder.x, left[0], other_shoulder.y, root),
            ),
            elbows=(
                self.project(elbow_f.x, right[1], elbow_f.y, root),
                self.project(other_elbow.x, left[1], other_elbow.y, root),
            ),
            hands=(hand, self.project(other_hand.x, left[2], other_hand.y, root)),
            flame=hand + Vec2(0.0, -4.5),
            flame_front=flame_front,
            finger=finger,
            jaw=jaw,
            crackle=crackle,
        )

    def center(self) -> Vec2:
        if self.dead:
            return self.position + Vec2(0.0, -5.0)
        return self.project(0.0, 0.0, CHEST_Y)

    def parts(self) -> list[Vec2]:
        if self.dead:
            return [self.center()]
        return [
            self.project(SKULL.x, 0.0, SKULL.y),
            self.center(),
            self.project(0.0, 0.0, -17.0),
            self.project(0.0, 0.0, -7.0),
        ]

    def hits(self, point: Vec2, margin: float = 0.0) -> bool:
        if self.dead or self.phased:
            return False
        if self.project(SKULL.x, 0.0, SKULL.y).distance_to(point) <= SKULL_RADIUS + margin:
            return True
        top, bottom = self.project(0.0, 0.0, -31.0), self.project(0.0, 0.0, -6.0)
        return _segment_distance(point, top, bottom) <= BODY_RADIUS + margin

    # ----- the terrain he knows ---------------------------------------------------------

    def _surfaces(self) -> list[Surface]:
        return [s for s in self.world.lich_terrain.surfaces if s.walkable]

    @staticmethod
    def span(surface: Surface) -> tuple[float, float]:
        """Where on `surface` he can stand: clear of its ends by half his width."""
        low, high = surface.low + BODY_HALF, surface.high - BODY_HALF
        if low > high:
            middle = (surface.low + surface.high) / 2
            return middle, middle
        return low, high

    def _blocked(self, left: float, right: float, top: float, bottom: float) -> bool:
        for box in self.world.boxes:
            if box.left < right and left < box.right and box.top < bottom and top < box.bottom:
                return True
        return False

    def _inside(self, point: Vec2) -> bool:
        """Whether his hem and feet standing at `point` would be inside a window."""
        return self._blocked(
            point.x - BODY_HALF + 1.0, point.x + BODY_HALF - 1.0, point.y - LEG_ROOM, point.y - 0.5
        )

    def _clear(self, a: Vec2, b: Vec2) -> bool:
        return not self._blocked(
            min(a.x, b.x) - BODY_HALF,
            max(a.x, b.x) + BODY_HALF,
            min(a.y, b.y) - LEG_ROOM,
            max(a.y, b.y) - 0.5,
        )

    def _path(
        self, start: Vec2, surface: Surface, x: float, lift: float = HOVER
    ) -> list[Vec2] | None:
        """A levitation path from `start` to `x` on `surface`: up off the ground, across
        to a clear column, up or down it to the surface's level, across onto it and down.
        The shortest such path clear of every window, or None."""
        world = self.world
        y0, y1 = start.y - lift, surface.start.y - HOVER
        end = Vec2(x, surface.start.y)
        columns = {start.x, x}
        for box in world.boxes:
            columns.add(box.left - BODY_HALF - 3.0)
            columns.add(box.right + BODY_HALF + 3.0)
        low, high = world.left + BODY_HALF, world.width - BODY_HALF
        best: list[Vec2] | None = None
        best_length = math.inf
        for column in columns:
            if not low <= column <= high:
                continue
            points = [start]
            for p in (Vec2(start.x, y0), Vec2(column, y0), Vec2(column, y1), Vec2(x, y1), end):
                if p.distance_to(points[-1]) > 0.5:
                    points.append(p)
            length = sum(a.distance_to(b) for a, b in zip(points, points[1:], strict=False))
            if length >= best_length:
                continue
            if all(self._clear(a, b) for a, b in zip(points, points[1:], strict=False)):
                best, best_length = points, length
        return best

    def _levitate_to(self, surface: Surface, x: float, path: list[Vec2] | None = None) -> None:
        path = path or [self.position, Vec2(x, surface.start.y)]
        speed = self.flight.speed if self.flight is not None else 0.0
        self.flight = Flight(path[1:] or [Vec2(x, surface.start.y)], surface, speed)
        self.surface = None
        self.goal = None
        self.speed = 0.0

    # ----- living -------------------------------------------------------------------

    def update(self, dt: float) -> None:
        self.time += dt
        self._replan_wait -= dt
        self.cast_wait -= dt
        self.door_wait -= dt
        before = self.position
        foe = self._choose_foe()
        if foe is not self.foe:
            self.foe = foe
            self._foe_since = self.time
            self._stranded_since = None
            self._replan_wait = 0.0
        if self.door is None and self.flight is not None and foe is not None:
            if self._replan_wait <= 0.0:
                self._replan_wait = REPLAN_EVERY
                if not self._try_door(foe) and self._strand(foe):
                    self._redirect(self.foe)
        if self.door is not None:
            self._door_step(dt)
        elif self.flight is not None:
            self._float(dt)
        elif self.surface is not None:
            self._think()
            if self.flight is None and self.door is None:
                self._walk(dt)
        if self.door is None and (self.surface is not None or self.flight is not None):
            if self.casting:
                self._casting(dt)
            elif self.foe is not None and self._can_cast(self.foe):
                self._begin_cast()
        self._face()
        self._animate(dt, before)

    def _choose_foe(self) -> Stickman | None:
        """The nearest free adventurer, kept for at least `FOE_COMMIT` unless another is
        much nearer."""
        prey = [s for s in self.world.stickmen if s.prey]
        welcome = [s for s in prey if self._shunned.get(id(s), -1.0) <= self.time]
        prey = welcome or prey
        if not prey:
            return None
        center = self.center()
        nearest = min(prey, key=lambda s: s.center().distance_to(center))
        current = self.foe
        if current is None or current not in prey:
            return nearest
        held = current.center().distance_to(center)
        near = nearest.center().distance_to(center)
        if near < FOE_SWITCH * held and self.time - self._foe_since >= FOE_COMMIT:
            return nearest
        return current

    def _think(self) -> None:
        foe = self.foe
        if self._replan_wait <= 0.0:
            self._replan_wait = REPLAN_EVERY
            if foe is None:
                self._wander()
            elif self._try_door(foe):
                return
            elif self._strand(foe):
                return
            else:
                self._keep_distance(foe)
            if self.flight is not None:
                return

    @property
    def stranded(self) -> bool:
        """Whether his foe has been out of his reach (walking, levitating or by door)
        for a while, with no other foe he could reach instead."""
        since = self._stranded_since
        return since is not None and self.time - since >= STRANDED_AFTER

    def _reachable(self, foe: Stickman) -> bool:
        low, high = CAST_MIN - CAST_SLACK, CAST_MAX + CAST_SLACK
        return self._route_time(foe, low, high) < math.inf or self.door_spot(foe) is not None

    def _strand(self, foe: Stickman) -> bool:
        """Track how long `foe` has been out of reach; past `STRANDED_AFTER` switch to
        the nearest prey he can reach. True if he switched."""
        if self._reachable(foe):
            self._stranded_since = None
            return False
        if self._stranded_since is None:
            self._stranded_since = self.time
        if not self.stranded:
            return False
        center = self.center()
        others = sorted(
            (s for s in self.world.stickmen if s.prey and s is not foe),
            key=lambda s: s.center().distance_to(center),
        )
        for other in others:
            if self._reachable(other):
                self._shunned = {k: t for k, t in self._shunned.items() if t > self.time}
                self._shunned[id(foe)] = self.time + SHUN_TIME
                self.foe = other
                self._foe_since = self.time
                self._stranded_since = None
                self._replan_wait = 0.0
                return True
        return False

    def _redirect(self, foe: Stickman | None) -> None:
        """Mid-flight, head instead for the best spot he can reach for `foe`."""
        if foe is None:
            return
        for _, s, x in self._candidates(foe)[:8]:
            path = self._path(self.position, s, x)
            if path is not None:
                self._levitate_to(s, x, path)
                return

    def range_to(self, foe: Stickman) -> float:
        return self.center().distance_to(foe.center())

    def _can_cast(self, foe: Stickman) -> bool:
        """Off cooldown, facing `foe` and within `CAST_RANGE`: walking, floating or
        standing, it doesn't matter."""
        if self.cast_wait > 0.0 or self.turning or not foe.prey:
            return False
        if _sign(foe.center().x - self.position.x) != self.heading:
            return False
        return self.range_to(foe) <= CAST_RANGE

    def _begin_cast(self) -> None:
        self.cast_spell = self.next_spell()
        self.cast_left = CAST_TIME
        self._released = False

    def _score(self, surface: Surface, x: float, foe: Stickman) -> float:
        chest = Vec2(x, surface.start.y + CHEST_Y)
        distance = chest.distance_to(foe.center())
        score = 0.15 * abs(distance - CAST_IDEAL)
        if distance < CAST_MIN:
            score += 2.0 * (CAST_MIN - distance)
        elif distance > CAST_MAX:
            score += 2.0 * (distance - CAST_MAX)
        for other in self.world.stickmen:
            if other.prey:
                near = chest.distance_to(other.center())
                if near < CROWD:
                    score += 1.5 * (CROWD - near)
                if near < TOO_CLOSE:
                    score += 600.0
        if self._inside(Vec2(x, surface.start.y)):
            score += 400.0
        here = self.position
        if surface == self.surface:
            score += 0.05 * abs(x - here.x)
            if self._walk_blocked(x):
                score += LEVITATE_COST
        else:
            score += LEVITATE_COST + 0.1 * here.distance_to(Vec2(x, surface.start.y))
        return score

    def _walk_blocked(self, x: float) -> bool:
        """Whether walking to `x` on his surface takes him past a free adventurer."""
        surface = self.surface
        assert surface is not None
        here = self.position.x
        low, high = min(x, here) - BODY_HALF, max(x, here) + BODY_HALF
        for other in self.world.stickmen:
            body = other.center()
            level = abs(body.y - (surface.start.y + CHEST_Y)) < LEVEL_REACH
            if other.prey and level and low < body.x < high:
                return True
        return False

    def _hop(self, x: float) -> list[Vec2] | None:
        """A levitation path over the heads of whoever is in the way, to `x` on his
        own surface."""
        surface = self.surface
        assert surface is not None
        start, y = self.position, surface.start.y - HOP
        points = [start, Vec2(start.x, y), Vec2(x, y), Vec2(x, surface.start.y)]
        if all(self._clear(a, b) for a, b in zip(points, points[1:], strict=False)):
            return points
        return None

    def _candidates(self, foe: Stickman) -> list[tuple[float, Surface, float]]:
        """Spots to stand at for keeping his distance from `foe`, best first."""
        surface = self.surface
        target = foe.center()
        candidates: list[tuple[float, Surface, float]] = []
        for s in self._surfaces():
            low, high = self.span(s)
            rise = (s.start.y + CHEST_Y) - target.y
            reach = math.sqrt(max(0.0, CAST_IDEAL * CAST_IDEAL - rise * rise))
            xs = {low, high, target.x - reach, target.x + reach}
            if s == surface:
                xs.add(self.position.x)
            for x in xs:
                x = clamp(x, low, high)
                candidates.append((self._score(s, x, foe), s, x))
        candidates.sort(key=lambda c: c[0])
        return candidates

    def _keep_distance(self, foe: Stickman) -> None:
        surface = self.surface
        assert surface is not None
        candidates = self._candidates(foe)
        stay = self._score(surface, self.position.x, foe)
        for score, s, x in candidates:
            if score >= stay - HOLD:
                break
            walk = s == surface and not self._walk_blocked(x)
            if walk:
                self.goal = (s, x)
                return
            if abs(self.speed) > 3.0:
                self.goal = (surface, self.position.x)
                self._replan_wait = 0.2
                return
            path = self._hop(x) if s == surface else self._path(self.position, s, x)
            if path is not None:
                self._levitate_to(s, x, path)
                return
        self.goal = None

    # ----- dimension door ---------------------------------------------------------------

    def _route_time(self, foe: Stickman, low: float = CAST_MIN, high: float = CAST_MAX) -> float:
        """Roughly how long walking or levitating to his best spot in casting range of
        `foe` would take (0 if he's in range; infinite if he can't get to one)."""
        surface = self.surface
        if low <= self.range_to(foe) <= high:
            return 0.0
        here = self.position
        target = foe.center()
        for _, s, x in self._candidates(foe):
            if not low <= Vec2(x, s.start.y + CHEST_Y).distance_to(target) <= high:
                continue
            if s == surface and not self._walk_blocked(x):
                return abs(x - here.x) / WALK_SPEED
            path = self._hop(x) if s == surface else self._path(here, s, x)
            if path is None:
                continue
            length = sum(a.distance_to(b) for a, b in zip(path, path[1:], strict=False))
            return length / FLOAT_SPEED + 1.0
        return math.inf

    def _sight(self, a: Vec2, b: Vec2) -> bool:
        """Whether the line from `a` to `b` passes through no window."""
        steps = max(1, int(a.distance_to(b) / SIGHT_STEP))
        for i in range(1, steps):
            point = a.lerp(b, i / steps)
            if any(box.contains(point) for box in self.world.boxes):
                return False
        return True

    def door_spot(self, foe: Stickman) -> tuple[Surface, Vec2] | None:
        """Where a dimension door to `foe` comes out: a spot on a surface `CAST_MIN`..
        `CAST_MAX` from him (as near `CAST_IDEAL` as it can), clear of every window and
        `DOOR_CROWD` from every free adventurer, best with a clear line to him and on his
        surface or one near it. None if there's nowhere."""
        target = foe.center()
        world = self.world
        prey = [other.center() for other in world.stickmen if other.prey]
        best: tuple[Surface, Vec2] | None = None
        best_score = math.inf
        for s in self._surfaces():
            if s.length < 2 * BODY_HALF:
                continue
            if world.ceiling is not None and s.start.y - HEIGHT < world.ceiling:
                continue
            low, high = self.span(s)
            rise = (s.start.y + CHEST_Y) - target.y
            if abs(rise) > CAST_MAX:
                continue
            reach = math.sqrt(max(0.0, CAST_IDEAL * CAST_IDEAL - rise * rise))
            under = s.low - 10.0 <= target.x <= s.high + 10.0 and 0.0 <= s.start.y - target.y < 40.0
            for side in (-1.0, 1.0):
                for dx in (0.0, -20.0, 20.0, -40.0, 40.0):
                    x = target.x + side * reach + dx
                    if not low <= x <= high:
                        continue
                    spot = Vec2(x, s.start.y)
                    chest = spot + Vec2(0.0, CHEST_Y)
                    distance = chest.distance_to(target)
                    if not CAST_MIN <= distance <= CAST_MAX:
                        continue
                    if spot.distance_to(self.position) < DOOR_MIN_JUMP or self._inside(spot):
                        continue
                    if any(chest.distance_to(p) < DOOR_CROWD for p in prey):
                        continue
                    score = abs(distance - CAST_IDEAL)
                    if not self._sight(chest, target):
                        score += 80.0
                    if not under:
                        score += 25.0 + 0.05 * abs(s.start.y - target.y)
                    if score < best_score:
                        best, best_score = (s, spot), score
        return best

    def _flight_time(self) -> float:
        flight = self.flight
        assert flight is not None
        points = [self.position, *flight.points]
        length = sum(a.distance_to(b) for a, b in zip(points, points[1:], strict=False))
        return length / FLOAT_SPEED

    def _try_door(self, foe: Stickman) -> bool:
        """Open a dimension door if `foe` is far enough to need it, or a much bigger
        group is gathered elsewhere, and it's ready (or wait for it, if it nearly is).
        Either way it comes out by the adventurer nearest the middle of the biggest
        group, who becomes his foe. True if that's what he's doing."""
        if self.door_wait > DOOR_PATIENCE or self.casting:
            return False
        prey = [s for s in self.world.stickmen if s.prey]
        if not prey:
            return False
        target, group = self._cluster(prey)
        crowd = (
            len(group) >= CLUSTER_DOOR
            and len(group) >= len(self._group_of(foe, prey)) + CLUSTER_GROWTH
            and foe not in group
        )
        if crowd and self.door_wait > 0.0:
            return False
        if not crowd and not self._far(foe):
            return False
        if self.range_to(target) <= CAST_MAX + CAST_SLACK:
            return False
        spot = self.door_spot(target)
        if spot is None:
            return False
        if self.door_wait > 0.0:
            if self.flight is None:
                self.goal = (self.surface, self.position.x) if self.surface else None
            return self.flight is None
        if self.flight is None and abs(self.speed) > 3.0:
            assert self.surface is not None
            self.goal = (self.surface, self.position.x)
            self._replan_wait = 0.2
            return True
        self.flight = None
        self.door = Door(self.position, self.surface, spot[1], spot[0])
        self.door_wait = DOOR_COOLDOWN
        self.doors += 1
        self.door_groups.append(len(group))
        self.foe, self._foe_since = target, self.time
        self.goal = None
        self.speed = 0.0
        return True

    def _far(self, foe: Stickman) -> bool:
        """Too far to cast at from a spot he can walk or float to soon enough."""
        reach = self.range_to(foe)
        if reach <= CAST_MAX + CAST_SLACK:
            return False
        if reach > DOOR_RANGE:
            return True
        if self.flight is not None:
            return self._flight_time() > DOOR_ROUTE_TIME
        return self._route_time(foe) > DOOR_ROUTE_TIME

    @staticmethod
    def _group_of(member: Stickman, prey: list[Stickman]) -> list[Stickman]:
        middle = member.center()
        return [s for s in prey if s.center().distance_to(middle) <= CLUSTER_RADIUS]

    def _cluster(self, prey: list[Stickman]) -> tuple[Stickman, list[Stickman]]:
        """The adventurer nearest the middle of the densest group (ties go to the
        group nearer him), and that group."""
        here = self.center()
        groups = [(self._group_of(s, prey), s) for s in prey]
        group, _ = max(groups, key=lambda g: (len(g[0]), -g[1].center().distance_to(here)))
        middle = Vec2(
            sum(s.center().x for s in group) / len(group),
            sum(s.center().y for s in group) / len(group),
        )
        return min(prey, key=lambda s: s.center().distance_to(middle)), group

    def _door_valid(self, surface: Surface, point: Vec2) -> bool:
        return surface in self._surfaces() and not self._inside(point)

    def _door_step(self, dt: float) -> None:
        door = self.door
        assert door is not None
        door.time += dt
        if not door.moved and door.time >= DOOR_SWAP:
            if not self._door_valid(door.surface, door.target):
                spot = self.door_spot(self.foe) if self.foe is not None else None
                if spot is not None:
                    door.surface, door.target = spot
                elif door.origin_surface is not None:
                    door.surface, door.target = door.origin_surface, door.origin
                else:
                    self.door = None
                    self._drop()
                    return
            door.moved = True
            self.position, self.surface = door.target, door.surface
            self.speed = 0.0
            foe = self.foe
            if foe is not None:
                self.heading = _sign(foe.center().x - self.position.x)
            self.yaw.value, self.yaw.rate = self._rest_yaw(self.heading), 0.0
        if door.time >= DOOR_TIME:
            self.door = None
            self._replan_wait = REPLAN_EVERY

    def _door_terrain(self, change: TerrainChange) -> None:
        """Windows moved mid-door: carry both ends, or find a new way out (back out of
        the door he went into, if need be)."""
        door = self.door
        assert door is not None
        if door.origin_surface is not None:
            origin = self._match(door.origin_surface, door.origin, change)
            door.origin_surface, door.origin = origin if origin else (None, door.origin)
        end = self._match(door.surface, door.target, change)
        if end is None or self._inside(end[1]):
            if door.moved:
                self.door = None
                self.surface = None
                self._drop()
                return
            end = self.door_spot(self.foe) if self.foe is not None else None
            if end is None and door.origin_surface is not None:
                end = (door.origin_surface, door.origin)
        if end is None:
            self.door = None
            self.surface = None
            self._drop()
            return
        door.surface, door.target = end
        if door.moved:
            self.surface, self.position = door.surface, door.target
        else:
            self.surface, self.position = door.origin_surface, door.origin

    def _wander(self) -> None:
        surface = self.surface
        assert surface is not None
        if self.goal is not None:
            return
        self._wander_wait -= REPLAN_EVERY
        if self._wander_wait > 0.0:
            return
        random = self.world.random
        self._wander_wait = random.uniform(*WANDER_WAIT)
        others = [s for s in self._surfaces() if s != surface and s.length > 4 * BODY_HALF]
        if others and random.random() < WANDER_LEVITATE:
            s = random.choice(others)
            x = random.uniform(*self.span(s))
            path = self._path(self.position, s, x)
            if path is not None and not self._inside(Vec2(x, s.start.y)):
                self._levitate_to(s, x, path)
                return
        self.goal = (surface, random.uniform(*self.span(surface)))

    def _walk(self, dt: float) -> None:
        surface = self.surface
        assert surface is not None
        low, high = self.span(surface)
        here = self.position.x
        target = here
        if self.goal is not None and self.goal[0] == surface:
            target = clamp(self.goal[1], low, high)
        dx = target - here
        backing = self.foe is not None and _sign(dx) != self.heading
        top = BACK_SPEED if backing else WALK_SPEED
        if self.turning:
            top *= 0.35
        want = _sign(dx) * min(top, math.sqrt(2.0 * ACCELERATION * max(0.0, abs(dx) - 0.3)))
        self.speed = _approach(self.speed, want, ACCELERATION * dt)
        x = clamp(here + self.speed * dt, low, high)
        if x != here + self.speed * dt:
            self.speed = 0.0
        self.position = Vec2(x, surface.start.y)
        if abs(dx) < 0.5 and abs(self.speed) < 1.0:
            self.speed = 0.0
            self.goal = None

    def _casting(self, dt: float) -> None:
        """The cast runs over whatever he's doing: only his arms and jaw take part."""
        self.cast_left -= dt
        progress = 1.0 - self.cast_left / CAST_TIME
        foe = self.foe
        if not self._released and progress >= CAST_RELEASE:
            self._released = True
            if foe is not None:
                self._cast(foe)
        if self.cast_left <= 0.0:
            self.cast_left = 0.0
            self.cast_wait = SPELL_DELAY.get(self.cast_spell or "", CAST_DELAY)

    def _float(self, dt: float) -> None:
        flight = self.flight
        assert flight is not None
        nxt = flight.points[0]
        remaining = self.position.distance_to(nxt)
        last = len(flight.points) == 1
        limit = math.sqrt(2.0 * FLOAT_ACCELERATION * remaining) + (0.0 if last else CORNER_SPEED)
        want = min(FLOAT_SPEED, limit)
        flight.speed = min(want, flight.speed + FLOAT_ACCELERATION * dt)
        step = max(flight.speed, 2.0) * dt
        position = self.position
        while step > 0.0 and flight.points:
            nxt = flight.points[0]
            gap = position.distance_to(nxt)
            if gap <= step:
                position = nxt
                step -= gap
                flight.points.pop(0)
            else:
                position = position + (nxt - position) * (step / gap)
                step = 0.0
        self.position = position
        if not flight.points:
            surface = flight.surface
            low, high = self.span(surface)
            self.position = Vec2(clamp(position.x, low, high), surface.start.y)
            self.surface = surface
            self.flight = None
            self.speed = 0.0
            self._replan_wait = 0.0

    def _face(self) -> None:
        foe = self.foe
        if self.door is not None and self.door.moved:
            return
        if foe is not None and (
            self.casting
            or self.levitating
            or self.door is not None
            or self.range_to(foe) < CAST_RANGE
        ):
            dx = foe.center().x - self.position.x
            if abs(dx) > 4.0:
                self.heading = _sign(dx)
            return
        if self.flight is not None:
            dx = self.flight.points[0].x - self.position.x
            if abs(dx) > 2.0:
                self.heading = _sign(dx)
            return
        if self.goal is not None:
            dx = self.goal[1] - self.position.x
            if abs(dx) > 2.0:
                self.heading = _sign(dx)

    def _animate(self, dt: float, before: Vec2) -> None:
        moved = self.position - before
        self.velocity = moved / dt if dt > 0.0 else Vec2(0.0, 0.0)
        self.yaw.update(self._rest_yaw(self.heading), TURN_RATE, dt)
        walking = clamp(abs(self.speed) / WALK_SPEED, 0.0, 1.0) if self.grounded else 0.0
        self.gait.update(walking, 8.0, dt)
        if self.grounded:
            self.phase = (self.phase + moved.x * self.facing / STRIDE) % 1.0
        self.lift.update(1.0 if self.levitating else 0.0, 5.0, dt)
        self.drag.update(clamp(self.velocity.x, -60.0, 60.0), 5.0, dt)
        progress = 1.0 - self.cast_left / CAST_TIME if self.casting else 1.0
        dooring = self.door is not None and self.door.time < DOOR_SWAP - 0.1
        self.raised.update(1.0 if dooring else 0.0, 9.0, dt)
        self.gesture.update(1.0 if self.casting and progress < 0.95 else 0.0, 10.0, dt)
        flaring = self.casting and CAST_RELEASE - 0.1 <= progress < CAST_RELEASE + 0.25
        flaring = flaring or (self.door is not None and 0.2 <= self.door.time < DOOR_FADE)
        self.flare.update(1.0 if flaring else 0.0, 14.0, dt)

    # ----- the terrain moving under him ----------------------------------------------

    def _match(
        self, surface: Surface, point: Vec2, change: TerrainChange
    ) -> tuple[Surface, Vec2] | None:
        """`surface` on the rebuilt terrain (the same kind on the same window, carried
        with it) and `point` on it, or None if that's gone."""
        box = surface.box
        if change.removed(box):
            return None
        point = point + (change.delta_for(box) or Vec2(0.0, 0.0))
        new_box = change.new_index(box)
        best: tuple[Surface, Vec2] | None = None
        best_distance = SURFACE_MATCH
        for s in self._surfaces():
            if s.kind is not surface.kind or s.box != new_box:
                continue
            closest = s.closest_point(point)
            distance = closest.distance_to(point)
            if distance <= best_distance:
                low, high = self.span(s)
                best, best_distance = (s, Vec2(clamp(closest.x, low, high), s.start.y)), distance
        return best

    def _landing(self, point: Vec2) -> tuple[Surface, float] | None:
        """The first surface straight below `point`, or the nearest clear one."""
        below = [
            s
            for s in self._surfaces()
            if s.low - 1.0 <= point.x <= s.high + 1.0 and s.start.y >= point.y - 1.0
        ]
        if below and not self._inside(point):
            s = min(below, key=lambda s: s.start.y)
            low, high = self.span(s)
            return s, clamp(point.x, low, high)
        best: tuple[Surface, float] | None = None
        best_distance = math.inf
        for s in self._surfaces():
            low, high = self.span(s)
            x = clamp(point.x, low, high)
            spot = Vec2(x, s.start.y)
            distance = spot.distance_to(point)
            if distance < best_distance and not self._inside(spot):
                best, best_distance = (s, x), distance
        return best

    def _drop(self) -> None:
        """Lost his footing (or a window opened over him): float down to safety."""
        landing = self._landing(self.position)
        self.surface = None
        self.cast_left = 0.0
        if landing is None:
            self.flight = None
            return
        surface, x = landing
        path = self._path(self.position, surface, x, lift=0.0)
        self._levitate_to(surface, x, path)

    def terrain_changed(self, change: TerrainChange) -> None:
        self.goal = None
        self._replan_wait = 0.0
        if self.dead:
            self._terrain_changed_dead(change)
            return
        if self.door is not None:
            self._door_terrain(change)
            return
        flight = self.flight
        if flight is not None:
            if change.shift is not None:
                self.position = self.position + change.shift
            target = self._match(flight.surface, flight.points[-1], change)
            if target is None:
                self._drop()
                return
            surface, end = target
            path = self._path(self.position, surface, end.x, lift=0.0)
            self._levitate_to(surface, end.x, path)
            return
        surface = self.surface
        if surface is None:
            self._drop()
            return
        moved = self._match(surface, self.position, change)
        if moved is None:
            carry = change.delta_for(surface.box)
            if carry is not None:
                self.position = self.position + carry
            self._drop()
            return
        self.surface, self.position = moved
        if self._inside(self.position):
            self._drop()

    # ----- death -------------------------------------------------------------------

    def die(self, point: Vec2, push: Vec2) -> None:
        joints = self.joints()
        self.dead = True
        self.down_time = 0.0
        self.cast_left = 0.0
        self.foe = None
        self.flight = None
        self.door = None
        self.position = joints.root
        side = self.facing
        nudge = Vec2(clamp(push.x * 0.12, -30.0, 30.0), 0.0)
        skull = joints.skull
        self.bits = [
            Bit("skull", skull, Vec2(side * 22.0, -60.0) + nudge, joints.tilt, side * 3.0, 4.6),
            Bit(
                "crown",
                skull + Vec2(0.0, -6.0),
                Vec2(-side * 34.0, -120.0) + nudge,
                0.0,
                -side * 7.0,
                2.5,
            ),
            Bit(
                "bone",
                joints.elbows[0].lerp(joints.hands[0], 0.5),
                Vec2(side * 30.0, -50.0),
                0.3,
                6.0,
                1.2,
            ),
            Bit("bone", joints.elbows[1], Vec2(-side * 15.0, -40.0), -0.8, -5.0, 1.2),
            Bit("hand", joints.hands[0], Vec2(side * 18.0, -30.0), 0.0, 4.0, 1.5),
        ]
        landing = self._landing(self.position)
        if landing is not None:
            self.surface = landing[0]

    def ground_below(self, point: Vec2) -> float:
        below = [
            s.start.y
            for s in self._surfaces()
            if s.low - 1.0 <= point.x <= s.high + 1.0 and s.start.y >= point.y - 1.0
        ]
        return min(below) if below else self.world.floor_y

    def update_dead(self, dt: float) -> None:
        self.down_time += dt
        self.time += dt
        self.slump = min(1.0, self.slump + dt / COLLAPSE_TIME)
        self.flame = max(0.0, 1.0 - self.down_time / FLAME_OUT)
        ground = self.ground_below(self.position)
        if self.position.y < ground:
            self.fall_speed += GRAVITY * dt
            self.position = Vec2(
                self.position.x, min(ground, self.position.y + self.fall_speed * dt)
            )
        else:
            self.fall_speed = 0.0
        for bit in self.bits:
            if bit.resting:
                floor = self.ground_below(bit.position - Vec2(0.0, bit.radius + 1.0))
                if floor - bit.radius > bit.position.y + 0.5:
                    bit.resting = False
                continue
            bit.velocity = bit.velocity + Vec2(0.0, GRAVITY * dt)
            bit.position = bit.position + bit.velocity * dt
            bit.angle += bit.spin * dt
            floor = self.ground_below(bit.position - Vec2(0.0, bit.radius + 4.0))
            if bit.position.y + bit.radius >= floor:
                bit.position = Vec2(bit.position.x, floor - bit.radius)
                if bit.velocity.y > 60.0:
                    bit.velocity = Vec2(bit.velocity.x * 0.5, -bit.velocity.y * 0.3)
                    bit.spin *= 0.5
                else:
                    bit.velocity = Vec2(0.0, 0.0)
                    bit.spin = 0.0
                    bit.resting = True

    def _terrain_changed_dead(self, change: TerrainChange) -> None:
        surface = self.surface
        carry = change.delta_for(surface.box) if surface is not None else change.shift
        if carry is not None:
            y = surface.start.y if surface is not None else None
            self.position = self.position + carry
            for bit in self.bits:
                if bit.resting and y is not None and abs(bit.position.y + bit.radius - y) < 2.0:
                    bit.position = bit.position + carry
        self.surface = None
        landing = (
            self._landing(self.position)
            if not change.removed(surface.box if surface else None)
            else None
        )
        if landing is not None:
            self.surface = landing[0]
