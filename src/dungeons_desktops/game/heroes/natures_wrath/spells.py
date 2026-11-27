"""Natures Wrath's rotation: a larger fireball and chaining electric bolts."""

from dataclasses import dataclass
from enum import Enum

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.defenders.lich.spells import (
    ARC_TIME,
    BLAST_TIME,
    CHAIN_DAMAGE,
    CHAIN_HOPS,
    CHAIN_REACH,
    CHAIN_STEP,
    FIREBALL_DAMAGE,
    FIREBALL_GRAVITY,
    FIREBALL_PACE,
    FIREBALL_PUSH,
)
from dungeons_desktops.game.defenders.lich.spells import FIREBALL_RADIUS as LICH_BLAST_RADIUS
from dungeons_desktops.game.world.api import World


class Ability(Enum):
    FIREBALL = "fireball"
    CHAIN_LIGHTNING = "chain_lightning"
    MAGMA_DRAGON = "magma_dragon"
    BEAR = "bear"


ROTATION = (Ability.FIREBALL, Ability.BEAR, Ability.CHAIN_LIGHTNING, Ability.MAGMA_DRAGON)
CAST_RANGE = 420.0
CAST_TIME = 0.9
CAST_RELEASE = 0.45
CAST_DELAY = 1.4
ABILITY_DELAYS = {
    Ability.FIREBALL: CAST_DELAY,
    Ability.CHAIN_LIGHTNING: 1.2,
    Ability.MAGMA_DRAGON: 1.4,
    Ability.BEAR: 1.4,
}
FIREBALL_RADIUS = LICH_BLAST_RADIUS * 1.5
ORB_RADIUS = 4.5 * 1.5


@dataclass
class Fireball:
    position: Vec2
    velocity: Vec2
    time: float
    age: float = 0.0


@dataclass
class Blast:
    center: Vec2
    age: float = 0.0


@dataclass
class LightningArc:
    start: Vec2
    end: Vec2
    target: object
    source: object | None
    damage: int
    delay: float
    seed: int
    age: float = 0.0
    struck: bool = False


class NatureSpells:
    def __init__(self, world: World, caster: object) -> None:
        self.world = world
        self.caster = caster
        self.fireballs: list[Fireball] = []
        self.blasts: list[Blast] = []
        self.arcs: list[LightningArc] = []

    def cast(self, ability: Ability, origin: Vec2, aim: Vec2, target: object | None = None) -> None:
        if ability is Ability.FIREBALL:
            time = max(0.45, min(1.1, abs(aim.x - origin.x) / FIREBALL_PACE))
            offset = aim - origin
            velocity = Vec2(
                offset.x / time, (offset.y - 0.5 * FIREBALL_GRAVITY * time * time) / time
            )
            self.fireballs.append(Fireball(origin, velocity, time))
        elif ability is Ability.CHAIN_LIGHTNING and target is not None:
            self._chain_lightning(origin, target)

    def _chain_lightning(self, origin: Vec2, target: object) -> None:
        point = self.world.closest_part(target, origin)
        if point is None:
            return
        chain = [(target, point)]
        for _ in range(CHAIN_HOPS):
            candidates = self.world.monsters_near(chain[-1][1], CHAIN_REACH)
            seen = [monster for monster, _ in chain]
            candidates = [(monster, part) for monster, part in candidates if monster not in seen]
            if not candidates:
                break
            chain.append(min(candidates, key=lambda pair: pair[1].distance_to(chain[-1][1])))
        start = origin
        source = None
        for index, (monster, end) in enumerate(chain):
            self.arcs.append(
                LightningArc(
                    start,
                    end,
                    monster,
                    source,
                    CHAIN_DAMAGE[min(index, len(CHAIN_DAMAGE) - 1)],
                    index * CHAIN_STEP,
                    int(end.x * 13 + end.y * 7) + index * 101,
                )
            )
            start, source = end, monster

    def update(self, dt: float) -> None:
        self._update_arcs(dt)
        for blast in self.blasts:
            blast.age += dt
        self.blasts = [blast for blast in self.blasts if blast.age < BLAST_TIME]
        flying = []
        for ball in self.fireballs:
            # Sample the arc so fast projectiles cannot skip a small goblin.
            duration = min(dt, max(0.0, ball.time - ball.age))
            steps = max(
                1, int((ball.velocity.length() + FIREBALL_GRAVITY * duration) * duration / 2.5) + 1
            )
            step = duration / steps
            for _ in range(steps):
                ball.age += step
                ball.position += ball.velocity * step + Vec2(0, 0.5 * FIREBALL_GRAVITY * step**2)
                ball.velocity += Vec2(0, FIREBALL_GRAVITY * step)
                hit = self.world.monster_at(ball.position) is not None or bool(
                    self.world.monsters_near(ball.position, ORB_RADIUS)
                )
                if hit or ball.age >= ball.time - 1e-9 or ball.position.y >= self.world.floor_y:
                    center = Vec2(ball.position.x, min(ball.position.y, self.world.floor_y - 2))
                    self._burst(center)
                    break
            else:
                flying.append(ball)
        self.fireballs = flying

    def _update_arcs(self, dt: float) -> None:
        for arc in self.arcs:
            active_dt = dt
            if arc.delay > 0:
                arc.delay -= dt
                if arc.delay > 0:
                    continue
                active_dt = -arc.delay
            if not arc.struck:
                arc.struck = True
                point = self.world.closest_part(arc.target, arc.end)
                if point is None:
                    arc.age = ARC_TIME
                    continue
                arc.end = point
                if arc.source is not None:
                    arc.start = self.world.closest_part(arc.source, arc.start) or arc.start
                self.world.hurt_monster(
                    arc.target,
                    arc.damage,
                    point,
                    (point - arc.start).normalized() * 120,
                    ranged=True,
                    attacker=self.caster,
                )
            arc.age += active_dt
        self.arcs = [arc for arc in self.arcs if arc.age < ARC_TIME]

    def _burst(self, center: Vec2) -> None:
        self.blasts.append(Blast(center))
        for monster, part in self.world.monsters_near(center, FIREBALL_RADIUS):
            away = (part - center).normalized() if part.distance_to(center) > 1 else Vec2(0, -1)
            self.world.hurt_monster(
                monster,
                FIREBALL_DAMAGE,
                part,
                away * FIREBALL_PUSH + Vec2(0, -160),
                ranged=True,
                attacker=self.caster,
            )
