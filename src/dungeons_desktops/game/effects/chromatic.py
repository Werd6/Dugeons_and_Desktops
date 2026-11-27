"""Chromatic Ray results shared by every defender, independent of the caster's life."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.effects.breath import DEATH_TIME, Demise, Mote, step_motes
from dungeons_desktops.rig.skeleton import Pose

if TYPE_CHECKING:
    from dungeons_desktops.game.world.api import World


class RayEffect(Enum):
    DISINTEGRATE = "disintegrate"
    ACID = "acid"
    POLYMORPH = "polymorph"
    ICE = "ice"
    PETRIFY = "petrify"


RAY_COLORS = {
    RayEffect.DISINTEGRATE: (255, 74, 94),
    RayEffect.ACID: (164, 245, 66),
    RayEffect.POLYMORPH: (195, 111, 255),
    RayEffect.ICE: (82, 234, 255),
    RayEffect.PETRIFY: (222, 194, 134),
}
RAY_DAMAGE = {RayEffect.DISINTEGRATE: 12, RayEffect.ACID: 4, RayEffect.ICE: 4}
TRANSFORM_TIME = 5.0


def body_center(actor: object) -> Vec2:
    center = getattr(actor, "center", None)
    if callable(center):
        return center()
    return getattr(actor, "body", getattr(actor, "head", Vec2(0, 0)))


def body_points(actor: object) -> list[Vec2]:
    transforms = getattr(actor, "transforms", None)
    parts = getattr(actor, "parts", None)
    if callable(transforms):
        points = [p for t in transforms().values() for p in (t.start, t.end)]
    elif callable(parts):
        points = list(parts())
    elif hasattr(actor, "points"):
        points = list(actor.points)
    else:
        points = [body_center(actor)]
        points += [getattr(actor, name) for name in ("head", "hip", "shoulder")
                   if isinstance(getattr(actor, name, None), Vec2)]
    contact = getattr(actor, "contact", None)
    feet = contact() if callable(contact) else getattr(actor, "position", None)
    if isinstance(feet, Vec2):
        points.append(feet)
    return points


@dataclass
class Transmutation:
    effect: RayEffect
    origin: Vec2
    points: list[Vec2]
    time: float = 0.0
    demise: Demise | None = None
    render_cache: object | None = None

    @property
    def temporary(self) -> bool:
        return self.demise is None


@dataclass
class StoneShatter:
    origin: Vec2
    motes: list[Mote]
    age: float = 0.0


class ChromaticEffects:
    def __init__(self, world: World) -> None:
        self.world = world
        self.active: dict[object, Transmutation] = {}
        self.shatters: list[StoneShatter] = []

    def hit(self, effect: RayEffect, target: object, point: Vec2,
            push: Vec2, caster: object) -> None:
        if self.world.locate(target) is None:
            return
        if effect in (RayEffect.POLYMORPH, RayEffect.PETRIFY):
            if getattr(target, "illusion", False):
                return
            self._interrupt(target)
            state = Transmutation(effect, body_center(target), body_points(target))
            self.active[target] = target.chromatic_status = state
            return
        points, origin = body_points(target), body_center(target)
        killed = self.world.hurt_monster(
            target, RAY_DAMAGE[effect], point, push, ranged=True, attacker=caster,
        )
        if not killed or getattr(target, "chromatic_shattered", False):
            return
        self.clear(target)
        if effect not in (RayEffect.ACID, RayEffect.ICE):
            return
        kind = "acid" if effect is RayEffect.ACID else "cold"
        # Mind-controlled adventurers already own the dragon's full death lifecycle.
        succumb = getattr(target, "succumb", None)
        if callable(succumb):
            succumb(kind)
            return
        demise = Demise(kind, Pose(Vec2(0, 0), {}))
        demise.rest = max(p.y for p in points)
        state = Transmutation(effect, origin, points, demise=demise)
        self.active[target] = target.chromatic_status = state
        target.linger = DEATH_TIME - 0.5

    @staticmethod
    def _interrupt(target: object) -> None:
        weapon = getattr(target, "weapon", None)
        if weapon is not None:
            weapon.cancel()
        # Captured adventurers must not remain inside a harmless cat or a statue.
        for name in ("release_captives", "_release_all"):
            release = getattr(target, name, None)
            if callable(release):
                release()
        for name in ("flames", "waves"):
            particles = getattr(target, name, None)
            if isinstance(particles, list):
                particles.clear()

    def clear(self, target: object) -> None:
        self.active.pop(target, None)
        target.chromatic_status = None

    def shatter(self, target: object, point: Vec2, push: Vec2) -> bool:
        """A lethal hit from any source breaks a living stone statue into rubble."""
        state = self.active.get(target)
        if state is None or state.effect is not RayEffect.PETRIFY or not state.temporary:
            return False
        points = body_points(target)
        middle = sum(points, Vec2(0, 0)) / len(points)
        floor = max(p.y for p in points)
        rng = self.world.random
        motes = []
        for _ in range(32):
            spot = rng.choice(points) + Vec2(rng.uniform(-3, 3), rng.uniform(-3, 3))
            away = (spot - point).normalized()
            velocity = (away + Vec2(rng.uniform(-0.5, 0.5), -0.8)) * rng.uniform(40, 100)
            motes.append(Mote(
                "shard", spot, velocity + push * 0.12, rng.uniform(1.7, 2.4),
                rng.uniform(1.8, 4.2), angle=rng.uniform(0, math.tau),
                spin=rng.uniform(-9, 9), floor=floor,
            ))
        for _ in range(12):
            motes.append(Mote(
                "mist", rng.choice(points), Vec2(rng.uniform(-25, 25), rng.uniform(-20, -5)),
                rng.uniform(0.5, 1.1), rng.uniform(3, 6),
            ))
        self.shatters.append(StoneShatter(middle, motes))
        self.clear(target)
        target.chromatic_shattered = True
        return True

    def blocked(self, target: object) -> bool:
        state = self.active.get(target)
        return state is not None and state.temporary

    def dying(self, target: object) -> bool:
        state = self.active.get(target)
        return state is not None and state.demise is not None

    def update(self, dt: float) -> None:
        for burst in self.shatters:
            burst.age += dt
            burst.motes = step_motes(burst.motes, dt, self.world.random)
        self.shatters = [burst for burst in self.shatters if burst.motes]
        for target, state in list(self.active.items()):
            state.time += dt
            if state.temporary:
                if getattr(target, "hp", 1) <= 0 and self.shatter(
                    target, body_center(target), Vec2(0, 0),
                ):
                    continue
                if state.time + 1e-9 >= TRANSFORM_TIME or self.world.locate(target) is None:
                    self.clear(target)
                continue
            state.demise.update(dt, state.points, self.world.random)
            target.down_time = state.time
            if state.time >= DEATH_TIME:
                target.down_time = target.linger + 0.5
                self.clear(target)
