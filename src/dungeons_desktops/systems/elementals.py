"""The elemental: one spirit with `ELEMENTAL_HP` that wears four forms in turn - water,
earth, air, then fire - each a torso, head and arms rising out of a swirling column of
its element, no legs.

Every `FORM_HP` of damage it shifts into the next form (`SHIFT_TIME`: it sinks into
its column and rises as the next element, untouchable meanwhile). A hit can't carry it
past a form: whatever is left over when a form runs out is lost. When the fire form's
HP are gone it collapses into its element and fades.

Every form hunts the nearest adventurer, punches whoever is in reach of its fist
(`MELEE_DAMAGE`), and has its own special (see `elemental_powers`). They get about
differently:

- water floats along a stickman's routes like the mind flayer (`floating`), very fast;
- earth glides only along window tops and the floor (the hydra's terrain), slowly, and
  to get anywhere else - or to anyone far off - it burrows: it tears a hole, sinks in,
  and after a moment underground (untouchable) cracks give away where it bursts out,
  beside its quarry, knocking over anyone on the spot;
- air flies freely, anywhere on the screen;
- fire floats like water but faster still, and never lets up: it never wanders, keeps
  to the nearest adventurer, and drops one it can't reach for one it can at once.
"""

from __future__ import annotations

import math
import random
from enum import Enum
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, clamp
from dungeons_desktops.creatures import stick_figure
from dungeons_desktops.navigation.planner import ALONG_MOVES, Anchor
from dungeons_desktops.navigation.terrain import Surface, TerrainChange
from dungeons_desktops.systems.actors import surface_below
from dungeons_desktops.systems.elemental_powers import (
    DEATHS,
    SOURCE,
    SPECIALS,
    UP,
    SeismicSlam,
    Special,
)
from dungeons_desktops.systems.floating import Floater
from dungeons_desktops.systems.hunt import nearest
from dungeons_desktops.systems.mortal import ELEMENTAL_HP, Mortal

if TYPE_CHECKING:
    from dungeons_desktops.systems.actors import Stickman
    from dungeons_desktops.systems.world import SimWorld

KINDS = ("water", "earth", "air", "fire")
"""Its forms, in the order it wears them."""
FORM_HP = 5
SCALE = 1.12
"""Everything in its frame (below, and in its drawing) is scaled by this."""
HEIGHT = 53.0 * SCALE
"""Ground to the top of its head (the minotaur is 64, to the top of its hump)."""
WAIST = Vec2(-1.0, -24.0)
CHEST = Vec2(1.0, -36.0)
HEAD = Vec2(12.0, -45.0)
FIST = Vec2(16.0, -26.0)
RAISED_HAND = Vec2(8.0, -52.0)
"""Where its body's parts sit over the ground point, facing +x (y down), before
`SCALE`."""

WALK = stick_figure.MOVES.walk_speed
PACE = {"water": 2.0, "earth": 0.5, "air": 1.2, "fire": 2.8}
"""How fast each form gets about, relative to a stickman walking."""
HOVER = 1.0
"""How high the tip of its column floats over the ground."""
WALL_GAP = 16.0
CEILING_GAP = 4.0
MAX_LEAN = 0.2
SHIFT_TIME = 0.7

MELEE_REACH = 26.0
"""How close to its fist (turned toward him) someone must be for it to punch."""
MELEE_HEIGHT = 30.0
MELEE_WINDUP = 0.3
MELEE_STRIKE = 0.15
MELEE_RECOVER = 0.2
MELEE_TIME = MELEE_WINDUP + MELEE_STRIKE + MELEE_RECOVER
MELEE_COOLDOWN = 1.3
MELEE_DAMAGE = 1
MELEE_PUSH = 160.0
FIRST_SPECIAL = 1.5
"""Seconds into a form before its special is ready."""

FLY_ACCEL = 3.0
FLY_SIDE = 22.0
FLY_BELOW = 26.0
"""Where air hovers for a punch: this far to the side of its quarry and with its
ground point this far below his middle (its fist then lands on him)."""
FLY_WANDER = (2.5, 4.5)

BURROW_RANGE = 250.0
"""Earth burrows to a quarry farther off than this (or one it can't route to)."""
BURROW_COOLDOWN = 6.0
MIN_SURFACED = 3.0
BURROW_SPEED = 420.0
MIN_UNDER = 0.6
MAX_UNDER = 2.0
SINK_TIME = 0.5
RISE_TIME = 0.5
WARN_TIME = 0.4
"""Cracks give its exit away this long before it bursts out."""
EXIT_SIDE = 30.0
"""How far beside its quarry it comes up."""
HOLE_RADIUS = 13.0
ERUPT_REACH = 18.0
ERUPT_DAMAGE = 1

FALL_GRAVITY = 600.0
COLLAPSE_TIME = 0.9
"""How long it takes to fall apart once it's dead."""

ZERO = Vec2(0.0, 0.0)


class Action(Enum):
    MELEE = "melee"
    SPECIAL = "special"
    SHIFT = "shift"
    BURROW = "burrow"


# ----- movers ----------------------------------------------------------------------------


class FloatMover(Floater):
    """Water and fire: floating along a stickman's routes."""

    hover = HOVER
    wall_gap = WALL_GAP
    ceiling_gap = CEILING_GAP
    max_lean = MAX_LEAN

    def __init__(self, world: SimWorld, anchor: Anchor, pace: float, relentless: bool) -> None:
        super().__init__(world, stick_figure.build_stick_figure(), anchor, HEIGHT)
        self.pace = pace
        if relentless:
            self.replan_every = 0.2
            self.patience = 0.0
            self.wanders = False

    @property
    def facing(self) -> int:
        return self._facing

    @property
    def in_transition(self) -> bool:
        return self.follower.in_transition

    def surface(self) -> Surface | None:
        """The window top or floor it's floating over, if it's settled on one."""
        follower = self.follower
        if follower.in_transition or (
            follower.step is not None and follower.step.move not in ALONG_MOVES
        ):
            return None
        surface = follower.current_anchor().surface
        return surface if surface.walkable else None

    def update(self, dt: float, target: Stickman | None, hunt, rooted: bool) -> None:
        self._travel(dt, target, hunt, rooted)
        self._glide(dt, not rooted, target.center() if target is not None else None)

    def face(self, point: Vec2) -> None:
        self._face(point)

    def dash(self, offset: Vec2) -> bool:
        return False


class GroundMover(FloatMover):
    """Earth: the same, but only along window tops and the floor (the hydra's terrain:
    no walls or undersides, drops but no climbs)."""

    patience = math.inf

    @property
    def planner(self):
        return self.world.hydra_planner


class FlyMover:
    """Air: flying freely, steering for a spot beside its quarry."""

    def __init__(self, world: SimWorld, feet: Vec2, facing: int, pace: float) -> None:
        self.world = world
        self.feet = feet
        self.drift = ZERO
        self.lean = 0.0
        self._facing = facing
        self.pace = pace
        self.stranded = False
        self.in_transition = False
        self._wander = feet
        self._wander_wait = 0.0

    @property
    def facing(self) -> int:
        return self._facing

    def contact(self) -> Vec2:
        return self.feet

    def surface(self) -> Surface | None:
        return None

    def _bounds(self) -> tuple[float, float, float, float]:
        world = self.world
        top = world.ceiling if world.ceiling is not None else 0.0
        return world.left + 12.0, world.width - 12.0, top + HEIGHT + 4.0, world.floor_y - HOVER

    def _clamped(self, point: Vec2) -> Vec2:
        left, right, top, bottom = self._bounds()
        return Vec2(clamp(point.x, left, right), clamp(point.y, top, bottom))

    def update(self, dt: float, target: Stickman | None, hunt, rooted: bool) -> None:
        speed = WALK * self.pace
        if rooted:
            desired = ZERO
        else:
            if target is not None:
                theirs = target.center()
                side = -1.0 if self.feet.x < theirs.x else 1.0
                goal = theirs + Vec2(side * FLY_SIDE, FLY_BELOW)
            else:
                self._wander_wait -= dt
                if self._wander_wait <= 0.0:
                    rng = self.world.random
                    self._wander_wait = rng.uniform(*FLY_WANDER)
                    left, right, top, bottom = self._bounds()
                    self._wander = Vec2(rng.uniform(left, right), rng.uniform(top, bottom))
                goal = self._wander
            goal = self._clamped(goal)
            offset = goal - self.feet
            distance = offset.length()
            desired = offset.normalized() * min(speed, distance * 2.5) if distance > 0.5 else ZERO
        self.drift += (desired - self.drift) * min(1.0, FLY_ACCEL * dt)
        self.feet = self._clamped(self.feet + self.drift * dt)
        lean = clamp(self.drift.x / speed, -1.0, 1.0) * MAX_LEAN
        self.lean += (lean - self.lean) * min(1.0, 6.0 * dt)
        if not rooted and abs(self.drift.x) > 6.0:
            self._facing = 1 if self.drift.x > 0 else -1

    def face(self, point: Vec2) -> None:
        if abs(point.x - self.feet.x) > 1.0:
            self._facing = 1 if point.x > self.feet.x else -1

    def dash(self, offset: Vec2) -> bool:
        """Shoot along `offset` (a whirlwind's dash); False if the screen's edge stops it."""
        wanted = self.feet + offset
        self.feet = self._clamped(wanted)
        self.drift = offset * 0.0
        return self.feet.distance_to(wanted) < 0.5

    def halt(self) -> None:
        pass

    def terrain_changed(self, change: TerrainChange) -> None:
        pass

    def move_goal_with_box(self, change: TerrainChange) -> None:
        pass


# ----- the elemental ---------------------------------------------------------------------


class Elemental(Mortal):
    max_hp = ELEMENTAL_HP
    linger = 2.0

    def __init__(self, world: SimWorld, anchor: Anchor, kind: str = KINDS[0], facing: int = 1):
        assert kind in KINDS
        self.world = world
        self.kind = kind
        self.damage = FORM_HP * KINDS.index(kind)
        self.hunt = nearest()
        self.target: Stickman | None = None
        self.action: Action | None = None
        self.action_time = 0.0
        self.special: Special | None = None
        self.melee_wait = 0.5
        self.special_wait = FIRST_SPECIAL
        self.burrow_wait = 0.0
        self.surfaced = MIN_SURFACED
        self.effects: list = []
        """What its specials set loose (waves, shockwaves, fireballs, burning ground...),
        running their course whatever becomes of it."""
        self._struck: set = set()
        self._fx = random.Random(world.random.random())
        self.clock = self._fx.uniform(0.0, 100.0)
        """Its own time, for its swirling (offset so no two swirl in step)."""
        self.trail = 0.0
        """0 at rest to 1 at full speed: how far its column trails behind it."""
        self.sunk = 0.0
        """0 up to 1 all the way underground (earth burrowing)."""
        self._burrow_phase = ""
        self._exit: Vec2 | None = None
        self._exit_box: int | None = None
        self._under_time = 0.0
        self._shift_switched = False
        self._dead_feet = ZERO
        self._dead_facing = facing
        self._dead_lean = 0.0
        self._dead_speed = 0.0
        self._dead_fall = 0.0
        self.mover = self._mover_for(kind, anchor.point - Vec2(0.0, HOVER), facing, anchor)

    # ----- where it is -----------------------------------------------------------

    @property
    def feet(self) -> Vec2:
        """Its ground point, where its column's tip is."""
        return self._dead_feet if self.dead else self.mover.feet

    @property
    def facing(self) -> int:
        return self._dead_facing if self.dead else self.mover.facing

    @property
    def lean(self) -> float:
        """Radians it leans forward (into the way it faces)."""
        return self._dead_lean if self.dead else self.mover.lean * self.facing

    @property
    def collapse(self) -> float:
        """0 alive to 1 fallen apart."""
        return clamp(self.down_time / COLLAPSE_TIME, 0.0, 1.0) if self.dead else 0.0

    @property
    def form(self) -> int:
        return KINDS.index(self.kind)

    @property
    def form_hp(self) -> int:
        """What's left of the current form's `FORM_HP`."""
        return FORM_HP * (self.form + 1) - self.damage

    @property
    def visible(self) -> bool:
        """Not (mostly) underground."""
        return self.sunk < 0.5

    @property
    def vulnerable(self) -> bool:
        return self.visible and self.action is not Action.SHIFT

    @property
    def shifting(self) -> float:
        """0..1..0 through a change of form: how far it has sunk into its column."""
        if self.action is not Action.SHIFT:
            return 0.0
        return 1.0 - abs(2.0 * self.action_time / SHIFT_TIME - 1.0)

    @property
    def swing(self) -> float:
        """0..1 through a punch (`MELEE_TIME`: windup, strike, then bringing its fist
        home)."""
        if self.action is not Action.MELEE:
            return 0.0
        return clamp(self.action_time / MELEE_TIME, 0.0, 1.0)

    @property
    def charge(self) -> float:
        """0..1 through its special's windup."""
        if self.action is not Action.SPECIAL or self.special is None:
            return 0.0
        return self.special.charge

    @property
    def spin(self) -> float:
        """0..1: air wound up into a tornado for its whirlwind."""
        special = self.special
        if self.action is not Action.SPECIAL or special is None:
            return 0.0
        return getattr(special, "spin", 0.0)

    @property
    def dash_way(self) -> Vec2 | None:
        special = self.special
        if self.action is Action.SPECIAL and special is not None and self.spin > 0.0:
            return getattr(special, "direction", None)
        return None

    def at(self, local: Vec2) -> Vec2:
        """A point in its own frame (x forward, y down, from its ground point) in the
        world, leaning with it."""
        v = Vec2(local.x * self.facing, local.y) * SCALE
        return self.feet + v.rotated(self.lean * self.facing)

    def center(self) -> Vec2:
        return self.at(Vec2(0.0, (WAIST.y + CHEST.y) / 2))

    def hand_raised(self) -> Vec2:
        return self.at(RAISED_HAND)

    def parts(self) -> list[Vec2]:
        return [
            self.at(Vec2(0.0, -6.0)),
            self.at(WAIST),
            self.at(CHEST),
            self.at(HEAD),
            self.at(FIST),
        ]

    def hits(self, point: Vec2, margin: float = 0.0) -> bool:
        if not self.vulnerable:
            return False
        for part, radius in (
            (CHEST, 11.0),
            (HEAD, 6.5),
            (WAIST, 8.0),
            (FIST, 5.0),
            (Vec2(-1.0, -12.0), 6.0),
        ):
            if point.distance_to(self.at(part)) <= radius * SCALE + margin:
                return True
        return False

    def surface(self) -> Surface | None:
        """The window top or floor it's settled on, if any."""
        return self.mover.surface()

    def face(self, point: Vec2) -> None:
        self.mover.face(point)

    def dash(self, offset: Vec2) -> bool:
        return self.mover.dash(offset)

    def _fist_toward(self, point: Vec2) -> Vec2:
        facing = 1 if point.x >= self.feet.x else -1
        v = Vec2(FIST.x * facing, FIST.y) * SCALE
        return self.feet + v.rotated(self.lean * facing)

    def in_reach(self, stickman: Stickman, slack: float = 1.0) -> bool:
        """Whether its fist, turned toward `stickman`, would land on him."""
        theirs = stickman.center()
        fist = self._fist_toward(theirs)
        return (
            abs(theirs.y - fist.y) <= MELEE_HEIGHT * slack
            and theirs.distance_to(fist) <= MELEE_REACH * slack
        )

    # ----- movers ------------------------------------------------------------------

    def _mover_for(
        self, kind: str, feet: Vec2, facing: int, anchor: Anchor | None = None
    ) -> FloatMover | FlyMover:
        """A mover for `kind` with its body at `feet`: air flies from there; the others
        settle onto the top or floor below (gliding down to it if it's some way off)."""
        world = self.world
        if kind == "air":
            return FlyMover(world, feet, facing, PACE[kind])
        if kind == "earth":
            if anchor is None or not anchor.surface.walkable:
                anchor = surface_below(world.hydra_planner, feet - Vec2(0.0, 2.0))
            mover: FloatMover = GroundMover(world, anchor, PACE[kind], relentless=False)
        else:
            if anchor is None:
                anchor = surface_below(world.planner, feet - Vec2(0.0, 2.0))
            mover = FloatMover(world, anchor, PACE[kind], relentless=kind == "fire")
        if anchor.point.y - feet.y > 3.0:
            mover.drop_from(feet + Vec2(0.0, HOVER))
        mover.feet = feet
        mover._facing = facing
        return mover

    # ----- simulation ----------------------------------------------------------------

    def update(self, dt: float) -> None:
        self.clock += dt
        self.melee_wait -= dt
        self.special_wait -= dt
        self.burrow_wait -= dt
        if self.visible:
            self.surfaced += dt
        self._update_effects(dt)
        mover = self.mover
        self.target = self.hunt.update(dt, mover.contact(), self.world.stickmen)
        if self.action is None and not mover.in_transition:
            self._choose()
        if self.action is not None:
            self._act(dt)
        rooted = self.action is not None
        self.mover.update(dt, self.target, self.hunt, rooted)
        speed = WALK * PACE[self.kind]
        fraction = clamp(abs(self.mover.drift.x) / speed, 0.0, 1.0)
        self.trail += (fraction - self.trail) * min(1.0, 4.0 * dt)

    def _update_effects(self, dt: float) -> None:
        current, self.effects = self.effects, []
        kept = [fx for fx in current if fx.update(self.world, dt)]
        self.effects = kept + self.effects

    def _choose(self) -> None:
        target = self.target
        if target is None:
            return
        if self.melee_wait <= 0.0 and self.in_reach(target):
            self._start(Action.MELEE)
            self.face(target.center())
            self._struck = set()
            return
        special = SPECIALS[self.kind]
        if self.special_wait <= 0.0 and special.ready(self, target):
            self.special = special(self, target)
            self._start(Action.SPECIAL)
            return
        if self.kind == "earth" and self._wants_burrow(target):
            self._start(Action.BURROW)
            self._burrow_phase = "sink"
            world = self.world
            world.debris.hole(self.feet, HOLE_RADIUS, world.boxes, world.bottom_border)
            world.debris.burst(self.feet, UP, 10, 140.0, chunks=2, puffs=5)

    def _start(self, action: Action) -> None:
        self.action, self.action_time = action, 0.0
        self.mover.halt()

    def _act(self, dt: float) -> None:
        self.action_time += dt
        action = self.action
        if action is Action.MELEE:
            self._punch()
        elif action is Action.SPECIAL:
            special = self.special
            assert special is not None
            if special.update(dt):
                self.special_wait = special.cooldown
                self.special = None
                self.action = None
        elif action is Action.SHIFT:
            if not self._shift_switched and self.action_time >= SHIFT_TIME / 2:
                self._shift_switched = True
                self._become(KINDS[self.form + 1])
            if self.action_time >= SHIFT_TIME:
                self.action = None
        elif action is Action.BURROW:
            self._burrow(dt)

    # ----- melee -----------------------------------------------------------------------

    def _punch(self) -> None:
        t = self.action_time
        if MELEE_WINDUP <= t < MELEE_WINDUP + MELEE_STRIKE:
            fist = self.at(FIST + Vec2(6.0 * min(1.0, (t - MELEE_WINDUP) / MELEE_STRIKE), 0.0))
            push = Vec2(self.facing * MELEE_PUSH, -60.0)
            for stickman in self.world.stickmen:
                if stickman in self._struck or not stickman.prey:
                    continue
                theirs = stickman.center()
                if stickman.hits(fist, 8.0) or (
                    theirs.distance_to(fist) <= MELEE_REACH
                    and abs(theirs.y - fist.y) <= MELEE_HEIGHT
                ):
                    self._struck.add(stickman)
                    stickman.hurt(MELEE_DAMAGE, fist, push, SOURCE[self.kind], DEATHS[self.kind])
        if t >= MELEE_TIME:
            self.melee_wait = MELEE_COOLDOWN
            self.action = None

    # ----- changing form -----------------------------------------------------------------

    def wounded(self) -> None:
        """After a hit: when this form's HP are gone, change into the next."""
        if self.form_hp <= 0 and self.form < len(KINDS) - 1 and self.action is not Action.SHIFT:
            self.shift()

    def shift(self) -> None:
        """Start changing into the next form (whatever it was doing is cut short)."""
        if self.form >= len(KINDS) - 1:
            return
        if self.special is not None:
            self.special.cancel()
            self.special = None
        if self.action is Action.BURROW:
            self._surface_now()
        self.damage = max(self.damage, FORM_HP * (self.form + 1))
        self._start(Action.SHIFT)
        self._shift_switched = False
        center = self.center()
        self.world.debris.burst(center, UP, 6, 120.0, spread=3.0, puffs=8, scale=0.6)

    def _become(self, kind: str) -> None:
        self.kind = kind
        self.mover = self._mover_for(kind, self.mover.feet, self.mover.facing)
        self.melee_wait = 0.5
        self.special_wait = FIRST_SPECIAL
        self.burrow_wait = 0.0
        self.surfaced = MIN_SURFACED
        self.trail = 0.0

    # ----- burrowing (earth) -------------------------------------------------------------

    def _wants_burrow(self, target: Stickman) -> bool:
        if self.burrow_wait > 0.0 or self.surfaced < MIN_SURFACED or self.mover.in_transition:
            return False
        far = target.contact().distance_to(self.mover.contact()) > BURROW_RANGE
        return far or self.mover.stranded

    def _burrow(self, dt: float) -> None:
        phase = self._burrow_phase
        t = self.action_time
        if phase == "sink":
            self.sunk = clamp(t / SINK_TIME, 0.0, 1.0)
            if t >= SINK_TIME:
                self.sunk = 1.0
                self._pick_exit()
                self._burrow_phase, self.action_time = "under", 0.0
        elif phase == "under":
            if t >= self._under_time - WARN_TIME and self._exit is not None:
                self._burrow_phase = "warn"
                self.world.debris.burst(
                    self._exit, UP, 4, 60.0, ring_radius=14.0, cracks=4, puffs=3
                )
        elif phase == "warn":
            if t >= self._under_time:
                self._erupt()
                self._burrow_phase, self.action_time = "rise", 0.0
        elif phase == "rise":
            self.sunk = clamp(1.0 - t / RISE_TIME, 0.0, 1.0)
            if t >= RISE_TIME:
                self.sunk = 0.0
                self._end_burrow()

    def _pick_exit(self) -> None:
        """Beside its quarry, on the top or floor nearest him."""
        target = self.target
        here = self.mover.contact()
        if target is None or not target.prey:
            goal = here
        else:
            goal = target.contact()
        side = 1.0 if here.x >= goal.x else -1.0
        best = None
        for surface in self.world.hydra_planner.surfaces:
            if not surface.walkable or surface.high - surface.low < 24.0:
                continue
            for way in (side, -side):
                x = clamp(goal.x + way * EXIT_SIDE, surface.low + 12.0, surface.high - 12.0)
                point = Vec2(x, surface.start.y)
                cost = point.distance_to(goal) + (8.0 if way != side else 0.0)
                if best is None or cost < best[0]:
                    best = (cost, point, surface.box)
        if best is None:
            best = (0.0, here, None)
        _, self._exit, self._exit_box = best
        travel = here.distance_to(self._exit)
        self._under_time = clamp(travel / BURROW_SPEED, MIN_UNDER, MAX_UNDER) + WARN_TIME

    def _erupt(self) -> None:
        world = self.world
        exit_ = self._exit if self._exit is not None else self.mover.contact()
        facing = self.mover.facing
        if self.target is not None and abs(self.target.center().x - exit_.x) > 1.0:
            facing = 1 if self.target.center().x > exit_.x else -1
        anchor = surface_below(world.hydra_planner, exit_ - Vec2(0.0, 2.0))
        self.mover = self._mover_for("earth", anchor.point - Vec2(0.0, HOVER), facing, anchor)
        world.debris.hole(anchor.point, HOLE_RADIUS, world.boxes, world.bottom_border)
        world.debris.burst(anchor.point, UP, 14, 200.0, chunks=4, puffs=6)
        for stickman in world.stickmen:
            if not stickman.prey or stickman.contact().distance_to(anchor.point) > ERUPT_REACH:
                continue
            push = Vec2(0.0, -200.0)
            if not stickman.hurt(
                ERUPT_DAMAGE, anchor.point, push, SOURCE["earth"], DEATHS["earth"]
            ):
                stickman.knock_down(anchor.point + Vec2(0.0, 20.0), 200.0, 0.8, 0.4)

    def _surface_now(self) -> None:
        """Cut a burrow short: come up where it would have come out (or where it went in)."""
        if self._burrow_phase in ("under", "warn"):
            self._erupt()
        self.sunk = 0.0
        self._end_burrow()

    def _end_burrow(self) -> None:
        self._burrow_phase = ""
        self._exit = None
        self.surfaced = 0.0
        self.burrow_wait = BURROW_COOLDOWN
        if self.action is Action.BURROW:
            self.action = None
        if SeismicSlam.ready(self, self.target):
            self.special_wait = 0.0

    # ----- terrain -----------------------------------------------------------------

    def move_goal_with_box(self, change: TerrainChange) -> None:
        if not self.dead:
            self.mover.move_goal_with_box(change)

    def terrain_changed(self, change: TerrainChange) -> None:
        self.effects = [fx for fx in self.effects if fx.terrain_changed(change)]
        if self.dead:
            return
        self.mover.terrain_changed(change)
        if self._exit is not None:
            if change.removed(self._exit_box):
                self._exit_box = None
            else:
                delta = change.delta_for(self._exit_box)
                if delta is not None:
                    self._exit += delta
                new = change.new_index(self._exit_box)
                self._exit_box = self._exit_box if new is None else new

    # ----- death -----------------------------------------------------------------------

    def die(self, point: Vec2, push: Vec2) -> None:
        self._dead_feet = self.mover.feet
        self._dead_facing = self.mover.facing
        self._dead_lean = self.mover.lean * self.mover.facing
        self._dead_speed = push.x * 0.2
        self.dead = True
        self.down_time = 0.0
        self.action = None
        self.special = None
        self.sunk = 0.0

    def _ground_below(self, point: Vec2) -> float:
        tops = [
            box.top
            for box in self.world.boxes
            if box.left <= point.x <= box.right and box.top >= point.y - 2.0
        ]
        return min([self.world.floor_y, *tops])

    def update_dead(self, dt: float) -> None:
        self.clock += dt
        self.down_time += dt
        self._update_effects(dt)
        self._dead_speed *= math.exp(-3.0 * dt)
        feet = self._dead_feet + Vec2(self._dead_speed * dt, 0.0)
        below = self._ground_below(feet - Vec2(0.0, 4.0))
        if feet.y < below:
            self._dead_fall += FALL_GRAVITY * dt
            feet = Vec2(feet.x, min(below, feet.y + self._dead_fall * dt))
        else:
            self._dead_fall = 0.0
        self._dead_feet = feet
        self._dead_lean *= math.exp(-4.0 * dt)
        self.trail *= math.exp(-4.0 * dt)
