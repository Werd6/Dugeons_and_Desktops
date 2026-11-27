"""A heavy, ground-only bear with an ambling walk and an enemy-charging bound."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.game.actors.base import _distance_to_segment, surface_below
from dungeons_desktops.game.heroes.natures_wrath.dragon import DefenderPrey, DefenderWorld
from dungeons_desktops.navigation.terrain import TerrainChange

if TYPE_CHECKING:
    from dungeons_desktops.game.heroes.natures_wrath.actor import NaturesWrath

BEAR_SECONDS = 30.0
BEAR_HEIGHT = 42.0
HALF_BODY = 23.0
WALK_SPEED = 32.0
CHARGE_SPEED = 165.0
NOTICE_RANGE = 480.0
BEAR_DAMAGE = 6
HIT_COOLDOWN = 1.1
MAUL_WINDUP = 0.22
MAUL_HIT = 0.34
MAUL_TIME = 0.68
GRAVITY = 850.0


@dataclass
class BearLeg:
    front: bool
    near: bool
    root: Vec2
    knee: Vec2
    foot: Vec2


class GiantBear:
    def __init__(self, hero: NaturesWrath) -> None:
        self.hero = hero
        self.world = DefenderWorld(hero)
        self.feet = hero.contact()
        self.facing = hero.facing
        self.velocity = Vec2(0, 0)
        self.elapsed = 0.0
        self.finished = False
        self.phase = 0.0
        self.gait = 0.0
        self.charge = 0.0
        self.charging = False
        self.hit_wait = 0.0
        self.impact = 0.0
        self.maul_time: float | None = None
        self.maul_target: DefenderPrey | None = None
        self.maul_offset = Vec2(0, 0)
        self._maul_struck = False
        self.wander_wait = 0.0
        self.wander_x: float | None = None
        anchor = surface_below(hero.planner, self.feet - Vec2(0, 2))
        self.support = anchor.surface if self.feet.distance_to(anchor.point) < 3 else None
        if self.support is not None:
            low, high = self._bounds()
            self.feet = Vec2(clamp(self.feet.x, low, high), self.support.start.y)
        self.legs = [
            BearLeg(front, near, self.feet, self.feet, self.feet)
            for near in (False, True)
            for front in (False, True)
        ]
        self._pose()

    @property
    def flying(self) -> bool:
        """Shared form interface: airborne only while falling, never powered flight."""
        return self.support is None

    @property
    def body(self) -> Vec2:
        bob = math.sin(self.phase * math.tau * 2) * (1.2 + self.charge * 2.5) * self.gait
        return self.feet + Vec2(0, -BEAR_HEIGHT + bob - self.charge * 1.5)

    @property
    def hip(self) -> Vec2:
        return self.body + Vec2(-self.facing * HALF_BODY, 1)

    @property
    def shoulder(self) -> Vec2:
        point = self.body + Vec2(self.facing * (HALF_BODY - 3), -4 + self.charge * 4)
        if self.maul_time is not None:
            coil, drive = Vec2(-3, -7), Vec2(7, 3)
            if self.maul_time < MAUL_WINDUP:
                offset = coil * smoothstep(self.maul_time / MAUL_WINDUP)
            elif self.maul_time < MAUL_HIT:
                offset = coil.lerp(
                    drive, smoothstep((self.maul_time - MAUL_WINDUP) / (MAUL_HIT - MAUL_WINDUP))
                )
            else:
                offset = drive * (
                    1
                    - smoothstep(clamp((self.maul_time - MAUL_HIT) / (MAUL_TIME - MAUL_HIT), 0, 1))
                )
            point += Vec2(self.facing * offset.x, offset.y)
        return point

    @property
    def head(self) -> Vec2:
        return self.shoulder + Vec2(self.facing * 18, -10 + self.charge * 7)

    def contact(self) -> Vec2:
        return self.feet

    def _bounds(self) -> tuple[float, float]:
        margin = HALF_BODY + 24
        low, high = self.support.low + margin, self.support.high - margin
        if low > high:
            low = high = (self.support.low + self.support.high) / 2
        return low, high

    def update(self, dt: float, paused: bool = False) -> None:
        self.elapsed += dt
        self.finished = self.elapsed >= BEAR_SECONDS - 1e-9
        self.hit_wait = max(0.0, self.hit_wait - dt)
        self.impact = max(0.0, self.impact - dt)
        if paused:
            return
        self.world.refresh()
        if self.support is None:
            self._cancel_maul()
            self._fall(dt)
        elif self.maul_time is not None:
            self._update_maul(dt)
        else:
            self._walk(dt)
        self._pose()

    def _fall(self, dt: float) -> None:
        old = self.feet
        self.velocity = Vec2(0, self.velocity.y + GRAVITY * dt)
        self.feet += self.velocity * dt
        surfaces = [
            s
            for s in self.hero.planner.surfaces
            if s.walkable
            and s.low <= self.feet.x <= s.high
            and old.y - 1 <= s.start.y <= self.feet.y
        ]
        if surfaces:
            self.support = min(surfaces, key=lambda s: s.start.y)
            low, high = self._bounds()
            self.feet = Vec2(clamp(self.feet.x, low, high), self.support.start.y)
            self.velocity = Vec2(0, 0)
        self.charging = False
        self.gait = 0.0

    def _walk(self, dt: float) -> None:
        low, high = self._bounds()
        # Only pursue enemies on this continuous walkable surface: no routes up walls.
        prey = [
            p
            for p in self.world.stickmen
            if p.prey
            and abs(p.contact().y - self.feet.y) < 12
            and self.support.low <= p.contact().x <= self.support.high
            and p.center().distance_to(self.body) <= NOTICE_RANGE
        ]
        target = min(prey, key=lambda p: p.center().distance_to(self.body), default=None)
        self.charging = target is not None
        if target is not None:
            self.wander_x = None
            goal = target.center().x
            distance = goal - self.feet.x
            if abs(distance) > 4:
                self.facing = 1 if distance > 0 else -1
            close = (
                target.hits(self.head, 19)
                or target.hits(self.shoulder, 23)
                or any(target.hits(leg.foot + Vec2(0, -6), 16) for leg in self.legs if leg.front)
            )
            desired = 0 if close else self.facing * CHARGE_SPEED
            if close and self.hit_wait <= 0:
                self._start_maul(target)
                return
        else:
            self.wander_wait = max(0.0, self.wander_wait - dt)
            if self.wander_x is None and self.wander_wait <= 0:
                self.wander_x = self.world.random.uniform(low, high)
            distance = 0 if self.wander_x is None else self.wander_x - self.feet.x
            if abs(distance) < 4:
                desired = 0
                if self.wander_x is not None:
                    self.wander_x = None
                    self.wander_wait = self.world.random.uniform(0.8, 2.5)
            else:
                self.facing = 1 if distance > 0 else -1
                desired = self.facing * WALK_SPEED
        speed = self.velocity.x + (desired - self.velocity.x) * min(1, dt * 7)
        x = clamp(self.feet.x + speed * dt, low, high)
        moved = x - self.feet.x
        self.feet = Vec2(x, self.support.start.y)
        self.velocity = Vec2(moved / dt if dt > 0 else 0, 0)
        self.charge += ((1 if self.charging else 0) - self.charge) * min(1, dt * 6)
        self.gait = min(1, abs(self.velocity.x) / WALK_SPEED)
        stride = 34 + 20 * self.charge
        self.phase += abs(moved) / stride

    @property
    def maul_aim(self) -> Vec2:
        return self.feet + self.maul_offset

    def _start_maul(self, target: DefenderPrey) -> None:
        self.maul_time = 0.0
        self.maul_target = target
        self._maul_struck = False
        self.hit_wait = HIT_COOLDOWN
        self.velocity = Vec2(0, 0)
        self.gait = 0.0
        aim = (
            self.world.real.closest_part(target.monster, self.shoulder + Vec2(self.facing * 30, 15))
            or target.center()
        )
        self.maul_offset = Vec2(
            self.facing * clamp((aim.x - self.feet.x) * self.facing, 5, 74),
            clamp(aim.y - self.feet.y, -62, -4),
        )

    def _update_maul(self, dt: float) -> None:
        assert self.maul_time is not None
        self.maul_time += dt
        if self.maul_time >= MAUL_HIT and not self._maul_struck:
            self._maul_struck = True
            target = self.maul_target
            if target is not None and target.prey and target.hits(self.maul_aim, 18):
                self.impact = 0.18
                self.world.real.hurt_monster(
                    target.monster,
                    BEAR_DAMAGE,
                    self.maul_aim,
                    Vec2(self.facing * 280, -80),
                    ranged=False,
                    attacker=self.hero,
                )
        if self.maul_time >= MAUL_TIME:
            self._cancel_maul()

    def _cancel_maul(self) -> None:
        self.maul_time = None
        self.maul_target = None

    def _maul_paw(self, rest: Vec2) -> Vec2:
        assert self.maul_time is not None
        raised = self.feet + Vec2(self.facing * 52, -94)
        if self.maul_time < MAUL_WINDUP:
            return rest.lerp(raised, smoothstep(self.maul_time / MAUL_WINDUP))
        if self.maul_time < MAUL_HIT:
            return raised.lerp(
                self.maul_aim, smoothstep((self.maul_time - MAUL_WINDUP) / (MAUL_HIT - MAUL_WINDUP))
            )
        return self.maul_aim.lerp(
            rest, smoothstep(clamp((self.maul_time - MAUL_HIT) / (MAUL_TIME - MAUL_HIT), 0, 1))
        )

    def _pose(self) -> None:
        for leg in self.legs:
            root = self.shoulder if leg.front else self.hip
            root += Vec2(0 if leg.near else self.facing * 5, 4 if leg.near else 1)
            # A four-beat amble blends into paired front/hind bounding legs.
            walk_offset = (0 if leg.front else 0.5) + (0 if leg.near else 0.25)
            run_offset = (0 if leg.front else 0.5) + (0 if leg.near else 0.08)
            phase = (self.phase + walk_offset * (1 - self.charge) + run_offset * self.charge) % 1
            stance = 0.7 - self.charge * 0.2
            span = (34 + 20 * self.charge) * stance
            if phase < stance:
                along, lift = span * (0.5 - phase / stance), 0.0
            else:
                u = (phase - stance) / (1 - stance)
                along = span * (-0.5 + smoothstep(u))
                lift = math.sin(math.pi * u) * (7 + 8 * self.charge)
            foot = Vec2(root.x + self.facing * along * self.gait, self.feet.y - lift * self.gait)
            if not leg.near:
                foot += Vec2(self.facing * 4, -1.5)
            if self.flying:
                foot = root + Vec2(-self.facing * 5, 25)
            if self.maul_time is not None and leg.front and leg.near:
                rest = self.feet + Vec2(self.facing * (HALF_BODY - 3), 0)
                foot = self._maul_paw(rest)
            # Rear legs swing as single masses. Forelegs retain only a shallow elbow.
            # The middle point also keeps collision geometry aligned with the silhouette.
            middle = root.lerp(foot, 0.6)
            if leg.front:
                middle += Vec2(-self.facing * (0.6 + 1.4 * self.gait), 0)
            leg.root, leg.knee, leg.foot = root, middle, foot

    def hits(self, point: Vec2, margin: float = 0.0) -> bool:
        return (
            _distance_to_segment(point, self.hip, self.shoulder) <= 22 + margin
            or point.distance_to(self.head) <= 19 + margin
            or any(
                _distance_to_segment(point, leg.root, leg.knee)
                <= (14 if leg.front else 12) + margin
                or _distance_to_segment(point, leg.knee, leg.foot)
                <= (10 if leg.front else 8) + margin
                for leg in self.legs
            )
        )

    def terrain_changed(self, change: TerrainChange) -> None:
        if self.support is None:
            return
        box = self.support.box
        delta = change.delta_for(box)
        if delta is not None:
            self.feet += delta
            if self.wander_x is not None:
                self.wander_x += delta.x
        anchor = surface_below(self.hero.planner, self.feet - Vec2(0, 2))
        if change.removed(box) or abs(anchor.point.y - self.feet.y) > 3:
            self._cancel_maul()
            self.support = None
            self.velocity = Vec2(0, 0)
        else:
            self.support = anchor.surface
            low, high = self._bounds()
            self.feet = Vec2(clamp(self.feet.x, low, high), anchor.point.y)
        self._pose()
