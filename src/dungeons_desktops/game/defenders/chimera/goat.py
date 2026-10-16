"""The chimera's goat: its head on its long neck turns on its own, whichever way the
lion is going, to find whoever is near, in front or behind, and breathes a jet of
fire at him: an absurdly strong, dead-straight beam that reaches far past him. Then it
has to wait before it can again.

It turns only so fast (`AIM_RATE`) and only so far from straight up off the back
(`NECK_CONE`), its neck leaning partway after its head. A breath is a short windup
with its jaw dropping, then `FIRE_BURST` of beam swept from one side of its target to
the other (`SWEEP`), then a `FIRE_COOLDOWN`. Whoever its fire kills burns.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, clamp, wrap_angle
from dungeons_desktops.game.effects.flames import Flame, burn_hits, emit, step_flames

if TYPE_CHECKING:
    from dungeons_desktops.game.adventurers.actor import Stickman
    from dungeons_desktops.game.defenders.chimera.actor import Chimera

GOAT_ROOT = Vec2(-1.0, -5.5)
"""Where the goat's neck leaves the back, relative to the body's middle (x forward,
y down)."""
GOAT_HEAD = Vec2(6.0, -17.0)
"""Where the goat's head sits at rest relative to its neck root."""
NECK_LENGTH = GOAT_HEAD.length()
NECK_LEAN = 0.45
"""How far (as a fraction) its neck swings round after the way its head aims."""
MOUTH_REACH = 8.0
"""Its mouth, this far from the middle of its head along its aim."""
REST_AIM = Vec2(1.0, -0.35)
"""The way it looks when it has no one to burn (x forward, y down)."""

FIRE_RANGE = 450.0
"""How far from its head it spots someone to burn (its beam carries farther)."""
NECK_CONE = 2.2
"""How far (radians) from the body's up it can turn its head."""
AIM_RATE = 3.5
BEAM_RATE = 6.0
"""How fast its head turns while it breathes, to hold the sweep on its target."""
WINDUP_TIME = 0.35
WINDUP_LIMIT = 1.2
"""Past `WINDUP_TIME` it holds its breath up to this long more to get its aim on."""
AIMED = 0.12
FIRE_BURST = 1.6
FIRE_COOLDOWN = 10
SWEEP = 0.4
"""How far (radians) either side of its target the beam sweeps."""
FLAME_RATE = 400.0
FLAME_SPEED = 1100.0
FLAME_SPREAD = 0.015
FLAME_SIZE = 1.7
FLAME_DRAG = 0.6
"""Much less than the dragon's flames, so the beam carries about 600 px."""
FIRE_PUSH = 350.0
FIRE_SOURCE = "chimera's fire"
FIRE_DEATH = "Burned by the chimera's goat!"
FACING_DEADBAND = 0.15


class Fire(Enum):
    READY = "ready"
    WINDUP = "windup"
    BREATHE = "breathe"
    COOLDOWN = "cooldown"


class GoatHead:
    """Where the goat aims (a world direction) and the fire it has breathed."""

    def __init__(self) -> None:
        self.state = Fire.READY
        self.timer = 0.0
        self.target: Stickman | None = None
        self.aim: Vec2 | None = None
        self.facing = 1
        """Which way its head is drawn: +1 when it aims along its body's +1 heading
        direction (see `chimera_lion.along`), -1 against."""
        self.flames: list[Flame] = []
        self.jaw = 0.0
        self.catches = 0
        self.sweep = 1
        """Which side of its target this breath's sweep starts on."""
        self.focus = Vec2(0.0, 0.0)
        """Where its target was last: a breath sweeps on round it to the end even if he
        burns up (or gets away) partway through."""
        self._due = 0.0

    @property
    def breathing(self) -> bool:
        return self.state is Fire.BREATHE

    def neck(self, chimera: Chimera) -> Vec2:
        """The way its neck leans: from its rest partway round toward its aim."""
        rest = chimera.local(GOAT_HEAD).normalized()
        aim = self.aim if self.aim is not None else rest
        turn = wrap_angle(aim.angle() - chimera.local(REST_AIM).angle())
        return rest.rotated(turn * NECK_LEAN)

    def mouth(self, chimera: Chimera) -> Vec2:
        aim = self.aim if self.aim is not None else chimera.forward
        return chimera.goat_head + aim * MOUTH_REACH

    def update(self, dt: float, chimera: Chimera) -> None:
        up = chimera.up
        sway = 0.12 * math.sin(chimera.clock * 0.9) + 0.05 * math.sin(chimera.clock * 2.3)
        rest = chimera.local(REST_AIM).normalized().rotated(sway * chimera.facing)
        if self.aim is None:
            self.aim = rest
        self.timer -= dt
        if self.state is Fire.COOLDOWN and self.timer <= 0.0:
            self.state = Fire.READY
        if self.state is Fire.READY:
            self.target = self._spot(chimera)
            if self.target is not None:
                self.state, self.timer = Fire.WINDUP, WINDUP_TIME
                self.sweep = 1 if chimera.world.random.random() < 0.5 else -1
        elif self.state is Fire.WINDUP and not self._fair(chimera, self.target, 1.2):
            self.state, self.target = Fire.READY, None
        elif self.state is Fire.BREATHE and not self._fair(chimera, self.target, 1.2):
            self.target = None
        elif self.state is Fire.COOLDOWN:
            self.target = None
        if self.target is not None:
            self.focus = self.target.center()

        desired = rest
        if self.state in (Fire.WINDUP, Fire.BREATHE):
            way = (self.focus - chimera.goat_head).normalized()
            desired = way.rotated(self._sweep_offset())
        rate = BEAM_RATE if self.state is Fire.BREATHE else AIM_RATE
        off, want = _off(up, self.aim), _off(up, desired)
        off += clamp(want - off, -rate * dt, rate * dt)
        self.aim = Vec2.from_angle(up.angle() + off)
        if self.state is Fire.WINDUP and self.timer <= 0.0:
            if abs(want - off) < AIMED or self.timer <= -WINDUP_LIMIT:
                self.state, self.timer = Fire.BREATHE, FIRE_BURST

        if self.state is Fire.BREATHE:
            self._due = emit(
                self.flames,
                self._due,
                FLAME_RATE,
                dt,
                self.mouth(chimera),
                self.aim,
                FLAME_SPEED,
                chimera.world.random,
                chimera.prowl.velocity * 0.2,
                FLAME_SPREAD,
                FLAME_SIZE,
            )
            if self.timer <= 0.0:
                self.state, self.timer = Fire.COOLDOWN, FIRE_COOLDOWN
                self.target = None
        opening = {Fire.BREATHE: 1.0, Fire.WINDUP: 0.45}.get(self.state, 0.0)
        self.jaw += (opening - self.jaw) * min(1.0, dt * 12.0)
        self._face(chimera)
        self.step_flames(dt, chimera)

    def step_flames(self, dt: float, chimera: Chimera) -> None:
        """Move its flames and burn whoever they touch (they outlast it)."""
        if not self.flames:
            return
        from dungeons_desktops.game.adventurers.actor import CHIMERA_FIRE_DAMAGE

        world = chimera.world
        self.flames, _ = step_flames(self.flames, dt, world.floor_y, FLAME_DRAG, skid=True)
        for stickman, flame in burn_hits(self.flames, world.stickmen):
            push = flame.velocity.normalized() * FIRE_PUSH + Vec2(0.0, -120.0)
            middle = stickman.center()
            if stickman.hurt_from(
                chimera,
                CHIMERA_FIRE_DAMAGE,
                middle,
                push,
                FIRE_SOURCE,
                FIRE_DEATH,
                False,
            ):
                stickman.succumb("fire")
                self.catches += 1

    def _sweep_offset(self) -> float:
        """How far off its target it aims: at the start of its sweep through the windup,
        then across to the far side as it breathes."""
        if self.state is Fire.WINDUP:
            return self.sweep * SWEEP
        if self.state is Fire.BREATHE:
            progress = clamp(1.0 - self.timer / FIRE_BURST, 0.0, 1.0)
            return self.sweep * SWEEP * math.cos(math.pi * progress)
        return 0.0

    def reflect(self, mirror: Vec2) -> None:
        """Swung round with the body: its aim mirrored across the plane with normal
        `mirror`."""
        if self.aim is not None:
            self.aim = self.aim - mirror * (2.0 * self.aim.dot(mirror))

    def _spot(self, chimera: Chimera) -> Stickman | None:
        best, best_distance = None, math.inf
        for stickman in chimera.world.stickmen:
            if not self._fair(chimera, stickman):
                continue
            distance = stickman.center().distance_to(chimera.goat_head)
            if distance < best_distance:
                best, best_distance = stickman, distance
        return best

    def _fair(self, chimera: Chimera, stickman: Stickman | None, slack: float = 1.0) -> bool:
        """`stickman` is fair game, in range of its head and within its neck's turn."""
        if stickman is None or not stickman.prey:
            return False
        offset = stickman.center() - chimera.goat_head
        if offset.length() > FIRE_RANGE * slack:
            return False
        return abs(wrap_angle(offset.angle() - chimera.up.angle())) <= NECK_CONE * slack

    def _face(self, chimera: Chimera) -> None:
        if self.aim is None:
            return
        side = self.aim.dot(chimera.forward * chimera.facing)
        if abs(side) > FACING_DEADBAND:
            self.facing = 1 if side > 0 else -1


def _off(up: Vec2, way: Vec2) -> float:
    """How far `way` is turned from `up`, held inside the neck's cone. The head turns
    between two of these, so always over its back, never down through its body."""
    return clamp(wrap_angle(way.angle() - up.angle()), -NECK_CONE, NECK_CONE)
