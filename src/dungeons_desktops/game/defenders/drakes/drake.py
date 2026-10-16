"""Kobold drake riders: a pack of little chromatic drakes (three of red, blue, green,
black and white, all different), each built like a chicken - two legs, a deep chest,
a long balancing tail - with a kobold archer of its own colour in the saddle.

A drake fights in a cycle. It takes off and holds station in the air for
`HOVER_TIME`, off to one side of and above its quarry (the pack spreads around him),
then dives on an adventurer standing on a window top or the floor, lands beside him
and fights on foot - running at him and biting - for `GROUND_FIGHT`, then takes off
again. With nobody about it wanders, and now and then flies off to another window.

Its attacks run on their own clocks whatever the drake is doing: the kobold shoots
arrows (`ARROW_DAMAGE`) at whichever adventurer is nearest him, and every
`BOLT_COOLDOWN` the drake spits a small bolt of its breath that flies through
windows to where it was aimed (or the first adventurer in its way) and bursts there
in a flask-sized blast (`BOLT_DAMAGE` to everyone in it). The kobold also drops a
trap now and then (see `kobolds`). When the drake dies the kobold jumps off and
fights on, on foot, until the last drake of the pack is dead (see `session`).

Walking is a two-beat gait: the legs swing half a cycle apart and the cycle advances
with distance travelled so planted feet never slide. Each leg is a two-bone IK chain
from the hip to the foot with the hock kicked back, like a bird's.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.game.actors.mortal import DRAKE_HP, Mortal
from dungeons_desktops.game.effects.breath import BREATHS
from dungeons_desktops.navigation.terrain import Surface, TerrainChange
from dungeons_desktops.rig.ik import two_bone_points

if TYPE_CHECKING:
    from dungeons_desktops.game.adventurers.actor import Stickman
    from dungeons_desktops.game.world.simulation import SimWorld

COLOURS = ("red", "blue", "green", "black", "white")
"""One drake of each chromatic colour, in the order the pack is summoned."""

BODY_LENGTH = 10.0
"""Hip to chest."""
BODY_TILT = 0.32
"""Chest held higher than the hip."""
HIP_HEIGHT = 9.5
THIGH = 5.5
SHANK = 5.5
STRIDE = 11.0
STANCE = 0.55
STEP_HEIGHT = 3.0
NECK = Vec2(3.5, -7.5)
"""Chest to head, body-relative (x forward, y down)."""
TAIL_SEGMENTS = 6
TAIL_SPACING = 2.2
SADDLE = Vec2(-3.2, -4.0)
"""Where the kobold sits, body-relative from the middle of the back."""
RIDER_TORSO = 4.5
RIDER_HEAD = 2.2

WALK_SPEED = 26.0
RUN_SPEED = 58.0
HOP_RANGE = 220.0
"""Quarry farther off than this along its own surface, it flies to rather than runs."""
ACCELERATION = 5.0
WANDER_WAIT = (0.8, 2.5)
GROUND_TIME = (6.0, 12.0)
"""How long it wanders on one surface with nobody about before flying elsewhere."""
GROUND_FIGHT = 6.0
"""How long it fights on foot after a dive before taking off again."""
SETTLE = 0.8
"""Seconds on the ground before it'll take off again after its quarry."""
STANDOFF = 9.0
"""How far from its quarry it lands and stands to bite."""
PACK_GAP = 5.0
"""Extra standoff per pack slot, so they spread out around their quarry."""
LAND_SCATTER = (15.0, 110.0)
"""How far from its quarry a dive comes down, picked afresh each flight."""
LAND_CHOICES = 8
"""Random spots it weighs for a landing, taking the one farthest from its packmates."""
RETARGET = 1.0

HOVER_TIME = 7.0
HOVER_RANGE = 90.0
"""How far off to the side of its quarry it holds station in the air..."""
HOVER_HEIGHT = 70.0
"""...and how far above him."""
HOVER_SPREAD = 16.0
"""Extra range per pack slot, so the pack doesn't hover in a clump."""
FLY_SPEED = 170.0
DIVE_SPEED = 260.0
TAKEOFF_SPEED = 150.0
LAND_SPEED = 150.0
STEER = 9.0
"""How hard it turns its velocity onto the course it wants: high, so it holds a line."""
CRUISE_RISE = 45.0
"""How far above a higher landing it climbs before heading over to it."""
APPROACH = 40.0
"""Horizontal distance from a higher landing where it stops climbing and drops in."""
REPLAN = 0.25
FLIGHT_LIMIT = 10.0
MIN_LANDING = 16.0
FLAP_BOB = 1.0
FALL_GRAVITY = 600.0
LYING_HEIGHT = 4.0

BITE_REACH = 4.0
BITE_TIME = 0.35
BITE_COOLDOWN = 1.0
BITE_DAMAGE = 2
BITE_PUSH = 160.0

BOW_RANGE = 280.0
BOW_COOLDOWN = (1.4, 2.0)
ARROW_SPEED = 330.0
ARROW_GRAVITY = 160.0
ARROW_LIFE = 2.5
ARROW_DAMAGE = 1

BOLT_COOLDOWN = 4.0
BOLT_RANGE = 300.0
BOLT_SPEED = 230.0
BOLT_GRAVITY = 90.0
BOLT_LIFE = 2.0
BOLT_DAMAGE = 3
BLAST_TIME = 0.45
BOLT_DEATHS = {
    "red": "Burned up by a red drake's fire bolt!",
    "green": "Choked by a green drake's poison bolt!",
    "blue": "Fried by a blue drake's lightning bolt!",
    "black": "Melted by a black drake's acid bolt!",
    "white": "Frozen by a white drake's frost bolt!",
}

ZERO = Vec2(0.0, 0.0)


class DrakeMode(Enum):
    WALK = "walk"
    FLY = "fly"
    """Holding station in the air near its quarry."""
    DIVE = "dive"
    """Coming down to land: on its quarry, or somewhere new with nobody about."""
    DEAD = "dead"


@dataclass
class DrakeLeg:
    near: bool
    phase_offset: float
    foot: Vec2 = ZERO
    hock: Vec2 = ZERO
    root: Vec2 = ZERO
    lift: float = 0.0
    """0 planted, 1 tucked up in flight."""


@dataclass
class Missile:
    """An arrow or a breath bolt in flight."""

    position: Vec2
    velocity: Vec2
    age: float = 0.0
    target: Vec2 | None = None
    """Where a breath bolt was aimed: it bursts on arriving there."""


@dataclass
class Blast:
    center: Vec2
    radius: float
    age: float = 0.0


def step_arrows(
    world: SimWorld,
    arrows: list[Missile],
    dt: float,
    gravity: float = ARROW_GRAVITY,
    damage: int = ARROW_DAMAGE,
    source: str = "kobold",
    death: str = "Shot by a kobold archer!",
) -> list[Missile]:
    """Fly arrows (kobold ones by default) on; one that hits an adventurer hurts him and
    is spent. Returns those still in flight."""
    flying = []
    prey = [s for s in world.stickmen if s.prey]
    for arrow in arrows:
        arrow.age += dt
        arrow.velocity += Vec2(0.0, gravity * dt)
        arrow.position += arrow.velocity * dt
        point = arrow.position
        if not world.left - 20.0 <= point.x <= world.width + 20.0:
            continue
        hit = next((s for s in prey if s.hits(point, 0.8)), None)
        if hit is not None:
            push = arrow.velocity.normalized() * 120.0 + Vec2(0.0, -40.0)
            hit.hurt(damage, point, push, source, death)
        elif point.y < world.floor_y and arrow.age < ARROW_LIFE:
            flying.append(arrow)
    return flying


def lobbed(origin: Vec2, target: Vec2, speed: float, gravity: float) -> Vec2:
    """A velocity of `speed` from `origin` aimed high enough to drop onto `target`."""
    flight = origin.distance_to(target) / speed
    aim = target - Vec2(0.0, 0.5 * gravity * flight * flight)
    return (aim - origin).normalized() * speed


@dataclass(eq=False, repr=False)
class Drake(Mortal):
    world: SimWorld
    body: Vec2
    facing: int = 1
    variant: str = "red"
    """Its colour (and its kobold's): "red", "blue", "green", "black" or "white"."""
    slot: int = 0
    """Its place in the pack: how far back it hangs from the quarry."""
    mode: DrakeMode = DrakeMode.WALK
    velocity: Vec2 = ZERO
    angle: float = 0.0
    legs: list[DrakeLeg] = field(default_factory=list)
    tail: list[Vec2] = field(default_factory=list)
    arrows: list[Missile] = field(default_factory=list)
    bolts: list[Missile] = field(default_factory=list)
    blasts: list[Blast] = field(default_factory=list)
    max_hp = DRAKE_HP
    linger = 3.5

    def __post_init__(self) -> None:
        rng = self.world.random
        self.angle = self._level()
        self.support: Surface | None = None
        self.x = self.body.x
        self.speed = 0.0
        self.phase = 0.0
        self.gait = 0.0
        self.flap = rng.uniform(0.0, math.tau)
        self.pitch = 0.0
        self.mode_time = 0.0
        self.clock = 0.0
        self.ground_timer = rng.uniform(*GROUND_TIME)
        self.wander_x: float | None = None
        self.wander_wait = rng.uniform(*WANDER_WAIT)
        self.quarry: Stickman | None = None
        self.side = 1
        """Which side of its quarry it makes for, picked when it picks him."""
        self.retarget = 0.0
        self.landing: Vec2 | None = None
        self.scatter = 0.0
        """Where along its quarry's surface this dive comes down, relative to him."""
        self.cruise_y = self.body.y
        self.replan = REPLAN
        self.jaw = 0.0
        self.bite_time = 0.0
        self.bite_cooldown = 0.0
        self._bitten = False
        self.lean = 0.0
        """The kobold's lean: forward positive, back negative (radians)."""
        self.aim = Vec2(float(self.facing), -0.6).normalized()
        """Where the kobold points his bow (unit)."""
        self.archer_target: Stickman | None = None
        self.bow_cooldown = rng.uniform(0.5, BOW_COOLDOWN[1])
        self.bolt_cooldown = rng.uniform(1.5, BOLT_COOLDOWN)
        self.trap_cooldown = rng.uniform(2.0, 6.0)
        self._fx = random.Random(self.slot * 7919 + len(self.world.drakes))
        self.head = self.body
        self.head_angle = self.angle
        self.legs = [DrakeLeg(near=True, phase_offset=0.0), DrakeLeg(near=False, phase_offset=0.5)]
        self.tail = []
        self.snap()

    def snap(self) -> None:
        """Pose it at once where it stands (or hangs in the air)."""
        self._pose(1.0 / 60.0, snap=True)
        self.tail = [
            self.hip - self.forward * (TAIL_SPACING * (i + 1)) for i in range(TAIL_SEGMENTS)
        ]
        self._pose(1.0 / 60.0, snap=True)

    # ----- frame -----------------------------------------------------------------

    def _level(self) -> float:
        return -BODY_TILT if self.facing > 0 else math.pi + BODY_TILT

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
    def chest(self) -> Vec2:
        return self.body + self.forward * (BODY_LENGTH / 2)

    @property
    def hip(self) -> Vec2:
        return self.body - self.forward * (BODY_LENGTH / 2)

    @property
    def neck_base(self) -> Vec2:
        return self.chest + self.local(Vec2(0.5, -2.0))

    @property
    def mouth(self) -> Vec2:
        return self.head + Vec2.from_angle(self.head_angle, 7.0)

    @property
    def seat(self) -> Vec2:
        return self.body + self.local(SADDLE)

    @property
    def rider_up(self) -> Vec2:
        """The kobold's spine, seat to shoulders (unit)."""
        return Vec2(0.0, -1.0).rotated(self.facing * self.lean)

    @property
    def rider_shoulder(self) -> Vec2:
        return self.seat + self.rider_up * RIDER_TORSO

    @property
    def rider_head(self) -> Vec2:
        return self.rider_shoulder + self.rider_up * (RIDER_HEAD + 0.6)

    @property
    def bow_hand(self) -> Vec2:
        return self.rider_shoulder + self.aim * 3.2

    @property
    def bow_draw(self) -> float:
        """How far the bowstring is drawn back: 0 just loosed, 1 ready to shoot."""
        if self.dead or self.archer_target is None:
            return 0.0
        return clamp(1.0 - self.bow_cooldown / 0.8, 0.0, 1.0)

    @property
    def flying(self) -> bool:
        return self.mode in (DrakeMode.FLY, DrakeMode.DIVE)

    @property
    def _top(self) -> float:
        return self.world.ceiling if self.world.ceiling is not None else 0.0

    def center(self) -> Vec2:
        return self.body

    def parts(self) -> list[Vec2]:
        return [self.body, self.chest, self.hip, self.head, self.rider_shoulder, self.rider_head]

    def hits(self, point: Vec2, margin: float = 0.0) -> bool:
        return (
            any(p.distance_to(point) <= 5.0 + margin for p in (self.body, self.chest, self.hip))
            or self.head.distance_to(point) <= 5.0 + margin
            or self.rider_shoulder.distance_to(point) <= 3.0 + margin
            or self.rider_head.distance_to(point) <= RIDER_HEAD + margin
        )

    # ----- simulation --------------------------------------------------------------

    def update(self, dt: float) -> None:
        self.clock += dt
        self.mode_time += dt
        self.bite_cooldown -= dt
        shown = self.facing
        self._pick_quarry(dt)
        if self.mode is DrakeMode.WALK:
            self._walk(dt)
        elif self.mode is DrakeMode.FLY:
            self._hover(dt)
        else:
            self._dive(dt)
        if self.flying and self.facing != shown:
            self._mirror()
        self._bite(dt)
        self._pose(dt)
        self._shoot(dt)
        self._spit(dt)
        self._update_missiles(dt)
        self.trap_cooldown = self.world.traps.lay(self.seat, self.variant, self.trap_cooldown, dt)

    def _set_mode(self, mode: DrakeMode) -> None:
        self.mode = mode
        self.mode_time = 0.0

    def _prey(self) -> list[Stickman]:
        return [s for s in self.world.stickmen if s.prey]

    def _pick_quarry(self, dt: float) -> None:
        self.retarget -= dt
        quarry = self.quarry
        if quarry is not None and quarry.prey and self.retarget > 0.0:
            return
        self.retarget = RETARGET
        chosen = min(self._prey(), key=lambda s: s.center().distance_to(self.body), default=None)
        if chosen is not None and chosen is not quarry:
            self._pick_side(chosen)
        self.quarry = chosen

    def _pick_side(self, stickman: Stickman) -> None:
        side = 1 if self.body.x >= stickman.contact().x else -1
        self.side = -side if self.slot % 2 else side

    def _spot_near(
        self, stickman: Stickman, offset: float | None = None
    ) -> tuple[Surface, float] | None:
        """The surface under `stickman` and the x on it this drake wants to stand at:
        `offset` from him, or by default its own distance off to its side of him
        (alternate drakes take opposite sides)."""
        from dungeons_desktops.game.adventurers.actor import surface_below

        foot = stickman.contact()
        anchor = surface_below(self.world.goblin_planner, foot - Vec2(0.0, 2.0))
        if anchor is None or not anchor.surface.walkable:
            return None
        surface = anchor.surface
        if offset is None:
            offset = self.side * (STANDOFF + PACK_GAP * ((self.slot + 1) // 2))
        low, high = self._range(surface)
        return surface, clamp(foot.x + offset, low, high)

    def _pick_scatter(self, stickman: Stickman) -> None:
        """A random spot near him to come down on, as clear of the rest of the pack
        (where they stand, or are landing) as the surface allows."""
        rng = self.world.random
        foot = stickman.contact()
        others = [
            d.landing if d.landing is not None else d.body
            for d in self.world.drakes
            if d is not self and d.mode is not DrakeMode.DEAD
        ]
        best, room = 0.0, -1.0
        for _ in range(LAND_CHOICES):
            offset = rng.choice((-1, 1)) * rng.uniform(*LAND_SCATTER)
            spot = self._spot_near(stickman, offset)
            if spot is None:
                return
            point = Vec2(spot[1], spot[0].start.y)
            clear = min((point.distance_to(p) for p in others), default=math.inf)
            if clear > room:
                best, room = spot[1] - foot.x, clear
        self.scatter = best

    def _grounded(self, stickman: Stickman) -> bool:
        """On his feet on a window top or the floor: somewhere to dive on him."""
        from dungeons_desktops.game.adventurers.actor import surface_below

        foot = stickman.contact()
        anchor = surface_below(self.world.goblin_planner, foot - Vec2(0.0, 2.0))
        return (
            anchor is not None
            and anchor.surface.walkable
            and abs(anchor.point.y - foot.y) < 3.0
            and abs(anchor.point.x - foot.x) < 3.0
        )

    # ----- walking -----------------------------------------------------------------

    def _range(self, surface: Surface) -> tuple[float, float]:
        margin = 5.0
        low, high = surface.low + margin, surface.high - margin
        if low > high:
            low = high = (surface.low + surface.high) / 2
        return low, high

    def _walk(self, dt: float) -> None:
        surface = self.support
        if surface is None:
            self._takeoff()
            return
        rng = self.world.random
        low, high = self._range(surface)
        quarry = self.quarry
        spot = self._spot_near(quarry) if quarry is not None else None
        top_speed = WALK_SPEED
        if quarry is not None:
            self.ground_timer = min(self.ground_timer, GROUND_FIGHT) - dt
            if self.ground_timer <= 0.0:
                self._takeoff()
                return
        if quarry is not None and spot is None:
            goal = self.x
        elif spot is not None and (spot[0] is not surface or abs(spot[1] - self.x) > HOP_RANGE):
            if self.mode_time > SETTLE:
                self._takeoff()
                return
            goal = self.x
        elif spot is not None:
            goal, top_speed = spot[1], RUN_SPEED
            self.wander_x = None
        else:
            self.ground_timer -= dt
            if self.ground_timer <= 0.0:
                self._takeoff()
                return
            if self.wander_x is None or abs(self.wander_x - self.x) < 2.0:
                self.wander_x = None
                self.wander_wait -= dt
                if self.wander_wait <= 0.0:
                    self.wander_x = rng.uniform(low, high)
                    self.wander_wait = rng.uniform(*WANDER_WAIT)
            goal = self.wander_x if self.wander_x is not None else self.x

        offset = goal - self.x
        if abs(offset) > 1.0 and self.bite_time <= 0.0:
            direction = 1 if offset > 0 else -1
            if direction != self.facing and abs(self.speed) < 8.0:
                self._turn(direction)
            desired = direction * top_speed * min(1.0, abs(offset) / 12.0)
        else:
            desired = 0.0
            if quarry is not None and abs(self.speed) < 4.0 and self.bite_time <= 0.0:
                face = 1 if quarry.contact().x > self.x else -1
                if face != self.facing:
                    self._turn(face)
        self.speed += (desired - self.speed) * min(1.0, ACCELERATION * dt)
        self.x += self.speed * dt
        if not low <= self.x <= high:
            self.x = clamp(self.x, low, high)
            self.speed = 0.0
            self.wander_x = None
        self.phase += abs(self.speed) * dt / STRIDE
        moving = min(1.0, abs(self.speed) / (WALK_SPEED * 0.4))
        self.gait += (moving - self.gait) * min(1.0, 8.0 * dt)

    def _turn(self, direction: int) -> None:
        self.facing = direction
        self.angle = self._level()

    # ----- biting ------------------------------------------------------------------

    @property
    def _bite_point(self) -> Vec2:
        return self.head + Vec2(self.facing * 4.0, 1.0)

    def _bite(self, dt: float) -> None:
        """On foot, snap at an adventurer in front of its jaws."""
        if self.bite_time > 0.0:
            self.bite_time -= dt
            if not self._bitten and self.bite_time <= BITE_TIME * 0.5:
                self._bitten = True
                point = self._bite_point
                for stickman in self._prey():
                    if stickman.hits(point, BITE_REACH + 2.0):
                        push = Vec2(self.facing * BITE_PUSH, -90.0)
                        death = f"Torn apart by a {self.variant} drake!"
                        stickman.hurt_from(self, BITE_DAMAGE, point, push, "drake", death)
                        break
            return
        if self.mode is not DrakeMode.WALK or self.bite_cooldown > 0.0:
            return
        point = self._bite_point
        if any(s.hits(point, BITE_REACH) for s in self._prey()):
            self.bite_time = BITE_TIME
            self.bite_cooldown = BITE_COOLDOWN
            self._bitten = False
            self.speed = 0.0

    # ----- flying ------------------------------------------------------------------

    def _random_spot(self) -> tuple[Surface, float] | None:
        rng = self.world.random
        spots = [
            s
            for s in self.world.goblin_planner.surfaces
            if s.walkable and s.length >= MIN_LANDING and s is not self.support
        ]
        if not spots:
            return None
        surface = rng.choices(spots, weights=[s.length for s in spots])[0]
        low, high = self._range(surface)
        return surface, rng.uniform(low, high)

    def _set_landing(self, spot: tuple[Surface, float] | None, fresh: bool = True) -> None:
        """Where to come down; a `fresh` flight also picks the height to cruise at (a
        re-plan in the air only ever lowers it, to clear a lower landing)."""
        if spot is None:
            spot = self._random_spot()
        if spot is None:
            self.landing = None
            return
        surface, x = spot
        self.landing = Vec2(x, surface.start.y)
        rise = self.landing.y - HIP_HEIGHT - CRUISE_RISE
        cruise = min(self.body.y - CRUISE_RISE, rise) if fresh else min(self.cruise_y, rise)
        self.cruise_y = max(self._top + 20.0, cruise)

    def _takeoff(self) -> None:
        """Up into the air: to hover near its quarry, or off to land somewhere else with
        nobody about."""
        self.support = None
        self.velocity = Vec2(self.facing * 40.0, -TAKEOFF_SPEED)
        self.replan = REPLAN
        self.bite_time = 0.0
        if self.quarry is not None:
            self._set_mode(DrakeMode.FLY)
            self.landing = None
        else:
            self._set_mode(DrakeMode.DIVE)
            self._set_landing(None)
        ground = self.body + self.local(Vec2(0.0, HIP_HEIGHT))
        self.world.debris.burst(ground, Vec2(0, -1), 5, 90.0, spread=1.4, puffs=3, scale=0.5)

    def _station(self, quarry: Stickman) -> Vec2:
        """Where it holds in the air: off to its side of its quarry and above him,
        drifting a little."""
        world = self.world
        target = quarry.center()
        reach = HOVER_RANGE + HOVER_SPREAD * (self.slot // 2)
        x = target.x + self.side * reach
        if not world.left + 20.0 <= x <= world.width - 20.0:
            x = target.x - self.side * reach
        height = HOVER_HEIGHT + 12.0 * (self.slot % 3)
        drift = Vec2(
            math.sin(self.clock * 0.9 + self.slot * 1.3) * 12.0,
            math.cos(self.clock * 1.3 + self.slot) * 8.0,
        )
        station = Vec2(x, target.y - height) + drift
        return Vec2(
            clamp(station.x, world.left + 20.0, world.width - 20.0),
            clamp(station.y, self._top + 20.0, world.floor_y - HIP_HEIGHT - 20.0),
        )

    def _hover(self, dt: float) -> None:
        quarry = self.quarry
        if quarry is None:
            self._set_mode(DrakeMode.DIVE)
            self._set_landing(None)
            return
        to_station = self._station(quarry) - self.body
        distance = to_station.length()
        desired = to_station.normalized() * min(FLY_SPEED, distance * 4.0)
        self.velocity += (desired - self.velocity) * min(1.0, STEER * dt)
        self._move_in_air(dt)
        dx = quarry.center().x - self.body.x
        if abs(dx) > 4.0:
            self.facing = 1 if dx > 0 else -1
            self.angle = self.pitch if self.facing > 0 else math.pi - self.pitch
        if self.mode_time >= HOVER_TIME:
            self._start_dive()

    def _start_dive(self) -> None:
        """Down on an adventurer on his feet - its quarry if he is, else the nearest
        one who is; with nobody on the ground it keeps circling a while longer."""
        quarry = self.quarry
        if quarry is None or not self._grounded(quarry):
            grounded = [s for s in self._prey() if self._grounded(s)]
            quarry = min(grounded, key=lambda s: s.center().distance_to(self.body), default=None)
        spot = self._spot_near(quarry) if quarry is not None else None
        if quarry is None or spot is None:
            self.mode_time = HOVER_TIME - 1.0
            return
        if quarry is not self.quarry:
            self.quarry = quarry
            self._pick_side(quarry)
            self.retarget = RETARGET
        self._pick_scatter(quarry)
        spot = self._spot_near(quarry, self.scatter)
        assert spot is not None
        self._set_mode(DrakeMode.DIVE)
        self.replan = REPLAN
        self._set_landing(spot)

    def _dive(self, dt: float) -> None:
        self.replan -= dt
        if self.replan <= 0.0:
            self.replan = REPLAN
            if self.quarry is not None:
                spot = self._spot_near(self.quarry, self.scatter)
                if spot is not None:
                    self._set_landing(spot, fresh=False)
        landing = self.landing
        if landing is None:
            self._set_landing(None)
            if self.landing is None:
                self._touch_down(self.body)
            return
        goal = landing - Vec2(0.0, HIP_HEIGHT - 1.0)
        below = self.body.y > goal.y - 15.0
        cruising = below and abs(goal.x - self.body.x) > APPROACH
        aim = Vec2(goal.x, min(goal.y, self.cruise_y)) if cruising else goal
        to_aim = aim - self.body
        distance = to_aim.length()
        if not cruising and distance < 5.0:
            self._touch_down(landing)
            return
        fast = DIVE_SPEED if self.quarry is not None else FLY_SPEED
        top = fast if distance > 60.0 else LAND_SPEED
        desired = to_aim.normalized() * min(top, distance * 5.0 + 30.0)
        self.velocity += (desired - self.velocity) * min(1.0, STEER * dt)
        self._move_in_air(dt)
        if self.mode_time > FLIGHT_LIMIT:
            self._touch_down(landing)

    def _move_in_air(self, dt: float) -> None:
        world = self.world
        x = clamp(self.body.x + self.velocity.x * dt, world.left + 6.0, world.width - 6.0)
        y = self.body.y + self.velocity.y * dt
        flap = self.flap + dt * (24.0 if self.velocity.y < -30.0 else 16.0)
        y += FLAP_BOB * (math.cos(flap) - math.cos(self.flap))
        y = clamp(y, self._top + 10.0, world.floor_y - HIP_HEIGHT + 1.0)
        self.body = Vec2(x, y)
        self.flap = flap
        if abs(self.velocity.x) > 12.0:
            self.facing = 1 if self.velocity.x > 0 else -1
        climb = math.atan2(self.velocity.y, max(abs(self.velocity.x), 1.0))
        pitch = clamp(0.5 * climb, -0.45, 0.35)
        self.pitch += (pitch - self.pitch) * min(1.0, 6.0 * dt)
        self.angle = self.pitch if self.facing > 0 else math.pi - self.pitch

    def _mirror(self) -> None:
        """Flip the posed head, tail and legs across the body as it turns in the air."""
        x2 = 2.0 * self.body.x

        def flip(p: Vec2) -> Vec2:
            return Vec2(x2 - p.x, p.y)

        self.head = flip(self.head)
        self.head_angle = math.pi - self.head_angle
        self.tail = [flip(p) for p in self.tail]
        for leg in self.legs:
            leg.foot, leg.hock, leg.root = flip(leg.foot), flip(leg.hock), flip(leg.root)

    def _touch_down(self, landing: Vec2) -> None:
        from dungeons_desktops.game.adventurers.actor import surface_below

        anchor = surface_below(self.world.goblin_planner, landing - Vec2(0.0, 2.0))
        if anchor is None:
            self._set_landing(None)
            return
        self.support = anchor.surface
        low, high = self._range(anchor.surface)
        self.x = clamp(anchor.point.x, low, high)
        self.speed = 0.0
        self.gait = 0.0
        self.velocity = ZERO
        self.landing = None
        self._turn(self.facing)
        fighting = self.quarry is not None
        self.ground_timer = GROUND_FIGHT if fighting else self.world.random.uniform(*GROUND_TIME)
        self.bite_cooldown = 0.0
        self._set_mode(DrakeMode.WALK)
        self.world.debris.burst(anchor.point, Vec2(0, -1), 5, 90.0, spread=1.4, puffs=3, scale=0.5)

    # ----- the kobold's bow and the drake's breath -----------------------------------

    def _shoot(self, dt: float) -> None:
        """The kobold picks his own mark - the adventurer nearest him in range, whatever
        the drake is after - turns his bow on him and looses an arrow when it's drawn."""
        self.bow_cooldown -= dt
        shoulder = self.rider_shoulder
        in_range = [s for s in self._prey() if s.center().distance_to(shoulder) < BOW_RANGE]
        target = min(in_range, key=lambda s: s.center().distance_to(shoulder), default=None)
        self.archer_target = target
        if target is None:
            rest = Vec2(float(self.facing), -0.6).normalized()
            self.aim = self.aim.lerp(rest, min(1.0, dt * 6.0)).normalized()
            return
        velocity = lobbed(self.bow_hand, target.center(), ARROW_SPEED, ARROW_GRAVITY)
        want = velocity.normalized()
        self.aim = self.aim.lerp(want, min(1.0, dt * 12.0)).normalized()
        if self.bow_cooldown <= 0.0 and self.aim.dot(want) > 0.97:
            self.arrows.append(Missile(self.bow_hand + want * 2.0, velocity))
            self.bow_cooldown = self._fx.uniform(*BOW_COOLDOWN)

    def _spit(self, dt: float) -> None:
        """Every `BOLT_COOLDOWN`, a bolt of breath at its quarry (or whoever is nearest)."""
        self.bolt_cooldown -= dt
        if self.bolt_cooldown > 0.0:
            return
        mouth = self.mouth
        quarry = self.quarry
        if quarry is None or quarry.center().distance_to(mouth) > BOLT_RANGE:
            near = [s for s in self._prey() if s.center().distance_to(mouth) < BOLT_RANGE]
            quarry = min(near, key=lambda s: s.center().distance_to(mouth), default=None)
        if quarry is None:
            self.bolt_cooldown = 0.25
            return
        target = quarry.center()
        velocity = lobbed(mouth, target, BOLT_SPEED, BOLT_GRAVITY)
        self.bolts.append(Missile(mouth, velocity, target=target))
        self.bolt_cooldown = BOLT_COOLDOWN
        self.jaw = 1.0

    def _update_missiles(self, dt: float) -> None:
        world = self.world
        for blast in self.blasts:
            blast.age += dt
        self.blasts = [b for b in self.blasts if b.age < BLAST_TIME]
        self.arrows = step_arrows(world, self.arrows, dt)
        bolts = []
        for bolt in self.bolts:
            alive = self._fly_missile(bolt, dt, BOLT_GRAVITY)
            point = bolt.position
            target = bolt.target
            if target is not None and (
                point.distance_to(target) < 4.0 or (target - point).dot(bolt.velocity) <= 0.0
            ):
                self._burst(target)
            elif (
                not alive
                or point.y >= world.floor_y
                or bolt.age >= BOLT_LIFE
                or any(s.hits(point, 1.5) for s in self._prey())
            ):
                self._burst(Vec2(point.x, min(point.y, world.floor_y)))
            else:
                bolts.append(bolt)
        self.bolts = bolts

    def _fly_missile(self, missile: Missile, dt: float, gravity: float) -> bool:
        """Move it; False once it's off the side of the screen."""
        missile.age += dt
        missile.velocity += Vec2(0.0, gravity * dt)
        missile.position += missile.velocity * dt
        return self.world.left - 20.0 <= missile.position.x <= self.world.width + 20.0

    def _burst(self, center: Vec2) -> None:
        """A flask-sized blast of breath: `BOLT_DAMAGE` to every adventurer in it."""
        radius = self.world.vials.blast_radius
        self.blasts.append(Blast(center, radius))
        breath = BREATHS[self.variant]
        for stickman in self._prey():
            if not stickman.hits(center, radius):
                continue
            away = (stickman.center() - center).normalized()
            push = away * 220.0 + Vec2(0.0, -140.0)
            death = BOLT_DEATHS[self.variant]
            if stickman.hurt_from(
                self, BOLT_DAMAGE, stickman.center(), push, "drake", death, bleed=False
            ):
                stickman.succumb(breath)

    # ----- death -------------------------------------------------------------------

    def die(self, point: Vec2, push: Vec2) -> None:
        """Stop everything and fall, knocked along a little by the killing blow."""
        self.dead = True
        self.down_time = 0.0
        self.velocity = (self.velocity if self.flying else ZERO) + push * 0.3
        self._set_mode(DrakeMode.DEAD)
        self.support = None
        self.quarry = None
        self.archer_target = None
        self.bite_time = 0.0
        leap = self.velocity * 0.4 + Vec2(-self.facing * 45.0, -110.0)
        self.world.add_kobold(self.seat, self.variant, self.facing, leap, self.aim)

    def update_dead(self, dt: float) -> None:
        self.clock += dt
        self.down_time += dt
        self.mode_time += dt
        ground = self._ground_below(self.body)
        rest = ground - LYING_HEIGHT
        down = self.body.y >= rest - 0.5 and self.velocity.y >= 0.0
        if down:
            if self.velocity.length() > 0.0:
                self.world.debris.burst(
                    Vec2(self.body.x, ground), Vec2(0.0, -1.0), 4, 90.0, spread=2.5, puffs=4
                )
            self.velocity = ZERO
            self.body = Vec2(self.body.x, rest)
        else:
            drag = math.exp(-1.5 * dt)
            self.velocity = Vec2(self.velocity.x * drag, self.velocity.y + FALL_GRAVITY * dt)
            self.body = Vec2(
                self.body.x + self.velocity.x * dt, min(rest, self.body.y + self.velocity.y * dt)
            )
        level = 0.0 if self.facing > 0 else math.pi
        self.angle += math.remainder(level - self.angle, math.tau) * min(1.0, dt * 5.0)
        self.lean += (1.3 - self.lean) * min(1.0, dt * 4.0)
        self._pose_limp(dt, ground, down)
        self._update_missiles(dt)

    def _ground_below(self, point: Vec2) -> float:
        """The floor or the top of the highest window under `point`."""
        tops = [
            box.top
            for box in self.world.boxes
            if box.left <= point.x <= box.right and box.top >= point.y - 2.0
        ]
        return min([self.world.floor_y, *tops])

    def _pose_limp(self, dt: float, ground: float, down: bool) -> None:
        rate = min(1.0, dt * 8.0)
        for leg in self.legs:
            root = self.hip + self.local(Vec2(0.5, 2.0))
            if down:
                out = (4.0 if leg.near else -2.0) * self.facing
                target = Vec2(root.x + out + self.facing * 6.0, ground)
            else:
                target = root + Vec2(self.facing * 2.0, THIGH + SHANK - 1.0)
            foot = leg.foot.lerp(target, rate)
            leg.root, leg.hock, leg.foot = two_bone_points(root, THIGH, SHANK, foot, -self.facing)
            leg.lift += (0.6 - leg.lift) * rate
        head = self.chest + Vec2(self.facing * 6.0, 3.0)
        head = Vec2(head.x, min(head.y, ground - 2.0))
        self.head = self.head.lerp(head, min(1.0, dt * 6.0))
        snout = (0.0 if self.facing > 0 else math.pi) + self.facing * 0.4
        self.head_angle += math.remainder(snout - self.head_angle, math.tau) * min(1.0, dt * 6.0)
        self.jaw += (0.35 - self.jaw) * min(1.0, dt * 6.0)
        self._pose_tail(dt, ground if down else None)

    # ----- terrain -----------------------------------------------------------------

    def terrain_changed(self, change: TerrainChange) -> None:
        from dungeons_desktops.game.adventurers.actor import surface_below

        if self.mode is DrakeMode.DEAD:
            return
        if self.flying or self.support is None:
            self.replan = 0.0
            if self.mode is DrakeMode.DIVE and self.quarry is None:
                self._set_landing(None)
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
            leg.hock += delta
            leg.root += delta

    # ----- pose --------------------------------------------------------------------

    def _pose(self, dt: float, snap: bool = False) -> None:
        walking = not self.flying
        if walking:
            ground = self.support.start.y if self.support is not None else self.body.y + HIP_HEIGHT
            self.angle = self._level()
            bob = abs(math.sin(self.phase * math.tau)) * -1.0 * self.gait
            hip = Vec2(self.x, ground - HIP_HEIGHT + bob) - self.local(Vec2(0.5, 2.0))
            self.body = hip + self.forward * (BODY_LENGTH / 2)
        else:
            ground = self.body.y + HIP_HEIGHT
        blend = 1.0 if snap else min(1.0, dt * 14.0)
        settled = snap or self.mode_time >= 0.2
        for leg in self.legs:
            root = self.hip + self.local(Vec2(0.5, 2.0))
            if walking:
                target = self._planted_foot(leg, root, ground)
                foot = (
                    target if settled else leg.foot.lerp(target, max(blend, self.mode_time / 0.2))
                )
            else:
                tuck = self.local(Vec2(-5.0, 5.5) if leg.near else Vec2(-3.5, 6.0))
                foot = leg.foot.lerp(root + tuck, blend)
            leg.root, leg.hock, leg.foot = two_bone_points(root, THIGH, SHANK, foot, -self.facing)
            if walking:
                leg.lift = clamp((ground - leg.foot.y) / 2.5, 0.0, 1.0)
            else:
                leg.lift += (1.0 - leg.lift) * (1.0 if snap else min(1.0, dt * 8.0))
        self._pose_head(dt, snap)
        self._pose_tail(dt, None)
        lean = 0.15 * self.gait if walking else -0.35 * self.pitch / 0.45 + 0.1
        self.lean += (lean - self.lean) * (1.0 if snap else min(1.0, dt * 6.0))

    def _planted_foot(self, leg: DrakeLeg, root: Vec2, ground: float) -> Vec2:
        p = (self.phase + leg.phase_offset) % 1.0
        span = STANCE * STRIDE
        if p < STANCE:
            along, lift = span * (0.5 - p / STANCE), 0.0
        else:
            u = (p - STANCE) / (1.0 - STANCE)
            along, lift = span * (-0.5 + smoothstep(u)), math.sin(math.pi * u) * STEP_HEIGHT
        x = root.x + self.facing * (0.5 + along * self.gait)
        return Vec2(x, ground - lift * self.gait)

    def _pose_head(self, dt: float, snap: bool) -> None:
        reach = Vec2(7.5, -4.0) if self.flying else NECK
        lunge = 0.0
        if self.bite_time > 0.0:
            lunge = math.sin(math.pi * (1.0 - self.bite_time / BITE_TIME))
            reach = reach.lerp(Vec2(8.0, -2.5), lunge)
        bob = math.sin(self.phase * math.tau * 2.0 + 0.8) * 0.8 * self.gait
        head = self.chest + self.local(reach + Vec2(0.0, bob))
        heading = self.angle + self.facing * (0.05 if self.flying else 0.3 - 0.3 * lunge)
        rate = 1.0 if snap else min(1.0, dt * (20.0 if lunge else 12.0))
        self.head = self.head.lerp(head, rate)
        self.head_angle += math.remainder(heading - self.head_angle, math.tau) * rate
        self.jaw += (lunge * 0.9 - self.jaw) * (1.0 if snap else min(1.0, dt * 8.0))

    def _pose_tail(self, dt: float, ground: float | None) -> None:
        """Each segment eases toward a resting curve straight out behind the hip (or
        along the ground once dead), then the chain is pulled back to its spacing."""
        tail = self.tail
        count = len(tail)
        if not count:
            return
        tail[0] = self.hip - self.forward * 1.5
        relax = min(1.0, (3.0 if self.flying else 6.0) * dt)
        level = 0.0 if self.facing > 0 else math.pi
        back = Vec2.from_angle(level).rotated(math.pi) if ground is None else ZERO
        for i in range(1, count):
            t = i / (count - 1)
            if ground is not None:
                rest = Vec2(tail[0].x - self.facing * TAIL_SPACING * i * 0.95, ground - 1.0)
            else:
                sway = math.sin(self.clock * 3.0 - i * 0.6) * 1.2 * t
                lift = -1.5 * t + 1.0 * math.sin(math.pi * t)
                rest = tail[0] + back * (TAIL_SPACING * i) + Vec2(0.0, lift + sway)
            pulled = tail[i].lerp(rest, relax)
            offset = pulled - tail[i - 1]
            length = offset.length()
            if length > 1e-6:
                tail[i] = tail[i - 1] + offset * (TAIL_SPACING / length)
