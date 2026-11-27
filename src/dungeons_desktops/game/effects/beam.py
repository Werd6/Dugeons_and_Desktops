"""Beam collision snapshots: reject empty space, then intersect body segments directly."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from dungeons_desktops.core.geometry import Vec2, clamp
from dungeons_desktops.game.actors.base import BODY_RADIUS, Actor
from dungeons_desktops.game.defenders.chimera.actor import Chimera
from dungeons_desktops.game.defenders.displacer import actor as displacer
from dungeons_desktops.game.defenders.dragon.actor import BODY_LENGTH, Dragon
from dungeons_desktops.game.defenders.drakes.drake import RIDER_HEAD, Drake
from dungeons_desktops.game.defenders.drakes.kobold import Kobold
from dungeons_desktops.game.defenders.drow import actor as drow
from dungeons_desktops.game.defenders.hydra.actor import Hydra
from dungeons_desktops.game.defenders.lich import actor as lich
from dungeons_desktops.game.defenders.minotaur import actor as minotaur
from dungeons_desktops.game.defenders.worm.actor import Worm
from dungeons_desktops.game.effects.chromatic import body_points

Capsule = tuple[Vec2, Vec2, float]


@dataclass
class BeamBody:
    bounds: tuple[float, float, float, float]
    capsules: list[Capsule]
    test: Callable[[Vec2, float], bool] | None = None
    margin: float = 0

    def intersect(self, start: Vec2, end: Vec2) -> Vec2 | None:
        interval = _clip(start, end, self.bounds)
        if interval is None:
            return None
        if self.test is None:
            for a, b, radius in self.capsules:
                hit = _capsule_hit(start, end, a, b, radius)
                if hit is not None:
                    return hit
            return None
        # Custom monsters retain their exact hit shapes, sampled only near their bodies.
        low, high = interval
        first, last = start.lerp(end, low), start.lerp(end, high)
        steps = max(1, math.ceil(first.distance_to(last) / 4))
        for index in range(steps + 1):
            point = first.lerp(last, index / steps)
            if self.test(point, self.margin):
                return point
        return None


def beam_body(actor: object, margin: float) -> BeamBody:
    capsules = []
    if isinstance(actor, Actor):
        transforms = actor.transforms()
        radius = BODY_RADIUS * actor.layout.scale + margin
        capsules = [(t.start, t.end, radius) for t in transforms.values()]
        head = transforms[actor.layout.head].end
        capsules.append((head, head, actor.layout.head_radius + 2 * actor.layout.scale + margin))
    elif isinstance(actor, Dragon):
        capsules = [(actor.body, actor.body, BODY_LENGTH * 0.5 + margin),
                    (actor.head, actor.head, 8 + margin)]
    elif isinstance(actor, Worm):
        capsules = [(p, p, actor.radius(i) + 1 + margin) for i, p in enumerate(actor.points)]
    elif isinstance(actor, Hydra):
        if actor.underground:
            return BeamBody((0, 0, 0, 0), [])
        capsules = [(s.center, s.center, s.radius + margin) for s in actor.segments if not s.hidden]
        for head in actor.heads:
            if not actor._head_hidden(head):
                capsules.append((head.position, head.position, 5 * head.scale + margin))
                capsules.extend((p, p, 3 + margin) for p in head.neck[1::2])
    elif isinstance(actor, Drake):
        capsules = [(p, p, 5 + margin) for p in (actor.body, actor.chest, actor.hip, actor.head)]
        capsules += [(actor.rider_shoulder, actor.rider_shoulder, 3 + margin),
                     (actor.rider_head, actor.rider_head, RIDER_HEAD + margin)]
    elif isinstance(actor, Kobold):
        capsules = [(actor.seat, actor.seat, 2.5 + margin),
                    (actor.rider_shoulder, actor.rider_shoulder, 2.5 + margin),
                    (actor.rider_head, actor.rider_head, RIDER_HEAD + margin)]
    elif isinstance(actor, drow.Lizard):
        middle, shoulders, hips, head = actor.parts()[:4]
        capsules = [(hips, middle, drow.BODY_RADIUS + margin),
                    (middle, shoulders, drow.BODY_RADIUS + margin),
                    (head, head, drow.HEAD_RADIUS + margin)]
        if actor.mounted:
            capsules += [(actor.seat, actor.rider_shoulder, 2.5 + margin),
                         (actor.rider_head, actor.rider_head, drow.RIDER_HEAD + margin)]
    elif isinstance(actor, minotaur.Minotaur):
        def at(local):
            return actor.to_world(actor.local(local))
        head, back = at(minotaur.HEAD), at(minotaur.BACK)
        hips = at(Vec2(0, -minotaur.HIP_HEIGHT))
        capsules = [
            (head, head, minotaur.HEAD_RADIUS + margin),
            (at(minotaur.NECK), head, minotaur.NECK_RADIUS + margin),
            (at(minotaur.WAIST), at(minotaur.SHOULDER), minotaur.TORSO_RADIUS + margin),
            (back, back, minotaur.BACK_RADIUS + margin),
            *[(actor.to_world(foot), hips, minotaur.LEG_RADIUS + margin)
              for foot in minotaur.STANCE],
        ]
    elif isinstance(actor, Chimera):
        mane, lion, goat, snake = actor.mane, actor.lion_head, actor.goat_head, actor.snake_head
        capsules = [
            (actor.hip, actor.shoulder, 7.5 + margin), (mane, mane, 9 + margin),
            (lion, lion, 6 + margin), (actor.goat_root, goat, 3.5 + margin),
            (goat, goat, 5 + margin), (snake, snake, 4 + margin),
            *[(p, p, 3 + margin) for p in actor.tail[2::2]],
        ]
    elif isinstance(actor, displacer.Displacer):
        middle, shoulders, hips, head = actor.parts()
        capsules = [(hips, middle, displacer.BODY_RADIUS + margin),
                    (middle, shoulders, displacer.BODY_RADIUS + margin),
                    (head, head, displacer.HEAD_RADIUS + margin)]
    elif isinstance(actor, lich.Lich):
        if actor.dead or actor.phased:
            return BeamBody((0, 0, 0, 0), [])
        head = actor.project(lich.SKULL.x, 0, lich.SKULL.y)
        capsules = [(head, head, lich.SKULL_RADIUS + margin),
                    (actor.project(0, 0, -31), actor.project(0, 0, -6), lich.BODY_RADIUS + margin)]

    return BeamBody(bounds, [], test, margin)


def _clip(start: Vec2, end: Vec2, bounds) -> tuple[float, float] | None:
    low, high = 0.0, 1.0
    left, top, right, bottom = bounds
    for origin, distance, near, far in (
        (start.x, end.x - start.x, left, right),
        (start.y, end.y - start.y, top, bottom),
    ):
        if abs(distance) < 1e-9:
            if not near <= origin <= far:
                return None
            continue
        a, b = (near - origin) / distance, (far - origin) / distance
        low, high = max(low, min(a, b)), min(high, max(a, b))
        if low > high:
            return None
    return low, high


def _capsule_hit(start: Vec2, end: Vec2, a: Vec2, b: Vec2, radius: float) -> Vec2 | None:
    """Closest points of two finite segments; a zero-length body segment is a circle."""
    ux, uy = end.x - start.x, end.y - start.y
    vx, vy = b.x - a.x, b.y - a.y
    wx, wy = start.x - a.x, start.y - a.y
    uu, vv = ux * ux + uy * uy, vx * vx + vy * vy
    uv, uw, vw = ux * vx + uy * vy, ux * wx + uy * wy, vx * wx + vy * wy
    if uu < 1e-9:
        s, t = 0.0, clamp(vw / vv, 0, 1) if vv > 1e-9 else 0.0
    elif vv < 1e-9:
        s, t = clamp(-uw / uu, 0, 1), 0.0
    else:
        denominator = uu * vv - uv * uv
        s = clamp((uv * vw - uw * vv) / denominator, 0, 1) if denominator > 1e-9 else 0.0
        t = (uv * s + vw) / vv
        if t < 0:
            s, t = clamp(-uw / uu, 0, 1), 0.0
        elif t > 1:
            s, t = clamp((uv - uw) / uu, 0, 1), 1.0
    dx, dy = wx + s * ux - t * vx, wy + s * uy - t * vy
    return Vec2(start.x + s * ux, start.y + s * uy) if dx * dx + dy * dy <= radius**2 else None
