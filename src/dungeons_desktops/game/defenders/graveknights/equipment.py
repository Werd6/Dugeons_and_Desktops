"""Sword-and-shield equipment for a Graveknight."""

import math

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.rig.equipment import Stroke, Sword, _world_angle
from dungeons_desktops.rig.skeleton import BoneTransform, Pose


class GraveSwordAndShield(Sword):
    """A one-handed longsword with a battered heater shield in the far hand."""

    name = "sword and shield"
    size = 1.35
    GUARD = Vec2(0.52, 0.28)

    def _hold(self, pose: Pose, skip: frozenset[str]) -> None:
        super()._hold(pose, skip)
        shoulder = self._shoulder(pose)
        self._solve(
            pose,
            {self.support_chain.name: shoulder + self.GUARD * self.arm_length},
            skip,
        )

    def strokes(
        self, transforms: dict[str, BoneTransform], facing: int, slung: bool = False
    ) -> list[Stroke]:
        if slung or not self.held:
            sword = super().strokes(transforms, facing, slung=True)
            low, high = self._back_line(transforms, facing, 2.0 * self.unit, 4.0 * self.unit)
            center = low.lerp(high, 0.48) + Vec2(-facing * 1.2 * self.unit, 0.0)
            return [*sword, *self._shield(center)]
        grip = transforms[self.hand_chain.bones[-1]].end
        direction = Vec2.from_angle(_world_angle(self.angle, facing))
        shield_hand = transforms[self.support_chain.bones[-1]].end
        return [
            *self._held(grip, direction, self.swing_facing(facing)),
            *self._shield(shield_hand + Vec2(facing * self.unit, 0.0)),
        ]

    def _shield(self, center: Vec2) -> list[Stroke]:
        s = self.unit
        width, top, side, bottom = 4.3 * s, 4.7 * s, 1.2 * s, 7.1 * s
        outline = (
            Vec2(-width, -top),
            Vec2(width, -top),
            Vec2(width, side),
            Vec2(0.68 * width, side + 0.56 * (bottom - side)),
            Vec2(0.0, bottom),
            Vec2(-0.68 * width, side + 0.56 * (bottom - side)),
            Vec2(-width, side),
        )
        rim = tuple(center + point for point in outline)
        face = tuple(center + point * 0.79 + Vec2(0.0, -0.25 * s) for point in outline)
        boss = tuple(
            center + Vec2.from_angle(index * math.tau / 12, 1.7 * s)
            for index in range(12)
        )
        return [
            Stroke(center, center, 0.7 * s, "grave_trim", rim),
            Stroke(center, center, 0.2 * s, "grave_shield", face),
            Stroke(center, center, 0.4 * s, "grave_boss", boss),
        ]
