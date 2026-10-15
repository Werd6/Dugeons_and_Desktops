"""Dragon colours and their breath weapons. Every colour hunts, flies and breathes the
same way (the breath is the same stream of `Flame` particles, with the same reach,
spread and damage); only the look differs: the scales, the horns, what the breath is
(fire, poison gas, lightning, acid or frost) and how a stickman it kills dies.

Burning is `fire.Burn`; the other four deaths are a `Demise`:
- poison: he clutches his throat and staggers, turns sickly green, then collapses
  while green fumes rise off him;
- lightning: rigid and jerking with his skeleton flickering through, throwing
  sparks, then he drops charred and smoking;
- acid: he slumps and melts down into a bubbling puddle;
- cold: frozen solid where he stands inside a shell of ice, then shatters into
  shards that scatter and melt away.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from random import Random
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.rig.ik import two_bone_points
from dungeons_desktops.rig.skeleton import Pose, forward_kinematics
from dungeons_desktops.systems.fire import BURN_TIME

if TYPE_CHECKING:
    from dungeons_desktops.rig.biped import BipedLayout

VARIANTS = ("red", "green", "blue", "black", "white")
BREATHS = {
    "red": "fire",
    "green": "poison",
    "blue": "lightning",
    "black": "acid",
    "white": "cold",
}
DEATH_MESSAGES = {
    "red": "Roasted by the red dragon!",
    "green": "Choked on the green dragon's poison!",
    "blue": "Struck down by the blue dragon's lightning!",
    "black": "Dissolved by the black dragon's acid!",
    "white": "Frozen solid by the white dragon!",
}

DEATH_TIME = BURN_TIME
"""Seconds from the killing breath until the body is gone, as for a burning one."""
CHOKE_TIME = 1.5
SHOCK_TIME = 1.0
MELT_TIME = (0.25, 3.2)
FREEZE_TIME = 0.35
"""Seconds for the ice to close over him."""
SHATTER_AT = 2.4
SHARDS = 22

MOTE_PHYSICS = {
    # kind: (gravity, drag)
    "fume": (-14.0, 1.6),
    "cloud": (-6.0, 1.4),
    "spark": (320.0, 0.6),
    "smoke": (-30.0, 2.0),
    "bubble": (-6.0, 3.0),
    "steam": (-26.0, 2.0),
    "mist": (-4.0, 2.2),
    "shard": (520.0, 0.3),
    "drip": (420.0, 0.3),
    "sizzle": (0.0, 8.0),
    "glint": (8.0, 2.0),
}
MOTE_LIMIT = 400


@dataclass(eq=False)
class Mote:
    """A short-lived visual particle: gas, spark, smoke, bubble, ice shard, acid drip."""

    kind: str
    position: Vec2
    velocity: Vec2
    life: float
    size: float
    age: float = 0.0
    angle: float = 0.0
    spin: float = 0.0
    floor: float | None = None
    """Where a falling mote lands (bounces, or splashes for a drip)."""

    @property
    def t(self) -> float:
        return min(1.0, self.age / self.life)


def step_motes(motes: list[Mote], dt: float, random: Random) -> list[Mote]:
    """Advance `motes`; returns the survivors plus any splashes from landed drips."""
    alive: list[Mote] = []
    for mote in motes:
        mote.age += dt
        if mote.age >= mote.life:
            continue
        gravity, drag = MOTE_PHYSICS[mote.kind]
        mote.velocity = mote.velocity * math.exp(-drag * dt) + Vec2(0.0, gravity * dt)
        mote.position += mote.velocity * dt
        mote.angle += mote.spin * dt
        floor = mote.floor
        if floor is not None and mote.position.y > floor:
            mote.position = Vec2(mote.position.x, floor)
            if mote.kind == "drip":
                alive += splash(mote.position, mote.size, random)
                continue
            mote.velocity = Vec2(mote.velocity.x * 0.45, -mote.velocity.y * 0.3)
            mote.spin *= 0.5
        alive.append(mote)
    return alive[-MOTE_LIMIT:]


def splash(point: Vec2, size: float, random: Random) -> list[Mote]:
    """Acid hitting a surface: a sizzling spot and a wisp of steam."""
    return [
        Mote("sizzle", point, Vec2(0.0, 0.0), random.uniform(0.5, 0.9), size * 1.6),
        Mote(
            "steam",
            point + Vec2(0.0, -1.0),
            Vec2(random.gauss(0.0, 6.0), -random.uniform(10.0, 25.0)),
            random.uniform(0.5, 0.9),
            size * 1.2,
        ),
    ]


@dataclass(eq=False)
class Demise:
    """How a stickman killed by poison, lightning, acid or cold goes: see the module doc."""

    kind: str
    pose: Pose
    """The pose he died in: held while he chokes, jerks or is frozen."""
    time: float = 0.0
    motes: list[Mote] = field(default_factory=list)
    rest: float = 0.0
    """The lowest point of the body: where the puddle spreads and shards land."""
    _carry: float = 0.0
    _shattered: bool = False

    @property
    def intensity(self) -> float:
        """1 at first, easing to 0 over the last 40% of the death."""
        return clamp((DEATH_TIME - self.time) / (0.4 * DEATH_TIME), 0.0, 1.0)

    @property
    def held(self) -> bool:
        """Stood rigid in a held pose (choking, jerking, frozen) rather than limp."""
        if self.kind == "poison":
            return self.time < CHOKE_TIME
        if self.kind == "lightning":
            return self.time < SHOCK_TIME
        return self.kind == "cold"

    @property
    def tint(self) -> float:
        """0 for his own colour, 1 fully green, charred, acid-soaked or frosted."""
        if self.kind == "poison":
            return smoothstep(self.time / CHOKE_TIME)
        if self.kind == "lightning":
            return smoothstep((self.time - SHOCK_TIME * 0.6) / 0.6)
        if self.kind == "acid":
            return smoothstep(self.time / 0.6)
        return smoothstep(self.time / FREEZE_TIME)

    @property
    def flashing(self) -> bool:
        """Lit up by the current (on alternate flickers) while it runs through him."""
        return self.kind == "lightning" and self.time < SHOCK_TIME and int(self.time * 22) % 2 == 0

    @property
    def melt(self) -> float:
        """0 standing, 1 melted flat into the puddle."""
        if self.kind != "acid":
            return 0.0
        start, end = MELT_TIME
        return smoothstep((self.time - start) / (end - start))

    @property
    def frost(self) -> float:
        """How far the ice shell has closed over him (0 to 1)."""
        if self.kind != "cold":
            return 0.0
        return smoothstep(self.time / FREEZE_TIME)

    @property
    def shattered(self) -> bool:
        return self._shattered

    def held_pose(self, layout: BipedLayout, facing: int, random: Random) -> Pose:
        if self.kind == "poison":
            return choke_pose(layout, self.pose, self.time, facing)
        if self.kind == "lightning":
            return shock_pose(layout, self.pose, random)
        return self.pose

    def update(self, dt: float, points: list[Vec2], random: Random) -> Vec2 | None:
        """Advance over `points` (spots along the body). Returns a jolt for the body
        (the last kick of the current as it lets go), or None."""
        was = self.time
        self.time += dt
        self.motes = step_motes(self.motes, dt, random)
        if points:
            self.rest = max(p.y for p in points)
        kind = self.kind
        if kind == "cold" and not self._shattered and self.time >= SHATTER_AT:
            self._shattered = True
            self._shatter(points, random)
        rate = {"poison": 16.0, "lightning": 70.0, "acid": 26.0, "cold": 10.0}[kind]
        if kind == "lightning" and self.time >= SHOCK_TIME:
            rate = 16.0
        if kind == "cold" and self._shattered:
            rate = 0.0
        if kind == "poison":
            rate *= clamp((self.time - 0.4 * CHOKE_TIME) / CHOKE_TIME, 0.0, 1.0)
        self._carry += rate * self.intensity * dt
        while self._carry >= 1.0 and points:
            self._carry -= 1.0
            self.motes.append(self._emit(random.choice(points), points, random))
        if kind == "lightning" and was < SHOCK_TIME <= self.time:
            return Vec2(random.uniform(-40.0, 40.0), -90.0)
        return None

    def _emit(self, spot: Vec2, points: list[Vec2], random: Random) -> Mote:
        jitter = Vec2(random.uniform(-1.5, 1.5), random.uniform(-1.5, 1.5))
        if self.kind == "poison":
            return Mote(
                "fume",
                spot + jitter,
                Vec2(random.gauss(0.0, 6.0), -random.uniform(6.0, 16.0)),
                random.uniform(1.0, 1.8),
                random.uniform(1.2, 2.4),
            )
        if self.kind == "lightning":
            if self.time < SHOCK_TIME:
                velocity = Vec2.from_angle(random.uniform(-math.pi, 0.3), random.uniform(40, 110))
                return Mote(
                    "spark",
                    spot,
                    velocity,
                    random.uniform(0.15, 0.4),
                    random.uniform(0.5, 1.1),
                    floor=self.rest,
                )
            return Mote(
                "smoke",
                spot + jitter,
                Vec2(random.gauss(0.0, 5.0), -random.uniform(8.0, 20.0)),
                random.uniform(0.8, 1.5),
                random.uniform(1.0, 2.0),
            )
        if self.kind == "acid":
            low = min(p.x for p in points)
            high = max(p.x for p in points)
            spread = (high - low) * 0.5 + 3.0 + 6.0 * self.melt
            x = (low + high) * 0.5 + random.uniform(-spread, spread)
            if random.random() < 0.35:
                return Mote(
                    "steam",
                    Vec2(x, self.rest - 1.0),
                    Vec2(random.gauss(0.0, 4.0), -random.uniform(8.0, 18.0)),
                    random.uniform(0.6, 1.1),
                    random.uniform(1.0, 1.8),
                )
            return Mote(
                "bubble",
                Vec2(x, self.rest - random.uniform(0.0, 1.5)),
                Vec2(0.0, -random.uniform(2.0, 6.0)),
                random.uniform(0.3, 0.7),
                random.uniform(0.5, 1.2),
            )
        return Mote(
            "glint",
            spot + jitter * 2.0,
            Vec2(random.gauss(0.0, 3.0), random.gauss(0.0, 3.0)),
            random.uniform(0.4, 0.8),
            random.uniform(0.8, 1.4),
        )

    def _shatter(self, points: list[Vec2], random: Random) -> None:
        if not points:
            return
        middle = Vec2(sum(p.x for p in points), sum(p.y for p in points)) * (1.0 / len(points))
        for _ in range(SHARDS):
            spot = random.choice(points) + Vec2(random.uniform(-2, 2), random.uniform(-2, 2))
            away = (spot - middle).normalized()
            if away.length() == 0.0:
                away = Vec2(0.0, -1.0)
            velocity = (away + Vec2(random.gauss(0.0, 0.5), -0.8)) * random.uniform(40.0, 110.0)
            self.motes.append(
                Mote(
                    "shard",
                    spot,
                    velocity,
                    random.uniform(2.6, DEATH_TIME - SHATTER_AT - 0.2),
                    random.uniform(1.4, 3.2),
                    angle=random.uniform(0.0, math.tau),
                    spin=random.gauss(0.0, 12.0),
                    floor=self.rest,
                )
            )
        for _ in range(8):
            self.motes.append(
                Mote(
                    "mist",
                    random.choice(points),
                    Vec2(random.gauss(0.0, 12.0), -random.uniform(2.0, 10.0)),
                    random.uniform(0.6, 1.2),
                    random.uniform(2.0, 3.5),
                )
            )


def _arms(layout: BipedLayout) -> list[tuple[str, str]]:
    names = [bone.name for bone in layout.skeleton.bones]
    return [
        (f"upper_arm_{side}", f"lower_arm_{side}")
        for side in ("l", "r")
        if f"upper_arm_{side}" in names and f"lower_arm_{side}" in names
    ]


def _bone_length(layout: BipedLayout, name: str) -> float:
    return next(bone.length for bone in layout.skeleton.bones if bone.name == name)


def choke_pose(layout: BipedLayout, pose: Pose, time: float, facing: int) -> Pose:
    """Hands clutching his throat, head thrown back, swaying as he chokes."""
    held = pose.copy()
    angles = held.angles
    ramp = min(1.0, time * 3.0)
    angles[layout.pelvis] += ramp * 0.12 * math.sin(time * 7.0) - facing * 0.08 * ramp
    angles[layout.head] += -facing * 0.45 * ramp + 0.15 * math.sin(time * 23.0) * ramp
    transforms = forward_kinematics(layout.skeleton, held)
    head = transforms[layout.head]
    for n, (upper, lower) in enumerate(_arms(layout)):
        shoulder = transforms[upper].start
        throat = head.start.lerp(head.end, 0.2) + Vec2(facing * (0.8 + 0.4 * n), 0.0)
        shake = 0.4 * math.sin(time * 31.0 + n * 2.0)
        throat += Vec2(0.0, shake) * layout.scale
        _, elbow, hand = two_bone_points(
            shoulder, _bone_length(layout, upper), _bone_length(layout, lower), throat, -facing
        )
        torso = transforms[upper].angle - angles[upper]
        upper_world = _blend(transforms[upper].angle, (elbow - shoulder).angle(), ramp)
        lower_world = _blend(transforms[lower].angle, (hand - elbow).angle(), ramp)
        angles[upper] = math.remainder(upper_world - torso, math.tau)
        angles[lower] = math.remainder(lower_world - upper_world, math.tau)
    return held


def shock_pose(layout: BipedLayout, pose: Pose, random: Random) -> Pose:
    """Stiff as a board, arms flung out, every joint twitching."""
    held = pose.copy()
    angles = held.angles
    transforms = forward_kinematics(layout.skeleton, held)
    for n, (upper, lower) in enumerate(_arms(layout)):
        torso = transforms[upper].angle - angles[upper]
        spread = (-1.0 if n == 0 else 1.0) * 1.15
        world = -math.pi / 2 + spread + random.gauss(0.0, 0.18)
        angles[upper] = math.remainder(world - torso, math.tau)
        angles[lower] = random.gauss(0.0, 0.2)
    for name in (layout.head, layout.torso):
        angles[name] += random.gauss(0.0, 0.1)
    jolt = Vec2(random.uniform(-0.6, 0.6), random.uniform(-0.8, 0.2))
    return Pose(root=held.root + jolt, angles=angles)


def _blend(a: float, b: float, t: float) -> float:
    return a + math.remainder(b - a, math.tau) * t
