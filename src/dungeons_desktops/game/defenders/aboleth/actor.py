"""An aboleth that swims freely through the air and hunts adventurers.

Two attacks:
- Psychic ray: eyes flare, a bolt flies out, and the hit adventurer is dominated
  (hunts friends as a thrall). After `DOMINATE_TIME` their brain bursts into a green
  slime explosion that kills them and damages nearby free adventurers.
- Tentacle whip: one tentacle (rotating through the six) swipes in an arc.

When brought to 0 HP it does not die in place: a deep portal opens and it slips
through before the tear closes (banished). Herald-spawned aboleths unlock the
mind flayer's next thrall rift only after that banish finishes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.game.actors.hunting import nearest
from dungeons_desktops.game.actors.mortal import Mortal
from dungeons_desktops.game.adventurers.actor import GOBLIN_DAMAGE, Stickman

if TYPE_CHECKING:
    from dungeons_desktops.game.world.simulation import SimWorld
    from dungeons_desktops.navigation.terrain import TerrainChange

ABOLETH_HP = 12
BODY_LENGTH = 90.0
BODY_HEIGHT = 32.0
FLY_SPEED = 70.0
FLY_ACCEL = 2.8
FLY_SIDE = 70.0
FLY_BELOW = 10.0
MAX_LEAN = 0.28
WANDER_WAIT = (2.2, 4.5)
BOB_AMP = 3.5
BOB_RATE = 1.7
ZERO = Vec2(0.0, 0.0)
EMERGE_TIME = 0.95
BANISH_OPEN = 0.35
BANISH_SWIM = 0.55
BANISH_CLOSE = 0.4


@dataclass
class DeepPortal:
    """A deep tear the aboleth arrives from or flees through."""

    center: Vec2
    age: float = 0.0
    closing: bool = False

    @property
    def life(self) -> float:
        """0..1 visibility: opens, then optionally seals shut."""
        open_by = min(1.0, self.age / max(BANISH_OPEN, 1e-3))
        if not self.closing:
            return open_by
        close_for = max(0.0, self.age - BANISH_OPEN - BANISH_SWIM)
        return open_by * max(0.0, 1.0 - close_for / max(BANISH_CLOSE, 1e-3))


PSYCHIC_RANGE = 220.0
PSYCHIC_WINDUP = 0.55
PSYCHIC_COOLDOWN = 9.0
BOLT_SPEED = 320.0
BOLT_HIT = 10.0
DOMINATE_TIME = 10.0
SLIME_RADIUS = 70.0
SLIME_DAMAGE = 2
SLIME_BURST_TIME = 0.55

WHIP_REACH = 95.0
WHIP_HEIGHT = 55.0
WHIP_WINDUP = 0.07
WHIP_STRIKE = 0.11
WHIP_RECOVER = 0.09
WHIP_COOLDOWN = 1.1
WHIP_DAMAGE = GOBLIN_DAMAGE
WHIP_PUSH = 140.0
# Half-width of the swipe arc (radians): tip starts above the aim and cuts through below.
WHIP_ARC = 1.05
WHIP_TRAIL_LIFE = 0.22
WHIP_TRAIL_MAX = 12
TENTACLE_COUNT = 6
# Local-space tentacle roots (front of body). Kept in sync with ambient render chains.
WHIP_ROOTS = (
    Vec2(14.0, -8.0),
    Vec2(10.0, -6.0),
    Vec2(16.0, 9.0),
    Vec2(12.0, 11.0),
    Vec2(8.0, 11.5),
    Vec2(4.0, 10.0),
)


def whip_kinematics(
    progress: float, root: Vec2, aim_local: Vec2
) -> tuple[Vec2, float, float, float]:
    """Tip pose for a swipe: local tip, tip angle, reach length, bow lag (into the swing)."""
    to = aim_local - root
    reach = max(to.length(), 52.0)
    base = to.angle() if to.length() > 1e-6 else 0.0
    half = WHIP_ARC
    u = progress
    windup_end = 0.28
    strike_end = 0.72
    if u < windup_end:
        pull = smoothstep(u / windup_end)
        tip_angle = base - half * pull
        length = reach * (0.5 + 0.2 * (1.0 - pull))
        lag = 0.25 * pull
    elif u < strike_end:
        strike = smoothstep((u - windup_end) / (strike_end - windup_end))
        tip_angle = base - half + 2.0 * half * strike
        length = reach * (0.85 + 0.3 * math.sin(math.pi * strike))
        lag = 0.55 * math.sin(math.pi * strike)
    else:
        recover = smoothstep((u - strike_end) / max(1e-6, 1.0 - strike_end))
        tip_angle = base + half * (1.0 - 0.55 * recover)
        length = reach * (1.0 - 0.4 * recover)
        lag = 0.2 * (1.0 - recover)
    tip = root + Vec2.from_angle(tip_angle, length)
    return tip, tip_angle, length, lag


class Action(Enum):
    PSYCHIC = "psychic"
    WHIP = "whip"


@dataclass
class PsychicBolt:
    position: Vec2
    target: Stickman
    age: float = 0.0


@dataclass
class Domination:
    victim: Stickman
    age: float = 0.0


@dataclass
class SlimeBurst:
    center: Vec2
    age: float = 0.0


@dataclass
class WhipTrailPoint:
    position: Vec2
    age: float = 0.0


@dataclass
class WhipState:
    index: int
    tip: Vec2
    progress: float = 0.0
    struck: bool = False


class Aboleth(Mortal):
    max_hp = ABOLETH_HP
    linger = 2.5

    def __init__(self, world: SimWorld, point: Vec2, facing: int = 1) -> None:
        self.world = world
        self.feet = point
        self.drift = ZERO
        self.lean = 0.0
        self._facing = 1 if facing >= 0 else -1
        self.clock = world.random.uniform(0.0, 40.0)
        self._wander = point
        self._wander_wait = 0.0
        self.damage = 0
        self.dead = False
        self.down_time = 0.0
        self._dead_feet = point
        self._dead_facing = self._facing
        self._dead_lean = 0.0

        self.hunt = nearest()
        self.target: Stickman | None = None
        self.action: Action | None = None
        self.action_time = 0.0
        self.victim: Stickman | None = None
        self.psychic_wait = 1.5
        self.whip_wait = 0.6
        self.next_tentacle = 0
        self.eye_charge = 0.0
        self.bolts: list[PsychicBolt] = []
        self.dominations: list[Domination] = []
        self.slime_bursts: list[SlimeBurst] = []
        self.whip: WhipState | None = None
        self.whip_trail: list[WhipTrailPoint] = []
        self.whip_trail_sage = False
        self.emerge: float | None = None
        self.banishing = False
        self._banished = False
        self.portal: DeepPortal | None = None
        self.herald_flayer = None

    @property
    def facing(self) -> int:
        return self._dead_facing if self.dead else self._facing

    @property
    def draw_lean(self) -> float:
        """Lean used for drawing: signed the same way as air elementals."""
        if self.dead:
            return self._dead_lean
        return self.lean * self._facing

    @property
    def emerge_progress(self) -> float:
        """0 while still in the tear, 1 once fully in the world."""
        if self.emerge is None:
            return 1.0
        return min(1.0, self.emerge / EMERGE_TIME)

    @property
    def fade(self) -> float:
        if self._banished:
            return 1.0
        if self.banishing:
            if self.down_time <= BANISH_OPEN:
                return 0.0
            return min(1.0, (self.down_time - BANISH_OPEN) / BANISH_SWIM)
        return super().fade

    @property
    def gone(self) -> bool:
        return self._banished or super().gone

    def center(self) -> Vec2:
        return self.feet if not self.dead else self._dead_feet

    def eye_point(self) -> Vec2:
        """Rough world position of the eye stack (for the psychic bolt)."""
        return self.draw_center() + Vec2(self.facing * BODY_LENGTH * 0.32, 0.0)

    def parts(self) -> list[Vec2]:
        at = self.center()
        forward = Vec2(self.facing * BODY_LENGTH * 0.28, 0.0)
        return [
            at,
            at + forward,
            at - forward,
            at + Vec2(0.0, -BODY_HEIGHT * 0.35),
            at + Vec2(0.0, BODY_HEIGHT * 0.35),
        ]

    def hits(self, point: Vec2, margin: float = 0.0) -> bool:
        if self.dead or self.emerge is not None:
            return False
        dx = (point.x - self.feet.x) / (BODY_LENGTH * 0.45)
        dy = (point.y - self.feet.y) / (BODY_HEIGHT * 0.55)
        return dx * dx + dy * dy <= (1.0 + margin / BODY_LENGTH) ** 2

    def begin_emergence(self, portal_center: Vec2) -> None:
        """Swim out of a mind-flayer rift into the world."""
        self.feet = portal_center + Vec2(0.0, -14.0)
        self.drift = ZERO
        self.emerge = 0.0
        self.action = None
        self.victim = None
        self.whip = None

    def world_to_local(self, point: Vec2) -> Vec2:
        """World point → local body frame (x toward head, y down)."""
        offset = (point - self.draw_center()).rotated(-self.draw_lean)
        return Vec2(offset.x / self.facing, offset.y)

    def local_to_world(self, point: Vec2) -> Vec2:
        """Local body frame → world point."""
        return self.draw_center() + Vec2(point.x * self.facing, point.y).rotated(self.draw_lean)

    def _bounds(self) -> tuple[float, float, float, float]:
        world = self.world
        top = world.ceiling if world.ceiling is not None else 0.0
        return (
            world.left + 40.0,
            world.width - 40.0,
            top + BODY_HEIGHT + 20.0,
            world.floor_y - BODY_HEIGHT - 10.0,
        )

    def _clamped(self, point: Vec2) -> Vec2:
        left, right, top, bottom = self._bounds()
        return Vec2(clamp(point.x, left, right), clamp(point.y, top, bottom))

    def _face(self, point: Vec2) -> None:
        if abs(point.x - self.feet.x) > 1.0:
            self._facing = 1 if point.x > self.feet.x else -1

    def _within_whip(self, stickman: Stickman, slack: float = 1.0) -> bool:
        theirs = stickman.center()
        mine = self.center()
        return (
            abs(theirs.y - mine.y) <= WHIP_HEIGHT * slack
            and theirs.distance_to(mine) <= WHIP_REACH * slack
        )

    def update(self, dt: float) -> None:
        if self.dead:
            self.update_dead(dt)
            return
        self.clock += dt
        if self.emerge is not None:
            self.emerge += dt
            if self.emerge >= EMERGE_TIME:
                self.emerge = None
            else:
                self._update_dominations(dt)
                self._update_slime(dt)
                return
        self.psychic_wait -= dt
        self.whip_wait -= dt
        self.target = self.hunt.update(dt, self.center(), self.world.stickmen)
        rooted = self.action is not None
        if self.action is not None:
            self._run_action(dt)
        elif not rooted:
            self._choose()
        self._swim(dt, rooted)
        self._update_bolts(dt)
        self._update_dominations(dt)
        self._update_slime(dt)
        self._update_whip_trail(dt)

    def _swim(self, dt: float, rooted: bool) -> None:
        if rooted:
            desired = ZERO
            if self.victim is not None:
                self._face(self.victim.center())
        else:
            target = self.target
            if target is not None:
                theirs = target.center()
                side = -1.0 if self.feet.x < theirs.x else 1.0
                goal = theirs + Vec2(side * FLY_SIDE, FLY_BELOW)
            else:
                self._wander_wait -= dt
                if self._wander_wait <= 0.0:
                    rng = self.world.random
                    self._wander_wait = rng.uniform(*WANDER_WAIT)
                    left, right, top, bottom = self._bounds()
                    self._wander = Vec2(rng.uniform(left, right), rng.uniform(top, bottom))
                goal = self._wander
            goal = self._clamped(goal)
            offset = goal - self.feet
            distance = offset.length()
            desired = (
                offset.normalized() * min(FLY_SPEED, distance * 2.2) if distance > 1.0 else ZERO
            )
        self.drift += (desired - self.drift) * min(1.0, FLY_ACCEL * dt)
        self.feet = self._clamped(self.feet + self.drift * dt)
        lean = clamp(self.drift.x / max(FLY_SPEED, 1.0), -1.0, 1.0) * MAX_LEAN
        self.lean += (lean - self.lean) * min(1.0, 6.0 * dt)
        if not rooted and abs(self.drift.x) > 6.0:
            self._facing = 1 if self.drift.x > 0 else -1

    def _choose(self) -> None:
        target = self.target
        if target is None or not target.prey:
            return
        if self._within_whip(target) and self.whip_wait <= 0.0:
            self._start_whip(target)
            return
        if (
            self.psychic_wait <= 0.0
            and target.center().distance_to(self.center()) <= PSYCHIC_RANGE
        ):
            self._start_psychic(target)

    def _start_psychic(self, victim: Stickman) -> None:
        self.action = Action.PSYCHIC
        self.action_time = 0.0
        self.victim = victim
        self.eye_charge = 0.0
        self.drift = ZERO
        self._face(victim.center())

    def _start_whip(self, victim: Stickman) -> None:
        self.action = Action.WHIP
        self.action_time = 0.0
        self.victim = victim
        self.whip = WhipState(index=self.next_tentacle % TENTACLE_COUNT, tip=victim.center())
        self.next_tentacle = (self.next_tentacle + 1) % TENTACLE_COUNT
        self.drift = ZERO
        self._face(victim.center())

    def _run_action(self, dt: float) -> None:
        self.action_time += dt
        victim = self.victim
        if self.action is Action.PSYCHIC:
            self.eye_charge = min(1.0, self.action_time / PSYCHIC_WINDUP)
            if victim is not None and victim.prey:
                self._face(victim.center())
            if self.action_time >= PSYCHIC_WINDUP:
                if victim is not None and victim.prey:
                    self.bolts.append(PsychicBolt(self.eye_point(), victim))
                self.psychic_wait = PSYCHIC_COOLDOWN
                self.action = None
                self.victim = None
                self.eye_charge = 0.0
        elif self.action is Action.WHIP:
            assert self.whip is not None
            total = WHIP_WINDUP + WHIP_STRIKE + WHIP_RECOVER
            self.whip.progress = min(1.0, self.action_time / total)
            aim = victim.center() if victim is not None and victim.animated else self.whip.tip
            self.whip.tip = aim
            if victim is not None and victim.prey:
                self._face(aim)
            self._sample_whip_trail()
            # Strike window: mid swipe, when the tentacle cuts through the aim.
            strike_start = WHIP_WINDUP / total
            strike_end = (WHIP_WINDUP + WHIP_STRIKE) / total
            if (
                not self.whip.struck
                and strike_start <= self.whip.progress <= strike_end
                and victim is not None
                and victim.prey
                and self._within_whip(victim, slack=1.25)
            ):
                radial = aim - self.center()
                if radial.length() > 1e-6:
                    radial = radial.normalized()
                else:
                    radial = Vec2(float(self.facing), 0.0)
                # Push along the swipe (downward slash) with a little outward shove.
                tangent = Vec2(-radial.y, radial.x)
                push = (radial * 0.3 + tangent * 0.95) * WHIP_PUSH + Vec2(0.0, -25.0)
                victim.hurt_from(
                    self,
                    WHIP_DAMAGE,
                    aim,
                    push,
                    "aboleth",
                    "Lashed by the aboleth!",
                )
                self.whip.struck = True
                self.world.spells.sparkle(aim, "hit", 6, 90.0)
            if self.action_time >= total:
                self.whip_wait = WHIP_COOLDOWN
                self.action = None
                self.victim = None
                self.whip = None

    def _update_bolts(self, dt: float) -> None:
        flying: list[PsychicBolt] = []
        for bolt in self.bolts:
            bolt.age += dt
            target = bolt.target
            if not target.prey:
                continue
            to = target.center() - bolt.position
            step = BOLT_SPEED * dt
            if to.length() <= step or target.hits(bolt.position, BOLT_HIT):
                self._psychic_hit(target, bolt.position)
                continue
            bolt.position += to.normalized() * step
            flying.append(bolt)
        self.bolts = flying

    def _psychic_hit(self, target: Stickman, point: Vec2) -> None:
        self.world.spells.sparkle(point, "magic", 14, 130.0)
        if not target.prey:
            return
        target.enthrall()
        # Psychic dominate — not an intellect devourer in the skull.
        target.mind_devoured = False
        self.dominations.append(Domination(target))

    def _update_dominations(self, dt: float) -> None:
        kept: list[Domination] = []
        for dom in self.dominations:
            victim = dom.victim
            if not victim.animated or not victim.thrall:
                continue
            dom.age += dt
            if dom.age >= DOMINATE_TIME:
                self._slime_burst(victim)
            else:
                kept.append(dom)
        self.dominations = kept

    def _slime_burst(self, victim: Stickman) -> None:
        center = victim.center()
        self.slime_bursts.append(SlimeBurst(center))
        self.world.spells.sparkle(center, "magic", 22, 200.0)
        self.world.spells.pulse(center, SLIME_RADIUS * 0.55)
        self.world.debris.burst(
            center, Vec2(0.0, -1.0), 14, 260.0, spread=2.4, puffs=10, scale=1.1
        )
        # Kill the thrall with a green acid melt — no intellect devourer (not mind-flayer).
        victim.hurt_from(
            self,
            max(8, victim.max_hp),
            center,
            Vec2(0.0, -80.0),
            "aboleth",
            "Its brain burst into slime!",
            bleed=False,
        )
        if not victim.animated and victim.demise is None and victim.burn is None:
            victim.succumb("acid")
        for stickman in self.world.stickmen:
            if not stickman.prey:
                continue
            theirs = stickman.center()
            if theirs.distance_to(center) <= SLIME_RADIUS:
                away = theirs - center
                push = (away.normalized() if away.length() > 1.0 else Vec2(0.0, -1.0)) * 180.0
                stickman.hurt_from(
                    self,
                    SLIME_DAMAGE,
                    theirs,
                    push + Vec2(0.0, -60.0),
                    "aboleth",
                    "Burned by the aboleth's slime!",
                )

    def _update_slime(self, dt: float) -> None:
        for burst in self.slime_bursts:
            burst.age += dt
        self.slime_bursts = [b for b in self.slime_bursts if b.age < SLIME_BURST_TIME]

    def _sample_whip_trail(self) -> None:
        whip = self.whip
        if whip is None or whip.index < 0 or whip.index >= len(WHIP_ROOTS):
            return
        tip_local, _, _, _ = whip_kinematics(
            whip.progress, WHIP_ROOTS[whip.index], self.world_to_local(whip.tip)
        )
        self.whip_trail_sage = whip.index < 2
        self.whip_trail.append(WhipTrailPoint(self.local_to_world(tip_local)))
        del self.whip_trail[:-WHIP_TRAIL_MAX]

    def _update_whip_trail(self, dt: float) -> None:
        for point in self.whip_trail:
            point.age += dt
        self.whip_trail = [p for p in self.whip_trail if p.age < WHIP_TRAIL_LIFE]

    def bob_offset(self) -> float:
        return BOB_AMP * math.sin(self.clock * BOB_RATE)

    def draw_center(self) -> Vec2:
        """Body center used for rendering (includes idle bob while alive)."""
        if self.dead:
            return self._dead_feet
        return self.feet + Vec2(0.0, self.bob_offset())

    def die(self, point: Vec2, push: Vec2) -> None:
        """Open a deep portal and slip through it instead of leaving a corpse."""
        _ = push
        self.dead = True
        self.banishing = True
        self._banished = False
        self.down_time = 0.0
        self._dead_feet = self.feet
        self._dead_facing = self._facing
        self._dead_lean = self.lean * self._facing
        self.drift = ZERO
        self.action = None
        self.victim = None
        self.whip = None
        self.whip_trail.clear()
        self.eye_charge = 0.0
        self.bolts.clear()
        self.emerge = None
        self.portal = DeepPortal(point if point.distance_to(self.feet) < 80.0 else self.feet)
        self.world.spells.sparkle(self.portal.center, "magic", 28, 220.0)
        self.world.spells.pulse(self.portal.center, 40.0)
        # Dominated thralls keep fighting until their brains burst on the timer.

    def update_dead(self, dt: float) -> None:
        self.down_time += dt
        if self.banishing and self.portal is not None:
            self.portal.age += dt
            if self.down_time >= BANISH_OPEN:
                self.portal.closing = self.down_time >= BANISH_OPEN + BANISH_SWIM
                u = min(1.0, (self.down_time - BANISH_OPEN) / BANISH_SWIM)
                self._dead_feet = self._dead_feet.lerp(self.portal.center, 0.2 + 0.55 * u)
            if self.down_time >= BANISH_OPEN + BANISH_SWIM + BANISH_CLOSE:
                self._finish_banish()
        # Dominated thralls still burst on the timer after the aboleth leaves.
        self._update_dominations(dt)
        self._update_slime(dt)

    def _finish_banish(self) -> None:
        self.banishing = False
        self.portal = None
        self._banished = True
        flayer = self.herald_flayer
        self.herald_flayer = None
        if flayer is not None and hasattr(flayer, "release_aboleth"):
            flayer.release_aboleth(self)

    def terrain_changed(self, change: TerrainChange) -> None:
        pass
