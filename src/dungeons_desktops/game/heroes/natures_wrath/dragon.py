"""The real dragon AI, adapted to hunt defenders during a timed hero transformation."""

from __future__ import annotations

from enum import Enum
from types import SimpleNamespace
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.actors.base import _distance_to_segment
from dungeons_desktops.game.adventurers.actor import DRAGON_DAMAGE
from dungeons_desktops.game.defenders.dragon.actor import (
    FIRE_BURST,
    FLY_SPEED,
    HIP_HEIGHT,
    Dragon,
    DragonMode,
)
from dungeons_desktops.game.effects.flames import burn_hits, step_flames
from dungeons_desktops.rig.locomotion import PoseMode

if TYPE_CHECKING:
    from dungeons_desktops.game.heroes.natures_wrath.actor import NaturesWrath

MAGMA_SIZE = 1.12
STRAFE_SECONDS = 6.0
NORMAL_SECONDS = 10.0


class DragonPhase(Enum):
    FIRST_STRAFE = "first_strafe"
    NORMAL = "normal"
    LAST_STRAFE = "last_strafe"


class DefenderPrey:
    """Present a live defender to the dragon's existing prey-selection and movement code."""

    def __init__(self, view: DefenderWorld, monster: object) -> None:
        self.view = view
        self.monster = monster
        self.last = view.real.closest_part(monster, view.hero.center()) or view.hero.center()

    @property
    def prey(self) -> bool:
        return self.view.hero.blind <= 0 and self.view.real.locate(self.monster) is not None

    def center(self) -> Vec2:
        self.last = self.view.real.closest_part(self.monster, self.last) or self.last
        return self.last

    def contact(self) -> Vec2:
        contact = getattr(self.monster, "contact", None)
        if contact is not None:
            return contact()
        support = getattr(self.monster, "support", None) or getattr(self.monster, "surface", None)
        center = self.center()
        return (
            Vec2(center.x, support.start.y) if support is not None and support.walkable else center
        )

    @property
    def locomotion(self):
        return getattr(self.monster, "locomotion", SimpleNamespace(mode=PoseMode.AIR))

    @property
    def follower(self):
        return self.monster.follower

    def hits(self, point: Vec2, margin: float = 0.0) -> bool:
        hit = getattr(self.monster, "hits", None)
        if hit is not None:
            return hit(point, margin)
        part = self.view.real.closest_part(self.monster, point)
        return part is not None and part.distance_to(point) <= margin + 8.0


class DefenderWorld:
    """Reuse the actual world, substituting defenders for the dragon's prey roster."""

    def __init__(self, hero: NaturesWrath) -> None:
        self.hero = hero
        self.real = hero.world
        self.stickmen: list[DefenderPrey] = []

    def refresh(self) -> None:
        existing = {prey.monster: prey for prey in self.stickmen}
        self.stickmen = [
            existing[monster] if monster in existing else DefenderPrey(self, monster)
            for monster in self.real.monsters()
        ]

    def __getattr__(self, name):
        return getattr(self.real, name)


class MagmaDragon(Dragon):
    """A 6-second strafe, 10 seconds of normal dragon AI, then a final 6-second strafe."""

    def __init__(self, hero: NaturesWrath) -> None:
        self.hero = hero
        view = DefenderWorld(hero)
        super().__init__(
            view,
            hero.contact() - Vec2(0, HIP_HEIGHT * MAGMA_SIZE),
            facing=hero.facing,
            size=MAGMA_SIZE,
            variant="red",
        )
        self.form_phase = DragonPhase.FIRST_STRAFE
        self.phase_elapsed = 0.0
        self.elapsed = 0.0
        self.finished = False
        self._hit_grace: dict[object, float] = {}
        view.refresh()
        self._begin_strafe()

    def _begin_strafe(self) -> None:
        self._set_mode(DragonMode.FLY)
        self.support = None
        self.landing = None
        target = self._spot_prey()
        if target is not None:
            self._turn(1 if target.center().x >= self.body.x else -1)
        self.velocity = Vec2(self.facing * FLY_SPEED, -30)
        self.flight_timer = STRAFE_SECONDS + 1
        self.fire_cooldown = 0.0
        self.fire_target = self._in_fire_range()
        self.fire_time = FIRE_BURST if self.fire_target is not None else 0.0
        self._pose(0.0, snap=True)

    def update(self, dt: float, paused: bool = False) -> None:
        self.world.refresh()
        self._hit_grace = {
            target: time - dt for target, time in self._hit_grace.items() if time > dt
        }
        remaining = dt
        while remaining > 1e-9 and not self.finished:
            duration = NORMAL_SECONDS if self.form_phase is DragonPhase.NORMAL else STRAFE_SECONDS
            step = min(remaining, duration - self.phase_elapsed)
            if paused:
                self._update_flames(step)
            else:
                if self.form_phase is not DragonPhase.NORMAL:
                    self.flight_timer = duration - self.phase_elapsed + 1
                super().update(step)
            self.elapsed += step
            self.phase_elapsed += step
            remaining -= step
            if self.phase_elapsed >= duration - 1e-9:
                self.phase_elapsed = 0.0
                if self.form_phase is DragonPhase.FIRST_STRAFE:
                    self.form_phase = DragonPhase.NORMAL
                    self.fire_time = 0.0
                    self.flight_timer = 0.0
                    self._start_landing()
                elif self.form_phase is DragonPhase.NORMAL:
                    self.form_phase = DragonPhase.LAST_STRAFE
                    self._begin_strafe()
                else:
                    self.finished = True

    def _hit(self, target: DefenderPrey, push: Vec2, death: str, bleed: bool = True) -> bool:
        if not target.prey or target.monster in self._hit_grace:
            return False
        self._hit_grace[target.monster] = 1.0
        killed = self.world.real.hurt_monster(
            target.monster,
            DRAGON_DAMAGE,
            target.center(),
            push,
            ranged=self.flying,
            attacker=self.hero,
        )
        self.catches += killed
        return killed

    def _update_flames(self, dt: float) -> None:
        self.flames, _ = step_flames(self.flames, dt, self.world.floor_y)
        for target, flame in burn_hits(self.flames, self.world.stickmen):
            self._hit(target, flame.velocity.normalized() * 200 + Vec2(0, -120), "", False)

    def contact(self) -> Vec2:
        if self.support is not None and not self.flying:
            return Vec2(self.body.x, self.support.start.y)
        return self.body + Vec2(0, HIP_HEIGHT * self.size)

    def hits(self, point: Vec2, margin: float = 0.0) -> bool:
        if _distance_to_segment(point, self.hip, self.shoulder) <= 8 * self.size + margin:
            return True
        if _distance_to_segment(point, self.neck_base, self.head) <= 5 * self.size + margin:
            return True
        if point.distance_to(self.head) <= 9 * self.size + margin:
            return True
        return any(
            _distance_to_segment(point, leg.root, leg.foot) <= 4 * self.size + margin
            for leg in self.legs
        )
