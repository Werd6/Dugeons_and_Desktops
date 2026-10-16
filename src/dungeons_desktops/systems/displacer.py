"""The displacer beast: a big six-legged panther with two barbed tentacles on its
shoulders, prowling the windows.

It has its own terrain and planner (`world.displacer_planner`): its feet go right on
a window's top, flat against either side, and upside down along its underside (and
on the screen edges and the screen top on the desktop), turning every corner by
rolling its body round it. Planned jumps and drops become ballistic leaps, and on
top of the planner it leaps straight across gaps: to another window up to
`LEAP_RANGE` off, or as a pounce at its quarry.

Every leap goes crouch (`CROUCH_TIME`), flight (an exact ballistic arc to the
surface it aims for, checked clear of every window before it goes), landing absorb
(`LAND_TIME`). If a window moves under it mid-flight it lands where that surface went;
if its target closes, or a window turns up in its way, it falls and clings to the
first window it hits.

With nobody near it wanders, prowling (`prowl`), loping on long routes (`lope`), now
and then leaping to another window. An adventurer within `NOTICE_RANGE` gets stalked at
a low, slow `stalk`, then pounced on from within `POUNCE_RANGE`: it lands right on him,
mauling him for `POUNCE_DAMAGE` if he's still there, and slinks off a way
(`RETREAT_TIME`) before stalking him again.

Every `RUSE_COOLDOWN` or so, stalking him, it sends its illusion out first: a second
`Displacer` (`illusion`, owned by and updated from the real one as its `ghost`) that
peels off from it, pounces at him (a swipe that does nothing), bounds over to his other
side and swipes again, for up to `RUSE_TIME`. To the adventurers it's a monster like any
other, but their blows pass straight through it. Meanwhile the real beast creeps in to
`RUSE_CREEP`, and the moment he goes for the illusion (or turns his back on it), it
pounces, whoever else is at it.

A pounce that lands sends it into a frenzy (`FRENZY_TIME`, longer per kill up to
`FRENZY_MAX`; its illusion vanishes): quick pounces (`CROUCH_TIME["frenzy"]`) on the
nearest adventurer within `FRENZY_RANGE`, up to `FRENZY_POUNCES`, clawing and stabbing
anyone too close.

Under attack it fights: it closes in to a spot `STAND_OFF` short of its foe (or on the
wall above him), and claws and stabs him by turns, a swipe of its paw ahead of it and a
thrust of its tentacles straight at him from its shoulders in any direction (up to
`STAB_REACH`); a claw swipe that wouldn't reach him it skips for a stab. With
`DISPLACER_HP` gone it drops off whatever it was on and lies on its side (and its
illusion vanishes).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Rect, Vec2, clamp, smoothstep, wrap_angle
from dungeons_desktops.navigation.planner import (
    ALONG_MOVES,
    Anchor,
    Move,
    MoveSettings,
    Planner,
    Route,
    RouteStep,
)
from dungeons_desktops.navigation.terrain import Surface, TerrainChange
from dungeons_desktops.systems.hunt import nearest
from dungeons_desktops.systems.mortal import DISPLACER_HP, Mortal
from dungeons_desktops.systems.movement import RouteFollower

if TYPE_CHECKING:
    from dungeons_desktops.systems.actors import Stickman
    from dungeons_desktops.systems.world import SimWorld

GRAVITY = 1100.0
BODY_HEIGHT = 13.0
"""Body center out from its feet."""
HALF_LENGTH = 14.0
"""Body center to the shoulders and to the hips."""
HEAD_REACH = 27.0
"""Body center to the head."""
BODY_RADIUS = 7.0
HEAD_RADIUS = 4.5

MOVES = MoveSettings(
    walk_speed=58.0,
    climb_speed=46.0,
    hang_speed=40.0,
    mantle_time=0.45,
    grab_time=0.4,
    swing_time=0.5,
    max_drop=320.0,
    max_hang_drop=1000.0,
    max_jump=110.0,
    gravity=GRAVITY,
    edge_clearance=4.0,
)
"""Its routes, timed at the prowl. Walls run the whole height of a window (it needs
no hang reach), the corner over a window top is `MANTLE_DEPTH` deep, and undersides
are right at a window's bottom edge (`HANG_DEPTH` 0)."""
HANG_REACH = 0.0
MANTLE_DEPTH = 6.0
HANG_DEPTH = 0.0
CLEARANCE = 15.0
"""Surfaces with another window closer than this (its body's room) are left out."""

GAITS = {
    "stalk": {Move.WALK: 30.0, Move.CLIMB: 26.0, Move.HANG: 24.0},
    "prowl": {Move.WALK: 58.0, Move.CLIMB: 46.0, Move.HANG: 40.0},
    "lope": {Move.WALK: 140.0, Move.CLIMB: 88.0, Move.HANG: 72.0},
}
"""Pixels a second along a top, up or down a side, and along an underside."""
CYCLE = {"stalk": 20.0, "prowl": 24.0, "lope": 50.0}
"""Distance covered in one full stride cycle (all six feet stepping once)."""
ACCELERATION = 3.0
"""How quickly (1/s) its pace eases toward the gait's speed."""
LOPE_DISTANCE = 240.0
"""Routes with more than this left to go are loped."""

LEAP_RANGE = 320.0
LEAP_MIN = 70.0
LEAP_CHANCE = 0.35
"""Odds a fresh wander goal is a leap to another window (if one is in range)."""
LEAP_COOLDOWN = 2.0
MAX_LEAP_SPEED = 950.0
LEAP_PACE = 650.0
"""Flight time grows by a second per this many pixels of leap."""
BODY_CLEARANCE = 4.0
"""How far its body center keeps off every window along a leap's arc."""
CROUCH_TIME = {"hop": 0.14, "leap": 0.32, "pounce": 0.55, "vault": 0.22, "frenzy": 0.15}
LAND_TIME = {"hop": 0.14, "leap": 0.3, "pounce": 0.45, "vault": 0.25, "frenzy": 0.15, "fall": 0.35}
POUNCES = ("pounce", "frenzy")
VAULT_TIME = 0.62
"""The least flight time of a vault (the illusion bounding over its quarry's head)."""
CLING_REACH = 26.0
"""How far from where it hits a window a surface may be for it to cling on."""
SLIDE_MAX = 40.0
ESCAPE_REACH = 120.0
"""A window opening (or moving) on top of it: it springs out to a surface this near."""
SLIDE_TIME = 0.09
"""A snap of its body (landing, a window jumping under it) is eased out over this."""

TURN_TIME = 0.3
"""Its head coming round, turning about in depth (past a front-on look)..."""
YAW_LAG = 0.35 * math.pi
"""...with the tail tip this far (in yaw) behind it, so it finishes last."""
TURN_SET_OFF = 0.6
"""It sets off the new way once this much of a turn is done."""
TURN_MIN = 10.0
"""A backward move shorter than this, ending its route, is a step back, not a turn."""
TURN_COOLDOWN = 0.7
"""It won't turn back again sooner than this."""
FACE_MARGIN = 20.0
"""It only turns to face something this far behind it (not someone right above or
below it)."""
TURN_SHUFFLE = 6.0
"""Turning about on the spot its feet shuffle as if walking this fast."""
TAIL_REACH = 50.0
"""Body center to the tail tip, along its body (for the yaw lag)."""
SPINE_REACH = 50.0
"""How far each way its body's center line is laid along the surfaces."""
SPINE_STEP = 1.5
SPINE_SMOOTH = 8
"""Samples each side averaged to round the center line's corners."""
WALK_STEP = 3.0
CORNER_JOIN = 9.0
"""Surface ends this close meet at a corner its body bends round."""
CORNER_SAMPLES = 6
BEND_RATE = 10.0
"""How quickly (1/s) its body goes from straight (in the air) to lying along its surfaces."""
ADVANCE_BUDGET = 0.6
"""Most route time it gets through in one frame (on the spot pivots in corners)."""

NOTICE_RANGE = 400.0
STALK_CLOSE = 300.0
"""Within this of its quarry it drops to the stalk."""
POUNCE_RANGE = 280.0
POUNCE_MIN = 45.0
"""Closer than this it slinks off rather than pounce."""
POUNCE_COOLDOWN = 5.0
POUNCE_DAMAGE = 10
POUNCE_HIT = 22.0
"""A pounce mauls its quarry if its body or head comes this near his middle."""
POUNCE_PUSH = 260.0
RUSE_COOLDOWN = 2.0
"""It sends its illusion out as soon as it starts stalking someone, and again this long
after the last one is gone."""
RUSE_TIME = 7.0
"""The longest the illusion keeps up its feints."""
HOLD_BACK = 210.0
"""Till its illusion is out after its quarry it creeps no closer than this to him."""
RUSE_CREEP = 140.0
"""While its illusion is out after him it creeps in to this, ready to pounce."""
FRENZY_TIME = 3.5
"""After a pounce lands it frenzies this long, chaining pounces on whoever's near."""
FRENZY_KILL = 1.0
"""Each kill in a frenzy draws it out this much longer..."""
FRENZY_MAX = 6.0
"""...up to this long in all."""
FRENZY_RANGE = 200.0
FRENZY_EVERY = 0.55
"""Least time from one frenzied pounce's crouch to the next."""
FRENZY_POUNCES = 3
CALM_TIME = 3.0
"""It counts as under attack for this long after a hit or a blow aimed at it from within
`THREAT_REACH`; under attack, or with anyone within `CLOSE_RANGE`, it fights instead of
stalking."""
THREAT_REACH = 80.0
CLOSE_RANGE = 110.0
FIGHT_REPLAN = 0.3
FOE_SHIFT = 30.0
"""It keeps its route to its foe till he's moved this far from where it was headed."""
FOE_COMMIT = 1.5
"""It sticks with a foe at least this long..."""
FOE_SWITCH = 0.6
"""...unless someone else is this much nearer (as a fraction of his distance)."""
FIGHT_KEEP = 40.0
"""A foe it's fighting it keeps fighting this much farther off than it'd pick one."""
FIGHT_GIVE_UP = 2.0
"""A foe it finds no way to for this long it leaves alone for `IGNORE_FOE`."""
IGNORE_FOE = 4.0
STAB_REACH = 80.0
"""How far from its shoulders its tentacles spear, in any direction."""
STAB_TIMES = (0.2, 0.1, 0.25)
"""Wind-up (drawing back, aim following him), thrust and recovery of a tentacle stab..."""
CLAW_TIMES = (0.15, 0.1, 0.25)
"""...and of a claw swipe."""
STAB_DAMAGE = 4
CLAW_DAMAGE = 4
MELEE_COOLDOWN = 1.0
"""From one claw swipe or stab to the next (they take turns)."""
STAB_PUSH = 180.0
CLAW_PUSH = 150.0
STAB_PAST = 10.0
"""A stab thrusts this far past where it aimed (within `STAB_REACH`)."""
STAB_MARGIN = 5.0
STAB_HITS = 2
"""The most adventurers one stab runs through."""
CLAW_REACH = 36.0
"""How far from its chest a claw swipe reaches (the paw's rake plus `CLAW_GRAB`)."""
CLAW_GRAB = 10.0
STAND_OFF = 28.0
"""Closing in, it stops this far short of its foe along his surface..."""
WALL_PERCH = 34.0
"""...or, with a wall in the way, on the wall this far above his feet."""
OVERLAP = 16.0
"""Its body this near his center, it's on top of him: it backs off to stand off."""
SHOULDER = Vec2(HALF_LENGTH - 3.0, -8.0)
CHEST = Vec2(HALF_LENGTH + 4.0, 2.0)
"""Where the tentacles and the chest are on its straight body (x toward the head, y
toward the feet)."""
TENTACLE_REST = 40.0
PAW_REST = Vec2(HALF_LENGTH + 1.0, BODY_HEIGHT)
PAW_RAISED = Vec2(HALF_LENGTH + 4.0, -12.0)
PAW_RAKE = Vec2(HALF_LENGTH + 30.0, 3.0)
RUSE_TRIES = 2
"""Its illusion failing to draw its quarry this many times running, it gives him up
for a while."""
FAIR_TIME = 2.0
"""...and for this long on one who was still fighting its illusion when it vanished."""
EMERGE_TIME = 0.5
VANISH_TIME = 0.5
FEINT_BESIDE = 14.0
"""The illusion's feints land this far short of the quarry, on the side it came from..."""
FEINT_CROSS = 75.0
"""...then it leaps over to this far past him on his other side..."""
FEINT_HOLD = 1.1
FEINT_TURN = 0.35
"""...after swiping at him this long, and turning round on landing this long."""
SHIMMER_TIME = 0.5
STRIKE_TIME = 0.45
"""A swipe at its quarry (as a pounce lands) lasts this long."""
RETREAT_TIME = 2.5
RETREAT_DISTANCE = (140.0, 280.0)
REPLAN_EVERY = 0.5
GOAL_SNAP = 80.0
ARRIVED = 3.0
REST_TIME = (0.6, 2.2)
STUCK_TIME = 3.0

ZERO = Vec2(0.0, 0.0)
UPRIGHT = Vec2(0.0, -1.0)
HOPS = (Move.JUMP, Move.DROP)


class Intent(Enum):
    WANDER = "wander"
    STALK = "stalk"
    FIGHT = "fight"
    RETREAT = "retreat"


@dataclass
class Leap:
    """A ballistic flight of its body center from `start` to the `target` surface."""

    target: Anchor
    kind: str
    """"hop" (a planned jump or drop), "leap", "pounce", "frenzy" (a quick pounce in a
    frenzy) or "vault" (an illusion's bound over its quarry)."""
    quarry: Stickman | None = None
    """Who a (real) pounce mauls if it reaches him."""
    start: Vec2 = ZERO
    velocity: Vec2 = ZERO
    time: float = 0.0
    elapsed: float = 0.0
    struck: bool = False
    killed: bool = False


def along(up: Vec2) -> Vec2:
    """The +1 heading along a surface whose outward side is `up` (+x on a top)."""
    return Vec2(-up.y, up.x)


def up_of(way: Vec2) -> Vec2:
    """The outward side for a +1 heading of `way` (the inverse of `along`)."""
    return Vec2(way.y, -way.x)


class Spine:
    """Its body's center line, in its +1 heading order: `points` every `step` apart,
    the first at arc position `first` (0 is at its body center)."""

    def __init__(self, points: list[Vec2], first: float, step: float) -> None:
        self.points = points
        self.first = first
        self.step = step
        last = len(points) - 1
        self.tangents = [
            (points[min(i + 1, last)] - points[max(i - 1, 0)]).normalized() for i in range(last + 1)
        ]

    def frame(self, p: float) -> tuple[Vec2, Vec2]:
        """The center line point at arc position `p` (straight on past its ends) and the
        way up from it there."""
        points, tangents = self.points, self.tangents
        last = len(points) - 1
        f = (p - self.first) / self.step
        if f <= 0.0 or f >= last:
            i = 0 if f <= 0.0 else last
            tangent = tangents[i]
            return points[i] + tangent * ((f - i) * self.step), up_of(tangent)
        i = int(f)
        t = f - i
        tangent = tangents[i].lerp(tangents[i + 1], t).normalized()
        return points[i].lerp(points[i + 1], t), up_of(tangent)

    def at(self, p: float, y: float) -> Vec2:
        """A point `y` below (toward its feet from) the center line at `p`."""
        point, up = self.frame(p)
        return point - up * y


def _turn_toward(current: Vec2, target: Vec2, amount: float) -> Vec2:
    angle = current.angle()
    return Vec2.from_angle(angle + wrap_angle(target.angle() - angle) * amount)


def _ease(value: float, target: float, rate: float, dt: float) -> float:
    return value + (target - value) * (1.0 - math.exp(-rate * dt))


def _grown(box: Rect, margin: float) -> Rect:
    return Rect(box.x - margin, box.y - margin, box.width + 2 * margin, box.height + 2 * margin)


def _along_move(surface: Surface) -> Move:
    if surface.walkable:
        return Move.WALK
    return Move.HANG if surface.hanging else Move.CLIMB


def _body_rate(step: RouteStep) -> float:
    """Roughly how fast its body goes (px/s) along `step` of a route at the prowl."""
    if step.move in ALONG_MOVES:
        return {Move.WALK: MOVES.walk_speed, Move.CLIMB: MOVES.climb_speed}.get(
            step.move, MOVES.hang_speed
        )
    turn = abs(wrap_angle(step.surface.normal.angle() - step.from_surface.normal.angle()))
    span = step.start.distance_to(step.end) + BODY_HEIGHT * turn
    return max(5.0, span / max(step.duration, 1e-3))


def _run(samples: list[tuple[Vec2, Vec2]], start: Vec2, offset: Vec2, up: Vec2) -> None:
    """Feet samples every `WALK_STEP` from `start` to `start + offset`."""
    count = math.ceil(offset.length() / WALK_STEP)
    for i in range(1, count + 1):
        samples.append((start + offset * (i / count), up))


def _least(kind: str) -> float:
    return VAULT_TIME if kind == "vault" else 0.0


def _closest_arc(line: list[Vec2], arcs: list[float], point: Vec2) -> float:
    """The arc position along the polyline `line` nearest `point`."""
    best, best_distance = 0.0, math.inf
    for i in range(len(line) - 1):
        a, b = line[i], line[i + 1]
        span = b - a
        t = clamp((point - a).dot(span) / max(span.length_sq(), 1e-12), 0.0, 1.0)
        distance = point.distance_to(a + span * t)
        if distance < best_distance:
            best, best_distance = arcs[i] + (arcs[i + 1] - arcs[i]) * t, distance
    return best


class Displacer(Mortal):
    max_hp = DISPLACER_HP
    linger = 3.0
    gaits = GAITS

    def __init__(
        self, world: SimWorld, anchor: Anchor, heading: int = 1, owner: Displacer | None = None
    ) -> None:
        self.world = world
        self.owner = owner
        """The real beast, if this is its illusion."""
        self.ghost: Displacer | None = None
        """Its illusion while one is out."""
        self.ruse_wait = 0.0
        self.fooled = False
        """An illusion its quarry has gone for."""
        self.fair: Stickman | None = None
        self.failed_ruses = 0
        self.fair_left = 0.0
        self.harried = 0.0
        """Under attack while this is above 0."""
        self._hurt_seen = 0
        self.foe: Stickman | None = None
        """Who it's fighting."""
        self._foe_stuck = 0.0
        self._foe_since = 0.0
        self._foe_goal: Vec2 | None = None
        self._ignored_foes: dict[Stickman, float] = {}
        self.attack: str | None = None
        """"stab" or "claw" while it's attacking."""
        self.attack_time = 0.0
        self._struck: set[Stickman] = set()
        self.melee_wait = 0.0
        self.next_melee = "claw"
        """Its next attack up close (they take turns)."""
        self.stab_way = Vec2(1.0, 0.0)
        """Which way (in the world) a stab spears from its shoulder..."""
        self.stab_span = STAB_REACH
        """...and how far."""
        self._stab_foe: Stickman | None = None
        self.frenzy_left = 0.0
        """In a frenzy while this is above 0."""
        self.frenzy_time = 0.0
        self.frenzy_pounces = 0
        self.frenzy_wait = 0.0
        self.fury = 0.0
        """0 calm to 1 in a frenzy (eased, for drawing)."""
        self.act = "out"
        """The illusion's script: "out" after its quarry, "strike" swiping at him,
        "cross" over to his other side, "run" there on foot, "turn" round to feint again."""
        self.act_left = 0.0
        self.side = 1.0
        """Which side of its quarry (along his surface) the illusion is feinting from."""
        self.feints = 0
        self.ruse_left = RUSE_TIME
        self.emerge = 0.0 if owner is not None else 1.0
        self.vanish = 0.0
        self.vanishing = False
        self.shimmer = 0.0
        """1 just after an attack passed through the illusion, easing to 0."""
        self.shimmer_at = ZERO
        self.strike = 0.0
        """1 at a swipe at its quarry (a pounce landing), easing to 0."""
        self.follower: RouteFollower | None = None
        """Its route while it's on a surface; None in the air."""
        self.position = anchor.point
        """Its feet, on a surface."""
        self.up = UPRIGHT
        """Away from the surface its feet are on."""
        self.body = anchor.point
        """Its body center: the feet plus `up` * `BODY_HEIGHT` on a surface."""
        self.velocity = ZERO
        self.heading = heading
        """+1 or -1: which way along its surface it faces (see `along`)."""
        self.intent = Intent.WANDER
        self.hunt = nearest()
        self.target: Stickman | None = None
        self.goal: Vec2 | None = None
        self.gait = "prowl"
        self.pace = 1.0
        """Its speed as a multiple of the planner's (prowl) speeds."""
        self.pending: Leap | None = None
        """The leap it's crouching for."""
        self.crouch_left = 0.0
        self.leap: Leap | None = None
        """The leap it's in the air on (None in a fall)."""
        self.land_left = 0.0
        self.land_time = 1.0
        self.leap_wait = 1.0
        self.retreat_left = 0.0
        self.rest = 0.5
        self._replan_wait = 0.0
        self._still = 0.0
        # Animation state (smoothed, read by the renderer and for hit testing).
        self.time = 0.0
        self.phase = 0.0
        self.speed = 0.0
        self.look_up = UPRIGHT
        """Its body's way up when straight (in the air), easing after its surface's."""
        self.head_yaw = self.tail_yaw = 0.0 if heading > 0 else math.pi
        """Turned about in depth: 0 facing its +1 heading, pi its -1 (past pi/2, face
        on), the tail lagging the head."""
        self.turn_wait = 0.0
        self.bend = 1.0
        """0 straight (in the air) to 1 lying along its surfaces."""
        self._spine: tuple[tuple, Spine] | None = None
        self.slide = ZERO
        self.low = 0.0
        self.lope = 0.0
        self.crouch = 0.0
        self.impact = 0.0
        self.slump = 0.0
        self._attach(anchor)
        self.look_up = self.up

    @property
    def planner(self) -> Planner:
        return self.world.displacer_planner

    @property
    def airborne(self) -> bool:
        return self.follower is None

    @property
    def support(self) -> Surface | None:
        return self.follower.current_anchor().surface if self.follower is not None else None

    @property
    def landing(self) -> float:
        """1 just after touching down, easing to 0 over the landing absorb."""
        return clamp(self.land_left / self.land_time, 0.0, 1.0) if self.land_time > 0 else 0.0

    @property
    def flight(self) -> float:
        """How far through its leap it is (0.5 in a fall)."""
        if self.leap is None or self.leap.time <= 0.0:
            return 0.5
        return clamp(self.leap.elapsed / self.leap.time, 0.0, 1.0)

    def center(self) -> Vec2:
        return self.body

    @property
    def illusion(self) -> bool:
        return self.owner is not None

    @property
    def feinting(self) -> bool:
        """An illusion that's out and can be seen (and attacked)."""
        return self.illusion and not self.vanishing

    @property
    def presence(self) -> float:
        """How much of an illusion is there: 0 to 1 coming out, back to 0 vanishing."""
        return self.emerge * (1.0 - self.vanish)

    # ----- its drawn body (no ghost), for hit testing and drawing -----------------

    @property
    def look_center(self) -> Vec2:
        return self.body + self.slide

    @property
    def turn(self) -> float:
        """How far round it's facing: 1 its +1 heading, -1 its -1, 0 face on."""
        return math.cos(0.5 * (self.head_yaw + self.tail_yaw))

    def yaw_at(self, x: float) -> float:
        """The yaw of its body `x` along it (toward the head): the head leads a turn."""
        u = clamp((x + TAIL_REACH) / (HEAD_REACH + TAIL_REACH), 0.0, 1.0)
        return self.tail_yaw + (self.head_yaw - self.tail_yaw) * u

    def to_world(self, local: Vec2, z: float = 0.0) -> Vec2:
        """A point of its body (x toward the head, y toward the feet, z toward its near
        side) in the world, turned about in depth and laid along its center line."""
        yaw = self.yaw_at(local.x)
        x = local.x * math.cos(yaw) - z * math.sin(yaw)
        return self.spine().at(x, local.y) + self.slide

    def parts(self) -> list[Vec2]:
        return [
            self.to_world(Vec2(0.0, 0.0)),
            self.to_world(Vec2(HALF_LENGTH, -1.0)),
            self.to_world(Vec2(-HALF_LENGTH, -1.0)),
            self.to_world(Vec2(HEAD_REACH, -3.0)),
        ]

    def hits(self, point: Vec2, margin: float = 0.0) -> bool:
        middle, shoulders, hips, head = self.parts()
        for a, b in ((hips, middle), (middle, shoulders)):
            span = b - a
            t = clamp((point - a).dot(span) / max(span.length_sq(), 1e-9), 0.0, 1.0)
            if point.distance_to(a + span * t) <= BODY_RADIUS + margin:
                return True
        return point.distance_to(head) <= HEAD_RADIUS + margin

    # ----- its body's center line ------------------------------------------------

    def spine(self) -> Spine:
        """Straight through its body in the air; on a surface, laid along the surfaces
        each way from its feet, round every corner (follow the leader, both ways)."""
        follower = self.follower
        key = (
            self.time,
            self.body,
            self.position,
            self.look_up,
            self.bend,
            None if follower is None else (id(follower.step), follower.elapsed),
        )
        if self._spine is not None and self._spine[0] == key:
            return self._spine[1]
        spine = self._lay_spine()
        self._spine = (key, spine)
        return spine

    def _lay_spine(self) -> Spine:
        way = along(self.look_up)
        rigid = Spine(
            [self.body - way * SPINE_REACH, self.body + way * SPINE_REACH],
            -SPINE_REACH,
            2 * SPINE_REACH,
        )
        if self.follower is None or self.bend <= 0.01:
            return rigid
        bent = self._bent_spine()
        if bent is None:
            return rigid
        if self.bend >= 0.99:
            return bent
        # Settling after a landing: turned to its eased way up, straight to bent.
        turn = wrap_angle(self.look_up.angle() - bent.frame(0.0)[1].angle())
        points = [
            rigid.frame(bent.first + i * bent.step)[0].lerp(
                self.body + (point - self.body).rotated(turn), self.bend
            )
            for i, point in enumerate(bent.points)
        ]
        return Spine(points, bent.first, bent.step)

    def _bent_spine(self) -> Spine | None:
        follower = self.follower
        assert follower is not None
        step = follower.step
        if step is not None and step.move not in ALONG_MOVES and step.move not in HOPS:
            t = follower.elapsed / step.duration if step.duration > 0.0 else 1.0
            surface, point = (
                (step.from_surface, step.start) if t < 0.5 else (step.surface, step.end)
            )
        else:
            anchor = follower.current_anchor()
            surface, point = anchor.surface, anchor.point
        reach = SPINE_REACH + 2.0 * BODY_HEIGHT
        near = [
            s
            for s in self.planner.surfaces
            if s.closest_point(point).distance_to(point) <= reach + 30.0
        ]
        ahead = self._walk(surface, point, 1, reach, near)
        behind = self._walk(surface, point, -1, reach, near)
        line: list[Vec2] = []
        for foot, up in [*reversed(behind[1:]), *ahead]:
            body = self._offset(foot + up * BODY_HEIGHT, near)
            if not line or body.distance_to(line[-1]) > 0.3:
                line.append(body)
        if len(line) < 2:
            return None
        arcs = [0.0]
        for a, b in zip(line, line[1:], strict=False):
            arcs.append(arcs[-1] + a.distance_to(b))
        zero = _closest_arc(line, arcs, self.body)
        first = arcs[0] - zero
        count = max(2, int((arcs[-1] - arcs[0]) / SPINE_STEP) + 1)
        samples: list[Vec2] = []
        j = 0
        for i in range(count):
            s = arcs[0] + i * SPINE_STEP
            while j < len(arcs) - 2 and arcs[j + 1] < s:
                j += 1
            span = arcs[j + 1] - arcs[j]
            t = clamp((s - arcs[j]) / span, 0.0, 1.0) if span > 1e-9 else 0.0
            samples.append(line[j].lerp(line[j + 1], t))
        last = len(samples) - 1
        smooth: list[Vec2] = []
        for i in range(last + 1):
            k = min(SPINE_SMOOTH, i, last - i)
            total = ZERO
            for point in samples[i - k : i + k + 1]:
                total = total + point
            smooth.append(total / (2 * k + 1))
        return Spine(smooth, first, SPINE_STEP)

    def _walk(
        self, surface: Surface, point: Vec2, sign: int, reach: float, near: list[Surface]
    ) -> list[tuple[Vec2, Vec2]]:
        """Feet and way up every `WALK_STEP` from `point` along `surface` its `sign` way,
        round the corners onto the next surfaces, straight on off the last one."""
        samples = [(point, surface.normal)]
        left = reach
        for _ in range(4):
            normal = surface.normal
            way = along(normal) * sign
            end = max((surface.start, surface.end), key=lambda e: (e - point).dot(way))
            go = min(max(0.0, (end - point).dot(way)), left)
            _run(samples, point, way * go, normal)
            point = point + way * go
            left -= go
            if left <= 1e-6:
                return samples
            corner = self._corner(surface, end, sign, near)
            if corner is None:
                break
            following, start = corner
            for i in range(1, CORNER_SAMPLES + 1):
                f = i / CORNER_SAMPLES
                up = normal.lerp(following.normal, f).normalized()
                samples.append((point.lerp(start, f), up))
            left -= point.distance_to(start)
            surface, point = following, start
        _run(samples, point, along(surface.normal) * (sign * max(0.0, left)), surface.normal)
        return samples

    @staticmethod
    def _corner(
        surface: Surface, end: Vec2, sign: int, near: list[Surface]
    ) -> tuple[Surface, Vec2] | None:
        """The surface that carries on round the corner at `end`, and where on it."""
        best: tuple[Surface, Vec2] | None = None
        best_distance = CORNER_JOIN
        for other in near:
            if other.id == surface.id or abs(other.normal.dot(surface.normal)) > 0.5:
                continue
            way = along(other.normal) * sign
            for tip, tail in ((other.start, other.end), (other.end, other.start)):
                distance = tip.distance_to(end)
                if distance <= best_distance and (tail - tip).dot(way) > 0.0:
                    best, best_distance = (other, tip), distance
        return best

    def _offset(self, body: Vec2, surfaces: list[Surface] | None = None) -> Vec2:
        """`body` pushed out to its body's height off every surface it's nearer than
        that to (in an inside corner it sits back from both)."""
        surfaces = self.planner.surfaces if surfaces is None else surfaces
        for _ in range(2):
            pushed = False
            for surface in surfaces:
                normal = surface.normal
                gap = (body - surface.start).dot(normal)
                if gap < 0.0 or gap >= BODY_HEIGHT - 1e-6:
                    continue
                coord = surface.coord(body)
                if not surface.low + 0.5 < coord < surface.high - 0.5:
                    continue
                body = body + normal * (BODY_HEIGHT - gap)
                pushed = True
            if not pushed:
                break
        return body

    # ----- simulation ----------------------------------------------------------

    def update(self, dt: float) -> None:
        self.time += dt
        self.leap_wait -= dt
        self.retreat_left -= dt
        if self.illusion:
            self._fade(dt)
        else:
            self.ruse_wait -= dt
            self.fair_left -= dt
            self.melee_wait -= dt
            if self.frenzy_left > 0.0:
                self.frenzy_left -= dt
                self.frenzy_time += dt
                self.frenzy_wait -= dt
                if self.frenzy_left <= 0.0:
                    self._calm_down()
            self._watch(dt)
            self.target = self.hunt.update(dt, self.body, self.world.stickmen)
        if self.pending is not None:
            self._crouching(dt)
        elif self.follower is None:
            self._fly(dt, alive=True)
        else:
            if self.land_left > 0.0:
                self.land_left -= dt
            elif self.attack is not None:
                self._swing(dt)
            elif not self.follower.in_transition:
                self._think(dt)
            if self.follower is not None and self.pending is None:
                self._crawl(dt)
        self._animate(dt)
        self._update_ghost(dt)

    def _update_ghost(self, dt: float) -> None:
        ghost = self.ghost
        if ghost is None:
            return
        ghost.update(dt)
        if ghost.vanish >= 1.0:
            self.ghost = None
            self.ruse_wait = RUSE_COOLDOWN
            if ghost.fooled:
                self.fair, self.fair_left = ghost.target, FAIR_TIME
                self.failed_ruses = 0
            elif ghost.target is self.target and not self.dead:
                self.failed_ruses += 1
                if self.failed_ruses >= RUSE_TRIES:
                    self.failed_ruses = 0
                    self.hunt.unreachable(0.0, 0.0)

    def _fade(self, dt: float) -> None:
        """An illusion comes out, keeps up its ruse a while, and vanishes."""
        self.emerge = min(1.0, self.emerge + dt / EMERGE_TIME)
        self.shimmer = max(0.0, self.shimmer - dt / SHIMMER_TIME)
        self.ruse_left -= dt
        target = self.target
        if target is not None and target.foe is self:
            self.fooled = True
        if self.ruse_left <= 0.0 or target is None or not target.prey:
            self.dispel()
        if self.vanishing:
            self.vanish = min(1.0, self.vanish + dt / VANISH_TIME)

    def dispel(self) -> None:
        """An illusion starts to vanish (it can't be seen or hit from now on)."""
        if self.illusion:
            self.vanishing = True
        elif self.ghost is not None:
            self.ghost.dispel()

    def ripple(self, point: Vec2) -> None:
        """An attack passes through the illusion."""
        self.shimmer = 1.0
        self.shimmer_at = point - self.look_center

    def _watch(self, dt: float) -> None:
        """Under attack: hit, or someone close by swinging, shooting or casting at it."""
        self.harried -= dt
        self._ignored_foes = {s: t - dt for s, t in self._ignored_foes.items() if t > dt}
        if self.damage > self._hurt_seen:
            self._hurt_seen, self.harried = self.damage, CALM_TIME
            return
        for stickman in self.world.stickmen:
            weapon = stickman.weapon
            if (
                stickman.prey
                and stickman.foe is self
                and weapon is not None
                and weapon.busy
                and stickman.center().distance_to(self.body) <= THREAT_REACH
            ):
                self.harried = CALM_TIME
                return

    # ----- deciding where to go ------------------------------------------------

    def _think(self, dt: float) -> None:
        if self.illusion:
            self._haunt(dt)
            return
        if self.frenzy_left > 0.0:
            self._frenzy(dt)
            return
        if self._seize():
            return
        foe = self._choose_foe()
        if foe is not None:
            self._fight(dt, foe)
            return
        if self.intent is Intent.FIGHT:
            self.intent = Intent.WANDER
            self.foe = None
            self._drop_goal()
        target = self.target
        distance = target.center().distance_to(self.body) if target is not None else math.inf
        engaged = distance <= NOTICE_RANGE and self.retreat_left <= 0.0
        if self.intent is Intent.RETREAT and self.retreat_left <= 0.0:
            self.intent = Intent.WANDER
        if target is not None and engaged and self.intent is not Intent.RETREAT:
            self._stalk(dt, target, distance)
        else:
            if self.intent is Intent.STALK:
                self.intent = Intent.WANDER
                self._drop_goal()
            self._wander(dt)
        self._check_stuck(dt)

    def _stalk(self, dt: float, target: Stickman, distance: float) -> None:
        self.intent = Intent.STALK
        self.gait = "stalk" if distance <= STALK_CLOSE else "prowl"
        if distance < POUNCE_MIN:
            self._retreat(target)
            return
        calm = self.harried <= 0.0
        if self.ghost is None and self.ruse_wait <= 0.0 and calm and self._split(target):
            return
        ruse = self.ghost is not None and self.ghost.feinting and self.ghost.target is target
        ready = self._drawn(target, distance)
        if distance <= (RUSE_CREEP if ruse else HOLD_BACK):
            self.gait = "stalk"
            if self.follower is not None and self.follower.route is not None:
                self._drop_goal()
            self._face(target.center())
            return
        self._replan_wait -= dt
        if self._replan_wait > 0.0:
            return
        self._replan_wait = REPLAN_EVERY
        self.goal = target.contact()
        if self._route_to(self.goal):
            self.hunt.reached()
            if self.follower is not None and self.follower.route is None:
                self._face(target.center())
            return
        self.goal = None
        self.hunt.unreachable(REPLAN_EVERY, 2.0)
        if ready and self.leap_wait <= 0.0 and distance <= LEAP_RANGE and self._pounce(target):
            return
        if ruse:
            self._face(target.center())
            return
        self._retreat(target)

    def _retreat(self, target: Stickman) -> None:
        """Slink off a way from `target` (leaping if it can), then stalk him again."""
        self.intent = Intent.RETREAT
        self.retreat_left = RETREAT_TIME
        self._drop_goal()
        low, high = RETREAT_DISTANCE
        here = target.center()
        for _ in range(16):
            anchor = self._random_anchor()
            if anchor is None or not low <= anchor.point.distance_to(here) <= high:
                continue
            if self.leap_wait <= 0.0 and self.world.random.random() < 0.5:
                if self._try_leap(anchor, "leap"):
                    return
            if self._route_to(anchor.point, max_time=10.0):
                self.goal = anchor.point
                return

    def _seize(self) -> bool:
        """Pounce on its quarry the moment its illusion has drawn him (even with others
        at it)."""
        target = self.target
        if target is None or self.leap_wait > 0.0:
            return False
        distance = target.center().distance_to(self.body)
        if not POUNCE_MIN <= distance <= POUNCE_RANGE or not self._drawn(target, distance):
            return False
        return self._pounce(target)

    # ----- the frenzy after a pounce -------------------------------------------

    def _frenzy(self, dt: float) -> None:
        """Chain quick pounces on whoever's within `FRENZY_RANGE`, nearest first, and
        claw and stab anyone too close for one."""
        self.intent = Intent.FIGHT
        near = sorted(
            (s.center().distance_to(self.body), i, s)
            for i, s in enumerate(self.world.stickmen)
            if s.prey
        )
        if self.frenzy_pounces < FRENZY_POUNCES and self.frenzy_wait <= 0.0:
            for distance, _, prey in near:
                if distance > FRENZY_RANGE:
                    break
                if distance >= POUNCE_MIN and self._pounce(prey, "frenzy"):
                    self.frenzy_pounces += 1
                    self.frenzy_wait = FRENZY_EVERY
                    return
        close = [s for distance, _, s in near if distance <= CLOSE_RANGE]
        if close:
            self._fight(dt, self.foe if self.foe in close else close[0])
            return
        spent = self.frenzy_pounces >= FRENZY_POUNCES
        if spent or not near or near[0][0] > FRENZY_RANGE:
            self._calm_down()
            return
        self._face(near[0][2].center())

    def _start_frenzy(self) -> None:
        self.frenzy_left, self.frenzy_time = FRENZY_TIME, 0.0
        self.frenzy_pounces, self.frenzy_wait = 0, 0.0

    def _frenzy_kill(self) -> None:
        self.frenzy_left = min(self.frenzy_left + FRENZY_KILL, FRENZY_MAX - self.frenzy_time)

    def _calm_down(self) -> None:
        """Out of its frenzy, back to its usual ways (and its usual pounce cooldown)."""
        self.frenzy_left = 0.0
        self.leap_wait = max(self.leap_wait, POUNCE_COOLDOWN)

    def _choose_foe(self) -> Stickman | None:
        """Who to fight: under attack, the nearest adventurer it notices; otherwise only
        one who's come within `CLOSE_RANGE`. It sticks with the foe it has (see
        `FOE_COMMIT`, `FOE_SWITCH`, `FIGHT_KEEP`)."""
        reach = NOTICE_RANGE if self.harried > 0.0 else CLOSE_RANGE
        foes = [
            (s.center().distance_to(self.body), i, s)
            for i, s in enumerate(self.world.stickmen)
            if s.prey and s not in self._ignored_foes
        ]
        nearest = min(((d, i, s) for d, i, s in foes if d <= reach), default=None)
        current = self.foe
        held = next((d for d, _, s in foes if s is current), None)
        if self.intent is not Intent.FIGHT or held is None or held > reach + FIGHT_KEEP:
            return None if nearest is None else nearest[2]
        if nearest is None or nearest[2] is current:
            return current
        settled = self.time - self._foe_since >= FOE_COMMIT
        if nearest[0] < FOE_SWITCH * held or (settled and nearest[0] < held - FACE_MARGIN):
            return nearest[2]
        return current

    def _fight(self, dt: float, foe: Stickman) -> None:
        """Close in on `foe` to a stand-off spot (`_stand_off`), clawing and stabbing him
        by turns (`_melee`)."""
        fresh = foe is not self.foe
        if fresh:
            self.foe, self._foe_stuck, self._replan_wait = foe, 0.0, 0.0
            self._foe_since, self._foe_goal = self.time, None
        self.intent = Intent.FIGHT
        here = foe.center()
        self._face(here, force=fresh)
        spot = self._stand_off(foe)
        on_top = self.body.distance_to(here) < OVERLAP
        # On top of him it backs off to stand off before it attacks (if it can).
        if self.melee_wait <= 0.0 and (not on_top or spot is None) and self._melee(foe):
            return
        follower = self.follower
        assert follower is not None
        goal = spot.point if spot is not None else foe.contact()
        there = follower.contact().distance_to(goal) <= ARRIVED * 2.0
        if not on_top and (there or self._claw_reaches(foe)):
            # Where it wants to be: stand and face him till its next attack is ready.
            if follower.route is not None:
                self._drop_goal()
            self._foe_goal = None
            return
        if self._turn_left() > 0.15:
            return
        self._replan_wait -= dt
        if self._replan_wait > 0.0:
            return
        self._replan_wait = FIGHT_REPLAN
        self.gait = "lope" if self.body.distance_to(here) > 160.0 else "prowl"
        aimed = self._foe_goal
        if (
            follower.route is not None
            and aimed is not None
            and goal.distance_to(aimed) <= FOE_SHIFT
        ):
            return
        if self._route_to(goal):
            self._foe_stuck, self._foe_goal = 0.0, goal
            return
        self._foe_stuck += FIGHT_REPLAN
        if self._foe_stuck >= FIGHT_GIVE_UP:
            self._ignored_foes[foe] = IGNORE_FOE
            self.foe = None

    def _stand_off(self, foe: Stickman) -> Anchor | None:
        """Where to fight `foe` from: `STAND_OFF` short of him along his surface on its
        side of him, or (a wall in the way) on the wall `WALL_PERCH` above his feet, or
        on his other side."""
        anchor = self.planner.anchor_near(foe.contact(), 40.0)
        if anchor is None:
            return None
        surface = anchor.surface
        side = 1.0 if surface.coord(self.body) >= surface.coord(anchor.point) else -1.0
        spot = self._beside(foe, side, STAND_OFF)
        if spot is not None:
            return spot
        perch = foe.contact() + surface.normal * WALL_PERCH
        walls = [
            (wall.closest_point(perch), wall)
            for wall in self.planner.surfaces
            if wall.normal.dot(surface.normal) < 0.5
        ]
        near = min(walls, key=lambda w: w[0].distance_to(perch), default=None)
        if near is not None and near[0].distance_to(perch) <= 20.0:
            return Anchor(near[1], near[0])
        return self._beside(foe, -side, STAND_OFF)

    # ----- up close: claw swipes and tentacle stabs, by turns -------------------

    def _melee(self, foe: Stickman) -> bool:
        """Claw `foe`, or stab him, whichever's turn it is (stabbing instead of a claw
        swipe that wouldn't reach him)."""
        claw = self._claw_reaches(foe)
        stab = self._stab_reaches(foe)
        if claw and (self.next_melee == "claw" or not stab):
            self._start_attack("claw")
        elif stab:
            self._stab_foe = foe
            self._aim_stab(foe)
            self._start_attack("stab")
        else:
            return False
        return True

    def _claw_reaches(self, foe: Stickman) -> bool:
        """Whether a claw swipe started now would rake through `foe`."""
        if self._turn_left() > 0.15:
            return False
        wind, strike, _ = CLAW_TIMES
        return any(
            foe.hits(self.to_world(self.paw_at(wind + strike * i / 4)), CLAW_GRAB) for i in range(5)
        )

    def _stab_reaches(self, foe: Stickman) -> bool:
        return self.to_world(SHOULDER).distance_to(foe.center()) <= STAB_REACH

    def _aim_stab(self, foe: Stickman) -> None:
        offset = foe.center() - self.to_world(SHOULDER)
        if offset.length() > 1e-6:
            self.stab_way = offset.normalized()
        self.stab_span = min(STAB_REACH, offset.length() + STAB_PAST)

    def _start_attack(self, kind: str) -> None:
        self.attack, self.attack_time = kind, 0.0
        self._struck = set()
        self.melee_wait = MELEE_COOLDOWN
        self.next_melee = "claw" if kind == "stab" else "stab"
        follower = self.follower
        if follower is not None and not follower.in_transition:
            follower.reset(follower.current_anchor())

    def _swing(self, dt: float) -> None:
        """Carry on with its attack, hurting whoever the paw or the tentacles go through."""
        kind = self.attack
        assert kind is not None
        wind, strike, recover = STAB_TIMES if kind == "stab" else CLAW_TIMES
        before = self.attack_time
        self.attack_time += dt
        foe = self._stab_foe
        if kind == "stab" and self.attack_time < wind and foe is not None and foe.prey:
            self._aim_stab(foe)
        start, end = max(before, wind), min(self.attack_time, wind + strike)
        if end > start:
            samples = 4
            for i in range(1, samples + 1):
                self._strike(kind, start + (end - start) * i / samples)
        if self.attack_time >= wind + strike + recover:
            self.attack = None

    def _strike(self, kind: str, t: float) -> None:
        if kind == "stab":
            root = self.to_world(SHOULDER)
            way, length = self.stab_at(t)
            points = [root + way * (length * f) for f in (0.5, 0.75, 1.0)]
            most, margin, damage = STAB_HITS, STAB_MARGIN, STAB_DAMAGE
            shove_of = way * STAB_PUSH
            death = "Speared by a displacer beast's tentacle!"
        else:
            points = [self.to_world(self.paw_at(t))]
            most, margin, damage = 1, CLAW_GRAB, CLAW_DAMAGE
            forward = along(self.up) * float(self.heading)
            shove_of = forward * CLAW_PUSH + self.up * (CLAW_PUSH * 0.4)
            death = "Raked by displacer beast claws!"
        for stickman in self.world.stickmen:
            if len(self._struck) >= most:
                return
            if not stickman.prey or stickman in self._struck:
                continue
            hit = next((p for p in points if stickman.hits(p, margin)), None)
            if hit is None:
                continue
            self._struck.add(stickman)
            stickman.hurt_from(self, damage, hit, shove_of, "displacer", death)

    def stab_at(self, t: float) -> tuple[Vec2, float]:
        """Which way (in the world) its tentacles spear from the shoulder and how far,
        `t` into a stab: drawn back, thrust out to `stab_span`, back to rest."""
        wind, strike, recover = STAB_TIMES
        rest, drawn = TENTACLE_REST * 0.7, TENTACLE_REST * 0.35
        if t < wind:
            return self.stab_way, rest + (drawn - rest) * smoothstep(t / wind)
        if t < wind + strike:
            u = (t - wind) / strike
            return self.stab_way, drawn + (self.stab_span - drawn) * (1.0 - (1.0 - u) ** 2)
        u = smoothstep(min(1.0, (t - wind - strike) / recover))
        return self.stab_way, self.stab_span + (rest - self.stab_span) * u

    def paw_at(self, t: float) -> Vec2:
        """Its raking front paw (on its straight body), `t` into a claw swipe."""
        wind, strike, recover = CLAW_TIMES
        if t < wind:
            return PAW_REST.lerp(PAW_RAISED, smoothstep(t / wind))
        if t < wind + strike:
            return PAW_RAISED.lerp(PAW_RAKE, smoothstep((t - wind) / strike))
        return PAW_RAKE.lerp(PAW_REST, smoothstep(min(1.0, (t - wind - strike) / recover)))

    @property
    def attack_weight(self) -> float:
        """How far into its attack pose it is: easing in and back out."""
        if self.attack is None:
            return 0.0
        total = sum(STAB_TIMES if self.attack == "stab" else CLAW_TIMES)
        t = self.attack_time
        return clamp(min(t / 0.06, (total - t) / 0.12), 0.0, 1.0)

    # ----- the ruse: its illusion feints at its quarry from both sides -------------

    def _split(self, target: Stickman) -> bool:
        """Send its illusion out after `target`, peeling off from where it stands."""
        follower = self.follower
        if follower is None or follower.in_transition:
            return False
        ghost = Displacer(self.world, follower.current_anchor(), self.heading, owner=self)
        ghost.target = target
        ghost.time = self.time + 3.7
        ghost.head_yaw, ghost.tail_yaw = self.head_yaw, self.tail_yaw
        ghost.look_up, ghost.low = self.look_up, self.low
        ghost.leap_wait = 0.0
        self.ghost = ghost
        return True

    def _drawn(self, target: Stickman, distance: float) -> bool:
        """Whether it may pounce on `target`: its illusion has his attention (or he was
        fighting the illusion as it vanished)."""
        ghost = self.ghost
        if ghost is not None and ghost.target is target and ghost.feinting:
            if self._distracted(target):
                return True
        if self.fair is target and self.fair_left > 0.0:
            return True
        return False

    def _distracted(self, target: Stickman) -> bool:
        """Whether `target` is taken up with its illusion: going for it once it's feinted
        at him (or swinging at it), or, on his feet, turned away from the real beast."""
        ghost = self.ghost
        if ghost is None:
            return True
        weapon = target.weapon
        busy = weapon is not None and weapon.busy
        if target.foe is ghost and (ghost.feints >= 1 or busy):
            return True
        anchor = self.planner.anchor_near(target.contact(), 40.0)
        if anchor is not None and not anchor.surface.walkable:
            # On a wall or underside he faces his surface, whatever he's looking at.
            return False
        middle = target.center().x
        toward = 1 if self.body.x >= middle else -1
        ghost_side = 1 if ghost.body.x >= middle else -1
        return target.facing != toward and (ghost_side != toward or ghost.feints >= 1)

    def _haunt(self, dt: float) -> None:
        """The illusion's script: pounce at its quarry (a swipe, no harm done), leap over
        to his other side, turn, and pounce again, till its ruse runs out."""
        target = self.target
        follower = self.follower
        if target is None or self.vanishing or follower is None:
            return
        self.act_left -= dt
        if self.act in ("strike", "turn"):
            self._face(target.center(), force=self.act == "turn")
            if self.act_left > 0.0:
                return
            if self.act == "strike":
                self._cross(target)
            else:
                self.act = "out"
            return
        if self.act == "run":
            if follower.route is None:
                self.act, self.act_left = "turn", FEINT_TURN
            return
        self.act = "out"
        distance = target.center().distance_to(self.body)
        if distance < POUNCE_MIN:
            self._cross(target)
            return
        if distance <= POUNCE_RANGE and self._feint(target):
            return
        self._replan_wait -= dt
        if self._replan_wait > 0.0:
            return
        self._replan_wait = REPLAN_EVERY
        self.gait = "lope"
        if not self._route_to(target.contact()):
            self.dispel()

    def _feint(self, target: Stickman) -> bool:
        anchor = self.planner.anchor_near(target.contact(), 40.0)
        if anchor is None:
            return False
        surface = anchor.surface
        self.side = 1.0 if surface.coord(self.body) >= surface.coord(anchor.point) else -1.0
        aimed = self._beside(target, self.side, FEINT_BESIDE)
        return aimed is not None and self._try_leap(aimed, "pounce")

    def _cross(self, target: Stickman) -> None:
        """Over to its quarry's other side: a leap, or a run if it can't leap there."""
        anchor = self._beside(target, -self.side, FEINT_CROSS)
        if anchor is not None and self._try_leap(anchor, "vault"):
            self.side, self.act = -self.side, "cross"
            return
        if anchor is not None and self._route_to(anchor.point, max_time=4.0):
            self.side, self.act, self.gait = -self.side, "run", "lope"
            return
        self.act = "out"

    def _landed(self, kind: str, leap: Leap | None) -> None:
        if kind in POUNCES:
            self.strike = 1.0
        if not self.illusion:
            if kind == "pounce" and not self.dead:
                self.dispel()
                self._start_frenzy()
                if leap is not None and leap.killed:
                    self._frenzy_kill()
            return
        if kind == "pounce":
            self.feints += 1
            self.act, self.act_left = "strike", FEINT_HOLD
        elif self.act == "cross":
            self.act, self.act_left = "turn", FEINT_TURN
        else:
            self.act = "out"

    def _maul(self, leap: Leap) -> None:
        """A pounce reaching its quarry mauls him (once)."""
        quarry = leap.quarry
        if leap.struck or quarry is None or not quarry.prey:
            return
        middle = quarry.center()
        reach = min(
            self.body.distance_to(middle), self.to_world(Vec2(HEAD_REACH, -3.0)).distance_to(middle)
        )
        if reach > POUNCE_HIT:
            return
        leap.struck = True
        push = self.velocity.normalized() * POUNCE_PUSH + Vec2(0.0, -120.0)
        death = (
            "Mauled by a frenzied displacer beast!"
            if leap.kind == "frenzy"
            else "Mauled by the displacer beast!"
        )
        leap.killed = quarry.hurt_from(self, POUNCE_DAMAGE, middle, push, "displacer", death)
        if leap.killed and leap.kind == "frenzy" and self.frenzy_left > 0.0:
            self._frenzy_kill()

    def _wander(self, dt: float) -> None:
        follower = self.follower
        assert follower is not None
        if self.goal is not None:
            if follower.route is None:
                if follower.current_anchor().point.distance_to(self._goal_point()) <= ARRIVED:
                    self._arrive()
                    return
                self._replan_wait -= dt
                if self._replan_wait <= 0.0:
                    self._replan_wait = REPLAN_EVERY
                    if not self._route_to(self.goal):
                        self._arrive()
            return
        if self.rest > 0.0:
            self.rest -= dt
            return
        self._pick_goal()

    def _arrive(self) -> None:
        self.goal = None
        self.rest = self.world.random.uniform(*REST_TIME)
        if self.intent is Intent.RETREAT and self.retreat_left <= 0.0:
            self.intent = Intent.WANDER

    def _goal_point(self) -> Vec2:
        assert self.goal is not None
        anchor = self.planner.anchor_near(self.goal, GOAL_SNAP)
        return anchor.point if anchor is not None else self.goal

    def _pick_goal(self) -> None:
        random = self.world.random
        if self.leap_wait <= 0.0 and random.random() < LEAP_CHANCE and self._leap_somewhere():
            return
        for _ in range(10):
            anchor = self._random_anchor()
            if anchor is None:
                return
            if anchor.point.distance_to(self.position) < 40.0:
                continue
            if self._route_to(anchor.point, max_time=30.0):
                self.goal = anchor.point
                self.gait = "prowl"
                return
        self.rest = 0.5

    def _leap_somewhere(self) -> bool:
        """A leap to a spot on another window (or the floor) within range."""
        here = self.support
        for _ in range(24):
            anchor = self._random_anchor()
            if anchor is None or here is None:
                return False
            if anchor.surface.box == here.box and anchor.surface.box is not None:
                continue
            if not LEAP_MIN <= anchor.point.distance_to(self.position) <= LEAP_RANGE:
                continue
            if self._try_leap(anchor, "leap"):
                return True
        return False

    def _random_anchor(self) -> Anchor | None:
        surfaces = [s for s in self.planner.surfaces if s.length >= 8.0]
        if not surfaces:
            return None
        random = self.world.random
        weights = [math.sqrt(s.length) * (1.0 if s.walkable else 1.4) for s in surfaces]
        surface = random.choices(surfaces, weights=weights)[0]
        inset = min(10.0, surface.length * 0.5)
        return Anchor(
            surface, surface.point_at(random.uniform(surface.low + inset, surface.high - inset))
        )

    def _route_to(self, point: Vec2, max_time: float = math.inf) -> bool:
        follower = self.follower
        if follower is None or follower.in_transition:
            return False
        goal = self.planner.anchor_near(point, GOAL_SNAP)
        if goal is None:
            return False
        start = follower.current_anchor()
        if goal.surface is start.surface and goal.point.distance_to(start.point) < 2.0:
            follower.reset(start)
            return True
        route = self.planner.plan(start, goal)
        if route is None or route.duration > max_time:
            return False
        follower.reset(start)
        follower.set_route(route)
        return True

    def _drop_goal(self) -> None:
        self.goal = None
        if self.follower is not None and not self.follower.in_transition:
            self.follower.reset(self.follower.current_anchor())

    def _check_stuck(self, dt: float) -> None:
        if self.goal is None or self.speed > 2.0:
            self._still = 0.0
            return
        self._still += dt
        if self._still >= STUCK_TIME:
            self._still = 0.0
            self._drop_goal()
            self.rest = 0.3

    def _face(self, point: Vec2, force: bool = False) -> None:
        """Turn to face `point` if it's behind it (well behind, and not just after a
        turn, unless `force`d)."""
        ahead = (point - self.body).dot(along(self.up))
        if force and abs(ahead) > 2.0:
            self._set_heading(1 if ahead > 0 else -1)
        elif abs(ahead) > FACE_MARGIN and self.turn_wait <= 0.0:
            self._set_heading(1 if ahead > 0 else -1)

    def _set_heading(self, heading: int) -> None:
        if heading != self.heading:
            self.heading = heading
            self.turn_wait = TURN_COOLDOWN

    def _turn_left(self) -> float:
        """How much of its turn it has yet to make (0 to 1, by its middle)."""
        target = 0.0 if self.heading > 0 else math.pi
        return abs(0.5 * (self.head_yaw + self.tail_yaw) - target) / math.pi

    # ----- leaps -----------------------------------------------------------------

    def _pounce(self, target: Stickman, kind: str = "pounce") -> bool:
        """Crouch for a leap that lands right on `target`."""
        anchor = self._beside(target)
        if anchor is None or self._arc(self.body, anchor, least=_least(kind)) is None:
            return False
        self._crouch(Leap(anchor, kind, target))
        return True

    def _beside(self, target: Stickman, side: float = 0.0, gap: float = 0.0) -> Anchor | None:
        """Where `target` stands, or `gap` along his surface from it toward `side`
        (None if his surface doesn't run on that far)."""
        anchor = self.planner.anchor_near(target.contact(), 40.0)
        if anchor is None or gap <= 0.0:
            return anchor
        surface = anchor.surface
        here = surface.coord(anchor.point)
        coord = clamp(here + side * gap, surface.low, surface.high)
        if abs(coord - here) < min(gap, 25.0) - 1e-6:
            return None
        return Anchor(surface, surface.point_at(coord))

    def _aim(self, target: Stickman) -> Anchor | None:
        """Where a pounce at `target` lands: on him, or (an illusion's feint) just short
        of him."""
        if self.illusion:
            return self._beside(target, self.side, FEINT_BESIDE)
        return self._beside(target)

    def _try_leap(self, anchor: Anchor, kind: str) -> bool:
        if self._arc(self.body, anchor, least=_least(kind)) is None:
            return False
        self._crouch(Leap(anchor, kind))
        return True

    def _crouch(self, leap: Leap) -> None:
        self.pending = leap
        self.crouch_left = CROUCH_TIME[leap.kind]
        self.goal = None if leap.kind != "hop" else self.goal
        follower = self.follower
        if follower is not None:
            follower.reset(follower.current_anchor())
            self._settle()
        self._face(leap.target.point + leap.target.surface.normal * BODY_HEIGHT, force=True)

    def _crouching(self, dt: float) -> None:
        leap = self.pending
        assert leap is not None
        self.crouch_left -= dt
        if self.crouch_left > 0.0:
            return
        self.pending = None
        quarry = self.target if self.illusion else leap.quarry
        if leap.kind in POUNCES and quarry is not None and quarry.prey:
            aimed = self._aim(quarry)
            if aimed is not None and self._arc(self.body, aimed) is not None:
                leap.target = aimed
        if not self.planner.owns(leap.target.surface):
            return
        arc = self._arc(self.body, leap.target, least=_least(leap.kind))
        if arc is None:
            if leap.kind != "hop":
                return
            arc = self._arc(self.body, leap.target, check=False)
            if arc is None:
                return
        self._launch(leap, *arc)

    def _launch(self, leap: Leap, velocity: Vec2, time: float) -> None:
        leap.start = self.body
        leap.velocity = velocity
        leap.time = time
        leap.elapsed = 0.0
        self.leap = leap
        self.follower = None
        self.velocity = velocity
        if abs(velocity.x) > 20.0:
            self._set_heading(1 if velocity.x > 0 else -1)
        if leap.kind in POUNCES:
            self.leap_wait = POUNCE_COOLDOWN
            if self.illusion:
                leap.quarry = None
        elif leap.kind == "leap":
            self.leap_wait = LEAP_COOLDOWN

    def _hop(self, step: RouteStep) -> None:
        """A planned jump or drop, done as a short leap."""
        follower = self.follower
        assert follower is not None
        start = Anchor(step.from_surface, step.start)
        follower.reset(start)
        self._settle()
        self._crouch(Leap(Anchor(step.surface, step.end), "hop"))

    def _arc(
        self, start: Vec2, anchor: Anchor, check: bool = True, least: float = 0.0
    ) -> tuple[Vec2, float] | None:
        """Launch velocity and flight time for a ballistic arc of the body center from
        `start` to standing on `anchor`, clear of every window, or None."""
        end = anchor.point + anchor.surface.normal * BODY_HEIGHT
        offset = end - start
        distance = offset.length()
        if distance < 1.0:
            return None
        base = max(least, clamp(0.22 + distance / LEAP_PACE, 0.28, 0.85))
        surface = anchor.surface
        for scale in (1.0, 0.8, 1.25, 1.55, 0.65, 1.9):
            time = base * scale
            velocity = Vec2(offset.x / time, (offset.y - 0.5 * GRAVITY * time * time) / time)
            if velocity.length() > MAX_LEAP_SPEED:
                continue
            arriving = velocity.y + GRAVITY * time
            if surface.walkable and arriving < 60.0:
                continue
            if surface.hanging and arriving > 120.0:
                continue
            if not check or self._clear(start, velocity, time):
                return velocity, time
        return None

    def _clear(self, start: Vec2, velocity: Vec2, time: float) -> bool:
        world = self.world
        boxes = [_grown(box, BODY_CLEARANCE) for box in world.boxes]
        count = max(8, int(velocity.length() * time / 8.0))
        for i in range(1, count):
            t = time * i / count
            body = start + velocity * t + Vec2(0.0, 0.5 * GRAVITY * t * t)
            if not world.left <= body.x <= world.width:
                return False
            if world.ceiling is not None and body.y < world.ceiling + BODY_HEIGHT * 0.5:
                return False
            if body.y > world.floor_y - BODY_HEIGHT * 0.5:
                return False
            if any(box.contains(body) for box in boxes):
                return False
            feet = body + Vec2(0.0, BODY_HEIGHT)
            if i < count - 1 and any(box.contains(feet) for box in world.boxes):
                return False
        return True

    # ----- on a surface ----------------------------------------------------------

    def _crawl(self, dt: float) -> None:
        follower = self.follower
        assert follower is not None
        step = follower.step
        if step is not None and step.move in HOPS:
            self._hop(step)
            return
        if self._turning_about():
            self.phase += TURN_SHUFFLE * dt / self.cycle()
            self.speed = _ease(self.speed, TURN_SHUFFLE, 12.0, dt)
            return
        surface = step.surface if step is not None else follower.current_anchor().surface
        move = _along_move(surface)
        self.pace = _ease(
            self.pace, self.gaits[self._gait()][move] / self._planned_speed(move), ACCELERATION, dt
        )
        before = self.body
        self._advance(self.pace * self._planned_speed(move) * dt)
        moved = self.body.distance_to(before)
        self.phase += moved / self.cycle()
        self.speed = _ease(self.speed, moved / dt, 12.0, dt)
        if self.intent is Intent.STALK and follower.route is None and self.target is not None:
            self._face(self.target.center())

    def _turning_about(self) -> bool:
        """Turn round first if its route heads back the way it's facing (a short last
        step back it just takes backward); True while it's still turning."""
        follower = self.follower
        assert follower is not None
        step = follower.step
        if step is not None and step.move in ALONG_MOVES and follower.route is not None:
            ahead = (step.end - step.start).dot(along(step.surface.normal))
            way = 1 if ahead > 0 else -1
            last = follower.index == len(follower.route.steps) - 1
            short = follower.contact().distance_to(step.end) < TURN_MIN
            if abs(ahead) > 1e-6 and way != self.heading and not (last and short):
                if self.turn_wait > 0.0:
                    return True
                self._set_heading(way)
        return self._turn_left() > 1.0 - TURN_SET_OFF

    def _advance(self, distance: float) -> None:
        """Along its route until its body has gone `distance` (so it doesn't stall where
        its feet move but its body can't, like pivoting in an inside corner)."""
        follower = self.follower
        assert follower is not None
        left = distance
        budget = ADVANCE_BUDGET
        wait: float | None = None
        for _ in range(10):
            step = follower.step
            if step is None or left <= 0.05 or budget <= 1e-6:
                return
            rate = _body_rate(step)
            wait = min(left / rate if wait is None else wait, budget)
            before = self.body
            follower.update(wait)
            budget -= wait
            step = follower.step
            if step is not None and step.move in HOPS:
                self._hop(step)
                return
            self._settle()
            gained = self.body.distance_to(before)
            left -= gained
            wait = left / rate if gained > 0.25 * wait * rate else wait * 2.0

    def _gait(self) -> str:
        if self.intent in (Intent.STALK, Intent.FIGHT) or self.illusion:
            return self.gait
        return "lope" if self._remaining() > LOPE_DISTANCE else "prowl"

    def _remaining(self) -> float:
        follower = self.follower
        if follower is None:
            return 0.0
        total = 0.0
        for step in follower.remaining_steps():
            total += step.start.distance_to(step.end)
        return (
            total - follower.contact().distance_to(follower.step.start) if follower.step else total
        )

    def _planned_speed(self, move: Move) -> float:
        if move is Move.WALK:
            return MOVES.walk_speed
        if move is Move.CLIMB:
            return MOVES.climb_speed
        return MOVES.hang_speed

    def cycle(self) -> float:
        stride = CYCLE["stalk"] + (CYCLE["prowl"] - CYCLE["stalk"]) * (1.0 - self.low)
        return stride + (CYCLE["lope"] - stride) * self.lope

    def _settle(self) -> None:
        """Feet and up from its route: along a surface, on it; round a corner, an eased
        roll from one surface onto the next."""
        follower = self.follower
        assert follower is not None
        step = follower.step
        if step is None or step.move in ALONG_MOVES or step.move in HOPS:
            anchor = follower.current_anchor()
            self.position, self.up = anchor.point, anchor.surface.normal
        else:
            t = 1.0 if step.duration <= 0.0 else clamp(follower.elapsed / step.duration, 0.0, 1.0)
            ease = smoothstep(t)
            self.position = step.start.lerp(step.end, ease)
            up = step.from_surface.normal.lerp(step.surface.normal, ease)
            if up.length() < 0.3:
                up = step.from_surface.normal if t < 0.5 else step.surface.normal
            self.up = up.normalized()
        self.body = self._offset(self.position + self.up * BODY_HEIGHT)

    def _attach(self, anchor: Anchor) -> None:
        self.follower = RouteFollower(anchor)
        self.velocity = ZERO
        self._replan_wait = 0.0
        self._settle()

    def _land(self, anchor: Anchor, kind: str, slide: float = SLIDE_MAX) -> None:
        seen = self.look_center
        velocity = self.velocity
        leap, self.leap = self.leap, None
        self._attach(anchor)
        self.slide = self._capped(seen - self.body, slide)
        self.land_time = self.land_left = LAND_TIME[kind]
        self.impact = clamp(velocity.length() / 700.0, 0.3, 1.0)
        self.pace = 0.6
        ahead = velocity.dot(along(self.up))
        if abs(ahead) > 20.0:
            self._set_heading(1 if ahead > 0 else -1)
        self.turn_wait = 0.0
        self._landed(kind, leap)

    def _loose(self) -> None:
        """Off its surface and into a fall, the body where it was."""
        self.follower = None
        self.leap = None
        self.pending = None
        self.attack = None
        self.velocity = ZERO

    @staticmethod
    def _capped(offset: Vec2, most: float = SLIDE_MAX) -> Vec2:
        return offset if offset.length() <= most else ZERO

    # ----- in the air ----------------------------------------------------------

    def _fly(self, dt: float, alive: bool) -> None:
        leap = self.leap
        if leap is not None:
            leap.elapsed += dt
            t = min(leap.elapsed, leap.time)
            body = leap.start + leap.velocity * t + Vec2(0.0, 0.5 * GRAVITY * t * t)
            velocity = leap.velocity + Vec2(0.0, GRAVITY * t)
            if leap.elapsed >= leap.time and self.planner.owns(leap.target.surface):
                self.velocity = velocity
                self.body = body
                self._maul(leap)
                self._land(leap.target, leap.kind)
                return
            blocked = any(box.contains(body) for box in self.world.boxes)
            if leap.elapsed < leap.time and not blocked:
                self.body, self.velocity = body, velocity
                self._maul(leap)
                return
            self.leap = None
        self._fall(dt, alive)

    def _fall(self, dt: float, alive: bool) -> None:
        """Free fall: land on a top or the floor, or (alive) cling to a window it hits."""
        world = self.world
        before = self.body
        self.velocity += Vec2(0.0, GRAVITY * dt)
        after = before + self.velocity * dt
        low, high = world.left + BODY_HEIGHT, world.width - BODY_HEIGHT
        if not low <= after.x <= high:
            after = Vec2(clamp(after.x, low, high), after.y)
            self.velocity = Vec2(0.0, self.velocity.y)
        if world.ceiling is not None and after.y < world.ceiling + BODY_HEIGHT:
            after = Vec2(after.x, world.ceiling + BODY_HEIGHT)
            self.velocity = Vec2(self.velocity.x, max(0.0, self.velocity.y))
        feet_before = before + Vec2(0.0, BODY_HEIGHT)
        feet_after = after + Vec2(0.0, BODY_HEIGHT)
        if self.velocity.y >= 0.0:
            crossed = [
                s
                for s in self.planner.surfaces
                if s.walkable
                and s.low - 1.0 <= after.x <= s.high + 1.0
                and feet_before.y <= s.start.y + 0.5
                and feet_after.y >= s.start.y
            ]
            if crossed:
                surface = min(crossed, key=lambda s: s.start.y)
                self.body = after
                self._land(Anchor(surface, surface.closest_point(Vec2(after.x, 0.0))), "fall")
                return
        for box in world.boxes:
            entering = box.contains(after) or box.contains(feet_after)
            if not entering or box.contains(before):
                continue
            if alive:
                anchor = self.planner.anchor_near(after, CLING_REACH)
                if anchor is not None and anchor.surface.box is not None:
                    self.body = after
                    self._land(anchor, "fall")
                    return
            if before.y >= box.bottom:
                after = Vec2(after.x, box.bottom + BODY_HEIGHT)
                self.velocity = Vec2(self.velocity.x, max(0.0, self.velocity.y))
            else:
                after = Vec2(before.x, after.y)
                self.velocity = Vec2(0.0, self.velocity.y)
        if feet_after.y >= world.floor_y:
            floor = [
                s
                for s in self.planner.surfaces
                if s.walkable and abs(s.start.y - world.floor_y) < 0.5
            ]
            if floor:
                nearest_floor = min(
                    floor, key=lambda s: abs(clamp(after.x, s.low, s.high) - after.x)
                )
                self.body = after
                self._land(
                    Anchor(
                        nearest_floor, nearest_floor.closest_point(Vec2(after.x, world.floor_y))
                    ),
                    "fall",
                )
                return
            after = Vec2(after.x, world.floor_y - BODY_HEIGHT)
        self.body = after

    # ----- animation -------------------------------------------------------------

    def _animate(self, dt: float) -> None:
        if self.follower is not None:
            target_up = self.up
            rate = 16.0
        else:
            target_up = self._flight_up()
            rate = 7.0
        self.look_up = _turn_toward(self.look_up, target_up, 1.0 - math.exp(-rate * dt))
        self.slide = self.slide * math.exp(-dt / SLIDE_TIME)
        self.turn_wait -= dt
        target = 0.0 if self.heading > 0 else math.pi
        spin = math.pi / TURN_TIME * dt
        self.head_yaw += clamp(target - self.head_yaw, -spin, spin)
        lag = self.head_yaw - self.tail_yaw
        if self.head_yaw == target or abs(lag) >= YAW_LAG - 1e-9:
            self.tail_yaw += clamp(target - self.tail_yaw, -spin, spin)
        lag = self.head_yaw - self.tail_yaw
        if abs(lag) > YAW_LAG:
            self.tail_yaw = self.head_yaw - math.copysign(YAW_LAG, lag)
        if self.follower is None:
            self.bend = 0.0
        else:
            self.bend = _ease(self.bend, 1.0, BEND_RATE, dt)
        stalking = self.follower is not None and self._gait() == "stalk" and not self.dead
        loping = self.follower is not None and self._gait() == "lope" and not self.dead
        self.low = _ease(self.low, 1.0 if stalking else 0.0, 4.0, dt)
        self.lope = _ease(self.lope, 1.0 if loping and self.speed > 70.0 else 0.0, 4.0, dt)
        if self.pending is not None:
            total = CROUCH_TIME[self.pending.kind]
            self.crouch = smoothstep(min(1.0, (1.0 - self.crouch_left / total) * 1.6))
        else:
            self.crouch = _ease(self.crouch, 0.0, 14.0, dt)
        if self.follower is None:
            self.speed = _ease(self.speed, 0.0, 6.0, dt)
        if self.pending is not None or self.land_left > 0.0:
            self.speed = _ease(self.speed, 0.0, 20.0, dt)
        lying = self.dead and self.follower is not None
        self.slump = _ease(self.slump, 1.0 if lying else 0.0, 6.0, dt)
        frenzied = self.frenzy_left > 0.0 and not self.dead
        self.fury = _ease(self.fury, 1.0 if frenzied else 0.0, 10.0 if frenzied else 3.0, dt)
        self.strike = 0.0 if self.dead else max(0.0, self.strike - dt / STRIKE_TIME)

    def _flight_up(self) -> Vec2:
        """In the air its body lines up with its flight (within a pitch limit)."""
        if self.dead:
            return UPRIGHT
        velocity = self.velocity
        if velocity.length() < 30.0:
            return UPRIGHT
        way = velocity.normalized()
        h = float(self.heading)
        up = Vec2(h * way.y, -h * way.x)
        pitch = clamp(wrap_angle(up.angle() + math.pi / 2), -1.0, 1.0)
        return Vec2.from_angle(-math.pi / 2 + pitch)

    # ----- terrain -------------------------------------------------------------

    def terrain_changed(self, change: TerrainChange) -> None:
        """Ride the window it's on (or land where its target went); fall if it closes or
        moves out from under it. Knocked into a fall, its illusion vanishes."""
        self._ride(change)
        if self.follower is None and self.leap is None:
            self.dispel()
        if self.ghost is not None:
            self.ghost.terrain_changed(change)

    def _ride(self, change: TerrainChange) -> None:
        seen = self.look_center
        follower = self.follower
        if follower is None:
            if change.shift is not None:
                self.body = self.body + change.shift
            leap = self.leap
            if leap is not None:
                if change.shift is not None:
                    leap.start = leap.start + change.shift
                target = self._moved(leap.target, change)
                if target is None:
                    self.leap = None
                else:
                    leap.target = target
            self._escape()
            return
        pending = self.pending
        step = follower.step
        if step is not None and follower.in_transition:
            if self._carry_transition(step, change):
                self.slide = self._capped(seen + self._carry(step.surface, change) - self.body)
                return
        anchor = follower.current_anchor()
        carry = self._carry(anchor.surface, change)
        moved = self._moved(anchor, change)
        if moved is None:
            self.body = self.body + carry
            self._loose()
            self._escape()
            return
        self._attach(moved)
        self.slide = self._capped(seen + carry - self.body)
        if pending is not None:
            target = self._moved(pending.target, change)
            self.pending = (
                Leap(target, pending.kind, pending.quarry) if target is not None else None
            )

    def _escape(self) -> None:
        """Out of the window that just closed over it, onto the nearest surface."""
        if self.dead or not any(box.contains(self.body) for box in self.world.boxes):
            return
        anchor = self.planner.anchor_near(self.body, ESCAPE_REACH)
        if anchor is not None:
            self._land(anchor, "fall", ESCAPE_REACH)

    def _carry_transition(self, step: RouteStep, change: TerrainChange) -> bool:
        """Keep rolling round the corner it's on, onto the corner's new place."""
        follower = self.follower
        assert follower is not None
        start = self._moved(Anchor(step.from_surface, step.start), change)
        end = self._moved(Anchor(step.surface, step.end), change)
        if start is None or end is None:
            return False
        elapsed = follower.elapsed
        follower.reset(start)
        moved = RouteStep(
            step.move, start.point, end.point, step.duration, end.surface, start.surface
        )
        follower.set_route(Route((moved,)))
        follower.elapsed = elapsed
        self._settle()
        return True

    @staticmethod
    def _carry(surface: Surface, change: TerrainChange) -> Vec2:
        return change.delta_for(surface.box) or ZERO

    def _moved(self, anchor: Anchor, change: TerrainChange) -> Anchor | None:
        """`anchor` on the rebuilt terrain: the same kind of surface of the same window,
        carried along with it, or None if that's gone."""
        box = anchor.surface.box
        if change.removed(box):
            return None
        point = anchor.point + self._carry(anchor.surface, change)
        new_box = change.new_index(box)
        best: Anchor | None = None
        best_distance = 12.0
        for surface in self.planner.surfaces:
            if surface.kind is not anchor.surface.kind or surface.box != new_box:
                continue
            closest = surface.closest_point(point)
            distance = closest.distance_to(point)
            if distance <= best_distance:
                best, best_distance = Anchor(surface, closest), distance
        return best

    # ----- death ---------------------------------------------------------------

    def die(self, point: Vec2, push: Vec2) -> None:
        self.dead = True
        self.down_time = 0.0
        self.frenzy_left = 0.0
        self.goal = None
        self._loose()
        self.velocity = push * 0.3 + Vec2(0.0, -60.0)
        self.dispel()

    def update_dead(self, dt: float) -> None:
        self.down_time += dt
        self.time += dt
        if self.follower is None:
            self._fall(dt, alive=False)
        elif not self.support.walkable:
            self._loose()
        self._animate(dt)
        self._update_ghost(dt)
