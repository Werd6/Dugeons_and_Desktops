"""Beastform Mutagen movement and claw combat."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.game.actors.base import _distance_to_segment, surface_below
from dungeons_desktops.game.defenders.minotaur.actor import GUARD_NEAR, PUNCH_TIMES
from dungeons_desktops.navigation.terrain import TerrainChange

if TYPE_CHECKING:
    from dungeons_desktops.game.heroes.hero_alchemist.actor import HeroAlchemist

MUTAGEN_SECONDS = 10.0
MUTAGEN_COOLDOWN = 18.0
TRANSFORM_IN = 0.85
TRANSFORM_OUT = 0.5
START_SCALE = 0.48
BEAST_SCALE = 0.78
BEAST_HEIGHT = 50.0
WALK_SPEED = 68.0
NOTICE_RANGE = 360.0
CLAW_REACH = 46.0
CLAW_DAMAGE = 4
CLAW_COOLDOWN = 0.78
CLAW_WINDUP, CLAW_STRIKE, CLAW_RECOVER = PUNCH_TIMES
CLAW_HIT = CLAW_WINDUP + CLAW_STRIKE
CLAW_TIME = CLAW_HIT + CLAW_RECOVER
FAR_GUARD = Vec2(-10.0, -32.0)
CLAW_CHAMBER = Vec2(-6.0, -38.0)
CLAW_COCKED = Vec2(2.0, -52.0)
FAR_CHAMBER = Vec2(-12.0, -36.0)
FAR_COCKED = Vec2(-3.0, -55.0)
NEAR_SHOULDER = Vec2(6.0, -53.5)
ARM_LENGTH = 15.2 + 14.2 - 1e-3
MINOTAUR_HIP = 27.0
MINOTAUR_HUNCH = 0.18
PUNCH_LEAN = 0.22
PUNCH_SQUAT = 3.0
GRAVITY = 900.0


class MutagenBeast:
    """A compact, ground-bound minotaur-shaped form that hunts defenders."""

    def __init__(self, hero: HeroAlchemist) -> None:
        self.hero = hero
        self.feet = hero.contact()
        self.facing = hero.facing
        self.velocity = Vec2(0.0, 0.0)
        self.elapsed = 0.0
        self.finished = False
        self.phase = 0.0
        self.gait = 0.0
        self.attack_time: float | None = None
        self.attack_target: object | None = None
        self.claw_aim = GUARD_NEAR
        self.hit_wait = 0.0
        self.impact = 0.0
        self._struck = False
        anchor = surface_below(hero.planner, self.feet - Vec2(0.0, 2.0))
        self.support = anchor.surface if self.feet.distance_to(anchor.point) < 3.0 else None
        if self.support is not None:
            low, high = self._bounds()
            self.feet = Vec2(clamp(self.feet.x, low, high), self.support.start.y)

    @property
    def transforming(self) -> bool:
        return self.elapsed < TRANSFORM_IN

    @property
    def visual_scale(self) -> float:
        grown = smoothstep(clamp(self.elapsed / TRANSFORM_IN, 0.0, 1.0))
        scale = START_SCALE + (BEAST_SCALE - START_SCALE) * grown
        remaining = MUTAGEN_SECONDS - self.elapsed
        if remaining < TRANSFORM_OUT:
            scale = START_SCALE + (scale - START_SCALE) * smoothstep(
                clamp(remaining / TRANSFORM_OUT, 0.0, 1.0)
            )
        return scale

    @property
    def body(self) -> Vec2:
        bob = abs(math.sin(self.phase * math.tau)) * 1.2 * self.gait
        return self.feet + Vec2(0.0, -BEAST_HEIGHT * 0.58 - bob)

    @property
    def flying(self) -> bool:
        return self.support is None

    def contact(self) -> Vec2:
        return self.feet

    def _bounds(self) -> tuple[float, float]:
        assert self.support is not None
        margin = 21.0
        low, high = self.support.low + margin, self.support.high - margin
        if low > high:
            low = high = (self.support.low + self.support.high) / 2
        return low, high

    def update(self, dt: float, paused: bool = False) -> None:
        self.elapsed += dt
        self.finished = self.elapsed >= MUTAGEN_SECONDS - 1e-9
        self.hit_wait = max(0.0, self.hit_wait - dt)
        self.impact = max(0.0, self.impact - dt)
        if paused or self.finished:
            return
        if self.support is None:
            self._fall(dt)
        elif self.transforming:
            self.velocity = Vec2(0.0, 0.0)
            self.gait = 0.0
        elif self.attack_time is not None:
            self._update_claw(dt)
        else:
            self._hunt(dt)

    def _fall(self, dt: float) -> None:
        old = self.feet
        self.velocity = Vec2(self.velocity.x, self.velocity.y + GRAVITY * dt)
        self.feet += self.velocity * dt
        surfaces = [
            surface
            for surface in self.hero.planner.surfaces
            if surface.walkable
            and surface.low <= self.feet.x <= surface.high
            and old.y - 1.0 <= surface.start.y <= self.feet.y
        ]
        if surfaces:
            self.support = min(surfaces, key=lambda surface: surface.start.y)
            low, high = self._bounds()
            self.feet = Vec2(clamp(self.feet.x, low, high), self.support.start.y)
            self.velocity = Vec2(0.0, 0.0)
        self.gait = 0.0

    def _hunt(self, dt: float) -> None:
        found = self.hero.world.nearest_monster(self.body, NOTICE_RANGE)
        if found is None:
            self.velocity = Vec2(0.0, 0.0)
            self.gait = 0.0
            return
        target, point = found
        delta = point - self.body
        if abs(delta.x) > 2.0:
            self.facing = 1 if delta.x > 0.0 else -1
        if point.distance_to(self.body) <= CLAW_REACH and self.hit_wait <= 0.0:
            self._start_claw(target)
            return
        low, high = self._bounds()
        desired = self.facing * WALK_SPEED
        speed = self.velocity.x + (desired - self.velocity.x) * min(1.0, dt * 8.0)
        x = clamp(self.feet.x + speed * dt, low, high)
        moved = x - self.feet.x
        self.feet = Vec2(x, self.support.start.y)
        self.velocity = Vec2(moved / dt if dt > 0.0 else 0.0, 0.0)
        self.gait = min(1.0, abs(self.velocity.x) / WALK_SPEED)
        self.phase += abs(moved) / 38.0

    def _start_claw(self, target: object) -> None:
        self.attack_time = 0.0
        self.attack_target = target
        point = self.hero.world.closest_part(target, self.body)
        if point is None:
            self.claw_aim = GUARD_NEAR
        else:
            aim = Vec2(
                (point.x - self.feet.x) * self.facing,
                point.y - self.feet.y,
            )
            hip = Vec2(0.0, -MINOTAUR_HIP + PUNCH_SQUAT)
            shoulder = hip + (NEAR_SHOULDER - Vec2(0.0, -MINOTAUR_HIP)).rotated(
                MINOTAUR_HUNCH + PUNCH_LEAN
            )
            offset = aim - shoulder
            if offset.length() > ARM_LENGTH:
                aim = shoulder + offset.normalized() * ARM_LENGTH
            self.claw_aim = aim
        self._struck = False
        self.hit_wait = CLAW_COOLDOWN
        self.velocity = Vec2(0.0, 0.0)
        self.gait = 0.0

    def _update_claw(self, dt: float) -> None:
        assert self.attack_time is not None
        self.attack_time += dt
        if self.attack_time >= CLAW_HIT and not self._struck:
            self._struck = True
            target = self.attack_target
            point = (
                None
                if target is None
                else self.hero.world.closest_part(target, self.claw_point())
            )
            if point is not None and point.distance_to(self.claw_point()) <= 22.0:
                self.impact = 0.18
                self.hero.world.hurt_monster(
                    target,
                    CLAW_DAMAGE,
                    point,
                    Vec2(self.facing * 230.0, -65.0),
                    ranged=False,
                    attacker=self.hero,
                )
        if self.attack_time >= CLAW_TIME:
            self.attack_time = None
            self.attack_target = None

    def hand_positions(self) -> tuple[Vec2, Vec2]:
        """Minotaur punch hands in the unscaled, right-facing render frame."""
        near = GUARD_NEAR
        far = FAR_GUARD
        if self.attack_time is None:
            return near, far
        far_aim = self.claw_aim + Vec2(-7.0, -10.0)
        if self.attack_time < CLAW_WINDUP:
            progress = smoothstep(self.attack_time / max(CLAW_WINDUP, 1e-3))
            near = CLAW_CHAMBER.lerp(
                CLAW_COCKED,
                progress,
            )
            far = FAR_CHAMBER.lerp(FAR_COCKED, progress)
        elif self.attack_time < CLAW_HIT:
            progress = ((self.attack_time - CLAW_WINDUP) / CLAW_STRIKE) ** 2
            near = CLAW_COCKED.lerp(
                self.claw_aim,
                progress,
            )
            far = FAR_COCKED.lerp(far_aim, progress)
        else:
            progress = smoothstep(
                clamp((self.attack_time - CLAW_HIT) / CLAW_RECOVER, 0.0, 1.0)
            )
            near = self.claw_aim.lerp(
                GUARD_NEAR,
                progress,
            )
            far = far_aim.lerp(FAR_GUARD, progress)
        return near, far

    def claw_point(self) -> Vec2:
        hand, _ = self.hand_positions()
        scale = BEAST_SCALE
        return self.feet + Vec2(self.facing * hand.x * scale, hand.y * scale)

    def hits(self, point: Vec2, margin: float = 0.0) -> bool:
        scale = self.visual_scale
        torso_top = self.feet + Vec2(self.facing * 2.0 * scale, -60.0 * scale)
        head = self.feet + Vec2(self.facing * 15.0 * scale, -60.0 * scale)
        near, far = self.hand_positions()
        hands = [
            self.feet + Vec2(self.facing * hand.x * scale, hand.y * scale)
            for hand in (near, far)
        ]
        return (
            _distance_to_segment(point, self.feet + Vec2(0.0, -20.0 * scale), torso_top)
            <= 15.0 * scale + margin
            or point.distance_to(head) <= 9.0 * scale + margin
            or any(point.distance_to(hand) <= 8.0 * scale + margin for hand in hands)
        )

    def terrain_changed(self, change: TerrainChange) -> None:
        del change
        anchor = surface_below(self.hero.planner, self.feet - Vec2(0.0, 2.0))
        self.support = anchor.surface
        self.feet = anchor.point
        self.velocity = Vec2(0.0, 0.0)
