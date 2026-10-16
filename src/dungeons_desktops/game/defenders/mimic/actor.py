"""The mimic: a treasure chest that isn't.

Disguised (`Mode.CHEST`) it sits on a window top or the floor, drawn front-on, and to
the adventurers it's just a chest: it isn't one of the world's monsters, can't be
targeted or hit, and nobody goes after it. Now and then its lid twitches.

Every `LURE_EVERY` it baits its marks: the `LURE_COUNT` nearest adventurers who can walk
up beside it (skipping anyone who can't, swapping the farthest for a clearly nearer one
until he's within `LURE_COMMIT`). Each gets a "!" over his head and runs over
(`Stickman.lure`), ignoring the monsters on the way. The first there springs the trap;
the rest are let go (no "!", no haste) once it's out of its disguise, or as soon as they
arrive while it's busy, right there to fight it. Beside it (`Mode.OPEN`) he stows his weapon
(`STOW_TIME`), bends and reaches for the lid (`REACH_TIME`), lifts it a crack, gold
light spilling out (`LIFT_TIME`)... and the trap springs: its lid flies open, its tongue
shoots out and wraps round him, reels him up over its mouth and he's swallowed whole
(`CHOMP_DAMAGE`, always deadly), its lid snapping shut on a gulp.

Then it's revealed (`Mode.REVEAL`): it flips side-on (drawn flat, see `scales`), the
lid now a toothy jaw opening forward. On floors and window tops it hops (`Gait`); to
climb walls and undersides on its own terrain and planner (`world.mimic_planner`) eight
IK spider legs burst out of it (`mimic_legs.LegRig`), folding away again back on top.
It chases the nearest adventurer (sticking to him for `FOE_COMMIT`). Within `LEAP_RANGE`
it crouches and leaps at him jaws wide (a short hop under `HOP_RANGE`), chomping him on
contact for `LEAP_DAMAGE`, but only when where it lands puts him in its jaws' reach;
hanging under an underside up close, where it can't hop, it snaps from where it is.
Now it's a monster like any other.

`CAMO_COOLDOWN` after the reveal it disguises again: right where it is if that's a
floor or window top an adventurer can walk up to, else it first scuttles to the
nearest such spot. It closes its mouth and turns front-on
(`Mode.HIDE`), and `LURE_DELAY` later the next mark gets his "!".

With `MIMIC_HP` gone (only while revealed) its legs crumple, its lid falls open and a
few coins spill out.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.game.actors.hunting import Hunt
from dungeons_desktops.game.actors.mortal import Mortal
from dungeons_desktops.game.actors.movement import RouteFollower
from dungeons_desktops.game.defenders.mimic.legs import LegRig
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
from dungeons_desktops.rig.ik import solve_two_bone
from dungeons_desktops.rig.skeleton import Pose, forward_kinematics

if TYPE_CHECKING:
    from dungeons_desktops.game.adventurers.actor import Stickman
    from dungeons_desktops.game.world.simulation import SimWorld

MIMIC_HP = 8

GRAVITY = 1100.0
CHEST_WIDTH = 20.0
"""Across its front face (the lock in the middle)."""
CHEST_DEPTH = 14.0
"""Front to back (its length side-on)."""
BOX_HEIGHT = 9.0
LID_HEIGHT = 3.0
"""The lid's front edge..."""
LID_ARCH = 3.0
"""...and how much higher its rounded top rises."""
HEIGHT = BOX_HEIGHT + LID_HEIGHT + LID_ARCH
LEG_LIFT = 7.0
"""How high its legs hold it off a wall or underside (on floors it hops, legless)."""

MOVES = MoveSettings(
    walk_speed=105.0,
    climb_speed=88.0,
    hang_speed=80.0,
    mantle_time=0.3,
    grab_time=0.32,
    swing_time=0.36,
    max_drop=320.0,
    max_hang_drop=1000.0,
    max_jump=90.0,
    gravity=GRAVITY,
    edge_clearance=4.0,
)
"""Its scuttle. Like the displacer beast's terrain: whole walls, a shallow corner over a
window top, undersides right at a window's bottom edge."""
HANG_REACH = 0.0
MANTLE_DEPTH = 6.0
HANG_DEPTH = 0.0
CLEARANCE = HEIGHT + LEG_LIFT + 3.0
"""Surfaces with another window closer than this (its body's room) are left out."""

LURE_EVERY = 0.4
LURE_COUNT = 3
"""How many adventurers it baits at once."""
LURE_DELAY = 1.5
"""After it disguises, how long before the next mark gets his "!"."""
LURE_SWITCH = 0.7
"""Another adventurer nearer than this fraction of the mark's distance takes his place..."""
LURE_COMMIT = 60.0
"""...until the mark is this close."""
LURE_IGNORE = 4.0
"""An adventurer who can't get to it (or got hurt on the way) isn't lured for this long."""
LURE_TRIES = 4
APPROACH = CHEST_WIDTH / 2 + 7.0
"""The mark stands this far from its middle to open it."""
ARRIVED = 5.0
STOW_TIME = 0.45
REACH_TIME = 0.35
LIFT_TIME = 0.5
CHOMP_AT = STOW_TIME + REACH_TIME + LIFT_TIME
"""When the trap springs: its lid flies open..."""
TRAP_SNAP = 0.08
TONGUE_OUT = 0.12
"""...its tongue shoots out and wraps round him..."""
REEL_TIME = 0.45
"""...reels him up over its open mouth..."""
SWALLOW_TIME = 0.25
"""...and he's swallowed whole..."""
SINK = 46.0
"""(his feet sinking this far into it, as he shrinks...)"""
SWALLOW_SCALE = 0.3
"""(...to this)."""
GULP_TIME = 0.4
"""...its lid snaps shut and it gulps him down before its legs come out."""
SPOT_TIME = 0.18
"""A rogue sees through it: he freezes a moment..."""
FLIP_TIME = 0.4
FLIP_BACK = (34.0, 26.0, 18.0, 10.0)
"""...hops back away from it (as far as these, with ground to land on)..."""
FLIP_HEIGHT = 20.0
WIND_TIME = 0.2
"""...winds up and throws a dagger at it..."""
KNIFE_TIME = 0.14
KNIFE_DAMAGE = 1
"""...which forces it out of its disguise as it hits."""
CRACK = 0.3
"""How far (radians) the mark gets the lid open."""
CHOMP_DAMAGE = 10
REVEAL_TIME = 0.6
HIDE_TIME = 0.6
TURN_TIME = 0.35
"""A quarter turn (front-on to side-on, or back) in a transition..."""
TURN_RATE = math.pi / 0.25
"""...and while scuttling (radians/s): a flat flip, squashing narrow and back."""
CAMO_COOLDOWN = 12.0
COVER_REPLAN = 0.6
COVER_PATIENCE = 8.0
"""Unable to reach a spot to disguise on for this long, it disguises on any floor."""

FOE_COMMIT = 1.5
CHASE_REPLAN = 0.35
UNREACHABLE = 2.0
STAND_OFF = CHEST_DEPTH / 2 + 7.0
"""Its middle stops this far short of its quarry (along his surface)."""
CLOSE_IN = 0.7
"""Waiting this long at its stand-off spot with its quarry out of reach, it closes in."""
GOAL_SNAP = 80.0
BITE_REACH = 13.0
"""Past its front."""
LEAP_DAMAGE = 4
LEAP_RANGE = 150.0
"""It leap-chomps a quarry this near (a short hop-chomp under `HOP_RANGE`)."""
HOP_RANGE = 50.0
LEAP_GAP = 12.0
"""It aims to land this far short of him, along his surface."""
CROUCH_TIME = 0.2
HOP_CROUCH = 0.12
LAND_TIME = 0.25
LEAP_COOLDOWN = 1.4
LEAP_PACE = 650.0
MAX_LEAP_SPEED = 900.0
SNAP_TIME = 0.4
"""Hanging under an underside it can't hop: it snaps from where it is."""
CHOMP_PUSH = 150.0
LUNGE = 5.0
GAPE = 0.2
"""How far its jaw hangs open while it scuttles (1 wide open)."""
STUCK_TIME = 1.0
REST_TIME = (0.4, 1.4)
TWITCH_EVERY = (3.5, 7.0)
TWITCH_TIME = 0.35
ESCAPE_REACH = 120.0
COINS = 7
CHOMP_FLASH = 0.35
STRIDE = 7.0
DUTY = 0.6
CYCLE = STRIDE / DUTY
"""Distance per gait cycle (its feet stay planted through the stance)."""


@dataclass(frozen=True)
class Gait:
    """Its hopping rhythm: hop `length` and `height`, `air` time, then `settle` on landing
    and a `windup` squash before the next."""

    length: float
    height: float
    air: float
    settle: float
    windup: float


CHASE_GAIT = Gait(60.0, 26.0, 0.36, 0.08, 0.1)
IDLE_GAIT = Gait(44.0, 18.0, 0.32, 0.22, 0.1)
HOP_SLIDE = 3.0
"""Less than this left to go along a surface, it shuffles there instead of hopping."""
GAP_HOP = 170.0
"""It hops straight across to its quarry's floor or window top this near."""
LEGS_OUT = 7.0
LEGS_IN = 4.0
"""How fast its legs burst out (and fold away), per second."""
MOUNT_HOP = 0.55
"""Mounting a wall from a floor: this much of the move hops up to it, the rest pivots
the box round its front feet onto it."""
LEG_BURST = 0.3
"""...and its legs burst out this far into it."""
DUST_TIME = 0.35

FRONT = math.pi / 2
"""`yaw` front-on; 0 is side-on facing its +1 heading, pi its -1."""
ZERO = Vec2(0.0, 0.0)
UPRIGHT = Vec2(0.0, -1.0)


@dataclass
class Leap:
    """A leap-chomp: a ballistic arc of its feet from `start` onto `target`."""

    start: Vec2
    velocity: Vec2
    time: float
    target: Anchor
    quarry: Stickman | None
    """None for a plain hop across a gap."""
    up: Vec2
    """Its surface's way out at take-off."""
    hop: bool
    elapsed: float = 0.0
    struck: bool = False


@dataclass
class Hop:
    """A hop along a floor or window top from `start` to `end` (the route followed
    `units` further on landing)."""

    start: Vec2
    end: Vec2
    air: float
    height: float
    units: float
    elapsed: float = 0.0
    follow: bool = True


@dataclass
class Knife:
    """A rogue's dagger thrown at it, spinning, from `start`."""

    start: Vec2
    position: Vec2
    time: float = 0.0
    spin: float = 0.0


class Mode(Enum):
    CHEST = "chest"
    OPEN = "open"
    REVEAL = "reveal"
    HUNT = "hunt"
    HIDE = "hide"


@dataclass
class Coin:
    """A spilled coin, in its surface frame (x along, y up off the surface)."""

    x: float
    y: float
    vx: float
    vy: float
    spin: float


def along(up: Vec2) -> Vec2:
    """The +1 heading along a surface whose outward side is `up` (+x on a top)."""
    return Vec2(-up.y, up.x)


def roomy(planner: Planner, point: Vec2) -> bool:
    """An adventurer (on `planner`) could stand beside a chest at `point` to open it."""
    for side in (-1, 1):
        spot = Vec2(point.x + side * APPROACH, point.y)
        anchor = planner.anchor_near(spot, 3.0, walk_only=True)
        if anchor is not None and abs(anchor.point.y - point.y) < 1.0:
            return True
    return False


def _turn(start: Vec2, end: Vec2, k: float, way: int) -> Vec2:
    """The unit direction `k` of the way round from `start` to `end`; flipping right
    over, it rolls the way of `way` along its surface."""
    a = math.atan2(start.y, start.x)
    turn = (math.atan2(end.y, end.x) - a + math.pi) % math.tau - math.pi
    if abs(turn) > math.pi - 0.05:
        turn = math.pi * (way or 1)
    return Vec2.from_angle(a + turn * k)


def _mounting(step: RouteStep) -> bool:
    """Hopping from a floor or window top onto a wall it meets (an inside corner)."""
    return step.move in (Move.JUMP, Move.GRAB) and step.from_surface.walkable and step.surface.wall


def _mount_pose(step: RouteStep, t: float) -> tuple[Vec2, Vec2]:
    """Its bottom and way out `t` (0..1) through mounting a wall: a hop to just short of
    it, its front up against the wall, then a pivot round its front feet until its
    underside is on the wall."""
    n0, n1 = step.from_surface.normal, step.surface.normal
    way = _sign((-n1).dot(along(n0)))
    front0, front1 = along(n0) * way, along(n1) * way
    pivot = step.end + front1 * (CHEST_DEPTH * 0.5)
    before = pivot - front0 * (CHEST_DEPTH * 0.5)
    if t < MOUNT_HOP:
        k = t / MOUNT_HOP
        rise = (before - step.start).dot(n0)
        flat = step.start + (before - step.start - n0 * rise) * smoothstep(k)
        bump = 8.0 * 4.0 * k * (1.0 - k)
        return flat + n0 * (rise * (1.0 - (1.0 - k) ** 2) + bump), n0
    k = smoothstep((t - MOUNT_HOP) / (1.0 - MOUNT_HOP))
    up = _turn(n0, n1, k, way)
    return pivot - along(up) * way * (CHEST_DEPTH * 0.5), up


def _sign(value: float) -> int:
    return 1 if value >= 0.0 else -1


def _approach(value: float, target: float, rate: float, dt: float) -> float:
    step = rate * dt
    if abs(target - value) <= step:
        return target
    return value + step if target > value else value - step


class Mimic(Mortal):
    max_hp = MIMIC_HP
    linger = 3.0

    def __init__(self, world: SimWorld, anchor: Anchor, heading: int = 1) -> None:
        self.world = world
        self.follower: RouteFollower | None = None
        """Its route while it's on a surface; None falling."""
        self.position = anchor.point
        """Its bottom middle (or its feet), on a surface."""
        self.up = UPRIGHT
        self.velocity = ZERO
        self.heading = heading
        """+1 or -1: which way along its surface it faces side-on (see `along`)."""
        self.mode = Mode.CHEST
        self.mode_time = 0.0
        self._from = (FRONT, 0.0, 0.0)
        """Yaw, rise and jaw when the current transition started."""
        self.baited: list[Stickman] = []
        """The adventurers it's luring, on their way over."""
        self.victim: Stickman | None = None
        """The one who got there first, opening it."""
        self.victim_side = 1
        """Which side of it he opens it from."""
        self._bait_damage: dict[Stickman, int] = {}
        self._chomped = False
        """The trap's sprung."""
        self._gulped = False
        self._caught_at = 0.0
        self._gulped_at = 0.0
        self.spotter: Stickman | None = None
        """A rogue who's seen through it, hopping back to throw a dagger at it."""
        self._spot_time = 0.0
        self._flip_from = ZERO
        self._flip_to: Anchor | None = None
        self.knife: Knife | None = None
        """His dagger, flying at it."""
        self.exposures = 0
        self._lure_wait = 0.5
        self._ignored: dict[Stickman, float] = {}
        self.camo_left = 0.0
        self.hunt = Hunt(FOE_COMMIT)
        self.target: Stickman | None = None
        self.attack: str | None = None
        """"crouch" for a leap, "land" from one, or "snap" (see `SNAP_TIME`)."""
        self.attack_time = 0.0
        self.pending: Leap | None = None
        self.leap: Leap | None = None
        """In the air on a leap-chomp."""
        self._snapped = False
        self.bite_wait = 0.0
        self.goal: Vec2 | None = None
        self._covering = 0.0
        self._idle = 0.0
        self._replan_wait = 0.0
        self._still = 0.0
        self.rest = 0.5
        self.lures = 0
        self.chomps = 0
        self.bites = 0
        """Leap- and hop-chomps that landed."""
        self.leaps = 0
        self.hop: Hop | None = None
        """In the air on a hop along its surface."""
        self.hop_ground = 0.0
        """Seconds since it last landed."""
        self.hurry = False
        self.tongue_tip: Vec2 | None = None
        """Where its tongue's tip is, out after its mark (None: in its mouth)."""
        self._tongued: Stickman | None = None
        self.caught: Stickman | None = None
        """Who it's reeling in on its tongue to swallow."""
        self._reel_from = ZERO
        self._last_move: Move | None = None
        # Animation state (read by the renderer).
        self.time = 0.0
        self.yaw = FRONT
        self.rise = 0.0
        """0 a chest to 1 a monster (eye open, jaw agape)."""
        self.legs = 0.0
        """0 folded away to 1 out (on walls and undersides)."""
        self.rig = LegRig()
        """Its spider legs' IK (out on walls and undersides)."""
        self.gulp = 0.0
        """1 as it gulps its mark down, easing to 0."""
        self.bounce = 0.0
        """Squash (+) and stretch (-) of its hops."""
        self.dust = DUST_TIME
        self.dust_at = anchor.point
        self.jaw = 0.0
        """0 shut to 1 wide open (its lid swung up as a jaw)."""
        self.crack = 0.0
        """The lid lifted by the mark (radians)."""
        self.lunge = 0.0
        self.crouch = 0.0
        self.tuck = 0.0
        """Legs drawn in, mid-leap."""
        self.tilt = 0.0
        """Lurching at its mark as it chomps (radians, toward `victim_side`)."""
        self.phase = 0.0
        self.speed = 0.0
        self.twitch = 0.0
        self._twitch_wait = world.random.uniform(*TWITCH_EVERY)
        self.chomp = 0.0
        """1 at a chomp, easing to 0."""
        self.chomp_at = anchor.point
        self.chomp_word = ""
        self.crumple = 0.0
        self.coins: list[Coin] = []
        self._attach(anchor)

    # ----- what the world sees -----------------------------------------------------

    @property
    def planner(self) -> Planner:
        return self.world.mimic_planner

    @property
    def revealed(self) -> bool:
        """Out of its disguise: a monster the adventurers can see, target and hit."""
        return self.mode in (Mode.REVEAL, Mode.HUNT, Mode.HIDE)

    @property
    def support(self) -> Surface | None:
        return self.follower.current_anchor().surface if self.follower is not None else None

    @property
    def lift(self) -> float:
        return self.legs * LEG_LIFT * (1.0 - 0.7 * self.crumple) * (1.0 - 0.5 * self.crouch)

    def center(self) -> Vec2:
        return self.position + self.up * (self.lift + HEIGHT * 0.5)

    def forward(self) -> Vec2:
        return along(self.up) * self.heading

    def mouth(self) -> Vec2:
        """Its open mouth: the top of the chest front-on, the front of its jaws side-on."""
        if self.mode in (Mode.CHEST, Mode.OPEN):
            return self.position + self.up * (BOX_HEIGHT + 1.5)
        return (
            self.position
            + self.up * (self.lift + BOX_HEIGHT)
            + self.forward() * (CHEST_DEPTH * 0.5)
        )

    @property
    def airborne(self) -> bool:
        """Mid-hop or mid-move between surfaces (not to be re-routed)."""
        follower = self.follower
        return self.hop is not None or (follower is not None and follower.in_transition)

    def scales(self) -> tuple[float, float]:
        """How wide it's drawn front-on (0..1) and side-on (-1..1, + facing its +1
        heading). Hunting it turns round flat, the side view squashing narrow and back
        mirrored; revealing (and hiding) the front view squashes narrow before the side
        view widens (and the other way round)."""
        c = math.cos(self.yaw)
        if self.mode in (Mode.CHEST, Mode.OPEN):
            return 1.0, 0.0
        if self.mode is Mode.HUNT:
            return 0.0, c
        k = abs(c)
        return clamp(1.0 - 2.0 * k, 0.0, 1.0), clamp(2.0 * k - 1.0, 0.0, 1.0) * _sign(c)

    def half_width(self) -> float:
        front, side = self.scales()
        return max(CHEST_WIDTH * 0.5 * front, CHEST_DEPTH * 0.5 * abs(side), 2.0)

    def parts(self) -> list[Vec2]:
        center = self.center()
        way = along(self.up) * self.half_width()
        return [center, center + way, center - way]

    def hits(self, point: Vec2, margin: float = 0.0) -> bool:
        rel = point - self.position
        x = rel.dot(along(self.up))
        y = rel.dot(self.up)
        low = self.lift
        return abs(x) <= self.half_width() + margin and low - margin <= y <= low + HEIGHT + margin

    def holds(self, stickman: Stickman) -> bool:
        """`stickman` is still one of its marks (it's alive, here, and luring him)."""
        return (
            not self.dead
            and (self.victim is stickman or stickman in self.baited)
            and self in self.world.mimics
            and self.mode in (Mode.CHEST, Mode.OPEN)
        )

    def lid_grip(self, side: int) -> Vec2:
        """Where the mark takes hold of the lid's corner on his `side` of it (front-on)."""
        lifted = CHEST_DEPTH * math.sin(self.crack) * 0.55
        local_x = side * CHEST_WIDTH * 0.42
        local_y = BOX_HEIGHT + 1.0 + lifted
        return self.position + along(self.up) * local_x + self.up * local_y

    # ----- simulation --------------------------------------------------------------

    def update(self, dt: float) -> None:
        self.time += dt
        self.mode_time += dt
        self.chomp = max(0.0, self.chomp - dt / CHOMP_FLASH)
        self.bite_wait -= dt
        self.gulp = max(0.0, self.gulp - dt / GULP_TIME)
        self.dust += dt
        if self.revealed:
            self.camo_left -= dt
        if self.knife is not None:
            self._fly_knife(dt)
        if self.leap is not None:
            self._fly(dt)
        elif self.follower is None:
            self._fall(dt)
        elif self.mode is Mode.CHEST:
            self._disguised(dt)
        elif self.mode is Mode.OPEN:
            self._open(dt)
        elif self.mode is Mode.HUNT:
            self._hunt(dt)
        else:
            self.speed = _approach(self.speed, 0.0, 400.0, dt)
        self._transitions()
        self._animate(dt)
        self._step_legs(dt)

    # ----- disguised ---------------------------------------------------------------

    def _disguised(self, dt: float) -> None:
        self.speed = 0.0
        self._twitch_wait -= dt
        if self._twitch_wait <= 0.0:
            self._twitch_wait = self.world.random.uniform(*TWITCH_EVERY)
            self.twitch = 1.0
        if self.spotter is not None:
            self._shed_arrivals()
            self._spotted(dt)
            return
        support = self.support
        if support is None or not support.walkable:
            return
        self._lure(dt)

    def _lure(self, dt: float) -> None:
        self._ignored = {s: t - dt for s, t in self._ignored.items() if t > dt}
        self._drop_unfit()
        first = next((s for s in self.baited if self._arrived(s)), None)
        if first is not None:
            self.baited.remove(first)
            if first.variant == "rogue":
                self._start_spotted(first)
            else:
                self._start_open(first)
            return
        self._lure_wait -= dt
        if self._lure_wait > 0.0:
            return
        self._lure_wait = LURE_EVERY
        for stickman in list(self.baited):
            follower = stickman.follower
            if not follower.moving and not follower.in_transition and not self._send(stickman):
                self._unbait(stickman, ignore=True)
        prey = sorted(
            (
                s
                for s in self.world.stickmen
                if s.prey and s.stun <= 0.0 and s not in self._ignored and s.lure is None
            ),
            key=self._distance,
        )
        tries = 0
        for stickman in prey:
            farthest = None
            if len(self.baited) >= LURE_COUNT:
                farthest = max(self.baited, key=self._distance)
                far = self._distance(farthest)
                if far < LURE_COMMIT or self._distance(stickman) >= LURE_SWITCH * far:
                    return
            if tries >= LURE_TRIES:
                return
            if stickman.follower.in_transition:
                continue
            tries += 1
            if self._send(stickman):
                if farthest is not None:
                    self._unbait(farthest)
                self._mark(stickman)
            else:
                self._ignored[stickman] = LURE_IGNORE

    def _drop_unfit(self) -> None:
        for stickman in list(self.baited):
            if not self._fit(stickman):
                self._unbait(stickman, ignore=stickman.prey)

    def _shed_arrivals(self) -> None:
        """The trap's taken: anyone else who gets there is let go to fight it."""
        self._drop_unfit()
        for stickman in list(self.baited):
            if self._arrived(stickman):
                self._unbait(stickman)

    def _distance(self, stickman: Stickman) -> float:
        return stickman.contact().distance_to(self.position)

    def _fit(self, stickman: Stickman) -> bool:
        return (
            stickman.prey
            and stickman in self.world.stickmen
            and stickman.lure is self
            and stickman.damage == self._bait_damage.get(stickman)
        )

    def _spot_for(self, stickman: Stickman) -> Anchor | None:
        """Beside it on its surface, on his side first, where he can stand."""
        first = _sign(stickman.contact().x - self.position.x)
        for side in (first, -first):
            x = self.position.x + side * APPROACH
            anchor = stickman.planner.anchor_near(Vec2(x, self.position.y), 3.0, walk_only=True)
            if anchor is not None and abs(anchor.point.y - self.position.y) < 1.0:
                return anchor
        return None

    def _send(self, stickman: Stickman) -> bool:
        """Route `stickman` to beside it; False if he can't get there."""
        spot = self._spot_for(stickman)
        if spot is None:
            return False
        start = stickman.follower.current_anchor()
        route = stickman.planner.plan(start, spot)
        if route is None:
            return False
        stickman.goal = spot.point
        stickman.follower.reset(start)
        stickman.follower.set_route(route)
        return True

    def _mark(self, stickman: Stickman) -> None:
        self.baited.append(stickman)
        self._bait_damage[stickman] = stickman.damage
        self.lures += 1
        stickman.lure = self
        stickman.lure_age = 0.0
        stickman.quarry = None
        if stickman.weapon is not None:
            stickman.weapon.cancel()

    def _arrived(self, stickman: Stickman) -> bool:
        if stickman.follower.moving:
            return False
        contact = stickman.contact()
        return (
            abs(abs(contact.x - self.position.x) - APPROACH) < ARRIVED
            and abs(contact.y - self.position.y) < 2.0
        )

    def _release(self, ignore: bool = False) -> None:
        """Free the mark opening it."""
        victim, self.victim = self.victim, None
        if victim is not None:
            self._free(victim, ignore)

    def _unbait(self, stickman: Stickman, ignore: bool = False) -> None:
        """Free a mark on his way over."""
        if stickman in self.baited:
            self.baited.remove(stickman)
        self._free(stickman, ignore)

    def _free(self, stickman: Stickman, ignore: bool) -> None:
        self._bait_damage.pop(stickman, None)
        if ignore:
            self._ignored[stickman] = LURE_IGNORE
        if stickman.lure is self:
            stickman.free_from_lure()

    def _release_all(self) -> None:
        self._release()
        for stickman in list(self.baited):
            self._unbait(stickman)

    def let_go(self) -> None:
        """Free its marks (it's leaving)."""
        self._drop_spotter()
        self._let_go_catch()
        self._release_all()

    # ----- a rogue sees through it --------------------------------------------------------

    def _start_spotted(self, rogue: Stickman) -> None:
        """Its mark is a rogue: he spots it for what it is instead of opening it."""
        self.victim = None
        self.spotter = rogue
        self._spot_time = 0.0
        self.knife = None
        contact = rogue.contact()
        away = Vec2(float(_sign(contact.x - self.position.x)), 0.0)
        self._flip_from = contact
        self._flip_to = rogue.follower.current_anchor()
        for back in FLIP_BACK:
            spot = contact + away * back
            anchor = rogue.planner.anchor_near(spot, 2.0, walk_only=True)
            if anchor is not None and abs(anchor.point.y - contact.y) < 1.0:
                self._flip_to = anchor
                break
        rogue.seize(self, Toss(rogue, self))

    def _spotted(self, dt: float) -> None:
        rogue = self.spotter
        self._spot_time += dt
        if rogue is None or not rogue.animated or rogue.reeled is not self:
            self._drop_spotter()
            return
        if self._spot_time < SPOT_TIME + FLIP_TIME + WIND_TIME:
            return
        layout = rogue.layout
        hand = rogue.transforms()[layout.arms[1].bones[-1]].end
        self.knife = Knife(hand, hand)
        self._lure_wait = LURE_DELAY
        landing = self._flip_to
        self.spotter = None
        if landing is not None:
            rogue.follower.reset(landing)
        rogue.free_from_reel(drop=False)

    def flip_feet(self, rogue: Stickman) -> Vec2 | None:
        """Where the rogue's feet are as he hops back from it (None: he's on his own)."""
        if self.spotter is not rogue or self.dead or self not in self.world.mimics:
            return None
        landing = self._flip_to.point if self._flip_to is not None else self._flip_from
        k = smoothstep(clamp((self._spot_time - SPOT_TIME) / FLIP_TIME, 0.0, 1.0))
        return self._flip_from.lerp(landing, k) + UPRIGHT * (FLIP_HEIGHT * math.sin(math.pi * k))

    def _drop_spotter(self) -> None:
        rogue, self.spotter = self.spotter, None
        if rogue is None:
            return
        self._lure_wait = LURE_EVERY
        if rogue.reeled is self:
            rogue.free_from_reel()

    def _fly_knife(self, dt: float) -> None:
        """His dagger spinning at it; when it lands it's out of its disguise."""
        knife = self.knife
        assert knife is not None
        knife.time += dt
        k = min(1.0, knife.time / KNIFE_TIME)
        target = self.center()
        knife.position = knife.start.lerp(target, k) + UPRIGHT * (3.0 * math.sin(math.pi * k))
        knife.spin = -_sign(target.x - knife.start.x) * 14.0 * knife.time
        if k < 1.0:
            return
        self.knife = None
        if self.dead:
            return
        self.exposures += 1
        if self.mode in (Mode.CHEST, Mode.OPEN):
            self._release()
            self._start_reveal()
        self.chomp, self.chomp_word, self.chomp_at = 0.5, "", target
        push = Vec2(_sign(target.x - knife.start.x) * 40.0, -20.0)
        self.world.hurt_monster(self, KNIFE_DAMAGE, target, push, ranged=True)

    # ----- the chomp -----------------------------------------------------------------

    def _start_open(self, victim: Stickman) -> None:
        self.mode = Mode.OPEN
        self.mode_time = 0.0
        self._chomped = False
        self.victim = victim
        self.victim_side = _sign(victim.contact().x - self.position.x)
        self.heading = self.victim_side
        victim.halt()
        victim.follower.facing = -self.victim_side
        victim.locomotion.upper = Fumble(victim, self)

    def _open(self, dt: float) -> None:
        self.speed = 0.0
        t = self.mode_time
        self._shed_arrivals()
        if self._chomped:
            self._swallow(t - CHOMP_AT)
            return
        victim = self.victim
        if victim is None or not self._fit(victim):
            self._release(ignore=victim is not None and victim.prey)
            self._abort_open()
            return
        self.crack = CRACK * smoothstep(clamp((t - STOW_TIME - REACH_TIME) / LIFT_TIME, 0, 1))
        if t >= CHOMP_AT:
            self._chomped = True
            self._gulped = False
            self._tongued = victim
            self.tongue_tip = self.mouth()

    def _swallow(self, s: float) -> None:
        """The trap sprung `s` seconds ago: its tongue out after its mark, reeling him in
        and swallowing him whole."""
        mouth = self.mouth()
        if self._gulped:
            if s - self._gulped_at >= GULP_TIME:
                self._start_reveal()
            return
        man = self.caught
        if man is not None:
            if man.reeled is not self or not man.animated:
                self._let_go_catch()
                self._start_reveal()
                return
            self.tongue_tip = man.center()
            squeeze = self.squeeze(man)
            if squeeze is not None:
                tip = mouth + (man.center() - mouth) * squeeze[2]
                self.tongue_tip = tip if (tip - mouth).dot(self.up) > 1.0 else None
            if s - self._caught_at >= REEL_TIME + SWALLOW_TIME:
                self._gulp_down(man, s)
            return
        man = self._tongued
        if man is None or not man.animated or man.lure is not self:
            self._let_go_catch()
            self._start_reveal()
            return
        k = clamp((s - TRAP_SNAP) / TONGUE_OUT, 0.0, 1.0)
        self.tongue_tip = mouth.lerp(man.center(), k)
        if k < 1.0:
            return
        self._release()
        man.seize(self, Flail(man))
        self.caught = man
        self._caught_at = s
        self._reel_from = man.contact()

    def reel_feet(self, man: Stickman) -> Vec2 | None:
        """Where `man`'s feet are as its tongue reels him up over its mouth and he sinks
        into it, or as a rogue hops back from it (None: it let go)."""
        if man is self.spotter:
            return self.flip_feet(man)
        if self.dead or self.caught is not man or self.mode is not Mode.OPEN:
            return None
        if self not in self.world.mimics:
            return None
        r = self.mode_time - CHOMP_AT - self._caught_at
        mouth = self.mouth()
        if r < REEL_TIME:
            k = smoothstep(clamp(r / REEL_TIME, 0.0, 1.0))
            return self._reel_from.lerp(mouth, k) + self.up * (16.0 * math.sin(math.pi * k))
        q = smoothstep(clamp((r - REEL_TIME) / SWALLOW_TIME, 0.0, 1.0))
        return mouth - self.up * (SINK * q)

    def squeeze(self, man: Stickman) -> tuple[Vec2, Vec2, float] | None:
        """Drawing `man` going down: its mouth, its way out (he's hidden past the mouth)
        and how small he's shrunk; None unless it's swallowing him."""
        if self.caught is not man or self.mode is not Mode.OPEN:
            return None
        r = self.mode_time - CHOMP_AT - self._caught_at
        q = smoothstep(clamp((r - REEL_TIME) / SWALLOW_TIME, 0.0, 1.0))
        if r < REEL_TIME:
            return None
        return self.mouth(), self.up, 1.0 - (1.0 - SWALLOW_SCALE) * q

    def _gulp_down(self, man: Stickman, s: float) -> None:
        """He's in: gone for good, and its lid snaps shut."""
        self.caught = None
        self.tongue_tip = None
        self._tongued = None
        self._gulped = True
        self._gulped_at = s
        man.free_from_reel(drop=False)
        point = self.mouth()
        self.chomp = 1.0
        self.chomp_word = "GULP!"
        self.chomp_at = point
        self.chomps += 1
        self.gulp = 1.0
        death = "Swallowed whole by a mimic!"
        man.hurt_from(self, max(CHOMP_DAMAGE, man.hp), point, ZERO, "mimic", death, bleed=False)
        man.swallowed = True
        self._lure_wait = LURE_DELAY

    def _let_go_catch(self) -> None:
        """Drop whoever its tongue has hold of."""
        man = self.caught
        self.caught = None
        self.tongue_tip = None
        self._tongued = None
        if man is not None and man.reeled is self:
            man.free_from_reel()

    def _abort_open(self) -> None:
        self.mode = Mode.CHEST
        self.mode_time = 0.0
        self._lure_wait = LURE_EVERY

    def _start_reveal(self) -> None:
        self._let_go_catch()
        self._release_all()
        self.mode = Mode.REVEAL
        self.mode_time = 0.0
        self._from = (self.yaw, self.rise, self.jaw)
        self.camo_left = CAMO_COOLDOWN
        self.hunt = Hunt(FOE_COMMIT)
        self.bite_wait = 0.4

    def _start_hide(self) -> None:
        self.mode = Mode.HIDE
        self.mode_time = 0.0
        self._from = (self.yaw, self.rise, self.jaw)
        self.attack = None
        self.target = None
        self.goal = None
        if self.follower is not None and not self.follower.in_transition:
            self.follower.reset(self.follower.current_anchor())

    def _transitions(self) -> None:
        if self.mode is Mode.REVEAL and self.mode_time >= REVEAL_TIME:
            self.mode = Mode.HUNT
            self.mode_time = 0.0
        elif self.mode is Mode.HIDE and self.mode_time >= HIDE_TIME:
            self.mode = Mode.CHEST
            self.mode_time = 0.0
            self.yaw, self.rise, self.jaw = FRONT, 0.0, 0.0
            self._lure_wait = LURE_DELAY
            self._covering = 0.0

    # ----- revealed --------------------------------------------------------------------

    def _hunt(self, dt: float) -> None:
        if self.attack is not None:
            self._attacking(dt)
            return
        self.hurry = True
        if self.camo_left <= 0.0:
            self._seek_cover(dt)
            self._move(dt)
            return
        prey = [s for s in self.world.stickmen if s.prey]
        target = self.hunt.update(dt, self.center(), prey)
        self.target = target
        if target is None:
            self.hurry = False
            self._wander(dt)
            self._move(dt)
            return
        follower = self.follower
        assert follower is not None
        settled = not self.airborne
        reaches = settled and self._reaches(target)
        way = _sign((target.center() - self.center()).dot(along(self.up)))
        distance = target.center().distance_to(self.center())
        if reaches:
            if follower.moving:
                follower.reset(follower.current_anchor())
                self._settle()
            self.hunt.reached()
            self.heading = way
            self.speed = _approach(self.speed, 0.0, 400.0, dt)
        facing = way == self.heading and abs(self.yaw - self._side_yaw()) < 0.3
        if settled and facing and self.bite_wait <= 0.0:
            if (reaches or distance <= LEAP_RANGE) and self._try_leap(target):
                return
            if reaches:
                self._start_attack("snap")
                return
        if reaches:
            return
        self._chase(dt, target)
        self._move(dt)

    def _reaches(
        self,
        target: Stickman,
        position: Vec2 | None = None,
        up: Vec2 | None = None,
        lift: float = 0.0,
    ) -> bool:
        """`target` within a chomp: in front of it (either way along its surface), from
        its mouth's height down to its feet; standing at `position` on a surface facing
        `up` (`lift` off it) if given."""
        if position is None or up is None:
            position, up, lift = self.position, self.up, self.lift
        center = position + up * (lift + HEIGHT * 0.5)
        way = along(up) * _sign((target.center() - center).dot(along(up)))
        mouth = center + way * (CHEST_DEPTH * 0.5)
        drop = lift + HEIGHT * 0.5 - 2.0
        return any(
            target.hits(mouth + way * (BITE_REACH * k / 4) - up * (drop * j / 2), 2.5)
            for k in range(5)
            for j in range(3)
        )

    def _start_attack(self, kind: str) -> None:
        self.attack = kind
        self.attack_time = 0.0
        self._snapped = False
        self.hop = None
        follower = self.follower
        if follower is not None and not follower.in_transition:
            follower.reset(follower.current_anchor())
            self._settle()

    def _try_leap(self, target: Stickman) -> bool:
        """Crouch for a leap (or a hop, close by) that lands where its jaws reach him."""
        follower = self.follower
        assert follower is not None
        landing = self._landing_for(target)
        if landing is None:
            return False
        hop = target.center().distance_to(self.center()) < HOP_RANGE
        arc = self._arc(self.position, landing, hop)
        if arc is None:
            return False
        velocity, time = arc
        self.pending = Leap(self.position, velocity, time, landing, target, self.up, hop)
        self.leaps += 1
        self._start_attack("crouch")
        return True

    def _landing_for(self, target: Stickman) -> Anchor | None:
        """A spot `LEAP_GAP` short of him on his surface, on its side, from which its
        jaws reach him."""
        anchor = self.planner.anchor_near(target.contact(), GOAL_SNAP)
        if anchor is None:
            return None
        surface = anchor.surface
        mid = surface.coord(anchor.point)
        edge = min(MOVES.edge_clearance, surface.length / 2)
        low, high = surface.low + edge, surface.high - edge
        spots = [surface.point_at(clamp(mid + side * LEAP_GAP, low, high)) for side in (-1, 1)]
        spots = [p for p in spots if p.distance_to(anchor.point) > LEAP_GAP * 0.5] or spots
        spot = min(spots, key=self.position.distance_to)
        if spot.distance_to(self.position) > LEAP_RANGE + 20.0:
            return None
        lift = 0.0 if surface.walkable else LEG_LIFT
        if not self._reaches(target, spot, surface.normal, lift):
            return None
        return Anchor(surface, spot)

    def _arc(self, start: Vec2, anchor: Anchor, hop: bool) -> tuple[Vec2, float] | None:
        """Launch velocity and flight time of its feet from `start` onto `anchor`, its
        body clear of every window, or None."""
        offset = anchor.point - start
        distance = offset.length()
        base = clamp((0.2 if hop else 0.24) + distance / LEAP_PACE, 0.22, 0.7)
        surface = anchor.surface
        for scale in (1.0, 0.8, 1.25, 1.5, 0.65):
            time = base * scale
            velocity = Vec2(offset.x / time, (offset.y - 0.5 * GRAVITY * time * time) / time)
            if velocity.length() > MAX_LEAP_SPEED:
                continue
            arriving = velocity.y + GRAVITY * time
            if surface.walkable and arriving < 0.0:
                continue
            if surface.hanging and arriving > 60.0:
                continue
            if self._clear(start, velocity, time, surface.normal):
                return velocity, time
        return None

    def _flight_up(self, start_up: Vec2, end_up: Vec2, k: float) -> Vec2:
        return _turn(start_up, end_up, smoothstep(k), self.heading)

    def _clear(self, start: Vec2, velocity: Vec2, time: float, end_up: Vec2) -> bool:
        world = self.world
        count = max(6, int(velocity.length() * time / 6.0))
        for i in range(1, count):
            t = time * i / count
            feet = start + velocity * t + Vec2(0.0, 0.5 * GRAVITY * t * t)
            body = feet + self._flight_up(self.up, end_up, i / count) * (LEG_LIFT + HEIGHT * 0.5)
            if not world.left <= body.x <= world.width:
                return False
            if world.ceiling is not None and body.y < world.ceiling:
                return False
            if body.y > world.floor_y:
                return False
            inner = 0.15 < i / count < 0.85
            for box in world.boxes:
                if box.contains(body) or (inner and box.contains(feet)):
                    return False
        return True

    def _attacking(self, dt: float) -> None:
        self.attack_time += dt
        self.speed = _approach(self.speed, 0.0, 400.0, dt)
        kind, t = self.attack, self.attack_time
        if kind == "crouch":
            pending = self.pending
            if pending is None or pending.quarry is None or not pending.quarry.prey:
                self.attack, self.pending = None, None
                self.bite_wait = 0.3
                return
            if t >= (HOP_CROUCH if pending.hop else CROUCH_TIME):
                self.attack = None
                self.pending = None
                pending.start = self.position
                self.leap = pending
                self.follower = None
        elif kind == "land":
            if t >= LAND_TIME:
                self.attack = None
                self.bite_wait = LEAP_COOLDOWN
        elif kind == "snap":
            target = self.target
            if not self._snapped and t >= SNAP_TIME * 0.4:
                self._snapped = True
                if target is not None and target.prey and self._reaches(target):
                    self._strike(target)
            if t >= SNAP_TIME:
                self.attack = None
                self.bite_wait = LEAP_COOLDOWN

    def _try_gap_hop(self, goal: Anchor) -> bool:
        """Hop straight across to `goal` on another floor or window top, if it's near and
        the arc there is clear."""
        follower = self.follower
        support = self.support
        if follower is None or support is None or self.airborne or not support.walkable:
            return False
        surface = goal.surface
        if surface is support or not surface.walkable:
            return False
        if goal.point.distance_to(self.position) > GAP_HOP:
            return False
        if abs(self.yaw - self._side_yaw()) > 0.05 or self.legs > 0.1:
            return False
        way = _sign(goal.point.x - self.position.x)
        if way != self.heading:
            return False
        arc = self._arc(self.position, goal, hop=False)
        if arc is None:
            return False
        velocity, time = arc
        self.leap = Leap(self.position, velocity, time, goal, None, self.up, False)
        self.follower = None
        return True

    def _strike(self, target: Stickman) -> None:
        self.bites += 1
        point = target.center()
        self.chomp = 0.6
        self.chomp_word = "chomp"
        self.chomp_at = point
        way = _sign((point - self.center()).dot(along(self.up)))
        push = along(self.up) * (way * CHOMP_PUSH) + Vec2(0.0, -CHOMP_PUSH * 0.4)
        target.hurt_from(self, LEAP_DAMAGE, point, push, "mimic", "Chomped by a mimic!")

    def _fly(self, dt: float) -> None:
        leap = self.leap
        assert leap is not None
        leap.elapsed += dt
        t = min(leap.elapsed, leap.time)
        self.position = leap.start + leap.velocity * t + Vec2(0.0, 0.5 * GRAVITY * t * t)
        self.velocity = leap.velocity + Vec2(0.0, GRAVITY * t)
        self.up = self._flight_up(leap.up, leap.target.surface.normal, t / leap.time)
        quarry = leap.quarry
        if quarry is not None and not leap.struck and quarry.prey and self._reaches(quarry):
            leap.struck = True
            self._strike(quarry)
        if leap.elapsed < leap.time:
            if any(box.contains(self.center()) for box in self.world.boxes):
                self.leap = None
            return
        self.leap = None
        if not self.planner.owns(leap.target.surface):
            return
        self._land(leap.target)
        if quarry is None:
            return
        if not leap.struck and quarry.prey and self._reaches(quarry):
            self._strike(quarry)
        if quarry.prey:
            way = (quarry.center() - self.center()).dot(along(self.up))
            self.heading = _sign(way)
        self.attack = "land"
        self.attack_time = 0.0

    def _chase(self, dt: float, target: Stickman) -> None:
        self._replan_wait -= dt
        if self._replan_wait > 0.0:
            return
        self._replan_wait = CHASE_REPLAN
        anchor = self.planner.anchor_near(target.contact(), GOAL_SNAP)
        if anchor is None:
            self.hunt.unreachable(CHASE_REPLAN, UNREACHABLE)
            return
        surface = anchor.surface
        mid = surface.coord(anchor.point)
        follower = self.follower
        assert follower is not None
        idle = not follower.moving and self.goal is not None
        if idle and self.position.distance_to(self.goal) < 2.0:
            self._idle += CHASE_REPLAN
        else:
            self._idle = 0.0
        gap = STAND_OFF * (0.45 if self._idle >= CLOSE_IN else 1.0)
        spots = [
            surface.point_at(clamp(mid + side * gap, surface.low, surface.high)) for side in (-1, 1)
        ]
        spots = [p for p in spots if p.distance_to(anchor.point) > gap * 0.5] or spots
        goal = min(spots, key=self.position.distance_to)
        if self._try_gap_hop(Anchor(surface, goal)):
            self.hunt.reached()
            return
        if self._route_to(Anchor(surface, goal)):
            self.hunt.reached()
        else:
            self.hunt.unreachable(CHASE_REPLAN, UNREACHABLE)

    def _route_to(self, goal: Anchor) -> bool:
        follower = self.follower
        assert follower is not None
        if self.airborne:
            return True
        start = follower.current_anchor()
        if goal.point.distance_to(start.point) < 1.5:
            follower.reset(start)
            self.goal = goal.point
            return True
        route = self.planner.plan(start, goal)
        if route is None:
            return False
        follower.reset(start)
        follower.set_route(route)
        self.goal = goal.point
        return True

    def _wander(self, dt: float) -> None:
        follower = self.follower
        assert follower is not None
        if follower.moving:
            return
        self.rest -= dt
        if self.rest > 0.0:
            return
        self.rest = self.world.random.uniform(*REST_TIME)
        start = follower.current_anchor()
        reachable = self.planner.reachable(start.surface)
        surfaces = [s for s in self.planner.surfaces if s.id in reachable and s.length > 1.0]
        if not surfaces:
            return
        random = self.world.random
        surface = random.choices(surfaces, weights=[s.length for s in surfaces])[0]
        self._route_to(Anchor(surface, surface.point_at(random.uniform(surface.low, surface.high))))

    # ----- going back into disguise ---------------------------------------------------

    def _seek_cover(self, dt: float) -> None:
        follower = self.follower
        assert follower is not None
        self._covering += dt
        support = self.support
        if not follower.in_transition and support is not None and support.walkable:
            turned = abs(self.yaw - self._side_yaw()) < 0.05
            settled = turned and self.hop is None and self.legs < 0.05
            if settled and (self._roomy(self.position) or self._covering >= COVER_PATIENCE):
                self._start_hide()
                return
        self._replan_wait -= dt
        if self._replan_wait > 0.0 and follower.moving:
            return
        self._replan_wait = COVER_REPLAN
        for anchor in self._covers():
            if self._route_to(anchor):
                return

    def _roomy(self, point: Vec2) -> bool:
        return roomy(self.world.planner, point)

    def _covers(self) -> list[Anchor]:
        """Floors and window tops it can get to and disguise on, nearest first."""
        follower = self.follower
        assert follower is not None
        start = follower.current_anchor()
        reachable = self.planner.reachable(start.surface)
        found = []
        here = self.center()
        for surface in self.planner.surfaces:
            if not surface.walkable or surface.id not in reachable:
                continue
            for inset in (0.0, APPROACH + 2.0):
                low, high = surface.low + inset, surface.high - inset
                if low > high:
                    continue
                point = surface.point_at(clamp(here.x, low, high))
                if self._roomy(point):
                    found.append(Anchor(surface, point))
                    break
        found.sort(key=lambda a: a.point.distance_to(here))
        return found[:4]

    # ----- moving -------------------------------------------------------------------

    def _side_yaw(self) -> float:
        return 0.0 if self.heading > 0 else math.pi

    def _move(self, dt: float) -> None:
        """Hop along floors and window tops; scuttle on its legs everywhere else."""
        follower = self.follower
        assert follower is not None
        step = follower.step
        on_top = follower.current_anchor().surface.walkable
        if self.hop is not None or (on_top and (step is None or step.move is Move.WALK)):
            self._hopping(dt)
        else:
            self._scuttle(dt)
        step = follower.step if self.follower is follower else None
        move = step.move if step is not None else None
        if self._last_move in (Move.JUMP, Move.DROP) and move not in (Move.JUMP, Move.DROP):
            if self.support is not None and self.support.walkable:
                self._landed()
        self._last_move = move

    def _gait(self) -> Gait:
        return CHASE_GAIT if self.hurry else IDLE_GAIT

    def _hopping(self, dt: float) -> None:
        follower = self.follower
        assert follower is not None
        hop = self.hop
        if hop is not None:
            hop.elapsed += dt
            k = min(1.0, hop.elapsed / hop.air)
            before = self.position
            self.up = UPRIGHT
            arc = UPRIGHT * (hop.height * 4.0 * k * (1.0 - k))
            self.position = hop.start.lerp(hop.end, k) + arc
            self.speed = _approach(self.speed, self.position.distance_to(before) / dt, 900.0, dt)
            if k >= 1.0:
                self.hop = None
                if hop.follow:
                    follower.update(hop.units)
                self._settle()
                self._landed()
            return
        self._settle()
        self.speed = _approach(self.speed, 0.0, 400.0, dt)
        self._still = 0.0
        step = follower.step
        gait = self._gait()
        if step is None or self.legs > 0.1:
            self.hop_ground = min(self.hop_ground + dt, gait.settle)
            return
        ahead = (step.end - step.start).dot(along(step.surface.normal))
        if abs(ahead) > 1e-6:
            self.heading = _sign(ahead)
        if abs(self.yaw - self._side_yaw()) > 0.05:
            self.hop_ground = min(self.hop_ground + dt, gait.settle)
            return
        self.hop_ground += dt
        if self.hop_ground < gait.settle + gait.windup:
            return
        contact = follower.contact()
        remaining = contact.distance_to(step.end)
        speed = self.planner.settings.walk_speed
        if remaining < HOP_SLIDE:
            follower.update(remaining / speed + 1e-6)
            self._settle()
            return
        length = remaining if remaining <= gait.length * 1.3 else gait.length
        end = contact + (step.end - contact) * (length / remaining)
        scale = clamp(length / gait.length, 0.5, 1.0)
        height = min(gait.height * scale, self._headroom(contact, end))
        air = gait.air * clamp(math.sqrt(length / gait.length), 0.7, 1.0)
        self.hop = Hop(contact, end, air, max(0.0, height), length / speed)
        self.hop_ground = 0.0

    def _headroom(self, a: Vec2, b: Vec2) -> float:
        """How high it can hop between `a` and `b` on a floor or window top."""
        world = self.world
        low, high = min(a.x, b.x) - CHEST_DEPTH, max(a.x, b.x) + CHEST_DEPTH
        floor = max(a.y, b.y)
        room = math.inf if world.ceiling is None else floor - world.ceiling
        for box in world.boxes:
            if box.right > low and box.left < high and box.bottom <= floor + 0.5:
                room = min(room, min(a.y, b.y) - box.bottom)
        return room - HEIGHT - 2.0

    def _landed(self) -> None:
        """Down on a floor or window top: a squash and a puff of dust."""
        self.hop_ground = 0.0
        self.dust = 0.0
        self.dust_at = self.position
        self.bounce = max(self.bounce, 0.0)

    def _scuttle(self, dt: float) -> None:
        """On its legs: along walls and undersides, and between surfaces."""
        follower = self.follower
        assert follower is not None
        step = follower.step
        if step is None:
            self.speed = _approach(self.speed, 0.0, 400.0, dt)
            self._still = 0.0
            return
        if step.move in ALONG_MOVES:
            ahead = (step.end - step.start).dot(along(step.surface.normal))
            if abs(ahead) > 1e-6:
                self.heading = _sign(ahead)
        elif _mounting(step):
            self.heading = _sign((-step.surface.normal).dot(along(step.from_surface.normal)))
        if abs(self.yaw - self._side_yaw()) > 0.8:
            self.phase += 0.6 * dt
            self.speed = _approach(self.speed, 0.0, 400.0, dt)
            return
        before = self.position
        follower.update(dt)
        self._settle()
        moved = self.position.distance_to(before)
        self.phase += moved / CYCLE
        self.speed = _approach(self.speed, moved / dt, 900.0, dt)
        if follower.moving and moved < 0.05:
            self._still += dt
            if self._still >= STUCK_TIME:
                self._still = 0.0
                if not follower.in_transition:
                    follower.reset(follower.current_anchor())
                self._replan_wait = 0.0
        else:
            self._still = 0.0

    def _settle(self) -> None:
        follower = self.follower
        assert follower is not None
        step = follower.step
        if step is None or step.move in ALONG_MOVES:
            anchor = follower.current_anchor()
            self.position, self.up = anchor.point, anchor.surface.normal
            return
        t = 1.0 if step.duration <= 0.0 else clamp(follower.elapsed / step.duration, 0.0, 1.0)
        ease = smoothstep(t)
        if _mounting(step):
            self.position, self.up = _mount_pose(step, t)
            return
        if step.from_surface.walkable and step.surface.walkable:
            self.position = follower.contact()
        else:
            self.position = step.start.lerp(step.end, ease)
        self.up = _turn(step.from_surface.normal, step.surface.normal, ease, self.heading)

    def _progress(self) -> float:
        follower = self.follower
        step = follower.step if follower is not None else None
        if step is None or step.duration <= 0.0:
            return 1.0
        return clamp(follower.elapsed / step.duration, 0.0, 1.0)

    def _attach(self, anchor: Anchor) -> None:
        self.follower = RouteFollower(anchor)
        self.velocity = ZERO
        self._replan_wait = 0.0
        self._settle()

    def _loose(self) -> None:
        """Off its surface and into a fall."""
        hop = self.hop
        self.follower = None
        self.attack = None
        self.pending = None
        self.hop = None
        self.velocity = ZERO
        if hop is not None:
            k = min(1.0, hop.elapsed / hop.air)
            rise = hop.height * 4.0 * (1.0 - 2.0 * k) / hop.air
            self.velocity = (hop.end - hop.start) * (1.0 / hop.air) + UPRIGHT * rise
        self._let_go_catch()
        self._drop_spotter()
        if self.mode is Mode.OPEN and not self._chomped:
            self._release_all()
            self._abort_open()
        elif self.mode in (Mode.OPEN, Mode.CHEST):
            self._release_all()

    def _fall(self, dt: float) -> None:
        world = self.world
        self.speed = 0.0
        before = self.position
        self.velocity += Vec2(0.0, GRAVITY * dt)
        after = before + self.velocity * dt
        half = CHEST_WIDTH * 0.5
        if not world.left + half <= after.x <= world.width - half:
            after = Vec2(clamp(after.x, world.left + half, world.width - half), after.y)
            self.velocity = Vec2(0.0, self.velocity.y)
        if world.ceiling is not None and after.y < world.ceiling + HEIGHT:
            after = Vec2(after.x, world.ceiling + HEIGHT)
            self.velocity = Vec2(self.velocity.x, max(0.0, self.velocity.y))
        self.up = self.up.lerp(UPRIGHT, min(1.0, dt * 8.0)).normalized()
        if self.velocity.y >= 0.0:
            crossed = [
                s
                for s in self.planner.surfaces
                if s.walkable
                and s.low - 1.0 <= after.x <= s.high + 1.0
                and before.y <= s.start.y + 0.5
                and after.y >= s.start.y
            ]
            if crossed:
                surface = min(crossed, key=lambda s: s.start.y)
                self._land(Anchor(surface, surface.closest_point(after)))
                return
            for box in world.boxes:
                if box.left <= after.x <= box.right and before.y <= box.top + 0.5 <= after.y + 0.5:
                    anchor = self.planner.anchor_near(Vec2(after.x, box.top), math.inf, True)
                    if anchor is not None:
                        self._land(anchor)
                        return
        for box in world.boxes:
            if box.contains(after) and not box.contains(before):
                after = Vec2(before.x, after.y)
                self.velocity = Vec2(0.0, self.velocity.y)
        if after.y >= world.floor_y:
            anchor = self.planner.anchor_near(Vec2(after.x, world.floor_y), math.inf, True)
            if anchor is not None:
                self._land(anchor)
                return
            after = Vec2(after.x, world.floor_y)
        self.position = after

    def _land(self, anchor: Anchor) -> None:
        self.leap = None
        self._attach(anchor)
        self.up = anchor.surface.normal
        if anchor.surface.walkable:
            self._landed()

    # ----- animation -------------------------------------------------------------------

    def _animate(self, dt: float) -> None:
        mode, t = self.mode, self.mode_time
        self.twitch = max(0.0, self.twitch - dt / TWITCH_TIME)
        legs = self._legs_wanted()
        self.legs = _approach(self.legs, legs, LEGS_OUT if legs > self.legs else LEGS_IN, dt)
        self.bounce = _approach(self.bounce, self._bounce_wanted(), 14.0, dt)
        if mode is Mode.REVEAL:
            yaw0, rise0, jaw0 = self._from
            turn = smoothstep(clamp((t - 0.1) / TURN_TIME, 0.0, 1.0))
            self.yaw = yaw0 + (self._side_yaw() - yaw0) * turn
            self.rise = rise0 + (1.0 - rise0) * smoothstep(clamp(t / REVEAL_TIME, 0.0, 1.0))
            self.jaw = jaw0 + (GAPE - jaw0) * smoothstep(clamp(t / REVEAL_TIME, 0.0, 1.0))
            self.tilt = _approach(self.tilt, 0.0, 2.0, dt)
            self.lunge = _approach(self.lunge, 0.0, 30.0, dt)
            self.crack = _approach(self.crack, 0.0, 2.0, dt)
            return
        if mode is Mode.HIDE:
            yaw0, rise0, jaw0 = self._from
            k = smoothstep(clamp(t / HIDE_TIME, 0.0, 1.0))
            turn = smoothstep(clamp(t / TURN_TIME, 0.0, 1.0))
            self.yaw = yaw0 + (FRONT - yaw0) * turn
            self.rise = rise0 * (1.0 - k)
            self.jaw = jaw0 * (1.0 - smoothstep(clamp(t / (HIDE_TIME * 0.7), 0.0, 1.0)))
            self.lunge = _approach(self.lunge, 0.0, 30.0, dt)
            return
        if mode is Mode.CHEST:
            self.yaw = _approach(self.yaw, FRONT, TURN_RATE, dt)
            self.rise = _approach(self.rise, 0.0, 3.0, dt)
            self.jaw = _approach(self.jaw, 0.0, 4.0, dt)
            self.crack = _approach(self.crack, 0.0, 1.5, dt)
            self.tilt = _approach(self.tilt, 0.0, 2.0, dt)
            self.lunge = _approach(self.lunge, 0.0, 30.0, dt)
            return
        if mode is Mode.OPEN:
            self.yaw = _approach(self.yaw, FRONT, TURN_RATE, dt)
            if self._chomped:
                self.crack = 0.0
                if self._gulped:
                    self.jaw = _approach(self.jaw, 0.0, 16.0, dt)
                    self.tilt = _approach(self.tilt, 0.0, 3.0, dt)
                else:
                    k = clamp((t - CHOMP_AT) / TRAP_SNAP, 0.0, 1.0)
                    self.jaw = max(self.jaw, k)
                    lurch = 0.22 if self.caught is None else 0.06
                    self.tilt = _approach(self.tilt, lurch, 5.0, dt)
            return
        # Hunting: its jaw hangs open, flapping as it hops, opening wide for a leap and
        # snapping on a chomp.
        self.yaw = _approach(self.yaw, self._side_yaw(), TURN_RATE, dt)
        self.rise = _approach(self.rise, 1.0, 3.0, dt)
        leap, kind, t = self.leap, self.attack, self.attack_time
        self.tuck = _approach(self.tuck, 1.0 if leap is not None else 0.0, 8.0, dt)
        hop = self.hop
        if hop is not None:
            k = min(1.0, hop.elapsed / hop.air)
            flap = 0.5 - 0.5 * math.cos(math.tau * 2.0 * k)
            self.jaw = _approach(self.jaw, GAPE + 0.55 * flap, 12.0, dt)
            self.crouch = _approach(self.crouch, 0.0, 10.0, dt)
            self.lunge = _approach(self.lunge, 0.0, 30.0, dt)
        elif leap is not None:
            self.crouch = _approach(self.crouch, 0.0, 10.0, dt)
            self.jaw = _approach(
                self.jaw, 0.0 if leap.struck else 1.0, 16.0 if leap.struck else 6.0, dt
            )
            self.lunge = _approach(self.lunge, 0.0, 30.0, dt)
        elif kind == "crouch":
            pending = self.pending
            k = smoothstep(
                clamp(t / (HOP_CROUCH if pending and pending.hop else CROUCH_TIME), 0, 1)
            )
            self.crouch = k
            self.jaw = max(self.jaw, GAPE + (1.0 - GAPE) * k)
        elif kind == "land":
            self.crouch = 1.0 - smoothstep(clamp(t / LAND_TIME, 0.0, 1.0))
            self.jaw = _approach(self.jaw, GAPE, 3.0, dt)
        elif kind == "snap":
            wind = SNAP_TIME * 0.4
            if t < wind:
                self.jaw = GAPE + (1.0 - GAPE) * smoothstep(t / wind)
                self.lunge = LUNGE * smoothstep(t / wind)
            else:
                k = clamp((t - wind) / 0.06, 0.0, 1.0)
                back = smoothstep(clamp((t - wind) / (SNAP_TIME - wind), 0.0, 1.0))
                self.jaw = (1.0 - k) + GAPE * back * k
                self.lunge = LUNGE * (1.0 - back)
        else:
            self.crouch = _approach(self.crouch, 0.0, 6.0, dt)
            self.jaw = _approach(self.jaw, GAPE + 0.06 * math.sin(self.time * 5.0), 3.0, dt)
            self.lunge = _approach(self.lunge, 0.0, 30.0, dt)

    def _legs_wanted(self) -> float:
        """Out on walls and undersides (bursting out partway through getting onto one),
        folded away on floors and window tops (folding in mid-air dropping onto one)."""
        if self.mode is not Mode.HUNT and self.mode is not Mode.HIDE:
            return 0.0 if self.mode is not Mode.REVEAL else self.legs
        leap = self.leap
        if leap is not None:
            k = leap.elapsed / max(leap.time, 1e-6)
            if leap.target.surface.walkable:
                return 0.0 if k > 0.3 or leap.up.y < -0.5 else self.legs
            return 1.0 if k > LEG_BURST or leap.up.y > -0.5 else self.legs
        follower = self.follower
        if follower is None:
            return 0.0
        step = follower.step
        if step is None or step.move in ALONG_MOVES:
            return 0.0 if follower.current_anchor().surface.walkable else 1.0
        if step.surface.walkable:
            if step.from_surface.walkable or step.move is Move.DROP:
                return 0.0
            return 1.0
        if step.from_surface.walkable:
            return 1.0 if self._progress() > LEG_BURST else self.legs
        return 1.0

    def _step_legs(self, dt: float) -> None:
        self.rig.update(
            dt,
            self.position,
            self.up,
            self.lift,
            self._leg_surfaces(),
            self.tuck,
            self.crumple,
        )

    def _leg_surfaces(self) -> list[Surface]:
        """What its feet can stand on: the wall or underside it's on, both surfaces
        it's crossing between (a window top only climbing onto it, the wall only
        hopping at it), nothing in the air or with its legs folded away."""
        follower = self.follower
        if self.dead or self.legs < 0.05 or follower is None or self.hop is not None:
            return []
        if self.leap is not None:
            return []
        step = follower.step
        if step is None or step.move in ALONG_MOVES:
            surface = follower.current_anchor().surface
            return [] if surface.walkable else [surface]
        if _mounting(step):
            return [step.surface]
        found = [s for s in (step.from_surface, step.surface) if not s.walkable]
        if step.move is Move.MANTLE and step.surface.walkable:
            found.append(step.surface)
        return found

    def _bounce_wanted(self) -> float:
        """Squash winding up a hop and landing from one, stretch leaving the ground."""
        if self.mode is not Mode.HUNT:
            return 0.0
        hop = self.hop
        if hop is not None:
            k = min(1.0, hop.elapsed / hop.air)
            return -0.8 * (1.0 - 2.0 * k) if k < 0.5 else -0.3 * (2.0 * k - 1.0)
        if self.leap is not None:
            k = self.leap.elapsed / max(self.leap.time, 1e-6)
            return -0.6 * (1.0 - k)
        support = self.support
        if self.legs > 0.1 or support is None or not support.walkable or self.attack:
            return 0.0
        gait = self._gait()
        g = self.hop_ground
        if g < gait.settle:
            return 0.8 * (1.0 - g / gait.settle)
        if self.target is None and self.goal is None:
            return 0.0
        follower = self.follower
        if follower is None or follower.step is None:
            return 0.0
        return 0.9 * clamp((g - gait.settle) / gait.windup, 0.0, 1.0)

    # ----- the terrain moving ----------------------------------------------------------

    def terrain_changed(self, change: TerrainChange) -> None:
        """Ride the window it's on; fall if it closes or moves out from under it."""
        before = self.position
        self._terrain_changed(change)
        moved = self.position - before
        if moved.length() < ESCAPE_REACH:
            self.rig.shift(moved)

    def _terrain_changed(self, change: TerrainChange) -> None:
        follower = self.follower
        if follower is None:
            leap = self.leap
            if change.shift is not None:
                self.position = self.position + change.shift
                if leap is not None:
                    leap.start = leap.start + change.shift
            if leap is not None:
                target = self._moved(leap.target, change)
                if target is None:
                    self.leap = None
                else:
                    leap.target = target
            self._escape()
            return
        if self.attack == "crouch":
            self.attack, self.pending = None, None
        hop = self.hop
        if hop is not None:
            end = self._moved(Anchor(follower.current_anchor().surface, hop.end), change)
            if end is None:
                self._loose()
                self._escape()
                return
            delta = end.point - hop.end
            hop.start, hop.end, hop.follow = hop.start + delta, end.point, False
            self.position = self.position + delta
            self.follower = RouteFollower(end)
            self._replan_wait = 0.0
            return
        step = follower.step
        if step is not None and follower.in_transition and self._carry_transition(step, change):
            return
        anchor = follower.current_anchor()
        moved = self._moved(anchor, change)
        if moved is None:
            self.position = self.position + (change.delta_for(anchor.surface.box) or ZERO)
            self._loose()
            self._escape()
            return
        self._attach(moved)
        if self.victim is not None or self.baited:
            self._lure_wait = 0.0

    def _escape(self) -> None:
        """Out of the window that just closed over it, onto the nearest surface."""
        center = self.center()
        if not any(box.contains(center) for box in self.world.boxes):
            return
        anchor = self.planner.anchor_near(center, ESCAPE_REACH)
        if anchor is not None:
            self._land(anchor)

    def _carry_transition(self, step: RouteStep, change: TerrainChange) -> bool:
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

    def _moved(self, anchor: Anchor, change: TerrainChange) -> Anchor | None:
        """`anchor` on the rebuilt terrain: the same kind of surface of the same window,
        carried along with it, or None if that's gone."""
        box = anchor.surface.box
        if change.removed(box):
            return None
        point = anchor.point + (change.delta_for(box) or ZERO)
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

    # ----- death -------------------------------------------------------------------------

    def die(self, point: Vec2, push: Vec2) -> None:
        self.dead = True
        self.down_time = 0.0
        self.attack = None
        self.pending = None
        self.leap = None
        self._let_go_catch()
        self._drop_spotter()
        if self.hop is not None:
            self._loose()
        self.target = None
        self._release_all()
        support = self.support
        if support is not None and not support.walkable:
            self._loose()
            self.velocity = push * 0.2 + Vec2(0.0, -40.0)
        random = self.world.random
        for _ in range(COINS):
            self.coins.append(
                Coin(
                    random.uniform(-4.0, 4.0),
                    BOX_HEIGHT,
                    random.uniform(-70.0, 70.0),
                    random.uniform(60.0, 150.0),
                    random.uniform(0.0, math.tau),
                )
            )

    def update_dead(self, dt: float) -> None:
        self.down_time += dt
        self.time += dt
        if self.follower is None:
            self._fall(dt)
        self.crumple = _approach(self.crumple, 1.0, 2.5, dt)
        self._step_legs(dt)
        self.jaw = _approach(self.jaw, 0.9, 4.0, dt)
        self.lunge = _approach(self.lunge, 0.0, 30.0, dt)
        self.tilt = _approach(self.tilt, 0.0, 2.0, dt)
        self.speed = 0.0
        for coin in self.coins:
            if coin.y <= 0.0 and coin.vy <= 0.0 and abs(coin.vx) < 1.0:
                continue
            coin.vy -= 500.0 * dt
            coin.x += coin.vx * dt
            coin.y += coin.vy * dt
            coin.spin += 12.0 * dt
            if coin.y <= 0.0:
                coin.y = 0.0
                coin.vy = -coin.vy * 0.3 if coin.vy < -40.0 else 0.0
                coin.vx *= 0.5


class Fumble:
    """A lured adventurer's upper body at the chest (an `UpperBodyLayer`): he stows his
    weapon, bends and reaches for the lid, and lifts it."""

    def __init__(self, stickman: Stickman, mimic: Mimic) -> None:
        self.stickman = stickman
        self.mimic = mimic
        self.weapon = stickman.weapon

    def apply(self, pose: Pose, mode: object, dt: float, skip: frozenset[str]) -> None:
        stickman, mimic = self.stickman, self.mimic
        layout = stickman.layout
        skeleton = layout.skeleton
        t = mimic.mode_time if mimic.mode is Mode.OPEN and mimic.victim is stickman else 0.0
        weapon = self.weapon
        hand_chain = layout.arms[1]
        facing = stickman.locomotion.facing
        arm = sum(skeleton.bone(name).length for name in hand_chain.bones)
        stow = clamp(t / STOW_TIME, 0.0, 1.0)
        reach = smoothstep(clamp((t - STOW_TIME) / REACH_TIME, 0.0, 1.0))
        lean = 0.55 * reach
        pose.angles[layout.torso] = pose.angles.get(layout.torso, 0.0) + lean
        pose.angles[layout.head] = pose.angles.get(layout.head, 0.0) + 0.3 * reach
        shoulder = forward_kinematics(skeleton, pose)[layout.torso].end
        rest = shoulder + Vec2(0.15, 0.8) * arm
        over = shoulder + Vec2(-0.35, -0.55) * arm
        if weapon is not None and stow < 0.55:
            weapon.apply(pose, mode, dt, skip)
            hand = forward_kinematics(skeleton, pose)[hand_chain.bones[-1]].end
            k = smoothstep(stow / 0.55)
            solve_two_bone(skeleton, pose, hand_chain, hand.lerp(over, k))
            return
        if weapon is not None:
            weapon.held = False
        grip = mimic.lid_grip(mimic.victim_side)
        target = Vec2(facing * grip.x, grip.y)
        back = smoothstep(clamp((stow - 0.55) / 0.45, 0.0, 1.0))
        for i, chain in enumerate(layout.arms):
            start = over.lerp(rest, back) if chain is hand_chain and weapon is not None else rest
            hand = target + Vec2(-1.0 * i, 0.6 * i)
            solve_two_bone(skeleton, pose, chain, start.lerp(hand, reach))


class Flail:
    """An adventurer reeled in on a mimic's tongue (an `UpperBodyLayer`): his arms
    windmill and his head lolls back."""

    def __init__(self, stickman: Stickman) -> None:
        self.stickman = stickman
        self.time = 0.0

    def apply(self, pose: Pose, mode: object, dt: float, skip: frozenset[str]) -> None:
        self.time += dt
        layout = self.stickman.layout
        skeleton = layout.skeleton
        pose.angles[layout.torso] = pose.angles.get(layout.torso, 0.0) - 0.35
        pose.angles[layout.head] = pose.angles.get(layout.head, 0.0) - 0.4
        shoulder = forward_kinematics(skeleton, pose)[layout.torso].end
        for i, chain in enumerate(layout.arms):
            if chain.name in skip:
                continue
            arm = sum(skeleton.bone(name).length for name in chain.bones)
            angle = self.time * 17.0 + i * math.pi
            hand = shoulder + Vec2(math.cos(angle) * 0.7, -0.55 + math.sin(angle) * 0.4) * arm
            solve_two_bone(skeleton, pose, chain, hand)


class Toss:
    """A rogue who's seen through a mimic (an `UpperBodyLayer`): he starts back, tucks
    through his hop away from it, then winds back and throws a dagger at it."""

    def __init__(self, stickman: Stickman, mimic: Mimic) -> None:
        self.stickman = stickman
        self.mimic = mimic

    def apply(self, pose: Pose, mode: object, dt: float, skip: frozenset[str]) -> None:
        layout = self.stickman.layout
        skeleton = layout.skeleton
        t = self.mimic._spot_time
        start = smoothstep(clamp(t / SPOT_TIME, 0.0, 1.0))
        flip = clamp((t - SPOT_TIME) / FLIP_TIME, 0.0, 1.0)
        tuck = math.sin(math.pi * flip)
        wind = smoothstep(clamp((t - SPOT_TIME - FLIP_TIME) / WIND_TIME, 0.0, 1.0))
        lean = -0.25 * start * (1.0 - wind) - 0.35 * tuck + 0.2 * wind
        pose.angles[layout.torso] = pose.angles.get(layout.torso, 0.0) + lean
        pose.angles[layout.head] = pose.angles.get(layout.head, 0.0) - 0.2 * start
        shoulder = forward_kinematics(skeleton, pose)[layout.torso].end
        for i, chain in enumerate(layout.arms):
            if chain.name in skip:
                continue
            arm = sum(skeleton.bone(name).length for name in chain.bones)
            startled = Vec2(0.35, -0.55 + 0.1 * i)
            tucked = Vec2(0.5, 0.15)
            if i == 1:
                aimed = Vec2(-0.55, -0.7)
            else:
                aimed = Vec2(0.75, -0.15)
            hand = startled.lerp(tucked, tuck).lerp(aimed, wind)
            solve_two_bone(skeleton, pose, chain, shoulder + hand * arm)
