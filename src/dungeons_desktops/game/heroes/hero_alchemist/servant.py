"""A thrown, monster-hunting ooze servant that grows when enemies hurt it."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.game.adventurers.actor import Stickman
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.rig.locomotion import LocomotionInput, PoseMode

if TYPE_CHECKING:
    from dungeons_desktops.game.heroes.hero_alchemist.actor import HeroAlchemist

SUMMON_COOLDOWN = 20.0
SUMMON_RANGE = 520.0
CAST_TIME = 0.55
CAST_RELEASE = 0.24
TOSS_TIME = 0.62
TOSS_DISTANCE = 48.0
BASE_WIDTH = 17.0
BASE_HEIGHT = 20.0
MOVE_SPEED = 10.0
TENDRIL_REACH = 115.0
TENDRIL_DAMAGE = 2
TENDRIL_COUNT = 3
ATTACK_WINDUP = 0.3
ATTACK_HIT = 0.46
ATTACK_TIME = 0.78
ATTACK_COOLDOWN = 1.1
GROWTH_PER_DAMAGE = 0.09
MAX_SCALE = 3.0
OOZE_LIFETIME = 12.0


@dataclass
class OozeToss:
    start: Vec2
    end: Vec2
    facing: int
    age: float = 0.0

    @property
    def progress(self) -> float:
        return clamp(self.age / TOSS_TIME, 0.0, 1.0)

    @property
    def position(self) -> Vec2:
        progress = self.progress
        return self.start.lerp(self.end, progress) + Vec2(
            0.0,
            -28.0 * math.sin(math.pi * progress),
        )

    def update(self, dt: float) -> bool:
        self.age += dt
        return self.age >= TOSS_TIME


class AlchemicalOoze(Stickman):
    """A priority decoy whose incoming damage becomes additional body mass."""

    display_name = "Alchemical Ooze"
    is_alchemical_ooze = True
    target_priority = 3

    def __init__(self, owner: HeroAlchemist, anchor: Anchor) -> None:
        self.owner = owner
        self._feet = anchor.point
        self._surface = anchor.surface
        self._facing = owner.facing
        super().__init__(owner.world, anchor, "unarmed", wander=False)
        self.age = 0.0
        self.wave = 0.0
        self.absorbed = 0.0
        self.ooze_scale = 1.0
        self.target_scale = 1.0
        self.grow_flash = 0.0
        self.attack_wait = 0.25
        self.attack_time: float | None = None
        self.attack_targets: list[tuple[object, Vec2]] = []
        self.attack_side = 1
        self._struck = False
        self._sync_pose()

    @property
    def prey(self) -> bool:
        return self in self.world.stickmen and not self.swallowed

    @property
    def facing(self) -> int:
        return self._facing

    @property
    def fade(self) -> float:
        return 0.0

    @property
    def limbs_draggable(self) -> bool:
        return False

    @property
    def movement_paused(self) -> bool:
        return True

    def contact(self) -> Vec2:
        return self._feet

    def center(self) -> Vec2:
        return self._feet + Vec2(0.0, -BASE_HEIGHT * self.ooze_scale * 0.44)

    def hits(self, point: Vec2, margin: float = 0.0) -> bool:
        width = BASE_WIDTH * self.ooze_scale + margin
        height = BASE_HEIGHT * self.ooze_scale + margin
        if width <= 0.0 or height <= 0.0:
            return False
        center = self._feet + Vec2(0.0, -height * 0.42)
        offset = point - center
        return (offset.x / width) ** 2 + (offset.y / (height * 0.62)) ** 2 <= 1.0

    def update(self, dt: float) -> None:
        self.age += dt
        if self.age + 1e-9 >= OOZE_LIFETIME:
            self._expire()
            return
        self.wave += dt
        self.grow_flash = max(0.0, self.grow_flash - dt)
        self.attack_wait = max(0.0, self.attack_wait - dt)
        self.ooze_scale += (self.target_scale - self.ooze_scale) * min(1.0, dt * 4.5)
        if self.attack_time is not None:
            self._update_attack(dt)
        else:
            self._hunt(dt)
        self._sync_pose()

    def _expire(self) -> None:
        """Remove the spent summon without leaving a corpse or awarding a kill."""
        self.attack_time = None
        self.attack_targets = []
        self.swallowed = True
        if self.owner.ooze_servant is self:
            self.owner.ooze_servant = None

    def _hunt(self, dt: float) -> None:
        found = self.world.nearest_monster(self.center(), SUMMON_RANGE)
        if found is None:
            return
        target, point = found
        delta = point - self.center()
        if abs(delta.x) > 1.0:
            self._facing = 1 if delta.x > 0.0 else -1
        reach = TENDRIL_REACH * min(1.45, self.ooze_scale)
        if point.distance_to(self.center()) <= reach and self.attack_wait <= 0.0:
            targets = self.world.monsters_near(self.center(), reach)[:TENDRIL_COUNT]
            self._start_attack(targets)
            return
        margin = BASE_WIDTH * self.ooze_scale
        low = self._surface.low + margin
        high = self._surface.high - margin
        if low > high:
            low = high = (self._surface.low + self._surface.high) * 0.5
        step = self._facing * MOVE_SPEED * dt
        x = clamp(self._feet.x + step, low, high)
        self._feet = self._surface.point_at(x)

    def _start_attack(self, targets: list[tuple[object, Vec2]]) -> None:
        self.attack_time = 0.0
        self.attack_targets = targets
        self.attack_side *= -1
        self._struck = False
        self.attack_wait = ATTACK_COOLDOWN

    def _update_attack(self, dt: float) -> None:
        assert self.attack_time is not None
        self.attack_time += dt
        tracked = []
        for target, old_point in self.attack_targets:
            point = self.world.closest_part(target, old_point)
            if point is not None:
                tracked.append((target, point))
        self.attack_targets = tracked
        if not self._struck and self.attack_time >= ATTACK_HIT:
            self._struck = True
            reach = TENDRIL_REACH * min(1.45, self.ooze_scale)
            for target, point in self.attack_targets:
                if point.distance_to(self.center()) > reach + 8.0:
                    continue
                away = (point - self.center()).normalized()
                self.world.hurt_monster(
                    target,
                    TENDRIL_DAMAGE,
                    point,
                    away * 85.0 + Vec2(0.0, -22.0),
                    ranged=False,
                    attacker=self.owner,
                )
        if self.attack_time >= ATTACK_TIME:
            self.attack_time = None
            self.attack_targets = []

    @property
    def tendril_strength(self) -> float:
        if self.attack_time is None:
            return 0.0
        if self.attack_time < ATTACK_WINDUP:
            return smoothstep(self.attack_time / ATTACK_WINDUP)
        return 1.0 - smoothstep(
            clamp((self.attack_time - ATTACK_HIT) / (ATTACK_TIME - ATTACK_HIT), 0.0, 1.0)
        )

    def absorb(self, amount: float) -> None:
        if amount <= 0.0:
            return
        self.absorbed += amount
        self.target_scale = min(MAX_SCALE, 1.0 + self.absorbed * GROWTH_PER_DAMAGE)
        self.grow_flash = 0.35

    def hurt(
        self,
        amount: float,
        point: Vec2,
        push: Vec2,
        source: str,
        death: str,
        bleed: bool = True,
        attacker: object | None = None,
    ) -> bool:
        del point, push, source, death, bleed, attacker
        self.absorb(amount)
        return False

    def ignite(self) -> None:
        self.absorb(3.0)

    def succumb(self, breath: str) -> None:
        del breath
        self.absorb(3.0)

    def enthrall(self) -> None:
        pass

    def paralyze(self, seconds: float) -> None:
        del seconds

    def knock_down(self, center: Vec2, speed: float, down: float, stunned: float) -> None:
        del center, speed, down, stunned

    def engulf(self, ooze: object) -> None:
        del ooze
        self.absorb(1.0)

    def seize(self, mimic: object, flail: object) -> None:
        del mimic, flail
        self.absorb(1.0)

    def go_ragdoll(self) -> None:
        pass

    def weapon_strokes(self) -> list:
        return []

    @property
    def weapon_held(self) -> bool:
        return False

    def terrain_changed(self, change: TerrainChange) -> None:
        del change
        anchor = self.planner.anchor_near(self._feet, walk_only=True)
        if anchor is None:
            return
        self._surface = anchor.surface
        self._feet = anchor.point
        self._sync_pose()

    def _sync_pose(self) -> None:
        self.locomotion.teleport(
            LocomotionInput(PoseMode.WALK, self._feet, self._facing, "alchemical_ooze")
        )
        self.ragdoll.facing = self._facing
        self.ragdoll.engage(self.locomotion.pose, self.world.step)
        self.velocity = Vec2(0.0, 0.0)
        self._last_contact = self._feet
