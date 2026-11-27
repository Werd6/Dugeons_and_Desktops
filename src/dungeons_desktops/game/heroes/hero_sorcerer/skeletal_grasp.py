"""Black Tentacles behavior expressed as grasping skeletal arms."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.defenders.lich.spells import (
    TENTACLE_CRUSH,
    TENTACLE_DAMAGE,
    TENTACLE_FOLLOW,
    TENTACLE_GROW,
    TENTACLE_RANGE,
    TENTACLE_TIME,
    tentacle_buried,
    tentacle_faces,
)
from dungeons_desktops.navigation.terrain import TerrainChange

ARM_SPACING = 24.0
ARM_CAP = 20
ARM_LENGTH = (24.0, 34.0)


@dataclass
class SkeletalArm:
    base: Vec2
    normal: Vec2
    box: int | None
    length: float
    phase: float
    tip: Vec2
    held: object | None = None


@dataclass
class SkeletalGrasp:
    owner: object
    arms: list[SkeletalArm]
    age: float = 0.0
    crush: float = TENTACLE_CRUSH
    seed: int = 0
    held: list[object] = field(default_factory=list)

    @classmethod
    def summon(cls, owner: object, target: Vec2) -> SkeletalGrasp | None:
        world = owner.world
        rng = world.random
        arms = []
        for start, end, normal, box in tentacle_faces(world):
            span = end - start
            length = span.length()
            if length < 1.0:
                continue
            count = int(length // ARM_SPACING) + 1
            offset = rng.uniform(0.0, ARM_SPACING)
            for index in range(count):
                along = min(length, offset + index * ARM_SPACING)
                base = start + span * (along / length)
                if (
                    base.distance_to(target) > TENTACLE_RANGE
                    or tentacle_buried(world, base, normal, box)
                ):
                    continue
                arms.append(
                    SkeletalArm(
                        base,
                        normal,
                        box,
                        rng.uniform(*ARM_LENGTH),
                        rng.uniform(0.0, math.tau),
                        base,
                    )
                )
        arms.sort(key=lambda arm: arm.base.distance_to(target))
        arms = [arm for arm in arms if cls._target_for(world, arm, 1.0) is not None]
        if not arms:
            return None
        return cls(owner, arms[:ARM_CAP], seed=rng.randrange(1 << 20))

    @staticmethod
    def _target_for(world, arm: SkeletalArm, strength: float) -> object | None:
        """Nearest enemy this hand can reach on the exposed side of its surface."""
        for monster, point in world.monsters_near(arm.base, arm.length * strength + 4.0):
            if (point - arm.base).dot(arm.normal) >= -3.0:
                return monster
        return None

    @property
    def strength(self) -> float:
        rise = min(1.0, self.age / TENTACLE_GROW)
        sink = min(1.0, max(0.0, (TENTACLE_TIME - self.age) / TENTACLE_GROW))
        return min(rise, sink)

    @property
    def expired(self) -> bool:
        return self.age >= TENTACLE_TIME or not self.arms

    def holds(self, monster: object) -> bool:
        return any(held is monster for held in self.held)

    def update(self, dt: float) -> None:
        world = self.owner.world
        self.age += dt
        strength = self.strength
        ending = self.age >= TENTACLE_TIME - TENTACLE_GROW
        for arm in self.arms:
            if arm.held is not None and (ending or world.locate(arm.held) is None):
                arm.held = None

        if not ending:
            for arm in self.arms:
                if arm.held is not None:
                    continue
                arm.held = self._target_for(world, arm, strength)

        # Several hands may hold one enemy, but restraint and crush damage apply once.
        held = []
        seen = set()
        for arm in self.arms:
            if arm.held is not None and id(arm.held) not in seen:
                held.append(arm.held)
                seen.add(id(arm.held))
        self.held = held
        for arm in self.arms:
            self._reach(arm, strength, dt)

        self.crush -= dt
        if self.crush <= 0.0:
            self.crush += TENTACLE_CRUSH
            for monster in list(self.held):
                point = world.closest_part(monster, self.owner.center())
                if point is not None:
                    world.hurt_monster(
                        monster,
                        TENTACLE_DAMAGE,
                        point,
                        Vec2(0.0, 0.0),
                        attacker=self.owner,
                    )

    def _reach(self, arm: SkeletalArm, strength: float, dt: float) -> None:
        side = Vec2(-arm.normal.y, arm.normal.x)
        if arm.held is not None:
            want = self.owner.world.closest_part(arm.held, arm.base)
            if want is None:
                arm.held = None
                want = arm.base
            else:
                offset = want - arm.base
                if offset.length() > arm.length:
                    want = arm.base + offset.normalized() * arm.length
        else:
            sway = math.sin(self.age * 3.1 + arm.phase) * 0.28
            reach = arm.length * strength * (
                0.75 + 0.15 * math.sin(self.age * 2.3 + arm.phase * 1.7)
            )
            want = arm.base + (arm.normal + side * sway).normalized() * reach
        blend = min(1.0, TENTACLE_FOLLOW * dt)
        arm.tip += (want - arm.tip) * blend

    def terrain_changed(self, change: TerrainChange) -> None:
        arms = []
        for arm in self.arms:
            if arm.box is not None:
                index = change.new_index(arm.box)
                if index is None:
                    continue
                delta = change.delta_for(arm.box)
                arm.box = index
                if delta is not None:
                    arm.base += delta
                    arm.tip += delta
            arms.append(arm)
        self.arms = arms
