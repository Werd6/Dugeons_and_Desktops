"""The desert hydra: a slow, heavy four-legged beast with five heads on long necks that
spit acid, plodding along window tops and the floor and diving into the ground to
break out again somewhere else.

The body is a trail: the path its lead point (the chest) has taken is kept as a
polyline, and segment i sits `i * SPACING` along it behind the lead, so the short bulky
torso and tapering tail follow exactly where the chest went (over ledges, into and out
of holes). Four legs carry it, a pair at the shoulder and a pair at the hip, each a
two-bone chain. Walking, they trot like the dragon's: diagonal pairs step together,
half a cycle apart, on a cycle that runs on the distance travelled, so planted feet
never slide and it never walks on the spot; the body bobs and pitches with the steps
and thuds down when it lands. Turning round, it narrows to face out of the screen and
widens again the other way.

It walks on its own terrain (`World.hydra_planner`: walkable tops and the floor with
headroom for its body and neck roots), dropping off ledges when the route says so,
but never climbs: to get anywhere else it dives. The necks do the reaching: it plants
itself where its heads reach the most adventurers and stands there while they have
someone. A dive lowers its front into a hole torn ahead of it on the surface, the
legs tucking in as they reach it; the body slides in after. Underground it is
just a timer (the distance over `BURROW_SPEED`) to an exit it picks on a window top,
the floor or (for adventurers on a wall) a window's side, scored by who is in reach
against how far it is. Cracks and dust give the exit away just before it breaks out:
from a top or the floor it heaves itself out, front feet slamming down on the lip, and
walks off; from a side its front half sticks out as a turret, front feet braced on the
wall, spits for a while and sinks back in. The holes ride along with their window; a
window closing mid-dive sends it straight underground, one closing under it or around
its exit drops it onto whatever is below.

Each neck is a FABRIK chain from the chest to its head, which eases toward its own
goal on a damped spring: a swaying rest pose, or toward the adventurer it picked in
its reach. A head with someone in front of its jaws sprays a short cone of acid (the
black dragon's: see `breath`); heads take turns, so they fire in a ripple. Acid that
lands splashes and sizzles; an adventurer it kills melts into a puddle.

With `HYDRA_HP` gone it sinks limp along its trail, heads flopping to the ground.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Rect, Vec2, clamp
from dungeons_desktops.game.actors.mortal import HYDRA_HP, Mortal
from dungeons_desktops.game.adventurers.actor import surface_below
from dungeons_desktops.game.defenders.dragon.actor import Flame, climbing_wall
from dungeons_desktops.game.effects.breath import Mote, splash, step_motes
from dungeons_desktops.navigation.planner import Anchor, Move, MoveSettings, Planner
from dungeons_desktops.navigation.terrain import Surface, Terrain, TerrainChange
from dungeons_desktops.rig.ik import two_bone_points

if TYPE_CHECKING:
    from dungeons_desktops.game.adventurers.actor import Stickman
    from dungeons_desktops.game.world.simulation import SimWorld

RADII = (14.0, 17.0, 18.0, 18.0, 16.0, 12.0, 9.0, 7.0, 5.5, 4.0)
"""Per segment, chest first: the torso (0-4) and a short tapering tail."""
CLEARANCE = (13.0, 9.0, 8.0, 8.0, 9.0, 7.0, 5.0, 3.0, 1.5, 0.5)
"""How far each segment's underside rides above its path: legs under the torso, the
tail sloping down to drag its tip."""
SEGMENTS = len(RADII)
SPACING = 11.0
BODY_LENGTH = (SEGMENTS - 1) * SPACING
SHOULDER = 1
HIP = 4
TORSO = 5
LIFT = RADII[2] + CLEARANCE[2]
"""How far the torso's middle sits off its path: where a path into the ground goes
for the body to pass through the hole."""
NODE_STEP = 2.0
"""The trail keeps a point every this far."""
BEND = 10.0
"""Each segment lies along the trail's chord this far either side of it, so the body
rounds the trail's corners instead of swinging across them."""

HEADROOM = 22.0
"""Room it needs above a surface to walk along it or break out onto it: just its legs
and belly (the lane under a maximized window). Its back and heads pass over a window
lower than `STANDING_ROOM`."""
STANDING_ROOM = 70.0
"""Its full height, heads up. A window whose bottom is closer than this above the ground
it's on doesn't block its body, necks, heads or acid."""
MOVES = MoveSettings(
    walk_speed=36.0,
    climb_speed=0.01,
    hang_speed=0.01,
    max_drop=260.0,
    max_hang_drop=0.0,
    max_jump=0.0,
    edge_clearance=10.0,
)
WALK_SPEED = 30.0
CHASE_SPEED = 42.0
ACCELERATION = 2.0
BRAKING = 5.0
DROP_SPEED = 80.0
STRIDE = 34.0
"""Distance per step cycle: each diagonal pair steps once a cycle, half a cycle apart."""
STANCE = 0.65
STEP_HEIGHT = 5.0
THIGH = 13.0
SHIN = 13.0
FOOT_REACH = 30.0
"""How far below a hip a free leg reaches for ground (dropping, breaking out)."""
BOB = 1.3
THUD = 4.0
"""How far the body squashes down when it lands."""
TURN_TIME = 0.9
"""Turning round: the body narrows to face out of the screen, then widens the other way."""

STANDOFF = 80.0
"""How far ahead of its chest it likes its foe (horizontally), choosing where to break out."""
SPOT_EVERY = 0.6
SPOT_STEP = 12.0
SPOT_RANGE = 320.0
SPOT_REACH = 0.85
"""A standing spot counts a foe as in reach within this share of the long neck's reach."""
REPLAN_EVERY = 0.8
FOE_COMMIT = 1.5
GIVE_UP = 2.0
"""Seconds it keeps after a foe it can neither reach nor dive for before trying another."""
IGNORE_FOR = 5.0
NO_PROGRESS = 3.0
WANDER_WAIT = (9.0, 15.0)
ROAM_DIVE = (10.0, 16.0)
"""Seconds of nobody to hunt before it dives off somewhere else."""
STALE_REACH = 6.0
"""Seconds of a foe staying out of its heads' reach before it dives to get at him."""

DIVE_AHEAD = 58.0
"""How far ahead of its chest it tears its hole."""
DIVE_MIN = LIFT + 12.0 + 0.6 * 24.0
"""Room it needs ahead to dive: its path into the ground is `LIFT` short of the hole."""
DIVE_SPEED = 90.0
DIVE_COOLDOWN = (6.0, 8.0)
MIN_SURFACED = 4.0
UNREACHABLE_DIVE = 1.0
"""With no crawling route to its foe, its dive cooldown is cut to at most this (once
it's been up `MIN_SURFACED`)."""
BURROW_SPEED = 420.0
MIN_UNDER = 0.6
MAX_UNDER = 3.0
TELEGRAPH = 0.4
ERUPT_SPEED = 120.0
ERUPT_DEPTH = 18.0
LANDING = 52.0
"""How far from its exit hole it comes down on a top or the floor."""
TURRET_OUT = 33.0
"""How far its chest comes out of a window side: the front half, legs braced on the wall."""
CRAMPED = TURRET_OUT + 8.0
"""A gap beside a window side narrower than this (a maximized window's screen-edge
lane) is too tight to come out of: it drops an acid glob down it from the top instead."""
GLOB_COOLDOWN = 25.0
GLOB_FIRST = 6.0
"""How long after it first appears before it may drop a glob."""
GLOB_REACH = 26.0
"""How close to the window's edge its lead comes to lean over and drop a glob."""
GLOB_WIND_UP = 0.7
GLOB_HOLD = 0.5
"""After letting go, the head stays leaning over watching it fall."""
GLOB_GRAVITY = 700.0
GLOB_RADIUS = 11.0
GLOB_KILL = 20.0
"""Half-width of the lane a falling glob sweeps clean."""
GLOB_DAMAGE = 99
GLOB_SOURCE = "acid glob"
GLOB_DEATH = "Melted off the wall by the hydra's acid glob!"
TURRET_TIME = (3.0, 5.0)
TURRET_MIN = 5
TURRET_IDLE = 1.2
RETRACT_SPEED = 80.0
HOLE_RADIUS = 24.0
EXIT_SPACING = 60.0
EXIT_ROOM = LANDING + HOLE_RADIUS + 6.0
"""The shortest top or floor stretch it breaks out onto: its hole and landing."""
FALL_GRAVITY = 900.0

NECK_POINTS = 9
NECK_LENGTHS = (70.0, 82.0, 96.0, 82.0, 70.0)
"""The middle neck (index 2) is the longest."""
HEAD_REACH = (180.0, 185.0, 190.0, 185.0, 180.0)
"""How far from its neck root a head picks an adventurer to spit at: about the same
for every head, so the short necks join in on whatever the long one can reach."""
HEAD_SCALES = (1.6, 1.6, 2.0, 1.6, 1.6)
REST_ANGLES = (0.05, 1.05, 0.5, 1.35, 0.75)
"""Each head's resting direction from straight up, toward its facing."""
REST_REACH = (0.7, 0.72, 0.8, 0.7, 0.66)
SWAY = 5.0
HEAD_STIFFNESS = 70.0
HEAD_DAMPING = 0.85
HEAD_TURN = 9.0

SPRAY_RANGE = 200.0
SPRAY_AIM = 0.9
SPRAY_TIME = 0.5
ATTACK_COOLDOWN = 2.0
"""Each head's own timer between its attacks, chomp or spray."""
ATTACK_GAP = 0.25
"""Least time between two heads starting an attack: they strike in a ripple."""
WIND_UP = 0.4
"""Seconds before a head's attack is ready that it starts to open its jaws; at rest
they stay shut."""
CHOMP_REACH = 0.9
"""A foe within this fraction of a head's neck length from its root gets chomped;
farther off, sprayed."""
CHOMP_TIME = 0.8
CHOMP_STRIKE = 0.34
"""Seconds left in the chomp when the head slams down (before that it rears up high,
jaws wide)."""
CHOMP_BITE = 0.24
"""Seconds left when it hits: the jaws snap shut and the head stops dead."""
CHOMP_HOLD = 0.12
"""Seconds left when the head lets go of where it hit and draws back."""
CHOMP_DAMAGE = 4
CHOMP_RADIUS = 8.0
"""How far round the jaws (times the head's scale) the smash lands."""
CHOMP_STIFFNESS = 10.0
"""How much harder the neck drives the head through the slam and holds it on impact."""
CHOMP_DEATH = "Chomped by the hydra!"
ACID_RATE = 50.0
ACID_SPEED = 380.0
ACID_LIFE = 1
ACID_DRAG = 1.5
ACID_DAMAGE = 2
RECOIL = 5.0
DEATH = "Dissolved by the hydra's acid!"
ZERO = Vec2(0.0, 0.0)
UP = Vec2(0.0, -1.0)


class Mode(Enum):
    WALK = "walk"
    DIVE = "dive"
    UNDER = "under"
    ERUPT = "erupt"
    TURRET = "turret"
    RETRACT = "retract"
    FALL = "fall"
    DEAD = "dead"


@dataclass(eq=False)
class Node:
    """A point of the trail: which way its back faces (`side`: +1 when the trail runs
    toward +x on the ground), the window it rides on, whether it's underground, and
    whether it lies on a surface (so a segment there walks on legs)."""

    point: Vec2
    side: int
    box: int | None = None
    under: bool = False
    grounded: bool = False

    def copy(self) -> Node:
        return Node(self.point, self.side, self.box, self.under, self.grounded)


@dataclass(eq=False)
class Exit:
    """Where it dives in or breaks out: a point on a top, the floor or a window side,
    the window it's on (None for the floor), and the way out of the ground."""

    point: Vec2
    box: int | None
    normal: Vec2
    facing: int
    out: float = 0.0
    """Out of a window side: how far its chest comes out (less in a narrow lane)."""

    @property
    def side(self) -> bool:
        return self.normal.y == 0.0


@dataclass(eq=False)
class Segment:
    contact: Vec2
    """On its path (the ground under it, for a segment lying on a surface)."""
    center: Vec2
    tangent: Vec2
    """Toward the head."""
    normal: Vec2
    """Its back."""
    radius: float
    hidden: bool
    grounded: bool


@dataclass(eq=False)
class LegPose:
    segment: int
    """`SHOULDER` or `HIP`."""
    near: bool
    hip: Vec2
    knee: Vec2
    foot: Vec2
    lift: float
    planted: bool
    """Standing on its step's spot on the ground (it doesn't move while so)."""
    forward: Vec2
    """The way its toes point."""

    @property
    def front(self) -> bool:
        return self.segment == SHOULDER


@dataclass(eq=False)
class Head:
    index: int
    length: float
    reach: float
    scale: float
    position: Vec2
    velocity: Vec2 = ZERO
    angle: float = -math.pi / 2
    neck: list[Vec2] = field(default_factory=list)
    root: Vec2 = ZERO
    target: Stickman | None = None
    commit: float = 0.0
    cooldown: float = 0.0
    spray: float = 0.0
    mouth: float = 0.1
    sway: tuple[float, float, float, float] = (1.0, 1.0, 0.0, 0.0)
    due: float = 0.0
    """Acid owed to the spray, in drops."""
    chomp: float = 0.0
    """Seconds left of a chomp."""
    bitten: bool = False
    """This chomp's jaws have already snapped shut."""
    impact: Vec2 = ZERO
    """Where this chomp hit."""

    @property
    def mouth_point(self) -> Vec2:
        return self.position + Vec2.from_angle(self.angle, 7.0 * self.scale)

    @property
    def spraying(self) -> bool:
        return self.spray > 0.0

    @property
    def chomping(self) -> bool:
        return self.chomp > 0.0

    @property
    def attacking(self) -> bool:
        return self.spraying or self.chomping

    def stop(self) -> None:
        self.spray = 0.0
        self.chomp = 0.0


@dataclass(eq=False)
class GlobPlan:
    """Dropping a glob down a cramped lane beside a window: from the `edge` of its top
    `surface`, the lane running `side` of it, centered on `lane`, `half` wide each way."""

    surface: Surface
    edge: float
    side: int
    lane: float
    half: float

    @property
    def top(self) -> float:
        return self.surface.start.y

    @property
    def stand(self) -> float:
        """Where its lead stands to lean over the edge."""
        return self.edge - self.side * GLOB_REACH


@dataclass(eq=False)
class Glob:
    position: Vec2
    velocity: Vec2
    lane: float
    half: float
    floor: float
    """Where it splashes down."""


def build_planner(boxes, floor_y: float, left: float, width: float, ceiling) -> Planner:
    terrain = Terrain(
        boxes,
        floor_y,
        left,
        width,
        hang_reach=0.0,
        mantle_depth=1e6,
        ceiling=ceiling,
        clearance=4.0,
        headroom=HEADROOM,
        wall_clearance=0.0,
        floor_headroom=True,
    )
    return Planner(terrain, MOVES)


def _bezier(a: Vec2, control: Vec2, b: Vec2, steps: int) -> list[Vec2]:
    out = []
    for k in range(1, steps + 1):
        t = k / steps
        out.append(a * ((1 - t) ** 2) + control * (2 * (1 - t) * t) + b * (t * t))
    return out


def _fabrik(points: list[Vec2], root: Vec2, goal: Vec2, link: float) -> list[Vec2]:
    count = len(points)
    if root.distance_to(goal) >= link * (count - 1):
        direction = (goal - root).normalized()
        return [root + direction * (link * i) for i in range(count)]
    joints = list(points)
    for _ in range(3):
        joints[-1] = goal
        for i in range(count - 2, -1, -1):
            joints[i] = joints[i + 1] + _toward(joints[i + 1], joints[i]) * link
        joints[0] = root
        for i in range(1, count):
            joints[i] = joints[i - 1] + _toward(joints[i - 1], joints[i]) * link
    return joints


def _inside(box: Rect, point: Vec2, inset: float) -> bool:
    return (
        box.left + inset < point.x < box.right - inset
        and box.top + inset < point.y < box.bottom - inset
    )


def _overlap(a: Rect, b: Rect) -> bool:
    return a.left < b.right and b.left < a.right and a.top < b.bottom and b.top < a.bottom


def _side(tangent: Vec2, fallback: int) -> int:
    """Which way the back faces along a stretch of trail: the way it runs, so a body on
    a window top is back-up whichever way it crawls; `fallback` (the node's) when the
    trail runs up or down."""
    if abs(tangent.x) > 0.3:
        return 1 if tangent.x > 0.0 else -1
    return fallback


def _toward(a: Vec2, b: Vec2) -> Vec2:
    direction = (b - a).normalized()
    return direction if direction.length_sq() > 0.0 else UP


class Hydra(Mortal):
    max_hp = HYDRA_HP
    linger = 4.0

    def __init__(
        self,
        world: SimWorld,
        anchor: Anchor,
        facing: int = 1,
        emerge: bool = True,
    ) -> None:
        """On the walkable `anchor`: breaking out of the ground there (`emerge`), or
        already lying along the surface behind it, facing `facing`."""
        self.world = world
        self.facing = facing
        self.mode = Mode.WALK
        self.mode_time = 0.0
        self.clock = 0.0
        self.travel = 0.0
        self.offset = 0.0
        """How far the body has slid back down its trail (sinking into its hole)."""
        self.speed = 0.0
        self.gait = 0.0
        """0 standing to 1 walking: how high its swinging feet lift and its body bobs."""
        self.thud = 0.0
        self._free: dict[tuple[int, bool], tuple[float, Vec2]] = {}
        """Per leg: how far off its walking step it is (0-1) and where its free foot is."""
        self.support: Surface | None = None
        self.nodes: list[Node] = []
        self.script: list[Node] = []
        self.script_speed = 0.0
        self._script_mark: int | None = None
        self.hole: Exit | None = None
        """The hole it's going into or coming out of, while some of it is in there."""
        self.exit: Exit | None = None
        self.under_time = 0.0
        self._telegraphed = False
        self._rumble = 0.0
        self.turret_time = 0.0
        self._idle_turret = 0.0
        self.fall_speed = 0.0
        self._fall_to: Anchor | None = None
        self.foe: Stickman | None = None
        self._foe_commit = 0.0
        self._foe_stuck = 0.0
        self._out_of_reach = 0.0
        self._ignored: dict[Stickman, float] = {}
        self._over: frozenset[int] = frozenset()
        self._route_steps: list = []
        self._route_found = True
        self._route_missing = False
        self._replan = 0.0
        self._spot: float | None = None
        self._spot_due = 0.0
        self.turn_wait = 0.0
        """Time left turning round."""
        self._turn_mid = 0.0
        self.wander_x: float | None = None
        self._wander_wait = 0.0
        self._idle = 0.0
        self._roam_after = world.random.uniform(*ROAM_DIVE)
        self._progress = (0.0, 0.0)
        self.dive_cooldown = 0.0
        self.surfaced = 0.0
        self.attack_gap = 0.0
        self.acid: list[Flame] = []
        self.glob: Glob | None = None
        self.glob_cooldown = GLOB_FIRST
        self.globbing = 0.0
        """Time left leaning over an edge to drop a glob (winding up, then watching)."""
        self._glob_aim: GlobPlan | None = None
        self.globs = 0
        self.wisps: list[Mote] = []
        self.segments: list[Segment] = []
        self.legs: list[LegPose] = []
        self.dives = 0
        self.eruptions = 0
        self.sprays = 0
        self.chomps = 0
        self.kills = 0
        rng = world.random
        self.heads = [
            Head(
                j,
                NECK_LENGTHS[j],
                HEAD_REACH[j],
                HEAD_SCALES[j],
                anchor.point,
                sway=(
                    rng.uniform(0.6, 1.3),
                    rng.uniform(0.5, 1.1),
                    rng.uniform(0.0, math.tau),
                    rng.uniform(0.0, math.tau),
                ),
                cooldown=rng.uniform(0.3, 1.5),
            )
            for j in range(len(NECK_LENGTHS))
        ]
        if emerge:
            self.exit = self._exit_at(anchor)
            self.mode = Mode.UNDER
            self.under_time = TELEGRAPH + 0.3
            self.nodes = [Node(anchor.point, facing, anchor.surface.box, under=True)]
        else:
            self._lie_on(anchor)
            self._pose(1.0 / 60.0, snap=True)
            self._rest_heads()

    def _rest_heads(self) -> None:
        """Every head straight to its resting spot, necks laid out to it."""
        for head, root in zip(self.heads, self._roots(), strict=True):
            j = head.index
            angle = -math.pi / 2 + self.facing * REST_ANGLES[j]
            head.root = root
            head.position = root + Vec2.from_angle(angle, head.length * REST_REACH[j])
            bow = [root, *_bezier(root, self._pole(head, root), head.position, NECK_POINTS - 1)]
            head.neck = _fabrik(bow, root, head.position, head.length / (NECK_POINTS - 1))
            head.angle = 0.0 if self.facing > 0 else math.pi

    # ----- the trail ---------------------------------------------------------------

    @property
    def lead(self) -> Vec2:
        return self.nodes[-1].point

    def _lie_on(self, anchor: Anchor) -> None:
        surface = anchor.surface
        back = Vec2(-self.facing, 0.0)
        length = BODY_LENGTH + 40.0
        self.nodes = [
            Node(anchor.point + back * length, self.facing, surface.box, grounded=True),
            Node(anchor.point, self.facing, surface.box, grounded=True),
        ]
        self.support = surface
        self.mode = Mode.WALK

    def _move_lead(self, point: Vec2, template: Node) -> None:
        nodes = self.nodes
        last = nodes[-1]
        self.travel += point.distance_to(last.point)
        last.point = point
        last.side, last.box = template.side, template.box
        last.under, last.grounded = template.under, template.grounded
        if len(nodes) < 2 or point.distance_to(nodes[-2].point) >= NODE_STEP:
            nodes.append(last.copy())

    def _sample(self, distances: list[float]) -> list[tuple[Vec2, Vec2, Node, Node, float]]:
        """For each distance back along the trail (ascending): the point there, the
        trail's direction toward the head, the nodes either side and how far between."""
        nodes = self.nodes
        out = []
        k = len(nodes) - 1
        walked = 0.0
        for s in distances:
            while k > 0:
                length = nodes[k].point.distance_to(nodes[k - 1].point)
                if walked + length >= s and length > 1e-9:
                    break
                walked += length
                k -= 1
            if k == 0:
                tip = nodes[0]
                direction = self._tail_direction()
                point = tip.point - direction * (s - walked)
                out.append((point, direction, tip, tip, 0.0))
                continue
            a, b = nodes[k], nodes[k - 1]
            length = a.point.distance_to(b.point)
            t = (s - walked) / length
            out.append((a.point.lerp(b.point, t), (a.point - b.point) / length, a, b, t))
        return out

    def _tail_direction(self) -> Vec2:
        nodes = self.nodes
        for k in range(1, len(nodes)):
            offset = nodes[k].point - nodes[k - 1].point
            if offset.length_sq() > 1e-9:
                return offset.normalized()
        return Vec2(float(self.facing), 0.0)

    def _trim(self) -> None:
        keep = self.offset + BODY_LENGTH + 40.0
        nodes = self.nodes
        walked = 0.0
        for k in range(len(nodes) - 1, 0, -1):
            walked += nodes[k].point.distance_to(nodes[k - 1].point)
            if walked > keep:
                if k > 1:
                    del nodes[: k - 1]
                return

    # ----- state ------------------------------------------------------------------

    @property
    def underground(self) -> bool:
        return self.mode is Mode.UNDER

    @property
    def visible(self) -> bool:
        """Anything of it out of the ground to be seen and hit."""
        return not self.underground and bool(self.parts())

    @property
    def cut(self) -> Rect | None:
        """The ground its hole is in: nothing of it shows inside."""
        if self.hole is None:
            return None
        return self._ground(self.hole.box)

    def _ground(self, box: int | None) -> Rect | None:
        world = self.world
        if box is None:
            return Rect(world.left - 1e4, world.floor_y, world.width - world.left + 2e4, 1e4)
        return world.boxes[box] if box < len(world.boxes) else None

    def _in_cut(self, point: Vec2) -> bool:
        cut = self.cut
        return cut is not None and _inside(cut, point, 0.5)

    @property
    def chest(self) -> Vec2:
        return self.segments[0].center if self.segments else self.lead

    def center(self) -> Vec2:
        shown = [s.center for s in self.segments if not s.hidden]
        if not shown:
            return self.hole.point if self.hole is not None else self.lead
        if not self.segments[0].hidden:
            return self.segments[0].center
        return shown[0]

    def parts(self) -> list[Vec2]:
        """What can be hit: segments, necks and heads out of the ground."""
        if self.underground:
            return []
        parts = [s.center for i, s in enumerate(self.segments) if not s.hidden and i % 2 == 0]
        for head in self.heads:
            if not self._head_hidden(head):
                parts.append(head.position)
                parts.append(head.neck[len(head.neck) // 2])
        return parts

    def hits(self, point: Vec2, margin: float = 0.0) -> bool:
        if self.underground:
            return False
        for segment in self.segments:
            if not segment.hidden and segment.center.distance_to(point) <= segment.radius + margin:
                return True
        for head in self.heads:
            if self._head_hidden(head):
                continue
            if head.position.distance_to(point) <= 5.0 * head.scale + margin:
                return True
            if any(p.distance_to(point) <= 3.0 + margin for p in head.neck[1::2]):
                return True
        return False

    def _head_hidden(self, head: Head) -> bool:
        return self.underground or self._in_cut(head.position)

    # ----- simulation ----------------------------------------------------------------

    def update(self, dt: float) -> None:
        self.clock += dt
        self.mode_time += dt
        self.dive_cooldown -= dt
        self.glob_cooldown -= dt
        self.surfaced += dt
        self.attack_gap -= dt
        self._ignored = {s: t - dt for s, t in self._ignored.items() if t > dt}
        mode = self.mode
        if mode is Mode.UNDER:
            self._under(dt)
        elif mode is Mode.FALL:
            self._fall(dt)
        elif mode is Mode.RETRACT:
            self._retract(dt)
        elif mode is Mode.TURRET:
            self._turret(dt)
        elif self.script:
            self._follow_script(dt)
        elif mode is Mode.WALK:
            self._walk(dt)
        self._over = self._windows_over()
        self._update_acid(dt)
        self._update_glob(dt)
        if self.mode is not Mode.UNDER:
            self._pose(dt)
            self._update_heads(dt)
        self._trim()

    def _windows_over(self) -> frozenset[int]:
        """The windows low over the ground it's on (within `STANDING_ROOM`), which it
        squeezes under with its back and heads passing over them."""
        if self.support is not None and self.support.walkable:
            ground = self.support.start.y
        elif self.hole is not None and not self.hole.side:
            ground = self.hole.point.y
        else:
            return frozenset()
        span = BODY_LENGTH + max(NECK_LENGTHS) + 20.0
        x = self.lead.x
        return frozenset(
            i
            for i, box in enumerate(self.world.boxes)
            if ground - STANDING_ROOM < box.bottom <= ground - HEADROOM + 1.0
            and box.left < x + span
            and box.right > x - span
        )

    def _set_mode(self, mode: Mode) -> None:
        self.mode = mode
        self.mode_time = 0.0
        self.globbing = 0.0

    # ----- choosing a foe ------------------------------------------------------------

    def _prey(self) -> list[Stickman]:
        return [s for s in self.world.stickmen if s.prey and s not in self._ignored]

    def _pick_foe(self, dt: float) -> Stickman | None:
        self._foe_commit -= dt
        prey = self._prey()
        foe = self.foe
        if foe is not None and foe in prey and self._foe_commit > 0.0:
            return foe
        chest = self.chest
        best = min(prey, key=lambda s: s.center().distance_to(chest), default=None)
        if foe is not None and foe in prey and best is not None:
            if best.center().distance_to(chest) > 0.6 * foe.center().distance_to(chest):
                best = foe
        if best is not foe:
            self._foe_stuck = 0.0
            self._out_of_reach = 0.0
        self.foe = best
        self._foe_commit = FOE_COMMIT
        return best

    def _give_up_on(self, foe: Stickman) -> None:
        self._ignored[foe] = IGNORE_FOR
        self.foe = None
        self._foe_commit = 0.0
        self._foe_stuck = 0.0

    def _heads_busy(self) -> bool:
        return any(h.target is not None for h in self.heads)

    # ----- walking -------------------------------------------------------------------

    def _on_support(self, stickman: Stickman) -> bool:
        surface = self.support
        foot = stickman.contact()
        return (
            surface is not None
            and abs(foot.y - surface.start.y) < 3.0
            and surface.low - 2.0 <= foot.x <= surface.high + 2.0
        )

    def _can_dive(self) -> bool:
        return (
            self.mode is Mode.WALK
            and not self.script
            and self.support is not None
            and self.surfaced >= MIN_SURFACED
            and self.dive_cooldown <= 0.0
            and self.turn_wait <= 0.0
        )

    def _try_dive(self) -> bool:
        """Go down if it may (True); with no room ahead for its hole but room behind, it
        turns round first, to dive the other way."""
        surface = self.support
        if surface is None or not self._can_dive():
            return False
        x = self.lead.x
        ahead = surface.high - x if self.facing > 0 else x - surface.low
        behind = surface.length - ahead - 4.0 * SPACING
        if self.hole is None and ahead < DIVE_MIN <= behind and self._level():
            self._start_turn()
        else:
            self._go_down()
        return True

    def _level(self) -> bool:
        """Out of the ground with its torso standing on the one level, so it can turn
        (turning lays the tail out flat too, wherever it trailed from)."""
        y = self.lead.y
        return (
            self.hole is None
            and not any(s.hidden for s in self.segments)
            and all(abs(s.contact.y - y) < 1.0 for s in self.segments[:TORSO])
        )

    def _start_turn(self) -> None:
        self.turn_wait = TURN_TIME
        self._turn_mid = self.segments[2].contact.x if self.segments else self.lead.x
        self.speed = 0.0

    def _walk(self, dt: float) -> None:
        surface = self.support
        if surface is None:
            self._start_fall()
            return
        foe = self._pick_foe(dt)
        want: float | None = None
        top_speed = WALK_SPEED
        if self.turn_wait > 0.0:
            before = self.turn_wait
            self.turn_wait = max(0.0, before - dt)
            self.speed = 0.0
            if before > TURN_TIME / 2.0 >= self.turn_wait:
                self._turn_round(surface)
            return
        if self._glob_walk(dt, surface):
            return
        if foe is not None and self._heads_busy():
            self._idle = 0.0
            self._out_of_reach = 0.0
            self._foe_stuck = 0.0
            self._spot = None
        elif foe is not None:
            self._idle = 0.0
            in_reach = self._heads_busy()
            self._out_of_reach = 0.0 if in_reach else self._out_of_reach + dt
            stale = self._out_of_reach >= STALE_REACH or self._no_progress()
            if stale and self._try_dive():
                return
            top_speed = CHASE_SPEED
            if self._on_support(foe):
                self._route_steps = []
                self._route_found = True
                want, reachable = self._standing_spot(foe, surface, dt)
                if reachable and (want is not None or in_reach):
                    self._foe_stuck = 0.0
                else:
                    self._foe_stuck += dt
                    if self._foe_stuck >= GIVE_UP:
                        self._spot = None
                        if self._try_dive():
                            return
                        self._give_up_on(foe)
            else:
                want = self._route_toward(foe, dt)
                if not self._route_found:
                    if self._route_missing and self.surfaced >= MIN_SURFACED:
                        self.dive_cooldown = min(self.dive_cooldown, UNREACHABLE_DIVE)
                    if self._try_dive():
                        return
                    if want is None and not in_reach:
                        want = foe.contact().x
                if want is None and not in_reach:
                    self._foe_stuck += dt
                    if self._foe_stuck >= GIVE_UP:
                        self._give_up_on(foe)
        else:
            self._out_of_reach = 0.0
            self._idle += dt
            if self._idle >= self._roam_after and self._try_dive():
                if self.turn_wait <= 0.0:
                    self._idle = 0.0
                    self._roam_after = self.world.random.uniform(*ROAM_DIVE)
                return
            want = self._wander(dt, surface)
            top_speed = WALK_SPEED * 0.75
        self._drive(dt, surface, want, top_speed)

    # ----- acid glob -----------------------------------------------------------------------

    def _plan_glob(self) -> GlobPlan | None:
        """The nearest cramped lane (narrower than `CRAMPED`, beside a window with a top
        it can stand on) with an adventurer climbing it below, if its glob is ready."""
        if self.glob_cooldown > 0.0 or self.glob is not None or self.dead:
            return None
        world = self.world
        plans = []
        for stickman in self._prey():
            if climbing_wall(stickman) is None:
                continue
            at = stickman.center()
            for surface in world.hydra_planner.surfaces:
                if not surface.walkable or surface.box is None or surface.start.y > at.y - 10.0:
                    continue
                box = world.boxes[surface.box]
                if at.x <= surface.low and abs(surface.low - box.left) < 2.0:
                    side, edge = -1, box.left
                elif at.x >= surface.high and abs(surface.high - box.right) < 2.0:
                    side, edge = 1, box.right
                else:
                    continue
                room = self._side_room(Vec2(edge, at.y), Vec2(float(side), 0.0), surface.box)
                if room >= CRAMPED or abs(at.x - edge) > room + 4.0:
                    continue
                lane = edge + side * room * 0.5
                if not self._clear(Vec2(lane, surface.start.y - 2.0), Vec2(lane, at.y)):
                    continue
                plans.append(GlobPlan(surface, edge, side, lane, room * 0.5 + 8.0))
        lead = self.lead
        return min(
            plans,
            key=lambda p: Vec2(p.stand, p.top).distance_to(lead),
            default=None,
        )

    def _glob_walk(self, dt: float, surface: Surface) -> bool:
        """Drop a glob if it's leaning over to (True), or walk to the edge to: on its own
        top, or (on another) diving to come up there."""
        if self.globbing > 0.0:
            self.speed = 0.0
            self._glob_step(dt)
            return True
        plan = self._plan_glob()
        if plan is None:
            return False
        if plan.surface.box != surface.box or abs(plan.top - surface.start.y) > 1.0:
            if self.surfaced >= MIN_SURFACED:
                self.dive_cooldown = min(self.dive_cooldown, UNREACHABLE_DIVE)
            return self._try_dive()
        if self.facing != plan.side:
            if self._level():
                self._start_turn()
                return True
        elif (plan.stand - self.lead.x) * plan.side < 4.0:
            self._start_glob(plan)
            return True
        self._drive(dt, surface, plan.stand, CHASE_SPEED)
        return True

    def _glob_exit(self) -> Exit | None:
        """Where to come up to drop a glob: on the top beside its lane, landing facing
        the edge."""
        plan = self._plan_glob()
        if plan is None:
            return None
        surface = plan.surface
        x = clamp(
            plan.stand - plan.side * LANDING,
            surface.low + HOLE_RADIUS,
            surface.high - HOLE_RADIUS,
        )
        exit_ = Exit(surface.point_at(x), surface.box, UP, plan.side)
        return exit_ if self._top_clear(exit_.point, exit_.facing) else None

    def _start_glob(self, plan: GlobPlan) -> None:
        self.globbing = GLOB_WIND_UP + GLOB_HOLD
        self._glob_aim = plan
        self.glob_cooldown = GLOB_COOLDOWN
        self.globs += 1
        self.speed = 0.0
        head = self.heads[2]
        head.stop()
        head.target = None

    def _glob_step(self, dt: float) -> None:
        before = self.globbing
        self.globbing -= dt
        plan = self._glob_aim
        if plan is None or not before > GLOB_HOLD >= self.globbing:
            return
        world = self.world
        mouth = self.heads[2].mouth_point
        start = Vec2(plan.lane, max(mouth.y, plan.top - 10.0))
        floor = self._ground_below(Vec2(plan.lane, start.y + 1.0))
        self.glob = Glob(start, Vec2(0.0, 40.0), plan.lane, plan.half, floor)
        world.debris.burst(start, Vec2(0.0, 1.0), 4, 60.0, spread=1.0, puffs=2, scale=0.6)

    @property
    def glob_charge(self) -> float:
        """0-1: how big the glob swelling in the big head's mouth has grown."""
        if self.globbing <= GLOB_HOLD:
            return 0.0
        return clamp(1.0 - (self.globbing - GLOB_HOLD) / GLOB_WIND_UP, 0.0, 1.0)

    def _update_glob(self, dt: float) -> None:
        """The glob falls down its lane, melting everyone on it, and splashes at the
        bottom."""
        glob = self.glob
        if glob is None:
            return
        world = self.world
        rng = world.random
        before = glob.position
        glob.velocity += Vec2(0.0, GLOB_GRAVITY * dt)
        glob.position = before + glob.velocity * dt
        if rng.random() < 0.7:
            drip = glob.position + Vec2(rng.uniform(-6.0, 6.0), rng.uniform(-8.0, 0.0))
            velocity = Vec2(rng.uniform(-15.0, 15.0), glob.velocity.y * 0.25)
            size = rng.uniform(1.2, 2.0)
            self.wisps.append(Mote("drip", drip, velocity, 3.0, size, floor=glob.floor))
        for stickman in world.stickmen:
            if not stickman.prey:
                continue
            at = stickman.center()
            swept = before.y - 30.0 <= at.y <= glob.position.y + 30.0
            if swept and abs(at.x - glob.lane) <= glob.half:
                push = Vec2(0.0, 220.0)
                if stickman.hurt_from(
                    self, GLOB_DAMAGE, at, push, GLOB_SOURCE, GLOB_DEATH, bleed=False
                ):
                    stickman.succumb("acid")
                    self.kills += 1
        if glob.position.y >= glob.floor:
            spot = Vec2(glob.lane, glob.floor)
            for _ in range(8):
                x = glob.lane + rng.uniform(-glob.half - 10.0, glob.half + 10.0)
                self.wisps += splash(Vec2(x, glob.floor), 3.0, rng)
            world.debris.burst(spot, UP, 6, 120.0, spread=1.3, puffs=5, scale=0.8)
            self.glob = None

    def _turn_round(self, surface: Surface) -> None:
        """Halfway round, squeezed to nothing: lay the body out the other way, mirrored
        about the middle of its torso."""
        self.facing = -self.facing
        x = clamp(2.0 * self._turn_mid - self.lead.x, surface.low + 3.0, surface.high - 3.0)
        lead = Vec2(x, self.lead.y)
        back = Vec2(-self.facing * (BODY_LENGTH + 40.0), 0.0)
        self.nodes = [
            Node(lead + back, self.facing, surface.box, grounded=True),
            Node(lead, self.facing, surface.box, grounded=True),
        ]
        self.offset = 0.0
        self._route_steps = []
        self._replan = 0.0

    def _standing_spot(
        self, foe: Stickman, surface: Surface, dt: float
    ) -> tuple[float | None, bool]:
        """Where along its surface to plant itself (None: stay put) and whether its foe
        is in its necks' reach from anywhere near. The spot reaches the most adventurers
        (its foe counting double, those behind it half), with a little against walking."""
        self._spot_due -= dt
        if self._spot_due <= 0.0 or self._spot is None:
            self._spot_due = SPOT_EVERY
            self._spot = self._best_spot(foe, surface)
        x = self._spot
        if x is None:
            return foe.contact().x, False
        if abs(x - self.lead.x) < 3.0:
            return None, True
        return x, True

    def _best_spot(self, foe: Stickman, surface: Surface) -> float | None:
        lead_x = self.lead.x
        low = max(surface.low + 3.0, lead_x - SPOT_RANGE)
        high = min(surface.high - 3.0, lead_x + SPOT_RANGE)
        if high < low:
            return None
        count = int((high - low) // SPOT_STEP)
        spots = [low + k * SPOT_STEP for k in range(count + 1)]
        reach = HEAD_REACH[2] * SPOT_REACH
        height = RADII[0] + CLEARANCE[0]
        prey = [(s, s.center()) for s in self._prey()]

        def score(x: float) -> tuple[float, bool]:
            chest = Vec2(x, surface.start.y - height)
            value, got = -abs(x - lead_x) / 250.0, False
            for stickman, at in prey:
                distance = at.distance_to(chest)
                if not 25.0 < distance <= reach or not self._clear(chest, at):
                    continue
                weight = 2.0 if stickman is foe else 1.0
                value += weight * (1.3 - distance / reach)
                got = got or stickman is foe
            return value, got

        scored = [(*score(x), x) for x in spots]
        best = max((s for s in scored if s[1]), key=lambda s: s[0], default=None)
        if best is None:
            return None
        here, here_got = score(lead_x)
        if here_got and here >= best[0] - 0.15:
            return lead_x
        return best[2]

    def _go_down(self) -> None:
        """Dive ahead, or (with its tail still in the hole it came out of) sink back in."""
        if self.hole is not None:
            self._set_mode(Mode.RETRACT)
            self.dives += 1
            self.dive_cooldown = self.world.random.uniform(*DIVE_COOLDOWN)
        else:
            self._dive()

    def _no_progress(self) -> bool:
        since, x = self._progress
        if abs(self.lead.x - x) > 8.0 or self.speed < 1.0:
            self._progress = (self.clock, self.lead.x)
            return False
        return self.clock - since > NO_PROGRESS

    def _plan(self, foe: Stickman):
        planner = self.world.hydra_planner
        surface = self.support
        if surface is None:
            return None
        goal = planner.anchor_near(foe.contact(), 80.0, walk_only=True)
        if goal is None:
            return None
        route = planner.plan(Anchor(surface, self.lead), goal)
        if route is None or any(s.move not in (Move.WALK, Move.DROP) for s in route.steps):
            return None
        return list(route.steps)

    def _route_toward(self, foe: Stickman, dt: float) -> float | None:
        """The x to head for along the route to `foe` (walking off the edge when the route
        drops), replanned no faster than `REPLAN_EVERY`. Sets `_route_found`: False with
        no walking route, or one so long a dive would be quicker."""
        self._replan -= dt
        if self._replan <= 0.0:
            self._replan = REPLAN_EVERY
            steps = self._plan(foe)
            self._route_missing = steps is None
            self._route_found = steps is not None and sum(s.duration for s in steps) < 6.0
            self._route_steps = steps or []
        steps = self._route_steps
        surface = self.support

        def reachable(x: float) -> float:
            if surface is None:
                return x
            return clamp(x, surface.low + 3.0, surface.high - 3.0)

        while (
            steps
            and steps[0].move is Move.WALK
            and abs(reachable(steps[0].end.x) - self.lead.x) < 1.5
        ):
            steps.pop(0)
        if not steps:
            return None
        step = steps[0]
        if step.move is Move.DROP:
            edge = reachable(step.start.x)
            if abs(edge - self.lead.x) < 2.0:
                self._start_drop(step.start, step.end, step.surface)
                steps.clear()
                self._replan = 0.0
                return None
            return step.start.x
        return step.end.x

    def _wander(self, dt: float, surface: Surface) -> float | None:
        low, high = surface.low + 6.0, surface.high - 6.0
        if self.wander_x is None or abs(self.wander_x - self.lead.x) < 3.0:
            self.wander_x = None
            self._wander_wait -= dt
            if self._wander_wait <= 0.0 and high > low:
                rng = self.world.random
                self.wander_x = rng.uniform(low, high)
                self._wander_wait = rng.uniform(*WANDER_WAIT)
        return self.wander_x

    def _drive(self, dt: float, surface: Surface, want: float | None, top_speed: float) -> None:
        low, high = surface.low + 3.0, surface.high - 3.0
        x = self.lead.x
        desired = 0.0
        if want is not None:
            want = clamp(want, low, high)
            offset = want - x
            if abs(offset) > 6.0 or (abs(offset) > 0.5 and self.speed > 1.0):
                direction = 1 if offset > 0 else -1
                if direction != self.facing and not self._level():
                    desired = top_speed
                elif direction != self.facing:
                    if self.speed < 4.0:
                        self._start_turn()
                        return
                else:
                    desired = top_speed * min(1.0, abs(offset) / 15.0)
        rate = ACCELERATION if desired > self.speed else BRAKING
        self.speed += (desired - self.speed) * min(1.0, rate * dt)
        if desired == 0.0 and self.speed < 1.0:
            self.speed = 0.0
        step = self.facing * self.speed * dt
        new_x = clamp(x + step, low, high) if low <= high else x
        if (new_x - x) * self.facing < 0.0:
            new_x = x
        if new_x == x and step != 0.0:
            self.speed = 0.0
        point = surface.point_at(new_x)
        self._move_lead(point, Node(point, self.facing, surface.box, grounded=True))

    # ----- scripted paths: drops, dives, break-outs --------------------------------------

    def _run(self, script: list[Node], speed: float, mark: int | None = None) -> None:
        self.script = script
        self.script_speed = speed
        self._script_mark = mark
        self.speed = 0.0
        self.support = None

    def _start_drop(self, start: Vec2, end: Vec2, surface: Surface) -> None:
        side = 1 if end.x >= start.x else -1
        down = end.y - start.y
        lip = Vec2(start.x + side * 9.0, start.y + min(10.0, down * 0.3))
        path = _bezier(start, Vec2(start.x + side * 8.0, start.y), lip, 5)
        low = Vec2(end.x, end.y - min(12.0, down * 0.3))
        if low.y > lip.y:
            path.append(low)
        path += _bezier(low, Vec2(end.x, end.y), end + Vec2(side * 10.0, 0.0), 5)
        script = [Node(p, side) for p in path]
        script[-1].box = surface.box
        script[-1].grounded = True
        self._run(script, DROP_SPEED)

    def _follow_script(self, dt: float) -> None:
        distance = self.script_speed * dt
        while distance > 0.0 and self.script:
            node = self.script[0]
            gap = self.lead.distance_to(node.point)
            if gap <= distance:
                self._move_lead(node.point, node)
                distance -= gap
                self.script.pop(0)
                if self._script_mark is not None:
                    self._script_mark -= 1
                    if self._script_mark < 0:
                        self._script_mark = None
                        self._break_ground(self.hole)
            else:
                point = self.lead + (node.point - self.lead) * (distance / gap)
                self._move_lead(point, node)
                distance = 0.0
        if self.mode is Mode.DIVE:
            if all(s.hidden for s in self._pose_segments()):
                self._go_under()
            return
        if not self.script:
            self._script_done()

    def _script_done(self) -> None:
        if self.mode is Mode.ERUPT and self.hole is not None and self.hole.side:
            self._set_mode(Mode.TURRET)
            self.turret_time = self.world.random.uniform(*TURRET_TIME)
            self._idle_turret = 0.0
            return
        anchor = self._anchor_at(self.lead)
        if anchor is None:
            self._start_fall()
            return
        self.support = anchor.surface
        landed = Node(anchor.point, self.facing, anchor.surface.box, grounded=True)
        self._move_lead(anchor.point, landed)
        self._set_mode(Mode.WALK)
        self._replan = 0.0
        self.thud = 0.0

    def _anchor_at(self, point: Vec2) -> Anchor | None:
        best = None
        for surface in self.world.hydra_planner.surfaces:
            if not surface.walkable:
                continue
            if surface.contains(point, 2.5):
                spot = surface.closest_point(point)
                if best is None or spot.distance_to(point) < best.point.distance_to(point):
                    best = Anchor(surface, spot)
        return best

    # ----- diving ---------------------------------------------------------------------------

    def _dive(self) -> None:
        surface = self.support
        assert surface is not None
        lead = self.lead
        facing = self.facing
        edge = HOLE_RADIUS * 0.6
        ahead = clamp(lead.x + facing * DIVE_AHEAD, surface.low + edge, surface.high - edge)
        if (ahead - lead.x) * facing < DIVE_MIN - edge:
            ahead = lead.x + facing * (DIVE_MIN - edge)
        hole = Vec2(ahead, surface.start.y)
        entry = hole - Vec2(facing * LIFT, 0.0)
        rise = (lead + entry) * 0.5 + UP * 8.0
        path = _bezier(lead, rise, entry, 8)
        script = [Node(p, facing, surface.box) for p in path]
        mark = len(script) - 1
        depth = BODY_LENGTH + 40.0
        down = Vec2(0.0, 1.0)
        for k in range(1, 9):
            point = entry + down * (depth * k / 8)
            script.append(Node(point, self.facing, surface.box, under=True))
        self.hole = Exit(hole, surface.box, UP, self.facing)
        self._set_mode(Mode.DIVE)
        self._run(script, DIVE_SPEED, mark)
        self.dives += 1
        self.dive_cooldown = self.world.random.uniform(*DIVE_COOLDOWN)
        for head in self.heads:
            head.target = None
            head.stop()

    def _break_ground(self, hole: Exit | None) -> None:
        if hole is None:
            return
        world = self.world
        debris = world.debris
        debris.burst(hole.point, hole.normal, 14, 260.0, spread=0.5, chunks=3, scale=1.2)
        debris.burst(hole.point, hole.normal, 10, 160.0, ring_radius=12.0, cracks=4, puffs=6)
        debris.hole(hole.point, HOLE_RADIUS, world.boxes, world.bottom_border)

    def _go_under(self) -> None:
        start = self.hole.point if self.hole is not None else self.lead
        self.script = []
        self.hole = None
        self.offset = 0.0
        self.support = None
        self.speed = 0.0
        self._set_mode(Mode.UNDER)
        self.exit = self._pick_exit(start)
        travel = self.exit.point.distance_to(start) if self.exit is not None else 0.0
        self.under_time = clamp(travel / BURROW_SPEED, MIN_UNDER, MAX_UNDER)
        self._telegraphed = False
        for head in self.heads:
            head.target = None
            head.stop()

    def _under(self, dt: float) -> None:
        self.under_time -= dt
        if self.exit is None or not self._exit_valid(self.exit):
            self.exit = self._pick_exit(self.lead)
            self.under_time = max(self.under_time, TELEGRAPH + 0.1)
            self._telegraphed = False
        exit_ = self.exit
        if exit_ is None:
            self.under_time = max(self.under_time, 0.5)
            return
        if self.under_time <= TELEGRAPH:
            debris = self.world.debris
            if not self._telegraphed:
                self._telegraphed = True
                debris.burst(exit_.point, exit_.normal, 6, 70.0, ring_radius=9.0, cracks=5, puffs=3)
            self._rumble -= dt
            if self._rumble <= 0.0:
                self._rumble = 0.1
                debris.burst(exit_.point, exit_.normal, 3, 70.0, spread=1.2, puffs=1, scale=0.6)
        if self.under_time <= 0.0:
            self._erupt(exit_)

    def _exit_at(self, anchor: Anchor) -> Exit:
        surface = anchor.surface
        point = anchor.point
        room_right = surface.high - point.x
        room_left = point.x - surface.low
        facing = self.facing
        if facing > 0 and room_right < LANDING + 4.0 and room_left > room_right:
            facing = -1
        elif facing < 0 and room_left < LANDING + 4.0 and room_right > room_left:
            facing = 1
        return Exit(point, surface.box, UP, facing)

    def _exit_valid(self, exit_: Exit) -> bool:
        if exit_.side:
            return (
                exit_.box is not None
                and self._ground(exit_.box) is not None
                and self._side_clear(exit_.point, exit_.normal, exit_.box)
            )
        return self._anchor_at(exit_.point) is not None and self._top_clear(
            exit_.point, exit_.facing
        )

    def _top_clear(self, point: Vec2, facing: int) -> bool:
        """Room above a top or the floor for it to arch out of a hole at `point` and
        come down `LANDING` on: no window in the way."""
        back = point.x - facing * HOLE_RADIUS
        front = point.x + facing * (LANDING + RADII[0] + 10.0)
        room = Rect(min(back, front), point.y - HEADROOM, abs(front - back), HEADROOM - 1.0)
        return not any(_overlap(box, room) for box in self.world.boxes)

    def _exit_candidates(self) -> list[Exit]:
        world = self.world
        found: list[Exit] = []
        for surface in world.hydra_planner.surfaces:
            if not surface.walkable or surface.length < EXIT_ROOM:
                continue
            low, high = surface.low + HOLE_RADIUS, surface.high - HOLE_RADIUS
            count = max(1, int((high - low) // EXIT_SPACING) + 1)
            spots = [low + (high - low) * (k + 0.5) / count for k in range(count)]
            for stickman in self._prey():
                foot = stickman.contact()
                if not surface.contains(foot, 4.0):
                    continue
                for facing in (1, -1):
                    spots.append(clamp(foot.x - facing * (STANDOFF * 0.6 + LANDING), low, high))
            for x in spots:
                for facing in (1, -1):
                    room = surface.high - x if facing > 0 else x - surface.low
                    point = surface.point_at(x)
                    if room >= LANDING + 4.0 and self._top_clear(point, facing):
                        found.append(Exit(point, surface.box, UP, facing))
        if any(climbing_wall(s) is not None for s in self._prey()):
            found += self._side_exits()
        return found

    def _side_exits(self) -> list[Exit]:
        world = self.world
        found = []
        for index, box in enumerate(world.boxes):
            bottom = min(box.bottom, world.floor_y) - 20.0
            for x, normal in ((box.left, Vec2(-1.0, 0.0)), (box.right, Vec2(1.0, 0.0))):
                y = box.top + 30.0
                while y <= bottom:
                    point = Vec2(x, y)
                    room = self._side_room(point, normal, index)
                    if room >= CRAMPED:
                        out = min(TURRET_OUT, room - 8.0)
                        found.append(Exit(point, index, normal, int(normal.x), out))
                    y += EXIT_SPACING
        return found

    def _side_clear(self, point: Vec2, normal: Vec2, own: int) -> bool:
        return self._side_room(point, normal, own) >= CRAMPED

    def _side_room(self, point: Vec2, normal: Vec2, own: int) -> float:
        """How far out from a window side at `point` is clear: to the screen's edge or
        the nearest other window level with it."""
        world = self.world
        if normal.x < 0.0:
            room = point.x - world.left
        else:
            room = world.width - point.x
        for i, box in enumerate(world.boxes):
            if i == own or box.bottom < point.y - HEADROOM or box.top > point.y + 30.0:
                continue
            gap = point.x - box.right if normal.x < 0.0 else box.left - point.x
            if gap > -0.5:
                room = min(room, gap)
        return room

    def _pick_exit(self, start: Vec2) -> Exit | None:
        rng = self.world.random
        glob_exit = self._glob_exit()
        if glob_exit is not None:
            return glob_exit
        candidates = self._exit_candidates()
        if not candidates:
            return None
        prey = self._prey()
        if not prey:
            roomy = [c for c in candidates if 150.0 <= c.point.distance_to(start) <= 600.0]
            choice = rng.choice(roomy or candidates)
            return choice

        def score(exit_: Exit) -> float:
            chest = self._chest_from(exit_)
            value = 0.0
            for stickman in prey:
                at = stickman.contact()
                distance = at.distance_to(chest)
                if distance < HEAD_REACH[2]:
                    climber = climbing_wall(stickman) is not None
                    weight = 2.0 if exit_.side and climber else 1.0
                    ahead = (at.x - chest.x) * exit_.facing
                    if not exit_.side and ahead < 15.0:
                        weight *= 0.3
                    value += weight * (1.2 - distance / HEAD_REACH[2])
            value -= exit_.point.distance_to(start) / 900.0
            if exit_.point.distance_to(start) < 40.0:
                value -= 0.5
            return value + rng.uniform(0.0, 0.05)

        return max(candidates, key=score)

    def _chest_from(self, exit_: Exit) -> Vec2:
        if exit_.side:
            return exit_.point + exit_.normal * exit_.out + UP * 9.0
        return exit_.point + Vec2(exit_.facing * LANDING, -RADII[0] - CLEARANCE[0])

    # ----- breaking out ----------------------------------------------------------------------

    def _erupt(self, exit_: Exit) -> None:
        world = self.world
        normal = exit_.normal
        point = exit_.point
        self.facing = exit_.facing
        depth = ERUPT_DEPTH
        if exit_.side:
            entry = point - UP * LIFT
        else:
            entry = point + Vec2(self.facing * LIFT, 0.0)
        start = entry - normal * depth
        tail = start - normal * (BODY_LENGTH + 40.0)
        self.nodes = [
            Node(tail, self.facing, exit_.box, under=True),
            Node(start, self.facing, exit_.box, under=True),
            Node(start, self.facing, exit_.box, under=True),
        ]
        self.offset = 0.0
        if exit_.side:
            out = entry + normal * exit_.out + UP * 8.0
            path = _bezier(entry, entry + normal * (exit_.out * 0.6), out, 8)
            script = [Node(p, self.facing, exit_.box) for p in path]
        else:
            f = self.facing
            landing = point + Vec2(f * LANDING, 0.0)
            peak = Vec2(entry.x + f * 12.0, point.y - 22.0)
            path = _bezier(entry, Vec2(entry.x, peak.y), peak, 7)
            path += _bezier(peak, Vec2(landing.x - f * 8.0, landing.y), landing, 6)
            script = [Node(p, self.facing, exit_.box) for p in path]
            script[-1].grounded = True
        script.insert(0, Node(entry, self.facing, exit_.box))
        self.hole = exit_
        self.exit = None
        self._set_mode(Mode.ERUPT)
        self._run(script, ERUPT_SPEED)
        self.eruptions += 1
        self.surfaced = 0.0
        self.dive_cooldown = max(self.dive_cooldown, world.random.uniform(*DIVE_COOLDOWN))
        self._free.clear()
        hidden = point - normal * 6.0
        for head in self.heads:
            head.position = hidden
            head.velocity = normal * 120.0
            head.neck = [hidden] * NECK_POINTS
            head.angle = normal.angle()
            head.target = None
        debris = world.debris
        debris.burst(point, normal, 20, 380.0, spread=0.3, chunks=4, scale=1.2)
        debris.burst(point, normal, 16, 220.0, ring_radius=14.0, cracks=5, puffs=8, scale=1.1)
        debris.hole(point, HOLE_RADIUS, world.boxes, world.bottom_border)

    def _turret(self, dt: float) -> None:
        self.turret_time -= dt
        self._pick_foe(dt)
        self._idle_turret = 0.0 if self._heads_busy() else self._idle_turret + dt
        done = self.turret_time <= 0.0 or (
            self.mode_time >= TURRET_MIN
            and (self._idle_turret >= TURRET_IDLE or self._plan_glob() is not None)
        )
        if done:
            self._set_mode(Mode.RETRACT)

    def _retract(self, dt: float) -> None:
        self.offset += RETRACT_SPEED * dt
        for head in self.heads:
            head.target = None
            head.stop()
        if all(s.hidden for s in self._pose_segments()):
            self._go_under()

    # ----- falling ---------------------------------------------------------------------------

    def _start_fall(self) -> None:
        """Its ground went: lie straight out from the lead and drop onto what's below."""
        lead = self.lead
        anchor = surface_below(self.world.hydra_planner, lead - Vec2(0.0, 2.0))
        self.script = []
        self.hole = None
        self.offset = 0.0
        self.support = None
        self.speed = 0.0
        back = Vec2(-self.facing, 0.0)
        self.nodes = [
            Node(lead + back * (BODY_LENGTH + 40.0), self.facing),
            Node(lead, self.facing),
            Node(lead, self.facing),
        ]
        self._fall_to = anchor
        self.fall_speed = 0.0
        self._set_mode(Mode.FALL)

    def _fall(self, dt: float) -> None:
        anchor = self._fall_to
        if anchor is None or not self.world.hydra_planner.owns(anchor.surface):
            anchor = self._fall_to = surface_below(self.world.hydra_planner, self.lead)
        target = anchor.point
        lead = self.lead
        self.fall_speed += FALL_GRAVITY * dt
        dy = min(self.fall_speed * dt, target.y - lead.y)
        dx = 0.0
        if not anchor.surface.low <= lead.x <= anchor.surface.high:
            dx = clamp(target.x - lead.x, -200.0 * dt, 200.0 * dt)
        shift = Vec2(dx, max(0.0, dy))
        for node in self.nodes:
            node.point += shift
        if abs(self.lead.y - target.y) < 0.5 and abs(dx) < 1e-6:
            for node in self.nodes:
                node.box, node.grounded = anchor.surface.box, True
            self.support = anchor.surface
            self._set_mode(Mode.WALK)
            self.world.debris.burst(self.lead, UP, 10, 150.0, spread=1.4, puffs=6)
            self._replan = 0.0
            self.thud = 0.0

    # ----- posing ----------------------------------------------------------------------------

    def _pose_segments(self) -> list[Segment]:
        distances = [self.offset + i * SPACING for i in range(SEGMENTS)]
        samples = self._sample(distances)
        ahead = self._sample([max(0.0, s - BEND) for s in distances])
        behind = self._sample([s + BEND for s in distances])
        segments = []
        settle = max(0.0, 1.0 - self.down_time * 1.5) if self.dead else 1.0
        cycle = math.tau * self._phase()
        bob = BOB * self.gait * math.cos(2.0 * cycle) + THUD * self._thud_amount()
        pitch = 0.5 * BOB * self.gait * math.sin(2.0 * cycle)
        for i, (point, tangent, a, b, t) in enumerate(samples):
            near = a if t < 0.5 else b
            chord = ahead[i][0] - behind[i][0]
            if chord.length_sq() > 1e-6:
                tangent = chord.normalized()
            normal = tangent.rotated(-_side(tangent, near.side) * math.pi / 2)
            radius = RADII[i]
            sag = bob * clamp(1.0 - (i - HIP) / 3.0, 0.0, 1.0) + pitch * (i - 2) / 2.0
            lift = CLEARANCE[i] * settle - sag * settle
            center = point + normal * (radius + lift)
            under = a.under if t < 0.5 else b.under
            hidden = self.underground or under or self._in_cut(center)
            grounded = a.grounded and b.grounded and not hidden
            segments.append(Segment(point, center, tangent, normal, radius, hidden, grounded))
        return segments

    def _phase(self) -> float:
        """Step cycles walked: it only advances with distance, so feet never slide."""
        return (self.travel - self.offset) / STRIDE

    def _thud_amount(self) -> float:
        if self.thud >= 0.4:
            return 0.0
        return math.sin(math.pi * self.thud / 0.4)

    def _pose(self, dt: float, snap: bool = False) -> None:
        if self.mode is Mode.UNDER:
            return
        moving = self.speed > 1.0 or bool(self.script) or self.mode is Mode.RETRACT
        goal = 1.0 if moving and not self.dead else 0.0
        self.gait = goal if snap else self.gait + (goal - self.gait) * min(1.0, 5.0 * dt)
        self.thud += dt
        self.segments = self._pose_segments()
        if self.hole is not None and self.mode is Mode.WALK:
            if not any(s.hidden for s in self.segments):
                self.hole = None
        self._pose_legs(dt, snap)
        if self.turn_wait > 0.0:
            self._foreshorten(abs(math.cos(math.pi * (1.0 - self.turn_wait / TURN_TIME))))

    def _pose_legs(self, dt: float, snap: bool) -> None:
        """Four legs, a near and far pair at the shoulder and the hip. Walking, they trot:
        diagonal pairs step together, half a cycle apart, on the cycle `_phase`. Off the
        ground (dropping, breaking out, braced on a wall, tucked into a dive) each foot
        eases toward a spot of its own, and back onto its step when it walks again."""
        legs = []
        span = STANCE * STRIDE
        phase = self._phase()
        walking_mode = self.mode not in (Mode.TURRET, Mode.DEAD)
        rate = 1.0 if snap else min(1.0, 12.0 * dt)
        forward = Vec2(float(self.facing), 0.0)
        for index in (SHOULDER, HIP):
            segment = self.segments[index]
            if segment.hidden:
                self._free.pop((index, False), None)
                self._free.pop((index, True), None)
                continue
            tangent, normal = segment.tangent, segment.normal
            hip = segment.center - normal * (segment.radius * 0.35)
            front = index == SHOULDER
            walking = walking_mode and segment.grounded
            for near in (False, True):
                p = (phase + (0.0 if front == near else 0.5)) % 1.0
                if p < STANCE:
                    along, lift = span * (0.5 - p / STANCE), 0.0
                else:
                    u = (p - STANCE) / (1.0 - STANCE)
                    along = span * (-0.5 + u * u * (3.0 - 2.0 * u))
                    lift = math.sin(math.pi * u) * STEP_HEIGHT * self.gait
                splay = (3.0 if front else -2.0) + (1.5 if near else -1.5)
                step = segment.contact + tangent * (along + splay) + normal * lift
                key = (index, near)
                off, free = self._free.get(key, (0.0 if walking else 1.0, step))
                if snap:
                    off = 0.0 if walking else 1.0
                else:
                    off = clamp(off + (-6.0 if walking else 6.0) * dt, 0.0, 1.0)
                if off == 0.0:
                    free = step
                else:
                    free = free + (self._free_foot(segment, hip, front, near) - free) * rate
                self._free[key] = (off, free)
                foot = step.lerp(free, off * off * (3.0 - 2.0 * off))
                bend = -self.facing if front else self.facing
                _, knee, foot = two_bone_points(hip, THIGH, SHIN, foot, bend)
                planted = off == 0.0 and p < STANCE
                legs.append(
                    LegPose(index, near, hip, knee, foot, lift / STEP_HEIGHT, planted, forward)
                )
        self.legs = legs

    def _free_foot(self, segment: Segment, hip: Vec2, front: bool, near: bool) -> Vec2:
        """Where a leg off its walking step reaches: splayed when dead, braced on the wall
        round a side hole, tucked under going into a hole, down onto ground in reach, or
        hanging."""
        tangent, normal = segment.tangent, segment.normal
        facing = self.facing
        spread = 1.5 if near else -1.5
        hole = self.hole
        if self.dead:
            reach = (12.0 if front else -10.0) + spread * 2.0
            return Vec2(hip.x + facing * reach, self._ground_below(hip))
        if hole is not None and hole.side and self.mode in (Mode.ERUPT, Mode.TURRET):
            return Vec2(hole.point.x, hip.y + (13.0 if near else -3.0))
        diving = self.mode in (Mode.DIVE, Mode.RETRACT)
        if hole is not None and diving and segment.center.distance_to(hole.point) < 50.0:
            return hip - normal * 5.0 - tangent * 7.0
        ground = self._ground_below(hip)
        if ground - hip.y <= FOOT_REACH:
            return Vec2(hip.x + facing * ((4.0 if front else -3.0) + spread), ground)
        return hip + Vec2(facing * (5.0 if front else -4.0), THIGH + SHIN - 5.0)

    def _foreshorten(self, k: float) -> None:
        """Turning round: squeeze it toward the middle of its torso, `k` of full width."""
        mid = self._turn_mid

        def squeeze(p: Vec2) -> Vec2:
            return Vec2(mid + (p.x - mid) * k, p.y)

        for s in self.segments:
            s.contact, s.center = squeeze(s.contact), squeeze(s.center)
        for leg in self.legs:
            leg.hip, leg.knee, leg.foot = squeeze(leg.hip), squeeze(leg.knee), squeeze(leg.foot)
            leg.forward = Vec2(leg.forward.x * k, 0.0)

    # ----- heads -------------------------------------------------------------------------------

    def _roots(self) -> list[Vec2]:
        chest = self.segments[0]
        roots = []
        for j in range(len(self.heads)):
            k = j - 2
            roots.append(
                chest.center
                + chest.tangent * (chest.radius * 0.5 - abs(k) * 1.5)
                + chest.normal * (k * 4.5)
            )
        return roots

    def _attacking(self) -> bool:
        if self.dead:
            return False
        if self.mode is Mode.TURRET:
            return True
        if self.mode is Mode.WALK:
            return self.turn_wait <= 0.0
        if self.mode is Mode.ERUPT:
            return self.hole is not None and not self._in_cut(self.chest)
        return False

    def _update_heads(self, dt: float) -> None:
        if not self.segments:
            return
        roots = self._roots()
        attacking = self._attacking()
        prey = self._prey() if attacking else []
        for head, root in zip(self.heads, roots, strict=True):
            head.root = root
            head.cooldown -= dt
            head.commit -= dt
            if not head.neck:
                head.neck = [root] * NECK_POINTS
            if self._leaning(head):
                head.target = None
            elif attacking:
                self._choose_target(head, prey)
            else:
                head.target = None
            goal = self._head_goal(head, root)
            self._spring(head, goal, dt)
            self._push_out(head)
            self._aim(head, dt)
            self._attack(head, dt)
            pole = self._pole(head, root)
            neck = head.neck
            count = len(neck)
            neck = [
                p + (pole - p) * (0.12 * math.sin(math.pi * i / (count - 1)))
                for i, p in enumerate(neck)
            ]
            neck = [
                neck[0],
                *(
                    neck[i] + (neck[i - 1] + neck[i + 1] - neck[i] * 2.0) * 0.3
                    for i in range(1, count - 1)
                ),
                neck[-1],
            ]
            head.neck = _fabrik(neck, root, head.position, head.length / (count - 1))
            if head.neck[-1].distance_to(head.position) > 0.01:
                out = (head.position - root).normalized()
                outward = head.velocity.dot(out)
                if outward > 0.0:
                    head.velocity -= out * outward
            head.position = head.neck[-1]
            self._push_out(head)
            head.neck[-1] = head.position

    def _pole(self, head: Head, root: Vec2) -> Vec2:
        """Where a neck bows toward: up and back, a swan's curve."""
        k = head.index - 2
        back = 0.04 * k - 0.05
        rise = 0.62 - 0.06 * abs(k)
        return root + Vec2(-self.facing * head.length * back, -head.length * rise)

    def _choose_target(self, head: Head, prey: list[Stickman]) -> None:
        root = head.root
        target = head.target
        if target is not None:
            valid = (
                target in prey
                and target.center().distance_to(root) <= head.reach * 1.1
                and self._sees(head, target.center())
            )
            if not valid:
                head.target = target = None
        if target is not None and head.commit > 0.0:
            return
        near = [
            s
            for s in prey
            if s.center().distance_to(root) <= head.reach and self._sees(head, s.center())
        ]
        head.target = min(near, key=lambda s: s.center().distance_to(root), default=None)
        head.commit = FOE_COMMIT

    def _sees(self, head: Head, point: Vec2) -> bool:
        """A clear line to `point` from its neck root, from where the head is, or from
        halfway up a raised neck: a head strikes over a window's corner."""
        root = head.root
        starts = [root, head.position]
        raised = root + UP * (head.length * 0.5)
        if self._clear(root, raised):
            starts.append(raised)
        return any(self._clear(start, point) for start in starts)

    def _clear(self, a: Vec2, b: Vec2) -> bool:
        """No window between `a` and `b` (but those it's squeezed under)."""
        span = b - a
        steps = max(1, int(span.length() / 8.0))
        solid = self._solid()
        for k in range(1, steps):
            point = a + span * (k / steps)
            if any(_inside(box, point, 1.0) for box in solid):
                return False
        return True

    def _solid(self) -> list[Rect]:
        """The windows that block its heads and acid: all but those it's squeezed under."""
        over = self._over
        return [box for i, box in enumerate(self.world.boxes) if i not in over]

    def _head_goal(self, head: Head, root: Vec2) -> Vec2:
        j = head.index
        if self.dead:
            ground = self._ground_below(root)
            spread = (j - 2) * 12.0
            x = root.x + self.facing * (head.length * 0.6 + spread * 0.5) + spread
            return Vec2(x, ground - 3.0 * head.scale)
        if self.mode is Mode.DIVE and self.hole is not None:
            return self.hole.point - self.hole.normal * 10.0
        if self.mode is Mode.RETRACT and self.hole is not None:
            return self.hole.point - self.hole.normal * 10.0
        if self.mode is Mode.ERUPT and self.hole is not None and self.script:
            out = self.segments[0].tangent
            across = Vec2(-out.y, out.x) * ((j - 2) * 9.0)
            return root + out * (head.length * 0.7) + across
        if self._leaning(head):
            plan = self._glob_aim
            assert plan is not None
            return Vec2(plan.lane - plan.side * 4.0, plan.top - 16.0)
        if head.chomping and head.bitten and head.chomp > CHOMP_HOLD:
            return head.impact
        if head.chomping and not head.bitten and head.target is not None:
            target = head.target
            aim = target.center().lerp(target.contact(), 0.4)
            toward = (aim - root).normalized()
            if head.chomp > CHOMP_STRIKE:
                goal = root + UP * (head.length * 0.72) + toward * (head.length * 0.12)
            else:
                goal = aim + toward * 10.0
            return self._keep_out(goal)
        if head.target is not None:
            aim = head.target.center()
            to = aim - root
            distance = to.length()
            reach = clamp(distance - SPRAY_RANGE * 0.45, head.length * 0.45, head.length * 0.85)
            way = to.normalized()
            fan = Vec2(-way.y, way.x) * ((j - 2) * 11.0 * self.facing)
            goal = root + way * reach + UP * 10.0 + fan
        else:
            angle = -math.pi / 2 + self.facing * REST_ANGLES[j]
            goal = root + Vec2.from_angle(angle, head.length * REST_REACH[j])
            f1, f2, p1, p2 = head.sway
            t = self.clock
            goal += Vec2(math.sin(t * f1 + p1), math.sin(t * f2 + p2) * 0.8) * SWAY
        if head.spraying:
            u = 1.0 - head.spray / SPRAY_TIME
            goal -= Vec2.from_angle(head.angle, RECOIL * math.sin(math.pi * u))
        return self._keep_out(goal)

    def _leaning(self, head: Head) -> bool:
        """The big head is leaning over an edge to drop a glob."""
        return head.index == 2 and self.globbing > 0.0 and self._glob_aim is not None

    def _keep_out(self, point: Vec2) -> Vec2:
        world = self.world
        x = clamp(point.x, world.left + 6.0, world.width - 6.0)
        point = Vec2(x, min(point.y, world.floor_y - 4.0))
        for box in self._solid():
            if box.contains(point):
                options = (
                    Vec2(box.left - 3.0, point.y),
                    Vec2(box.right + 3.0, point.y),
                    Vec2(point.x, box.top - 4.0),
                    Vec2(point.x, min(box.bottom + 4.0, world.floor_y - 4.0)),
                )
                point = min(options, key=point.distance_to)
        return point

    def _push_out(self, head: Head) -> None:
        """Out of any window it has swung into (but not the one its hole is in), losing
        the speed that took it in."""
        own = self.hole.box if self.hole is not None else -1
        p = head.position
        for index, box in enumerate(self.world.boxes):
            if index == own or index in self._over or not _inside(box, p, 0.0):
                continue
            exits = (
                (p.x - box.left, Vec2(box.left - 0.5, p.y), Vec2(-1.0, 0.0)),
                (box.right - p.x, Vec2(box.right + 0.5, p.y), Vec2(1.0, 0.0)),
                (p.y - box.top, Vec2(p.x, box.top - 0.5), Vec2(0.0, -1.0)),
                (box.bottom - p.y, Vec2(p.x, box.bottom + 0.5), Vec2(0.0, 1.0)),
            )
            _, p, out = min(exits, key=lambda e: e[0])
            inward = head.velocity.dot(out)
            if inward < 0.0:
                head.velocity -= out * inward
        world = self.world
        if not world.left + 2.0 <= p.x <= world.width - 2.0:
            p = Vec2(clamp(p.x, world.left + 2.0, world.width - 2.0), p.y)
            head.velocity = Vec2(0.0, head.velocity.y)
        floor = world.floor_y - 0.5
        if p.y > floor and own is not None:
            p = Vec2(p.x, floor)
            head.velocity = Vec2(head.velocity.x, min(0.0, head.velocity.y))
        head.position = p

    def _ground_below(self, point: Vec2) -> float:
        tops = [
            box.top
            for box in self.world.boxes
            if box.left <= point.x <= box.right and box.top >= point.y - 2.0
        ]
        return min([self.world.floor_y, *tops])

    def _spring(self, head: Head, goal: Vec2, dt: float) -> None:
        stiffness = HEAD_STIFFNESS * (0.35 if self.dead else 1.0)
        if self.mode in (Mode.DIVE, Mode.RETRACT):
            stiffness *= 1.6
        if head.chomping and CHOMP_HOLD < head.chomp <= CHOMP_STRIKE:
            stiffness *= CHOMP_STIFFNESS
        damping = 2.0 * HEAD_DAMPING * math.sqrt(stiffness)
        accel = (goal - head.position) * stiffness - head.velocity * damping
        head.velocity += accel * dt
        head.position += head.velocity * dt

    def _aim(self, head: Head, dt: float) -> None:
        neck = head.neck
        along = (head.position - neck[-2]).angle() if len(neck) > 1 else head.angle
        leaning = self._leaning(head)
        if leaning:
            desired = math.pi / 2 - self.facing * 0.25
        elif head.target is not None:
            desired = (head.target.center() - head.position).angle()
        elif self.dead:
            desired = along
        else:
            level = 0.0 if self.facing > 0 else math.pi
            desired = along + math.remainder(level + self.facing * 0.3 - along, math.tau) * 0.85
        turn = math.remainder(desired - head.angle, math.tau)
        head.angle += turn * min(1.0, HEAD_TURN * dt)
        winding_up = head.target is not None and head.cooldown < WIND_UP
        if leaning:
            opening = 1.0
        elif head.chomping:
            opening = 0.0 if head.bitten else 1.0
        else:
            opening = 1.0 if head.spraying else 0.4 if winding_up else 0.0
        rate = 40.0 if head.chomping and head.bitten else 12.0
        head.mouth += (opening - head.mouth) * min(1.0, dt * rate)

    def _close(self, head: Head, target: Stickman) -> bool:
        return target.center().distance_to(head.root) <= head.length * CHOMP_REACH

    def _attack(self, head: Head, dt: float) -> None:
        """Chomp a foe within neck reach, spray acid at one farther off. Each head has
        its own `ATTACK_COOLDOWN`; no two heads start within `ATTACK_GAP`."""
        target = head.target
        if self._leaning(head):
            return
        if head.spraying:
            head.spray -= dt
            self._emit(head, dt)
            return
        if head.chomping:
            head.chomp -= dt
            if not head.bitten and head.chomp <= CHOMP_BITE:
                head.bitten = True
                self._bite(head)
            return
        if target is None or head.cooldown > 0.0 or self.attack_gap > 0.0:
            return
        mouth = head.mouth_point
        if not self._clear(mouth, target.center()):
            return
        if self._close(head, target):
            head.chomp = CHOMP_TIME
            head.bitten = False
            self.chomps += 1
        else:
            aim = target.center() - mouth
            if aim.length() > SPRAY_RANGE:
                return
            if abs(math.remainder(aim.angle() - head.angle, math.tau)) > SPRAY_AIM:
                return
            head.spray = SPRAY_TIME
            head.due = 0.0
            self.sprays += 1
        head.cooldown = ATTACK_COOLDOWN
        self.attack_gap = ATTACK_GAP

    def _bite(self, head: Head) -> None:
        """The slam lands: the head stops dead where it hit, the jaws snap shut on
        everyone round them, and on the ground it throws up dirt."""
        head.impact = head.position
        head.velocity = ZERO
        mouth = head.mouth_point
        radius = CHOMP_RADIUS * head.scale
        world = self.world
        ground = self._ground_below(mouth)
        if ground - mouth.y < radius + 6.0:
            spot = Vec2(mouth.x, ground)
            world.debris.burst(spot, UP, 8, 170.0, spread=1.1, puffs=3, scale=0.8)
        for stickman in world.stickmen:
            if not stickman.prey or not stickman.hits(mouth, radius):
                continue
            push = Vec2.from_angle(head.angle, 240.0) + Vec2(0.0, -140.0)
            if stickman.hurt_from(self, CHOMP_DAMAGE, mouth, push, "hydra", CHOMP_DEATH):
                self.kills += 1

    def _emit(self, head: Head, dt: float) -> None:
        rng = self.world.random
        head.due += ACID_RATE * dt
        mouth = head.mouth_point
        while head.due >= 1.0:
            head.due -= 1.0
            direction = Vec2.from_angle(head.angle + rng.gauss(0.0, 0.13))
            self.acid.append(Flame(mouth, direction * (ACID_SPEED * rng.uniform(0.8, 1.1))))

    # ----- acid ----------------------------------------------------------------------------------

    def _update_acid(self, dt: float) -> None:
        rng = self.world.random
        if self.wisps:
            self.wisps = step_motes(self.wisps, dt, rng)
        if not self.acid:
            return
        world = self.world
        drag = math.exp(-ACID_DRAG * dt)
        solid = self._solid()
        alive = []
        for flame in self.acid:
            flame.age += dt
            flame.velocity = flame.velocity * drag + Vec2(0.0, 60.0 * dt)
            flame.position += flame.velocity * dt
            point = flame.position
            if point.y >= world.floor_y:
                self.wisps += splash(Vec2(point.x, world.floor_y), 2.0, rng)
                continue
            box = next((b for b in solid if b.contains(point)), None)
            if box is not None:
                spot = Vec2(point.x, box.top) if point.y - box.top < 10.0 else point
                if rng.random() < 0.5:
                    self.wisps += splash(spot, 1.6, rng)
                continue
            if flame.age >= ACID_LIFE:
                if rng.random() < 0.35:
                    ground = self._ground_below(point)
                    velocity = Vec2(flame.velocity.x * 0.3, max(0.0, flame.velocity.y * 0.3))
                    self.wisps.append(
                        Mote("drip", point, velocity, 3.0, rng.uniform(1.0, 1.6), floor=ground)
                    )
                continue
            alive.append(flame)
        self.acid = alive
        for stickman in world.stickmen:
            if not stickman.prey:
                continue
            center = stickman.center()
            for flame in alive:
                radius = flame.radius * 0.8
                if center.distance_to(flame.position) < 26.0 + radius and stickman.hits(
                    flame.position, radius * 0.6
                ):
                    push = flame.velocity.normalized() * 160.0 + Vec2(0.0, -100.0)
                    if stickman.hurt_from(
                        self,
                        ACID_DAMAGE,
                        stickman.center(),
                        push,
                        "hydra",
                        DEATH,
                        bleed=False,
                    ):
                        stickman.succumb("acid")
                        self.kills += 1
                    break

    # ----- death ---------------------------------------------------------------------------------

    def die(self, point: Vec2, push: Vec2) -> None:
        """Go limp where it is: the chest sinks onto the trail, the heads flop down."""
        self.dead = True
        self.down_time = 0.0
        self.script = []
        self.speed = 0.0
        self.foe = None
        for head in self.heads:
            head.target = None
            head.stop()
            head.velocity += push * 0.2
        self._set_mode(Mode.DEAD)

    def update_dead(self, dt: float) -> None:
        self.down_time += dt
        self.clock += dt
        self._update_acid(dt)
        self._update_glob(dt)
        if not self.segments:
            return
        self._pose(dt)
        self._update_heads(dt)

    # ----- terrain -------------------------------------------------------------------------------

    def terrain_changed(self, change: TerrainChange) -> None:
        lost_lead = self._carry_nodes(self.nodes, change)
        lost_script = self._carry_nodes(self.script, change)
        lost_hole = self._carry_exit("hole", change)
        lost_exit = self._carry_exit("exit", change)
        if lost_exit:
            self.exit = None
        if self.dead:
            if lost_hole:
                self.hole = None
            return
        self._route_steps = []
        self._replan = 0.0
        mode = self.mode
        if mode is Mode.UNDER:
            return
        if mode is Mode.FALL:
            self._fall_to = None
            return
        if mode is Mode.DIVE:
            if lost_hole or lost_lead:
                self.hole = self.hole or Exit(self.lead, None, UP, self.facing)
                self._go_under()
            return
        if mode is Mode.RETRACT:
            if lost_hole:
                self._go_under()
            return
        if lost_hole and mode in (Mode.ERUPT, Mode.TURRET):
            self._start_fall()
            return
        if lost_hole:
            self.hole = None
        if self.script:
            if lost_script:
                self._start_fall()
            return
        if mode is Mode.TURRET:
            return
        anchor = self._anchor_at(self.lead)
        if lost_lead or anchor is None:
            self._start_fall()
            return
        self.support = anchor.surface
        if anchor.point.distance_to(self.lead) > 1e-6:
            self.nodes[-1].point = anchor.point

    def _carry_nodes(self, nodes: list[Node], change: TerrainChange) -> bool:
        """Carry each node along with its window; True if the last one's window closed."""
        lost = False
        for k, node in enumerate(nodes):
            if change.removed(node.box):
                node.box = None
                lost = lost or k == len(nodes) - 1
                continue
            delta = change.delta_for(node.box)
            if delta is not None:
                node.point += delta
            node.box = change.new_index(node.box)
        return lost

    def _carry_exit(self, name: str, change: TerrainChange) -> bool:
        exit_: Exit | None = getattr(self, name)
        if exit_ is None:
            return False
        if change.removed(exit_.box):
            return True
        delta = change.delta_for(exit_.box)
        point = exit_.point + delta if delta is not None else exit_.point
        moved = Exit(point, change.new_index(exit_.box), exit_.normal, exit_.facing, exit_.out)
        setattr(self, name, moved)
        return False
