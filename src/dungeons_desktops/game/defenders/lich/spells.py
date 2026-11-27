"""The lich's spells, once they leave his palm, and the dead they raise.

`Necromancy.cast` starts one of the five spells from the flame at a foe; `update`
flies, arcs, grips and detonates them. Every hit goes through `Stickman.hurt` with
the source "lich" (so kills count) and only ever lands on free adventurers (`prey`),
never on thralls. Like the adventurers' missiles they fly straight through windows
and stop at the floor.

- fireball: a bead lobbed at the foe that bursts (`FIREBALL_RADIUS`) for
  `FIREBALL_DAMAGE` to everyone caught, leaving a scorch.
- power_word_kill: a rune flashes over the foe; a beat later he dies outright, his
  soul drawn off toward the lich.
- magic_missiles: `MISSILES` homing darts of 1 damage, the first `MISSILES_AT_FOE` at
  the foe, the rest shared among the prey near him.
- chain_lightning: a bolt to the foe that arcs on to up to `CHAIN_HOPS` more, each
  near the last, for `CHAIN_DAMAGE`, stunning briefly.
- black_tentacles: tentacles erupt from every surface near the foe (floor, window
  tops, sides and undersides, the screen's edges) and grip everyone in their reach,
  crushing them over `TENTACLE_TIME`.

An adventurer killed by any of them rises `RISE_DELAY` later as a skeleton (see
`skeletons`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.navigation.terrain import TerrainChange

if TYPE_CHECKING:
    from dungeons_desktops.game.adventurers.actor import Stickman

SPELLS = ("fireball", "power_word_kill", "magic_missiles", "chain_lightning", "black_tentacles")
BASE_SPELLS = SPELLS
SOURCE = "lich"

FIREBALL_GRAVITY = 420.0
FIREBALL_PACE = 300.0  # px/s along the ground, for its flight time
FIREBALL_RADIUS = 70.0
FIREBALL_DAMAGE = 4
FIREBALL_PUSH = 300.0
BLAST_TIME = 0.7
SCORCH_TIME = 6.0

WORD_DELAY = 0.75  # the rune hangs over him this long before the word lands
WORD_TIME = 1.2
WISP_TIME = 0.9

MISSILES = 8
MISSILES_AT_FOE = 4
MISSILE_SPREAD = 250.0
MISSILE_STAGGER = 0.035
MISSILE_SPEED = 360.0
MISSILE_TURN = 9.0
MISSILE_LIFE = 9.0

CHAIN_HOPS = 3
CHAIN_REACH = 300.0
CHAIN_DAMAGE = (3, 3, 2, 2)
CHAIN_STEP = 0.08
CHAIN_STUN = 2.5
ARC_TIME = 0.35

TENTACLE_RANGE = 130.0  # they erupt from surfaces this near the foe
TENTACLE_SPACING = 20.0
TENTACLE_CAP = 44
TENTACLE_LENGTH = (40.0, 55.0)
TENTACLE_TIME = 4.0
TENTACLE_GROW = 0.35
TENTACLE_CRUSH = 0.8
TENTACLE_DAMAGE = 1
TENTACLE_FOLLOW = 10.0  # how quickly a tip closes on where it wants to be (1/s)

RISE_DELAY = 1.5

CLOUD_DURATION = 7.0
CLOUD_RADIUS = 92.0
CLOUD_DAMAGE = 1
CLOUD_HIT_INTERVAL = 1.0
CLOUD_SUMMON_TIME = 0.55


def tentacle_faces(world) -> list[tuple[Vec2, Vec2, Vec2, int | None]]:
    """Every surface face from which a Black Tentacle-style spell can emerge."""
    floor, left, right = world.floor_y, world.left, world.width
    top = world.ceiling if world.ceiling is not None else 0.0
    faces: list[tuple[Vec2, Vec2, Vec2, int | None]] = [
        (Vec2(left, floor), Vec2(right, floor), Vec2(0.0, -1.0), None),
        (Vec2(left, top), Vec2(left, floor), Vec2(1.0, 0.0), None),
        (Vec2(right, top), Vec2(right, floor), Vec2(-1.0, 0.0), None),
    ]
    if world.ceiling is not None:
        faces.append((Vec2(left, top), Vec2(right, top), Vec2(0.0, 1.0), None))
    for index, rect in enumerate(world.boxes):
        x0, x1, y0 = rect.x, rect.x + rect.width, rect.y
        y1 = min(rect.y + rect.height, floor)
        faces.append((Vec2(x0, y0), Vec2(x1, y0), Vec2(0.0, -1.0), index))
        faces.append((Vec2(x0, y0), Vec2(x0, y1), Vec2(-1.0, 0.0), index))
        faces.append((Vec2(x1, y0), Vec2(x1, y1), Vec2(1.0, 0.0), index))
        if rect.y + rect.height < floor - 1.0:
            faces.append((Vec2(x0, y1), Vec2(x1, y1), Vec2(0.0, 1.0), index))
    return faces


def tentacle_buried(world, base: Vec2, normal: Vec2, box: int | None) -> bool:
    """Whether an arm at ``base`` would emerge directly inside another window."""
    probe = base + normal * 3.0
    return any(index != box and rect.contains(probe) for index, rect in enumerate(world.boxes))

SMITE_HANG = 0.35
SMITE_DROP = 0.15
SMITE_LINGER = 0.6
SMITE_STAGGER = 0.3
SMITE_HEIGHT = 260.0
"""How high over him the sword appears (or just under the top of the screen)."""
SMITE_DAMAGE = 3
SMITE_FADE = 0.3


@dataclass
class Fireball:
    position: Vec2
    velocity: Vec2
    time: float
    """Seconds until it reaches its mark."""
    age: float = 0.0
    caster: object = None


@dataclass
class Blast:
    center: Vec2
    age: float = 0.0


@dataclass
class Scorch:
    point: Vec2
    box: int | None
    age: float = 0.0


@dataclass
class Word:
    """Power word kill: a rune over `target`, the word landing at `WORD_DELAY`."""

    target: Stickman
    caster: object
    age: float = 0.0
    spoken: bool = False


@dataclass
class Wisp:
    """A soul drawn out of a body toward the lich who spoke the word."""

    start: Vec2
    caster: object
    age: float = 0.0
    end: Vec2 = field(default_factory=lambda: Vec2(0.0, 0.0))


@dataclass
class Dart:
    position: Vec2
    velocity: Vec2
    target: Stickman
    delay: float
    age: float = 0.0
    trail: list[Vec2] = field(default_factory=list)
    caster: object = None


@dataclass
class Arc:
    """One jagged hop of chain lightning, shown for `ARC_TIME` once it strikes."""

    start: Vec2
    end: Vec2
    target: Stickman
    damage: int
    delay: float
    seed: int
    age: float = 0.0
    struck: bool = False
    caster: object = None


@dataclass
class Tentacle:
    """One arm, rooted at `base` on box `box` (None: the floor or the screen's edge),
    growing out along `normal` up to `length`, its tip closing on what it holds."""

    base: Vec2
    normal: Vec2
    box: int | None
    length: float
    phase: float
    tip: Vec2
    held: Stickman | None = None


@dataclass
class Tentacles:
    """Black tentacles: arms from every surface near where it was cast."""

    arms: list[Tentacle]
    seed: int
    age: float = 0.0
    crush: float = TENTACLE_CRUSH
    caster: object = None

    @property
    def strength(self) -> float:
        """0 -> 1 as they erupt, back to 0 as they sink."""
        rise = min(1.0, self.age / TENTACLE_GROW)
        sink = min(1.0, max(0.0, (TENTACLE_TIME - self.age) / TENTACLE_GROW))
        return min(rise, sink)

    @property
    def held(self) -> list[Stickman]:
        return [arm.held for arm in self.arms if arm.held is not None]

    @staticmethod
    def reaches(arm: Tentacle, stickman: Stickman, strength: float = 1.0) -> Vec2 | None:
        """The nearest part of `stickman` within `arm`'s reach (on its side), if any."""
        head = stickman.transforms()[stickman.layout.head].end
        best = None
        for point in (stickman.center(), stickman.contact(), head):
            offset = point - arm.base
            if offset.dot(arm.normal) < -3.0:
                continue
            if offset.length() <= arm.length * strength + 4.0:
                if best is None or offset.length() < (best - arm.base).length():
                    best = point
        return best


@dataclass
class Smite:
    """Divine judgment on a lich who slew a cleric: a sword of light hangs over him,
    plunges onto him and dissolves. `x`, `top` and `impact` follow him until it falls."""

    lich: object
    wait: float
    age: float = 0.0
    x: float = 0.0
    top: float = 0.0
    impact: float = 0.0
    struck: bool = False
    fizzled: float = -1.0
    """Seconds since it began fading harmlessly (his death), or -1."""

    @property
    def drop(self) -> float:
        """0 hanging over him -> 1 driven home."""
        u = min(1.0, max(0.0, (self.age - SMITE_HANG) / SMITE_DROP))
        return u * u


@dataclass
class Rising:
    body: Stickman
    wait: float = RISE_DELAY


@dataclass
class Cloudkill:
    center: Vec2
    caster: object
    age: float = 0.0
    ticks: int = 0

    @property
    def strength(self) -> float:
        grow = min(1.0, self.age / CLOUD_SUMMON_TIME)
        fade = min(1.0, max(0.0, (CLOUD_DURATION - self.age) / 0.8))
        return grow * grow * (3.0 - 2.0 * grow) * fade


class Necromancy:
    def __init__(self, world) -> None:
        self.world = world
        self.fireballs: list[Fireball] = []
        self.blasts: list[Blast] = []
        self.scorches: list[Scorch] = []
        self.words: list[Word] = []
        self.wisps: list[Wisp] = []
        self.darts: list[Dart] = []
        self.arcs: list[Arc] = []
        self.tentacles: list[Tentacles] = []
        self.cloudkills: list[Cloudkill] = []
        self.risings: list[Rising] = []
        self.smites: list[Smite] = []
        self.smitten = 0
        tracked = (*SPELLS, "cloudkill")
        self.hits: dict[str, int] = {spell: 0 for spell in tracked}
        self.kills: dict[str, int] = {spell: 0 for spell in tracked}
        self.raised = 0

    @property
    def random(self):
        return self.world.random

    def _prey(self) -> list[Stickman]:
        return [s for s in self.world.stickmen if s.prey]

    # ----- casting ------------------------------------------------------------------

    def cast(self, spell: str, caster: object, origin: Vec2, foe: Stickman) -> None:
        if not foe.prey:
            return
        getattr(self, f"_cast_{spell}")(caster, origin, foe)

    def _cast_fireball(self, caster: object, origin: Vec2, foe: Stickman) -> None:
        aim = foe.center() + foe.velocity * 0.3
        time = max(0.45, min(1.1, abs(aim.x - origin.x) / FIREBALL_PACE))
        offset = aim - origin
        velocity = Vec2(offset.x / time, (offset.y - 0.5 * FIREBALL_GRAVITY * time * time) / time)
        self.fireballs.append(Fireball(origin, velocity, time, caster=caster))

    def _cast_power_word_kill(self, caster: object, origin: Vec2, foe: Stickman) -> None:
        self.words.append(Word(foe, caster))

    def _cast_magic_missiles(self, caster: object, origin: Vec2, foe: Stickman) -> None:
        center = foe.center()
        others = sorted(
            (s for s in self._prey() if s is not foe),
            key=lambda s: s.center().distance_to(center),
        )
        others = [s for s in others if s.center().distance_to(center) <= MISSILE_SPREAD]
        targets = [foe] * MISSILES_AT_FOE
        for i in range(MISSILES - MISSILES_AT_FOE):
            targets.append(others[i % len(others)] if others else foe)
        side = 1.0 if center.x >= origin.x else -1.0
        for i, target in enumerate(targets):
            fan = -1.25 + 1.6 * i / (MISSILES - 1)
            heading = Vec2(side * math.cos(fan), math.sin(fan))
            velocity = heading * (MISSILE_SPEED * (0.75 + 0.1 * (i % 3)))
            self.darts.append(
                Dart(origin, velocity, target, delay=i * MISSILE_STAGGER, caster=caster)
            )

    def _cast_chain_lightning(self, caster: object, origin: Vec2, foe: Stickman) -> None:
        chain = [foe]
        prey = self._prey()
        while len(chain) <= CHAIN_HOPS:
            last = chain[-1].center()
            near = [
                s for s in prey if s not in chain and s.center().distance_to(last) <= CHAIN_REACH
            ]
            if not near:
                break
            chain.append(min(near, key=lambda s: s.center().distance_to(last)))
        start = origin
        for i, target in enumerate(chain):
            end = target.center()
            damage = CHAIN_DAMAGE[min(i, len(CHAIN_DAMAGE) - 1)]
            seed = self.random.randrange(1 << 20)
            self.arcs.append(Arc(start, end, target, damage, i * CHAIN_STEP, seed, caster=caster))
            start = end

    def _cast_black_tentacles(self, caster: object, origin: Vec2, foe: Stickman) -> None:
        target = foe.center()
        rng = self.random
        arms = []
        for start, end, normal, box in self._faces():
            span = end - start
            length = span.length()
            if length < 1.0:
                continue
            count = int(length // TENTACLE_SPACING) + 1
            offset = rng.uniform(0.0, TENTACLE_SPACING)
            for k in range(count):
                along = min(length, offset + k * TENTACLE_SPACING)
                base = start + span * (along / length)
                if base.distance_to(target) > TENTACLE_RANGE or self._buried(base, normal, box):
                    continue
                arms.append(
                    Tentacle(
                        base,
                        normal,
                        box,
                        rng.uniform(*TENTACLE_LENGTH),
                        rng.uniform(0.0, 2.0 * math.pi),
                        base,
                    )
                )
        arms.sort(key=lambda arm: arm.base.distance_to(target))
        if arms:
            self.tentacles.append(
                Tentacles(arms[:TENTACLE_CAP], rng.randrange(1 << 20), caster=caster)
            )

    def _cast_cloudkill(self, caster: object, origin: Vec2, foe: Stickman) -> None:
        self.cloudkills.append(Cloudkill(foe.center(), caster))

    def _faces(self) -> list[tuple[Vec2, Vec2, Vec2, int | None]]:
        """Every face tentacles can grow from: (start, end, outward normal, box)."""
        return tentacle_faces(self.world)

    def _buried(self, base: Vec2, normal: Vec2, box: int | None) -> bool:
        """Whether a tentacle at `base` would grow straight into another window."""
        return tentacle_buried(self.world, base, normal, box)

    # ----- landing --------------------------------------------------------------------

    def _strike(
        self,
        spell: str,
        stickman: Stickman,
        amount: int,
        point: Vec2,
        push: Vec2,
        death: str,
        caster: object = None,
    ) -> bool:
        if not stickman.prey or stickman not in self.world.stickmen:
            return False
        self.hits[spell] += 1
        killed = stickman.hurt(amount, point, push, SOURCE, death)
        if killed:
            self.kills[spell] += 1
            self.risings.append(Rising(stickman))
            if stickman.variant in ("cleric", "hero_cleric") and caster is not None:
                self.smite(caster)
        return killed

    def smite(self, lich: object) -> None:
        """A cleric's god answers: a sword of light for `lich`, after any already due."""
        due = [m.wait for m in self.smites if m.lich is lich and not m.struck]
        wait = max(due) + SMITE_STAGGER if due else 0.0
        self.smites.append(Smite(lich, wait))

    def _update_smites(self, dt: float) -> None:
        world = self.world
        kept = []
        for smite in self.smites:
            lich = smite.lich
            alive = not getattr(lich, "dead", False) and lich in world.liches
            if smite.fizzled >= 0.0 or (not alive and not smite.struck):
                smite.fizzled = max(0.0, smite.fizzled) + dt
                if smite.fizzled < SMITE_FADE and smite.age > 0.0:
                    kept.append(smite)
                continue
            if smite.wait > 0.0:
                smite.wait -= dt
                kept.append(smite)
                continue
            if not smite.struck and (getattr(lich, "door", None) is not None or lich.phased):
                kept.append(smite)
                continue
            smite.age += dt
            if not smite.struck:
                center = lich.center()
                ceiling = world.ceiling if world.ceiling is not None else 0.0
                smite.x = center.x
                smite.impact = center.y
                smite.top = max(ceiling + 10.0, center.y - SMITE_HEIGHT)
                if smite.age >= SMITE_HANG + SMITE_DROP:
                    smite.struck = True
                    self.smitten += 1
                    world.hurt_monster(lich, SMITE_DAMAGE, center, Vec2(0.0, 60.0))
            if smite.age < SMITE_HANG + SMITE_DROP + SMITE_LINGER:
                kept.append(smite)
        self.smites = kept

    def update(self, dt: float) -> None:
        self._update_risings(dt)
        self._update_smites(dt)
        self._update_fireballs(dt)
        self._update_words(dt)
        self._update_darts(dt)
        self._update_arcs(dt)
        self._update_tentacles(dt)
        self._update_cloudkills(dt)
        for blast in self.blasts:
            blast.age += dt
        self.blasts = [b for b in self.blasts if b.age < BLAST_TIME]
        for scorch in self.scorches:
            scorch.age += dt
        self.scorches = [s for s in self.scorches if s.age < SCORCH_TIME]
        for wisp in self.wisps:
            wisp.age += dt
            flame = getattr(wisp.caster, "flame_point", None)
            if flame is not None:
                wisp.end = flame()
        self.wisps = [w for w in self.wisps if w.age < WISP_TIME]

    def _update_risings(self, dt: float) -> None:
        waiting = []
        for rising in self.risings:
            rising.wait -= dt
            if rising.wait > 0.0:
                waiting.append(rising)
            elif self.world.raise_skeleton(rising.body) is not None:
                self.raised += 1
        self.risings = waiting

    def _update_fireballs(self, dt: float) -> None:
        floor = self.world.floor_y
        flying = []
        for ball in self.fireballs:
            ball.age += dt
            ball.velocity = ball.velocity + Vec2(0.0, FIREBALL_GRAVITY * dt)
            ball.position = ball.position + ball.velocity * dt
            hit = any(s.prey and s.hits(ball.position, 2.0) for s in self.world.stickmen)
            if hit or ball.age >= ball.time or ball.position.y >= floor:
                self._burst(Vec2(ball.position.x, min(ball.position.y, floor - 2.0)), ball.caster)
            else:
                flying.append(ball)
        self.fireballs = flying

    def _burst(self, center: Vec2, caster: object = None) -> None:
        self.blasts.append(Blast(center))
        for stickman in self._prey():
            body = stickman.center()
            if body.distance_to(center) > FIREBALL_RADIUS:
                continue
            away = (body - center).normalized() if body.distance_to(center) > 1 else Vec2(0, -1)
            push = away * FIREBALL_PUSH + Vec2(0.0, -160.0)
            damage = 2 if getattr(caster, "legendary_mage", False) else FIREBALL_DAMAGE
            self._strike(
                "fireball",
                stickman,
                damage,
                body,
                push,
                "Burned up by a fireball!",
                caster,
            )
        ground = self._ground_under(center)
        if ground is not None:
            self.scorches.append(Scorch(*ground))

    def _ground_under(self, point: Vec2) -> tuple[Vec2, int | None] | None:
        """The floor or window top just under `point` (within reach of the blast)."""
        best: tuple[Vec2, int | None] | None = None
        if self.world.floor_y - point.y <= FIREBALL_RADIUS:
            best = (Vec2(point.x, self.world.floor_y), None)
        for i, rect in enumerate(self.world.boxes):
            if rect.x <= point.x <= rect.x + rect.width and 0 <= rect.y - point.y + 4 <= 40:
                if best is None or rect.y < best[0].y:
                    best = (Vec2(point.x, rect.y), i)
        return best

    def _update_words(self, dt: float) -> None:
        for word in self.words:
            word.age += dt
            if not word.spoken and word.age >= WORD_DELAY:
                word.spoken = True
                target = word.target
                if target.prey and target in self.world.stickmen:
                    head = target.transforms()[target.layout.head].end
                    amount = max(1, target.hp)
                    self._strike(
                        "power_word_kill",
                        target,
                        amount,
                        head,
                        Vec2(0.0, -40.0),
                        "Slain by a word of power!",
                        word.caster,
                    )
                    self.wisps.append(Wisp(head, word.caster, end=head))
        self.words = [w for w in self.words if w.age < WORD_TIME]

    def _update_darts(self, dt: float) -> None:
        flying = []
        for dart in self.darts:
            if dart.delay > 0.0:
                dart.delay -= dt
                flying.append(dart)
                continue
            dart.age += dt
            target = dart.target
            if not target.prey or target not in self.world.stickmen:
                others = self._prey()
                if not others:
                    continue
                target = dart.target = min(
                    others, key=lambda s: s.center().distance_to(dart.position)
                )
            aim = target.center() - dart.position
            speed = MISSILE_SPEED
            want = aim.normalized() * speed
            blend = min(1.0, MISSILE_TURN * dt * (0.02 + dart.age * 1.6))
            dart.velocity = dart.velocity + (want - dart.velocity) * blend
            dart.trail.append(dart.position)
            del dart.trail[:-6]
            dart.position = dart.position + dart.velocity * dt
            if target.hits(dart.position, 2.0) or aim.length() < 5.0:
                push = dart.velocity.normalized() * 90.0
                self._strike(
                    "magic_missiles",
                    target,
                    1,
                    dart.position,
                    push,
                    "Riddled with magic missiles!",
                    dart.caster,
                )
                continue
            if dart.age < MISSILE_LIFE:
                flying.append(dart)
        self.darts = flying

    def _update_arcs(self, dt: float) -> None:
        for arc in self.arcs:
            if arc.delay > 0.0:
                arc.delay -= dt
                continue
            if not arc.struck:
                arc.struck = True
                if arc.target.prey and arc.target in self.world.stickmen:
                    arc.end = arc.target.center()
                    push = (arc.end - arc.start).normalized() * 120.0
                    damage = 2 if getattr(arc.caster, "legendary_mage", False) else arc.damage
                    killed = self._strike(
                        "chain_lightning",
                        arc.target,
                        damage,
                        arc.end,
                        push,
                        "Fried by chain lightning!",
                        arc.caster,
                    )
                    if not killed:
                        arc.target.paralyze(CHAIN_STUN)
            arc.age += dt
        self.arcs = [a for a in self.arcs if a.age < ARC_TIME]

    def _update_tentacles(self, dt: float) -> None:
        prey = self._prey()
        for spell in self.tentacles:
            spell.age += dt
            strength = spell.strength
            ending = spell.age >= TENTACLE_TIME - TENTACLE_GROW
            for arm in spell.arms:
                if arm.held is not None and (
                    ending or not arm.held.prey or arm.held not in self.world.stickmen
                ):
                    arm.held = None
            gripped = {id(s) for s in spell.held}
            if not ending:
                for arm in spell.arms:
                    if arm.held is not None:
                        continue
                    for stickman in prey:
                        if id(stickman) not in gripped and spell.reaches(arm, stickman, strength):
                            arm.held = stickman
                            gripped.add(id(stickman))
                            break
            for arm in spell.arms:
                self._writhe(arm, spell, strength, dt)
            for stickman in spell.held:
                stickman.paralyze(0.25)
            spell.crush -= dt
            if spell.crush <= 0.0:
                spell.crush += TENTACLE_CRUSH
                for stickman in spell.held:
                    self._strike(
                        "black_tentacles",
                        stickman,
                        TENTACLE_DAMAGE,
                        stickman.center(),
                        Vec2(0.0, 0.0),
                        "Crushed by black tentacles!",
                        spell.caster,
                    )
        self.tentacles = [t for t in self.tentacles if t.age < TENTACLE_TIME and t.arms]

    def _update_cloudkills(self, dt: float) -> None:
        for cloud in self.cloudkills:
            previous = cloud.age
            cloud.age = min(CLOUD_DURATION, cloud.age + dt)
            active = max(0.0, cloud.age - CLOUD_SUMMON_TIME)
            previous_active = max(0.0, previous - CLOUD_SUMMON_TIME)
            due = int((active + 1e-9) / CLOUD_HIT_INTERVAL)
            previous_due = int((previous_active + 1e-9) / CLOUD_HIT_INTERVAL)
            for _ in range(max(0, due - max(cloud.ticks, previous_due))):
                for stickman in self._prey():
                    point = stickman.center()
                    if point.distance_to(cloud.center) > CLOUD_RADIUS:
                        continue
                    if any(box.contains(point) for box in self.world.boxes):
                        continue
                    away = (point - cloud.center).normalized()
                    self._strike(
                        "cloudkill",
                        stickman,
                        CLOUD_DAMAGE,
                        point,
                        away * 10.0 + Vec2(0.0, -8.0),
                        "Choked by an archlich's cloudkill!",
                        cloud.caster,
                    )
                cloud.ticks += 1
        self.cloudkills = [cloud for cloud in self.cloudkills if cloud.age < CLOUD_DURATION]

    def _writhe(self, arm: Tentacle, spell: Tentacles, strength: float, dt: float) -> None:
        """Move the tip: onto what it holds, else reaching out along its normal and
        swaying, or curling toward anyone gripped close by."""
        side = Vec2(-arm.normal.y, arm.normal.x)
        t = spell.age
        if arm.held is not None:
            want = arm.held.center()
            offset = want - arm.base
            if offset.length() > arm.length:
                want = arm.base + offset.normalized() * arm.length
        else:
            sway = math.sin(t * 3.1 + arm.phase) * 0.35
            reach = arm.length * strength * (0.75 + 0.15 * math.sin(t * 2.3 + arm.phase * 1.7))
            want = arm.base + (arm.normal + side * sway).normalized() * reach
        blend = min(1.0, TENTACLE_FOLLOW * dt)
        arm.tip = arm.tip + (want - arm.tip) * blend

    # ----- the ground shifting ------------------------------------------------------------

    def terrain_changed(self, change: TerrainChange) -> None:
        kept = []
        for spell in self.tentacles:
            arms = []
            for arm in spell.arms:
                if arm.box is not None:
                    index = change.new_index(arm.box)
                    if index is None:
                        continue
                    delta = change.delta_for(arm.box)
                    arm.box = index
                    if delta is not None:
                        arm.base = arm.base + delta
                        arm.tip = arm.tip + delta
                arms.append(arm)
            spell.arms = arms
            if arms:
                kept.append(spell)
        self.tentacles = kept
        scorched = []
        for scorch in self.scorches:
            if scorch.box is not None:
                delta = change.delta_for(scorch.box)
                index = change.new_index(scorch.box)
                if index is None:
                    continue
                scorch.box = index
                if delta is not None:
                    scorch.point = scorch.point + delta
            scorched.append(scorch)
        self.scorches = scorched
