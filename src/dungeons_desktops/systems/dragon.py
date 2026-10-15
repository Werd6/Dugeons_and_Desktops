"""The dragon: a four-legged brute that prowls window tops and the floor, swiping at any
stickman who gets within reach, and now and then takes off to strafe the screen and
breathe fire on whoever it spots, wheeling round in the air for prey behind it.

Walking is a trot: diagonal leg pairs swing together, half a cycle apart, and the
cycle advances with distance travelled so planted feet never slide. Each leg is a
two-bone IK chain from the shoulder or hip to its foot. In the air the body follows
its velocity, the wings flap and the legs tuck up. A flight ends with a glide down
onto a walkable surface. With `DRAGON_HP` gone it drops out of the sky (or slumps
where it stands) and lies sprawled across whatever is below.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.navigation.terrain import Surface, TerrainChange
from dungeons_desktops.rig.ik import two_bone_points
from dungeons_desktops.rig.locomotion import PoseMode
from dungeons_desktops.systems.actors import DRAGON_DAMAGE
from dungeons_desktops.systems.breath import (
    BREATHS,
    DEATH_MESSAGES,
    Mote,
    splash,
    step_motes,
)
from dungeons_desktops.systems.flames import Flame, burn_hits, emit, step_flames
from dungeons_desktops.systems.mortal import DRAGON_HP, Mortal

if TYPE_CHECKING:
    from dungeons_desktops.systems.actors import Stickman
    from dungeons_desktops.systems.world import SimWorld

SCALE = 1.0
BODY_LENGTH = 34.0 * SCALE
HIP_HEIGHT = 19.5 * SCALE
UPPER_LEG = 11.7 * SCALE
LOWER_LEG = 11.7 * SCALE
STRIDE = 36.0 * SCALE
STANCE = 0.6
STEP_HEIGHT = 6.5 * SCALE
NECK = Vec2(19.5, -17.0) * SCALE
"""Where the head sits relative to the shoulder (x forward, y down)."""
TAIL_SEGMENTS = 13
TAIL_SPACING = 4.5 * SCALE

WALK_SPEED = 26.0 * SCALE
CHARGE_SPEED = 55.0 * SCALE
ACCELERATION = 4.0
WANDER_WAIT = (1.0, 3.5)
SWIPE_REACH = 14.0 * SCALE
BODY_REACH = 10.0 * SCALE
"""How close to its belly line (hips to chest) a stickman must be to get trampled."""
BELLY_DROP = 8.0 * SCALE
"""The belly line sits this far below the spine."""
SWIPE_TIME = 0.55
SWIPE_COOLDOWN = 0.7
SWIPE_PUSH = 380.0

GROUND_TIME = (14.0, 22.0)
"""Seconds of walking between flights."""
FLIGHT_TIME = (15.0, 22.5)
FLY_SPEED = 190.0
TAKEOFF_SPEED = 230.0
FLAP_BOB = 2.0 * SCALE
"""The body sinks on the upstroke and is lifted by the downstroke."""
CRUISE_DEPTH = (60.0, 170.0)
"""Cruising altitude, measured down from the top of the screen."""
TURN_MARGIN = 90.0
"""It turns this far from a screen side, so its head stays on screen through the turn."""
TURN_FLARE = 0.45
"""How far (radians) it rears its nose up, wings braking, while it slows to turn round."""
SPOT_RANGE = 900.0
"""How far it notices prey and swoops toward them, ahead or behind, above or below it."""
TURN_BEHIND = 110.0
"""How far behind its body prey must fall before it wheels round in the air for them, so
it makes strafing passes instead of flip-flopping over someone right below it."""
FIRE_RANGE = 240.0
FIRE_BURST = 1.1
FIRE_COOLDOWN = 1.2
FLAME_RATE = 70.0
FLAME_SPEED = 330.0
FLAME_LIFE = 0.7
STRAFE_HEIGHT = 75.0
"""How far above its prey the dragon swoops while strafing."""
WALL_STRAFE_HEIGHT = 20.0
"""How far above a climber the dragon flies its run at the wall."""
WALL_STANDOFF = 105.0
"""Distance from a climber's wall at which the dragon breaks off its run."""
WALL_RUNUP = 320.0
"""How far it flies back out from a climber's wall before turning for another run."""
LAND_SPEED = 170.0
MIN_LANDING = BODY_LENGTH + 30.0
LAND_BLEND = 0.25
FALL_GRAVITY = 600.0
LYING_HEIGHT = 7.0 * SCALE
"""Body height above the ground once it's down."""
ZERO = Vec2(0.0, 0.0)


class DragonMode(Enum):
    WALK = "walk"
    SWIPE = "swipe"
    FLY = "fly"
    LAND = "land"
    DEAD = "dead"


@dataclass
class Leg:
    front: bool
    near: bool
    phase_offset: float
    foot: Vec2 = ZERO
    knee: Vec2 = ZERO
    root: Vec2 = ZERO
    lift: float = 0.0
    """0 planted flat on the ground, 1 tucked up in the air; the toes curl with it."""


def climbing_wall(stickman: Stickman) -> Surface | None:
    """The wall side a stickman is climbing, if he is on one."""
    if stickman.locomotion.mode is not PoseMode.CLIMB:
        return None
    surface = stickman.follower.current_anchor().surface
    return None if surface.walkable else surface


@dataclass(eq=False, repr=False)
class Dragon(Mortal):
    world: SimWorld
    body: Vec2
    facing: int = 1
    mode: DragonMode = DragonMode.FLY
    velocity: Vec2 = ZERO
    angle: float = 0.0
    """Body axis, tail to chest."""
    legs: list[Leg] = field(default_factory=list)
    tail: list[Vec2] = field(default_factory=list)
    flames: list[Flame] = field(default_factory=list)
    variant: str = "red"
    """Its colour ("red", "green", "blue", "black" or "white"): the scales, horns, the look
    of its breath and how its victims die. Every colour fights exactly the same."""
    wisps: list[Mote] = field(default_factory=list)
    """What its breath leaves behind (lingering gas, frost, acid drips): just for show."""
    max_hp = DRAGON_HP
    linger = 4.0

    def __post_init__(self) -> None:
        rng = self.world.random
        self.angle = 0.0 if self.facing > 0 else math.pi
        self.support: Surface | None = None
        self.x = self.body.x
        self.speed = 0.0
        self.phase = 0.0
        self.gait = 0.0
        self.flap = 0.0
        self.pitch = 0.0
        self.mode_time = 0.0
        self.ground_timer = rng.uniform(*GROUND_TIME)
        self.flight_timer = rng.uniform(*FLIGHT_TIME)
        self.cruise_y = self._top + rng.uniform(*CRUISE_DEPTH)
        self.wander_x: float | None = None
        self.wander_wait = 0.0
        self.swipe_time = 0.0
        self.swipe_cooldown = 0.0
        self._swiped = False
        self.fire_time = 0.0
        self.fire_cooldown = 0.5
        self.fire_target: Stickman | None = None
        self._flame_due = 0.0
        self.landing: Vec2 | None = None
        self.jaw = 0.0
        self.catches = 0
        self.head = self.body
        self.head_angle = self.angle
        self.clock = 0.0
        self._fx = random.Random(len(self.world.dragons))
        self.legs = [
            Leg(front=True, near=True, phase_offset=0.0),
            Leg(front=False, near=False, phase_offset=0.0),
            Leg(front=True, near=False, phase_offset=0.5),
            Leg(front=False, near=True, phase_offset=0.5),
        ]
        hip = self.hip
        back = -self.forward
        self.tail = [hip + back * (TAIL_SPACING * (i + 1)) for i in range(TAIL_SEGMENTS)]
        self._pose(1.0 / 60.0, snap=True)

    # ----- frame ---------------------------------------------------------------

    @property
    def forward(self) -> Vec2:
        return Vec2.from_angle(self.angle)

    @property
    def up(self) -> Vec2:
        return self.forward.rotated(-self.facing * math.pi / 2)

    def local(self, v: Vec2) -> Vec2:
        """A body-relative offset (x forward, y down) in world space."""
        return self.forward * v.x - self.up * v.y

    @property
    def shoulder(self) -> Vec2:
        return self.body + self.forward * (BODY_LENGTH / 2)

    @property
    def hip(self) -> Vec2:
        return self.body - self.forward * (BODY_LENGTH / 2)

    @property
    def neck_base(self) -> Vec2:
        return self.shoulder + self.local(Vec2(2.0, -3.0) * SCALE)

    @property
    def mouth(self) -> Vec2:
        return self.head + Vec2.from_angle(self.head_angle, 9.0 * SCALE)

    @property
    def flying(self) -> bool:
        return self.mode in (DragonMode.FLY, DragonMode.LAND)

    @property
    def _top(self) -> float:
        return self.world.ceiling if self.world.ceiling is not None else 0.0

    # ----- simulation ----------------------------------------------------------

    def update(self, dt: float) -> None:
        self.clock += dt
        self.mode_time += dt
        self.swipe_cooldown -= dt
        shown = self.facing
        if self.mode is DragonMode.WALK:
            self._walk(dt)
        elif self.mode is DragonMode.SWIPE:
            self._swipe(dt)
        elif self.mode is DragonMode.FLY:
            self._fly(dt)
        else:
            self._land(dt)
        if self.flying and self.facing != shown:
            self._mirror()
        self._pose(dt)
        self._update_flames(dt)

    def _set_mode(self, mode: DragonMode) -> None:
        self.mode = mode
        self.mode_time = 0.0

    # ----- walking -------------------------------------------------------------

    def _range(self) -> tuple[float, float]:
        surface = self.support
        assert surface is not None
        margin = BODY_LENGTH / 2 + 6.0 * SCALE
        low, high = surface.low + margin, surface.high - margin
        if low > high:
            low = high = (surface.low + surface.high) / 2
        return low, high

    def _on_support(self, stickman: Stickman) -> bool:
        surface = self.support
        foot = stickman.contact()
        return (
            surface is not None
            and abs(foot.y - surface.start.y) < 3.0
            and surface.low - 2.0 <= foot.x <= surface.high + 2.0
        )

    def _claw_point(self) -> Vec2:
        return self.shoulder + self.local(Vec2(21.0, 10.5) * SCALE)

    def _within_claws(self, stickman: Stickman, slack: float = 0.0) -> bool:
        """In front of its chest within claw reach, or anywhere under or against its
        body, hips to chest: it rears and tramples whoever got in close."""
        claw = self._claw_point()
        center = stickman.center()
        ahead = (center - self.shoulder).dot(self.forward) > -4.0
        if (
            ahead
            and center.distance_to(claw) < 30.0 + slack
            and stickman.hits(claw, SWIPE_REACH + slack)
        ):
            return True
        belly = self.local(Vec2(0.0, BELLY_DROP))
        return any(
            stickman.hits(point + belly, BODY_REACH + slack)
            for point in (self.hip, self.body, self.shoulder)
        )

    def _in_reach(self) -> Stickman | None:
        return next((s for s in self.world.stickmen if s.prey and self._within_claws(s)), None)

    def _walk(self, dt: float) -> None:
        if self.support is None:
            self._takeoff()
            return
        rng = self.world.random
        low, high = self._range()
        if self.swipe_cooldown <= 0.0 and self._in_reach() is not None:
            self._start_swipe()
            return
        self.ground_timer -= dt
        if self.ground_timer <= 0.0:
            self._takeoff()
            return

        prey = [s for s in self.world.stickmen if s.prey and self._on_support(s)]
        target = min(prey, key=lambda s: abs(s.contact().x - self.x), default=None)
        if target is not None:
            goal, top_speed = target.contact().x, CHARGE_SPEED
            self.wander_x = None
        else:
            top_speed = WALK_SPEED
            if self.wander_x is None or abs(self.wander_x - self.x) < 2.0:
                self.wander_x = None
                self.wander_wait -= dt
                if self.wander_wait <= 0.0:
                    self.wander_x = rng.uniform(low, high)
                    self.wander_wait = rng.uniform(*WANDER_WAIT)
            goal = self.wander_x if self.wander_x is not None else self.x
        offset = goal - self.x
        if abs(offset) > 1.0:
            direction = 1 if offset > 0 else -1
            if direction != self.facing and abs(self.speed) < 8.0:
                self._turn(direction)
            desired = direction * top_speed * min(1.0, abs(offset) / 20.0)
        else:
            desired = 0.0
        self.speed += (desired - self.speed) * min(1.0, ACCELERATION * dt)
        self.x += self.speed * dt
        if not low <= self.x <= high:
            self.x = clamp(self.x, low, high)
            self.speed = 0.0
            self.wander_x = None
        self.phase += abs(self.speed) * dt / STRIDE
        moving = min(1.0, abs(self.speed) / (WALK_SPEED * 0.4))
        self.gait += (moving - self.gait) * min(1.0, 6.0 * dt)

    def _turn(self, direction: int) -> None:
        self.facing = direction
        self.angle = 0.0 if direction > 0 else math.pi

    def _start_swipe(self) -> None:
        self._set_mode(DragonMode.SWIPE)
        self.speed = 0.0
        self._swiped = False

    def _swipe(self, dt: float) -> None:
        if not self._swiped and self.mode_time >= SWIPE_TIME * 0.55:
            self._swiped = True
            for stickman in self.world.stickmen:
                if stickman.prey and self._within_claws(stickman, slack=4.0):
                    push = self.forward * SWIPE_PUSH + self.up * 180.0
                    self._hit(stickman, push, "Mauled by the dragon!")
        if self.mode_time >= SWIPE_TIME:
            self._set_mode(DragonMode.WALK)
            self.swipe_cooldown = SWIPE_COOLDOWN

    # ----- flying ----------------------------------------------------------------

    def _takeoff(self) -> None:
        rng = self.world.random
        self._set_mode(DragonMode.FLY)
        self.support = None
        self.velocity = Vec2(self.facing * 70.0, -TAKEOFF_SPEED)
        self.flight_timer = rng.uniform(*FLIGHT_TIME)
        self.cruise_y = self._top + rng.uniform(*CRUISE_DEPTH)
        self.fire_cooldown = 0.6
        self.world.debris.burst(self.body + Vec2(0, HIP_HEIGHT), Vec2(0, -1), 10, 140.0, 1.4)

    def _spot_prey(self) -> Stickman | None:
        """The nearest stickman in any direction, high or low, or a climber whose wall it
        can make a run at from the wall's open side."""
        spotted = [s for s in self._targets() if s.center().distance_to(self.body) < SPOT_RANGE]
        return min(spotted, key=lambda s: s.center().distance_to(self.body), default=None)

    def _targets(self) -> list[Stickman]:
        return [
            s
            for s in self.world.stickmen
            if s.prey and ((wall := climbing_wall(s)) is None or self._can_run_at(wall))
        ]

    def _in_fire_range(self) -> Stickman | None:
        """The nearest target ahead within a breath of fire, while it may be wheeling
        round for one behind."""
        mouth = self.mouth
        ahead = [
            s
            for s in self._targets()
            if self._ahead(s) and s.center().distance_to(mouth) < FIRE_RANGE
        ]
        return min(ahead, key=lambda s: s.center().distance_to(mouth), default=None)

    def _come_about(self, prey: Stickman) -> None:
        """Wheel round in the air for prey left behind, once it is far enough back that
        the dragon won't flip-flop over someone right below it."""
        behind = (self.body.x - prey.center().x) * self.facing
        side = -self.facing
        near_edge = (
            self.body.x > self.world.width - TURN_MARGIN
            if side > 0
            else self.body.x < self.world.left + TURN_MARGIN
        )
        if behind > TURN_BEHIND and not near_edge:
            self.facing = side

    def _can_run_at(self, wall: Surface) -> bool:
        side = 1 if wall.normal.x > 0 else -1
        x = wall.start.x
        room = self.world.width - x if side > 0 else x - self.world.left
        return room >= WALL_STANDOFF + TURN_MARGIN and (self.body.x - x) * side > 0.0

    def _wall_run(self, wall: Surface) -> None:
        """Fly in at the wall and break off at the standoff, then back out to the run-up
        (or the screen edge) and turn for another pass."""
        side = 1 if wall.normal.x > 0 else -1
        away = (self.body.x - wall.start.x) * side
        if away < WALL_STANDOFF:
            self.facing = side
        elif away > WALL_RUNUP:
            self.facing = -side

    def _fly(self, dt: float) -> None:
        world = self.world
        self.flight_timer -= dt
        if self.facing > 0 and self.body.x > world.width - TURN_MARGIN:
            self.facing = -1
        elif self.facing < 0 and self.body.x < world.left + TURN_MARGIN:
            self.facing = 1

        prey = self._spot_prey()
        target_y = self.cruise_y + math.sin(self.mode_time * 1.4) * 20.0
        if prey is not None:
            wall = climbing_wall(prey)
            if wall is None:
                self._come_about(prey)
                target_y = prey.center().y - STRAFE_HEIGHT
            else:
                target_y = prey.center().y - WALL_STRAFE_HEIGHT
                self._wall_run(wall)
        target_y = clamp(target_y, self._top + 30.0, world.floor_y - STRAFE_HEIGHT + 10.0)
        climb = clamp((target_y - self.body.y) * 2.0, -150.0, 150.0)
        desired = Vec2(self.facing * FLY_SPEED, climb)
        self.velocity += (desired - self.velocity) * min(1.0, 1.6 * dt)
        self._move_in_air(dt)

        self.fire_cooldown -= dt
        if self.fire_time > 0.0:
            self.fire_time -= dt
            target = self.fire_target
            if target is None or not target.prey:
                self.fire_target = target = prey
            if target is not None and not self._ahead(target):
                self.fire_time = 0.0
                self.fire_cooldown = min(self.fire_cooldown, FIRE_COOLDOWN / 2)
            elif target is not None:
                self._breathe(dt, target.center())
        elif self.fire_cooldown <= 0.0 and (target := self._in_fire_range()) is not None:
            self.fire_target = target
            self.fire_time = FIRE_BURST
            self.fire_cooldown = FIRE_COOLDOWN + FIRE_BURST
        if self.flight_timer <= 0.0 and self.fire_time <= 0.0:
            self._start_landing()

    def _ahead(self, stickman: Stickman) -> bool:
        """Somewhere its neck can turn the jaws to; anyone else it wheels round for."""
        return (stickman.center() - self.neck_base).dot(self.forward) > 0.0

    def _move_in_air(self, dt: float) -> None:
        world = self.world
        body = self.body + self.velocity * dt
        x, y = body.x, body.y
        if (x < world.left + 10.0 and self.velocity.x < 0) or (
            x > world.width - 10.0 and self.velocity.x > 0
        ):
            x = clamp(x, world.left + 10.0, world.width - 10.0)
        flap = self.flap + dt * (11.0 if self.velocity.y < -40.0 else 7.0)
        y += FLAP_BOB * (math.cos(flap) - math.cos(self.flap))
        y = clamp(y, self._top + 12.0, world.floor_y - HIP_HEIGHT + 2.0 * SCALE)
        self.body = Vec2(x, y)
        self.flap = flap
        braking = self.facing * self.velocity.x < 0.0
        if abs(self.velocity.x) > 15.0:
            self.facing = 1 if self.velocity.x > 0 else -1
        climb = math.atan2(self.velocity.y, max(abs(self.velocity.x), 1.0))
        pitch = clamp(0.6 * climb, -0.35, 0.35) - (TURN_FLARE if braking else 0.0)
        self.pitch += (pitch - self.pitch) * min(1.0, 6.0 * dt)
        self.angle = self.pitch if self.facing > 0 else math.pi - self.pitch

    def _mirror(self) -> None:
        """Flip the posed head, tail and legs across the body, so a turn in the air reads
        as the dragon swinging round rather than its head and tail trailing across."""
        x2 = 2.0 * self.body.x

        def flip(p: Vec2) -> Vec2:
            return Vec2(x2 - p.x, p.y)

        self.head = flip(self.head)
        self.head_angle = math.pi - self.head_angle
        self.tail = [flip(p) for p in self.tail]
        for leg in self.legs:
            leg.foot, leg.knee, leg.root = flip(leg.foot), flip(leg.knee), flip(leg.root)

    def _breathe(self, dt: float, target: Vec2) -> None:
        mouth = self.mouth
        aim = (target - mouth).normalized()
        self._flame_due = emit(
            self.flames,
            self._flame_due,
            FLAME_RATE,
            dt,
            mouth,
            aim,
            FLAME_SPEED,
            self.world.random,
            self.velocity * 0.2,
        )

    def _start_landing(self) -> None:
        rng = self.world.random
        spots = [
            s for s in self.world.goblin_planner.surfaces if s.walkable and s.length >= MIN_LANDING
        ]
        if not spots:
            self.flight_timer = 2.0
            return
        surface = rng.choices(spots, weights=[s.length for s in spots])[0]
        margin = BODY_LENGTH / 2 + 8.0
        x = rng.uniform(surface.low + margin, surface.high - margin)
        self.landing = Vec2(x, surface.start.y)
        self._set_mode(DragonMode.LAND)

    def _land(self, dt: float) -> None:
        landing = self.landing
        if landing is None:
            self._start_landing()
            return
        goal = landing - Vec2(0.0, HIP_HEIGHT - 2.0 * SCALE)
        to_goal = goal - self.body
        distance = to_goal.length()
        if distance < 4.0:
            self._touch_down(landing)
            return
        desired = to_goal.normalized() * min(LAND_SPEED, distance * 2.5 + 30.0)
        self.velocity += (desired - self.velocity) * min(1.0, 3.0 * dt)
        self._move_in_air(dt)
        if self.mode_time > 8.0:
            self._touch_down(landing)

    def _touch_down(self, landing: Vec2) -> None:
        from dungeons_desktops.systems.actors import surface_below

        anchor = surface_below(self.world.goblin_planner, landing - Vec2(0.0, 2.0))
        if anchor is None:
            self._start_landing()
            return
        self.support = anchor.surface
        self.x = anchor.point.x
        self.speed = 0.0
        self.gait = 0.0
        self.velocity = ZERO
        self.landing = None
        self._turn(self.facing)
        self.ground_timer = self.world.random.uniform(*GROUND_TIME)
        self._set_mode(DragonMode.WALK)
        self.world.debris.burst(anchor.point, Vec2(0, -1), 12, 170.0, spread=1.4, puffs=6)

    # ----- flames and kills -------------------------------------------------------

    def _update_flames(self, dt: float) -> None:
        if self.wisps:
            self.wisps = step_motes(self.wisps, dt, self._fx)
        if not self.flames:
            return
        floor = self.world.floor_y
        self.flames, spent = step_flames(self.flames, dt, floor)
        if self.variant != "red":
            for flame in spent:
                self._leave_wisp(flame, floor)
        for stickman, flame in burn_hits(self.flames, self.world.stickmen):
            push = flame.velocity.normalized() * 200.0 + Vec2(0.0, -120.0)
            death = DEATH_MESSAGES[self.variant]
            if self._hit(stickman, push, death, bleed=False):
                stickman.succumb(BREATHS[self.variant])

    def _leave_wisp(self, flame: Flame, floor: float) -> None:
        """A spent breath particle lingers as gas or frost, or drips as acid."""
        fx = self._fx
        breath = BREATHS[self.variant]
        point, drift = flame.position, flame.velocity * 0.12
        size = flame.radius
        if breath == "poison" and fx.random() < 0.6:
            life = fx.uniform(1.0, 1.8)
            self.wisps.append(Mote("cloud", point, drift, life, size * fx.uniform(0.9, 1.2)))
        elif breath == "cold":
            self.wisps.append(Mote("mist", point, drift, fx.uniform(0.5, 0.9), size * 0.9))
        elif breath == "acid":
            ground = self._ground_below(point)
            if point.y >= floor - 0.5:
                self.wisps += splash(Vec2(point.x, floor), 2.0, fx)
            elif fx.random() < 0.6:
                velocity = Vec2(flame.velocity.x * 0.3, max(0.0, flame.velocity.y * 0.3))
                drip = Mote("drip", point, velocity, 3.0, fx.uniform(1.0, 1.8), floor=ground)
                self.wisps.append(drip)
        elif breath == "lightning" and fx.random() < 0.3:
            velocity = Vec2.from_angle(fx.uniform(0.0, math.tau), fx.uniform(30.0, 80.0))
            self.wisps.append(Mote("spark", point, velocity, fx.uniform(0.15, 0.3), 1.0))

    # ----- death -----------------------------------------------------------------

    def die(self, point: Vec2, push: Vec2) -> None:
        """Stop everything and fall, knocked along a little by the killing blow."""
        self.dead = True
        self.down_time = 0.0
        self.velocity = (self.velocity if self.flying else ZERO) + push * 0.3
        self._set_mode(DragonMode.DEAD)
        self.fire_time = 0.0
        self.fire_target = None
        self.support = None

    def update_dead(self, dt: float) -> None:
        self.clock += dt
        self.down_time += dt
        self.mode_time += dt
        ground = self._ground_below(self.body)
        rest = ground - LYING_HEIGHT
        base = 0.0 if self.facing > 0 else math.pi
        down = self.body.y >= rest - 0.5 and self.velocity.y >= 0.0
        if down:
            if self.velocity.length() > 0.0:
                self.world.debris.burst(
                    Vec2(self.body.x, ground), Vec2(0.0, -1.0), 6, 120.0, spread=2.5, puffs=8
                )
            self.velocity = ZERO
            self.body = Vec2(self.body.x, rest)
        else:
            drag = math.exp(-1.5 * dt)
            self.velocity = Vec2(self.velocity.x * drag, self.velocity.y + FALL_GRAVITY * dt)
            self.body += self.velocity * dt
            if self.body.y > rest:
                self.body = Vec2(self.body.x, rest)
        tilt = 0.08 if down else 0.5
        self.angle += (base + self.facing * tilt - self.angle) * min(1.0, dt * 4.0)
        self._pose_limp(dt, ground, down)
        self._update_flames(dt)

    def _ground_below(self, point: Vec2) -> float:
        """The floor or the top of the highest window under `point`."""
        tops = [
            box.top
            for box in self.world.boxes
            if box.left <= point.x <= box.right and box.top >= point.y - 2.0
        ]
        return min([self.world.floor_y, *tops])

    def _pose_limp(self, dt: float, ground: float, down: bool) -> None:
        """Legs splayed (or dangling while it falls), head and tail sagging to the ground."""
        rate = min(1.0, dt * 8.0)
        for leg in self.legs:
            root = (self.shoulder if leg.front else self.hip) + self.local(Vec2(0.0, 2.0))
            out = (1.0 if leg.front else -1.0) * self.facing
            if down:
                target = Vec2(root.x + out * 14.0 * SCALE, ground)
            else:
                target = root + Vec2(out * 5.0, 18.0) * SCALE
            bend = -self.facing if leg.front else self.facing
            foot = leg.foot.lerp(target, rate)
            leg.root, leg.knee, leg.foot = two_bone_points(root, UPPER_LEG, LOWER_LEG, foot, bend)
        head = self.neck_base + Vec2(self.facing * 16.0, 14.0) * SCALE
        head = Vec2(head.x, min(head.y, ground - 4.0 * SCALE))
        self.head = self.head.lerp(head, min(1.0, dt * 6.0))
        snout = (0.0 if self.facing > 0 else math.pi) + self.facing * 0.5
        self.head_angle += math.remainder(snout - self.head_angle, math.tau) * min(1.0, dt * 6.0)
        self.jaw += (0.35 - self.jaw) * min(1.0, dt * 6.0)
        tail = self.tail
        tail[0] = self.hip - self.forward * (2.0 * SCALE)
        relax = min(1.0, dt * 5.0)
        for i in range(1, len(tail)):
            if down:
                x = tail[0].x - self.facing * TAIL_SPACING * i * 0.95
                rest = Vec2(x, self._ground_below(Vec2(x, tail[0].y)) - 1.5 * SCALE)
            else:
                rest = tail[0] + self.local(Vec2(-TAIL_SPACING * i, 0.0))
            pulled = tail[i].lerp(rest, relax)
            floor = self._ground_below(pulled) - 1.5 * SCALE
            pulled = Vec2(pulled.x, min(pulled.y, floor))
            offset = pulled - tail[i - 1]
            length = offset.length()
            if length > 1e-6:
                tail[i] = tail[i - 1] + offset * (TAIL_SPACING / length)

    def _hit(self, stickman: Stickman, push: Vec2, death: str, bleed: bool = True) -> bool:
        """`DRAGON_DAMAGE` to `stickman`; True if it killed him."""
        killed = stickman.hurt(DRAGON_DAMAGE, stickman.center(), push, "dragon", death, bleed)
        self.catches += killed
        return killed

    # ----- terrain ---------------------------------------------------------------

    def terrain_changed(self, change: TerrainChange) -> None:
        from dungeons_desktops.systems.actors import surface_below

        if self.mode is DragonMode.LAND:
            self._start_landing()
            return
        if self.flying or self.support is None:
            return
        box = self.support.box
        if change.removed(box):
            self._takeoff()
            return
        ground = self.support.start.y
        delta = change.delta_for(box)
        if delta is not None:
            self.x += delta.x
            ground += delta.y
            self._shift(delta)
        anchor = surface_below(self.world.goblin_planner, Vec2(self.x, ground - 2.0))
        if anchor is None or abs(anchor.point.y - ground) > 2.0:
            self._takeoff()
            return
        self.support = anchor.surface

    def _shift(self, delta: Vec2) -> None:
        self.body += delta
        self.head += delta
        self.tail = [p + delta for p in self.tail]
        for leg in self.legs:
            leg.foot += delta
            leg.knee += delta
            leg.root += delta

    # ----- pose ------------------------------------------------------------------

    def _pose(self, dt: float, snap: bool = False) -> None:
        walking = not self.flying
        swiping = self.mode is DragonMode.SWIPE
        rear = math.sin(math.pi * min(1.0, self.mode_time / SWIPE_TIME)) if swiping else 0.0
        if walking:
            assert self.support is not None or snap
            ground = self.support.start.y if self.support is not None else self.body.y
            base = 0.0 if self.facing > 0 else math.pi
            self.angle = base - self.facing * 0.18 * rear
            bob = math.sin(self.phase * math.tau * 2.0) * 1.0 * self.gait
            hip = Vec2(self.x - self.facing * BODY_LENGTH / 2, ground - HIP_HEIGHT + bob)
            self.body = hip + self.forward * (BODY_LENGTH / 2)
        else:
            ground = self.body.y + HIP_HEIGHT

        blend = 1.0 if snap else min(1.0, dt * 14.0)
        settled = snap or self.mode_time >= LAND_BLEND
        if walking and not swiping:
            blend = max(blend, self.mode_time / LAND_BLEND)
        for leg in self.legs:
            root = (self.shoulder if leg.front else self.hip) + self.local(Vec2(0.0, 2.0))
            if walking:
                target = self._planted_foot(leg, root, ground)
                if swiping and leg.front and leg.near:
                    target = self._swipe_foot(root, ground)
                foot = target if settled else leg.foot.lerp(target, blend)
            else:
                tuck = self.local(Vec2(-9.0, 11.5) * SCALE)
                foot = leg.foot.lerp(root + tuck, blend)
            bend = -self.facing if leg.front else self.facing
            leg.root, leg.knee, leg.foot = two_bone_points(root, UPPER_LEG, LOWER_LEG, foot, bend)
            if walking:
                leg.lift = clamp((ground - leg.foot.y) / (3.5 * SCALE), 0.0, 1.0)
            else:
                leg.lift += (1.0 - leg.lift) * (1.0 if snap else min(1.0, dt * 8.0))

        self._pose_head(dt, snap)
        self._pose_tail(dt)
        opening = self.fire_time > 0.0 or (swiping and 0.2 < rear)
        self.jaw += ((1.0 if opening else 0.0) - self.jaw) * min(1.0, dt * 12.0)

    def _planted_foot(self, leg: Leg, root: Vec2, ground: float) -> Vec2:
        p = (self.phase + leg.phase_offset) % 1.0
        span = STANCE * STRIDE
        if p < STANCE:
            along, lift = span * (0.5 - p / STANCE), 0.0
        else:
            u = (p - STANCE) / (1.0 - STANCE)
            along, lift = span * (-0.5 + smoothstep(u)), math.sin(math.pi * u) * STEP_HEIGHT
        x = root.x + self.facing * (1.5 * SCALE + along * self.gait)
        return Vec2(x, ground - lift * self.gait)

    def _swipe_foot(self, root: Vec2, ground: float) -> Vec2:
        u = min(1.0, self.mode_time / SWIPE_TIME)
        rest = Vec2(1.5, ground - root.y)
        raised, struck = Vec2(13.0, -8.0) * SCALE, Vec2(28.5, 11.5) * SCALE
        if u < 0.45:
            point = rest.lerp(raised, smoothstep(u / 0.45))
        elif u < 0.6:
            point = raised.lerp(struck, smoothstep((u - 0.45) / 0.15))
        else:
            point = struck.lerp(rest, smoothstep((u - 0.6) / 0.4))
        return root + self.local(point)

    def _pose_head(self, dt: float, snap: bool) -> None:
        swiping = self.mode is DragonMode.SWIPE
        reach = NECK
        if self.flying:
            reach = Vec2(30.0, -9.0) * SCALE
        if swiping:
            u = min(1.0, self.mode_time / SWIPE_TIME)
            reach = reach.lerp(Vec2(26.0, -5.0) * SCALE, math.sin(math.pi * u))
        bob = math.sin(self.phase * math.tau * 2.0 + 0.8) * 0.8 * self.gait
        head = self.shoulder + self.local(reach + Vec2(0.0, bob))
        heading = self.angle + self.facing * 0.25
        if self.fire_time > 0.0 and self.fire_target is not None:
            aim = (self.fire_target.center() - self.neck_base).normalized()
            head = self.neck_base + aim * (NECK.length() * 1.05)
            heading = aim.angle()
        rate = 1.0 if snap else min(1.0, dt * 12.0)
        self.head = self.head.lerp(head, rate)
        turn = math.remainder(heading - self.head_angle, math.tau)
        self.head_angle += turn * rate

    def _pose_tail(self, dt: float) -> None:
        """Each segment eases toward a resting curve behind the hip (a low S that lifts
        at the tip, swaying), then the chain is pulled back to its segment spacing."""
        tail = self.tail
        count = len(tail)
        tail[0] = self.hip - self.forward * (2.0 * SCALE)
        relax = min(1.0, (2.5 if self.flying else 5.0) * dt)
        for i in range(1, count):
            t = i / (count - 1)
            sway = math.sin(self.mode_time * 2.2 - i * 0.5) * 2.5 * SCALE * t
            drop = 4.0 * SCALE * math.sin(math.pi * t) - 9.0 * SCALE * t * t
            rest = tail[0] + self.local(Vec2(-TAIL_SPACING * i, drop + sway))
            pulled = tail[i].lerp(rest, relax)
            offset = pulled - tail[i - 1]
            length = offset.length()
            if length > 1e-6:
                tail[i] = tail[i - 1] + offset * (TAIL_SPACING / length)
