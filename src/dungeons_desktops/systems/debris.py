"""Dirt sprays, rock chunks, dust clouds, impact rings and holes, e.g. where the worm
breaks out of or slams into the ground."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from random import Random

from dungeons_desktops.core.geometry import Rect, Vec2, clamp
from dungeons_desktops.navigation.terrain import TerrainChange

GRAVITY = 700.0
DUST_DRAG = 2.5
DUST_RISE = 25.0
HOLE_LIFE = 12.0
HOLE_FADE = 2.5


@dataclass
class Particle:
    position: Vec2
    velocity: Vec2
    life: float
    size: float
    shade: int = 0
    """0 dirt, 1 dark dirt, 2 light dirt."""
    chunk: bool = False
    """A tumbling rock rather than a round clod."""
    angle: float = 0.0
    spin: float = 0.0
    age: float = 0.0


@dataclass
class Puff:
    """A dust cloud that billows out, slows, drifts up and fades."""

    position: Vec2
    velocity: Vec2
    radius: float
    life: float
    age: float = 0.0


@dataclass
class Ring:
    center: Vec2
    radius: float
    life: float
    cracks: list[list[Vec2]] = field(default_factory=list)
    """Each crack is a jagged polyline in units of `radius`, relative to the center."""
    age: float = 0.0


@dataclass
class Hole:
    """A hole torn in a window (or the screen's bottom border) where the worm went in
    or came out. It rides along with its window and fades away after a while."""

    center: Vec2
    radius: float
    box: int | None
    """Index of the window it's in, or None for the bottom border."""
    outline: list[float]
    """Jagged edge: a radius multiplier at evenly spaced angles."""
    border: Rect | None = None
    """The bottom border band it's in, when `box` is None."""
    age: float = 0.0

    def ground(self, boxes: Sequence[Rect]) -> Rect | None:
        """The patch of ground it shows on."""
        if self.box is None:
            return self.border
        return boxes[self.box] if self.box < len(boxes) else None


class Debris:
    def __init__(self, random: Random) -> None:
        self.random = random
        self.particles: list[Particle] = []
        self.puffs: list[Puff] = []
        self.rings: list[Ring] = []
        self.holes: list[Hole] = []

    def burst(
        self,
        point: Vec2,
        direction: Vec2,
        count: int,
        speed: float,
        ring_radius: float = 0.0,
        cracks: int = 0,
        spread: float = 0.9,
        chunks: int = 0,
        puffs: int = 0,
        scale: float = 1.0,
    ) -> None:
        """Spray `count` clods and `chunks` rocks in a cone of half-angle `spread` around
        `direction`, with `puffs` dust clouds and optionally a ring with cracks.
        `scale` sizes everything (a bigger worm makes a bigger mess)."""
        rng = self.random
        base = direction.angle() if direction.length_sq() > 0 else -math.pi / 2
        speed *= math.sqrt(scale)

        def launch(fraction: tuple[float, float]) -> Vec2:
            angle = base + rng.uniform(-spread, spread)
            return Vec2.from_angle(angle, speed * rng.uniform(*fraction))

        for _ in range(count):
            self.particles.append(
                Particle(
                    point,
                    launch((0.35, 1.0)),
                    rng.uniform(0.45, 0.95),
                    rng.uniform(1.2, 2.8) * scale,
                    rng.randrange(3),
                )
            )
        for _ in range(chunks):
            self.particles.append(
                Particle(
                    point,
                    launch((0.5, 0.9)),
                    rng.uniform(0.8, 1.3),
                    rng.uniform(2.8, 4.5) * scale,
                    rng.choice((0, 1)),
                    chunk=True,
                    angle=rng.uniform(0, math.tau),
                    spin=rng.uniform(-14.0, 14.0),
                )
            )
        for _ in range(puffs):
            angle = base + rng.uniform(-spread * 1.4, spread * 1.4)
            self.puffs.append(
                Puff(
                    point + Vec2.from_angle(angle, rng.uniform(0.0, 6.0) * scale),
                    Vec2.from_angle(angle, speed * rng.uniform(0.15, 0.4)),
                    rng.uniform(5.0, 9.0) * scale,
                    rng.uniform(0.7, 1.2),
                )
            )
        if ring_radius > 0.0:
            lines = [self._crack(rng) for _ in range(cracks)]
            self.rings.append(Ring(point, ring_radius * scale, 1.4, lines))

    def hole(
        self, point: Vec2, radius: float, boxes: Sequence[Rect], border: Rect | None = None
    ) -> None:
        """Tear a hole in the window at (or just outside) `point`, or failing that in
        the bottom `border` band, if either is there."""
        grounds: list[tuple[int | None, Rect]] = list(enumerate(boxes))
        if border is not None:
            grounds.append((None, border))
        for index, ground in grounds:
            inside = Vec2(
                clamp(point.x, ground.left, ground.right), clamp(point.y, ground.top, ground.bottom)
            )
            if inside.distance_to(point) <= radius:
                outline = [self.random.uniform(0.75, 1.15) for _ in range(14)]
                kept_border = border if index is None else None
                self.holes.append(Hole(inside, radius, index, outline, kept_border))
                return

    def terrain_changed(self, change: TerrainChange) -> None:
        kept = []
        for hole in self.holes:
            if change.removed(hole.box):
                continue
            delta = change.delta_for(hole.box)
            if delta is not None:
                hole.center += delta
                if hole.border is not None:
                    hole.border = hole.border.moved(delta.x, delta.y)
            new = change.new_index(hole.box)
            hole.box = hole.box if new is None else new
            kept.append(hole)
        self.holes = kept

    @staticmethod
    def _crack(rng: Random) -> list[Vec2]:
        """A jagged line out from near the center, sometimes forking."""
        angle = rng.uniform(0, math.tau)
        length = rng.uniform(0.7, 1.3)
        points = [Vec2.from_angle(angle, 0.25)]
        steps = 4
        for k in range(1, steps + 1):
            distance = 0.25 + (length - 0.25) * k / steps
            points.append(Vec2.from_angle(angle + rng.uniform(-0.35, 0.35), distance))
        if rng.random() < 0.5:
            fork = points[2]
            side = angle + rng.choice((-1.0, 1.0)) * rng.uniform(0.5, 0.9)
            points += [fork, fork + Vec2.from_angle(side, length * 0.35)]
        return points

    def update(self, dt: float) -> None:
        for particle in self.particles:
            particle.age += dt
            particle.velocity += Vec2(0.0, GRAVITY * dt)
            particle.position += particle.velocity * dt
            particle.angle += particle.spin * dt
        drag = math.exp(-DUST_DRAG * dt)
        for puff in self.puffs:
            puff.age += dt
            puff.velocity = puff.velocity * drag + Vec2(0.0, -DUST_RISE * dt)
            puff.position += puff.velocity * dt
        for ring in self.rings:
            ring.age += dt
        for hole in self.holes:
            hole.age += dt
        self.particles = [p for p in self.particles if p.age < p.life]
        self.puffs = [p for p in self.puffs if p.age < p.life]
        self.rings = [r for r in self.rings if r.age < r.life]
        self.holes = [h for h in self.holes if h.age < HOLE_LIFE]
