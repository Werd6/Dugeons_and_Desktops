"""Iggy's independent spell clocks, chromatic beams, and individual homing missiles."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from dungeons_desktops.core.geometry import Vec2, clamp, wrap_angle
from dungeons_desktops.game.defenders.chimera.goat import BEAM_RATE, FIRE_BURST, SWEEP
from dungeons_desktops.game.defenders.lich.actor import DOOR_COOLDOWN
from dungeons_desktops.game.effects.beam import beam_body
from dungeons_desktops.game.effects.chromatic import RAY_COLORS, RayEffect
from dungeons_desktops.game.world.api import World


class Ability(Enum):
    SIMULACRUM = "simulacrum"
    DIMENSION_DOOR = "dimension_door"
    CHROMATIC_RAY = "chromatic_ray"
    MAGIC_MISSILE = "magic_missile"


COOLDOWNS = {
    Ability.SIMULACRUM: 10.0,
    Ability.DIMENSION_DOOR: DOOR_COOLDOWN,
    Ability.CHROMATIC_RAY: 6.0,
    Ability.MAGIC_MISSILE: 4.0,
}
CAST_RANGE = 420.0
CAST_RELEASE = 0.3
CAST_TIME = 0.7
CAST_RECOVERY = 0.2
COPY_HP = 3
COPY_LIMIT = 4
MISSILE_COUNT = 5
MISSILE_INTERVAL = 0.18
MISSILE_DAMAGE = 1
VOLLEY_TIME = CAST_RELEASE + (MISSILE_COUNT - 1) * MISSILE_INTERVAL + 0.25
RAY_TIME = FIRE_BURST
RAY_CAST_TIME = CAST_RELEASE + RAY_TIME
RAY_FADE = 0.15
RAY_REACH = 600.0
RAY_RADIUS = 3.0


@dataclass
class ChromaticRay:
    start: Vec2
    end: Vec2
    effect: RayEffect
    target: object
    focus: Vec2
    sweep: int
    angle: float
    previous_angle: float
    previous_start: Vec2
    age: float = 0.0
    struck: set[object] = field(default_factory=set)
    trail: list[Vec2] = field(default_factory=list)

    @property
    def color(self) -> tuple[int, int, int]:
        return RAY_COLORS[self.effect]


@dataclass
class Missile:
    origin: Vec2
    target: Vec2
    monster: object | None
    duration: float
    bend: float
    sway: float
    waves: float
    phase: float
    curl: float
    age: float = 0.0
    trail: list[Vec2] = field(default_factory=list)

    def point(self, t: float) -> Vec2:
        t = clamp(t, 0, 1)
        line = self.target - self.origin
        forward = line.normalized()
        side = forward.rotated(math.pi / 2)
        envelope = math.sin(math.pi * t)
        across = self.bend + self.sway * math.sin(math.tau * self.waves * t + self.phase)
        curl = self.curl * math.sin(math.tau * t + self.phase)
        return self.origin + line * t + (side * across + forward * curl) * envelope


@dataclass
class Sparkle:
    point: Vec2
    color: tuple[int, int, int]
    radius: float = 7.0
    age: float = 0.0


class IggySpells:
    def __init__(self, world: World, caster: object) -> None:
        self.world = world
        self.caster = caster
        self.rays: list[ChromaticRay] = []
        self.missiles: list[Missile] = []
        self.sparks: list[Sparkle] = []

    def ray(self, origin: Vec2, target: object, effect: RayEffect | None = None) -> bool:
        point = self.world.closest_part(target, origin)
        if point is None:
            return False
        effect = effect or self.world.random.choice(tuple(RayEffect))
        sweep = self.world.random.choice((-1, 1))
        angle = (point - origin).angle() + sweep * SWEEP
        ray = ChromaticRay(
            origin, self._beam_end(origin, angle), effect, target, point, sweep,
            angle, angle, origin,
        )
        self.rays = [ray]
        return True

    def _beam_end(self, origin: Vec2, angle: float) -> Vec2:
        direction = Vec2.from_angle(angle)
        reach = RAY_REACH
        if direction.y > 1e-6:
            reach = min(reach, max(0, (self.world.floor_y - origin.y) / direction.y))
        elif direction.y < -1e-6 and self.world.ceiling is not None:
            reach = min(reach, max(0, (self.world.ceiling - origin.y) / direction.y))
        return origin + direction * reach

    def advance_ray(self, dt: float) -> Vec2 | None:
        """Turn the wand first; resolve the beam from the newly posed hand afterward."""
        if not self.rays:
            return None
        ray = self.rays[-1]
        ray.previous_angle, ray.previous_start = ray.angle, ray.start
        point = self.world.closest_part(ray.target, ray.start)
        if point is not None:
            ray.focus = point
        ray.age = min(RAY_TIME, ray.age + dt)
        offset = ray.sweep * SWEEP * math.cos(math.pi * ray.age / RAY_TIME)
        desired = (ray.focus - ray.start).angle() + offset
        ray.angle += clamp(wrap_angle(desired - ray.angle), -BEAM_RATE * dt, BEAM_RATE * dt)
        return Vec2.from_angle(ray.angle)

    def resolve_ray(self, origin: Vec2) -> None:
        if not self.rays:
            return
        ray = self.rays[-1]
        ray.start = origin
        ray.end = self._beam_end(origin, ray.angle)
        ray.trail.append(ray.end)
        del ray.trail[:-6]
        turn = wrap_angle(ray.angle - ray.previous_angle)
        # Sample the swept interval so small enemies cannot slip between frames.
        steps = max(1, math.ceil(abs(turn) * RAY_REACH / RAY_RADIUS))
        candidates = [
            (monster, beam_body(monster, RAY_RADIUS))
            for monster, _ in self.world.monsters_near(origin, RAY_REACH + RAY_RADIUS)
            if monster not in ray.struck
        ]
        for index in range(steps + 1):
            t = index / steps
            start = ray.previous_start.lerp(origin, t)
            angle = ray.previous_angle + turn * t
            end = self._beam_end(start, angle)
            for monster, body in candidates:
                if monster in ray.struck:
                    continue
                hit = body.intersect(start, end)
                if hit is None:
                    continue
                ray.struck.add(monster)
                self.sparks.append(Sparkle(hit, ray.color, 10))
                self.world.chromatic.hit(
                    ray.effect, monster, hit, Vec2.from_angle(angle, 70), self.caster,
                )

    def stop_ray(self) -> None:
        for ray in self.rays:
            ray.age = max(ray.age, RAY_TIME)

    def move_ray(self, origin: Vec2) -> None:
        """Carry a beam with a moved window without striking across the old location."""
        for ray in self.rays:
            ray.start = ray.previous_start = origin
            ray.end = self._beam_end(origin, ray.angle)
            ray.trail.clear()

    def missile(self, origin: Vec2, target: object | None, aim: Vec2) -> None:
        rng = self.world.random
        missile = Missile(
            origin, aim, target, clamp(origin.distance_to(aim) / 230, 0.6, 1.5),
            rng.choice((-1, 1)) * rng.uniform(30, 85), rng.uniform(16, 38),
            rng.uniform(1.2, 2.8), rng.uniform(0, math.tau), rng.uniform(20, 45),
            trail=[origin],
        )
        # Near the taskbar, curl upward so every shot stays visible on the desktop.
        floor = self.world.floor_y - 1
        ceiling = self.world.ceiling + 1 if self.world.ceiling is not None else -math.inf
        if max(missile.point(i / 30).y for i in range(1, 30)) > floor:
            side = (aim - origin).normalized().rotated(math.pi / 2)
            missile.bend = -math.copysign(abs(missile.bend) + missile.sway, side.y)
        for _ in range(24):
            if all(ceiling <= missile.point(i / 30).y <= floor for i in range(1, 30)):
                break
            missile.bend *= 0.8
            missile.sway *= 0.8
            missile.curl *= 0.8
        self.missiles.append(missile)

    def update(self, dt: float) -> None:
        for ray in self.rays:
            if ray.age >= RAY_TIME:
                ray.age += dt
        self.rays = [ray for ray in self.rays if ray.age < RAY_TIME + RAY_FADE]
        for spark in self.sparks:
            spark.age += dt
        self.sparks = [spark for spark in self.sparks if spark.age < 0.5]
        flying = []
        for missile in self.missiles:
            point = self.world.closest_part(missile.monster, missile.target)
            if point is not None:
                missile.target = point
            missile.age += dt
            missile.trail.append(missile.point(missile.age / missile.duration))
            del missile.trail[:-14]
            if missile.age < missile.duration:
                flying.append(missile)
                continue
            self.sparks.append(Sparkle(missile.target, (177, 190, 255)))
            if point is not None:
                self.world.hurt_monster(
                    missile.monster, MISSILE_DAMAGE, point,
                    (point - missile.origin).normalized() * 35,
                    ranged=True, attacker=self.caster,
                )
        self.missiles = flying
