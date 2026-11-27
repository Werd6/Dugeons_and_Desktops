"""The paladin's familiar blue-and-gold shield, extended into a tower shield."""

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.rig.biped import BipedLayout
from dungeons_desktops.rig.equipment import HammerAndShield, Key, Stroke, _sample
from dungeons_desktops.rig.skeleton import Pose

THROW_RELEASE = 0.28


class TowerHammerAndShield(HammerAndShield):
    name = "warhammer and tower shield"
    GUARD = Vec2(0.7, 0.32)
    REST_ANGLE = -0.65
    THROW = (
        Key(0, Vec2(0.42, 0.55), REST_ANGLE),
        Key(0.16, Vec2(-0.45, -0.75), -2.5, torso=-0.18),
        Key(THROW_RELEASE, Vec2(0.95, -0.15), -0.15, torso=0.22),
        Key(0.55, Vec2(0.42, 0.55), REST_ANGLE),
    )

    def __init__(self, layout: BipedLayout) -> None:
        super().__init__(layout)
        self.hand_chain, self.support_chain = layout.arms[0], layout.arms[1]
        self.throwing = False
        self.hammer_away = False

    @property
    def busy(self) -> bool:
        return self.hammer_away or super().busy

    @property
    def stops_movement(self) -> bool:
        return self.throwing

    @property
    def trail_active(self) -> bool:
        return not self.throwing and not self.hammer_away and super().trail_active

    def _rest(self, pose: Pose) -> Key:
        return Key(0.0, Vec2(0.42, 0.55), self.REST_ANGLE)

    def _hold(self, pose: Pose, skip: frozenset[str]) -> None:
        if self.throwing:
            key = _sample(self.THROW, self.time if self.time is not None else self.duration)
            pose.angles[self.layout.torso] += key.torso
            shoulder = self._shoulder(pose)
            self._solve(pose, {
                self.hand_chain.name: shoulder + key.hand * self.arm_length,
                self.support_chain.name: shoulder + self.GUARD * self.arm_length,
            }, skip)
            self.angle = key.angle
            return
        if self.time is None:
            hand = self._shoulder(pose) + self._rest(pose).hand * self.arm_length
            self._solve(pose, {self.hand_chain.name: hand}, skip)
        super()._hold(pose, skip)

    def _shield(self, center: Vec2) -> list[Stroke]:
        s = self.unit
        width, top, bottom, bevel = 5.1, 4.5, 18.0, 1.1
        corners = (
            (-width + bevel, -top), (width - bevel, -top),
            (width, -top + bevel), (width, bottom - bevel),
            (width - bevel, bottom), (-width + bevel, bottom),
            (-width, bottom - bevel), (-width, -top + bevel),
        )
        middle = (bottom - top) / 2
        rim = tuple(center + Vec2(x, y) * s for x, y in corners)
        face = tuple(
            center + Vec2(x * 0.78, middle + (y - middle) * 0.91) * s
            for x, y in corners
        )
        return [
            Stroke(center, center, 0.6 * s, "hilt", rim),
            Stroke(center, center, 0.2 * s, "shield", face),
            Stroke(
                center + Vec2(0, -top + 2) * s,
                center + Vec2(0, bottom - 2) * s, 1.0 * s, "hilt",
            ),
            Stroke(
                center + Vec2(-3.2, 2.0) * s,
                center + Vec2(3.2, 2.0) * s, 1.0 * s, "hilt",
            ),
        ]
