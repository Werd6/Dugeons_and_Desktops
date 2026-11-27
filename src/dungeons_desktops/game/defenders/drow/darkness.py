"""The drow's globes of darkness, and the faerie fire that lights up whoever is in one.

A drow throws a small orb of darkness (`throw`) on a lob at where the adventurers are
bunched up. It flies straight through windows and bursts where it was aimed (or on
the floor, or after `ORB_LIFE`) into a globe that swells to `GLOBE_RADIUS` and holds
for `GLOBE_TIME` before it thins away. Every adventurer inside is blind
(`Stickman.blind_for`): he can't attack and only gropes about, slowly. And every one
of them is outlined in faerie fire (`Stickman.faerie`) for the drow to pick out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, smoothstep
from dungeons_desktops.game.defenders.drakes.drake import lobbed

if TYPE_CHECKING:
    from dungeons_desktops.game.world.simulation import SimWorld

ORB_SPEED = 240.0
ORB_GRAVITY = 220.0
ORB_LIFE = 2.5
ORB_ARRIVE = 5.0
"""An orb this near where it was aimed bursts."""
GLOBE_RADIUS = 70.0
GROW_TIME = 0.35
GLOBE_TIME = 6.0
"""How long a globe blinds whoever is in it..."""
FADE_TIME = 0.8
"""...and how long it then takes to thin away (harmless by then)."""
BLIND_LINGER = 0.3
"""Out of a globe, an adventurer is blind this much longer."""
FAERIE_LINGER = 0.6
"""...and his faerie fire burns on this long."""
LEGENDARY_RADIUS = 105.0
LEGENDARY_TIME = 9.0


@dataclass
class Orb:
    position: Vec2
    velocity: Vec2
    target: Vec2
    age: float = 0.0
    trail: list[Vec2] | None = None
    legendary: bool = False


@dataclass
class Globe:
    center: Vec2
    age: float = 0.0
    legendary: bool = False

    @property
    def full_radius(self) -> float:
        return LEGENDARY_RADIUS if self.legendary else GLOBE_RADIUS

    @property
    def duration(self) -> float:
        return LEGENDARY_TIME if self.legendary else GLOBE_TIME

    @property
    def radius(self) -> float:
        return self.full_radius * smoothstep(min(1.0, self.age / GROW_TIME))

    @property
    def active(self) -> bool:
        return self.age < self.duration

    @property
    def strength(self) -> float:
        """1 while it holds, thinning to 0 as it fades."""
        if self.age <= self.duration:
            return 1.0
        return max(0.0, 1.0 - (self.age - self.duration) / FADE_TIME)

    def covers(self, point: Vec2) -> bool:
        return self.active and point.distance_to(self.center) <= self.radius


class Darkness:
    def __init__(self, world: SimWorld) -> None:
        self.world = world
        self.orbs: list[Orb] = []
        self.globes: list[Globe] = []
        self.time = 0.0

    def throw(self, origin: Vec2, target: Vec2, legendary: bool = False) -> Orb:
        orb = Orb(
            origin, lobbed(origin, target, ORB_SPEED, ORB_GRAVITY), target,
            trail=[], legendary=legendary,
        )
        self.orbs.append(orb)
        return orb

    def burst(self, center: Vec2, legendary: bool = False) -> Globe:
        globe = Globe(center, legendary=legendary)
        self.globes.append(globe)
        return globe

    def covers(self, point: Vec2) -> bool:
        return any(globe.covers(point) for globe in self.globes)

    def update(self, dt: float) -> None:
        world = self.world
        self.time += dt
        flying = []
        for orb in self.orbs:
            orb.age += dt
            orb.velocity += Vec2(0.0, ORB_GRAVITY * dt)
            orb.position += orb.velocity * dt
            assert orb.trail is not None
            orb.trail.append(orb.position)
            del orb.trail[:-10]
            ahead = orb.target - orb.position
            arrived = ahead.length() <= ORB_ARRIVE or ahead.dot(orb.velocity) < 0.0
            if orb.position.y >= world.floor_y:
                self.burst(
                    Vec2(
                        orb.position.x,
                        world.floor_y
                        - (LEGENDARY_RADIUS if orb.legendary else GLOBE_RADIUS) * 0.4,
                    ),
                    orb.legendary,
                )
            elif arrived or orb.age >= ORB_LIFE:
                self.burst(orb.position, orb.legendary)
            else:
                flying.append(orb)
        self.orbs = flying
        for globe in self.globes:
            globe.age += dt
        self.globes = [g for g in self.globes if g.age < g.duration + FADE_TIME]
        for stickman in world.stickmen:
            if stickman.prey and self.covers(stickman.center()):
                stickman.blind_for(BLIND_LINGER)
                stickman.faerie = FAERIE_LINGER

    def clear(self) -> None:
        self.orbs.clear()
        self.globes.clear()
