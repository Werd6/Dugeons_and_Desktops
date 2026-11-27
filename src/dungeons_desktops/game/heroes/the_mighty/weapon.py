"""A longer, thicker war axe with a broad, weighty crescent head."""

from dataclasses import replace

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.heroes.the_mighty.combat import Attack
from dungeons_desktops.rig.equipment import Axe, Key, Stroke
from dungeons_desktops.rig.locomotion import PoseMode
from dungeons_desktops.rig.skeleton import BoneTransform, Pose


class HeavyAxe(Axe):
    name = "heavy war axe"
    size = Axe.size * 1.3

    def __init__(self, layout) -> None:
        super().__init__(layout)
        self.action = Attack.MELEE

    def start_action(self, action: Attack, duration: float | None = None) -> bool:
        if self.busy:
            return False
        self.action = action
        self.duration = duration or (1.2 if action is Attack.BOULDER else 1.1)
        self.hit_time = None if action is Attack.LEAP else 0.55
        self.WINDUP = Key(0.4, Vec2(-0.35, -1.1), -2.15, torso=-0.3)
        self.STRIKE = Key(0.55, Vec2(0.75, -0.8), 0.8, torso=0.35, head=0.15)
        self.FOLLOW = Key(0.72, Vec2(0.65, -0.65), 0.8, torso=0.35)
        self.trail_window = (0.38, 0.72)
        self.held_modes = frozenset({PoseMode.WALK, PoseMode.AIR})
        if action is Attack.MELEE:
            self.duration, self.hit_time = Axe.duration, Axe.hit_time
            self.WINDUP, self.STRIKE, self.FOLLOW = Axe.WINDUP, Axe.STRIKE, Axe.FOLLOW
            self.trail_window = Axe.trail_window
            self.held_modes = Axe.held_modes
        elif action is Attack.BOULDER:
            self.WINDUP = Key(0.4, Vec2(-0.5, -1.0), -1.5, torso=-0.25)
            self.STRIKE = Key(0.57, Vec2(0.95, -0.5), -0.7, torso=0.3)
            self.FOLLOW = Key(0.75, Vec2(0.9, 0.15), 0.0, torso=0.2)
        return super().start()

    def _hold(self, pose: Pose, skip: frozenset[str]) -> None:
        super()._hold(pose, skip)
        if self.busy and self.action is Attack.LEAP:
            self.angle = -2.2 if self.time < self.duration - 0.4 else 0.8
            shoulder = self._shoulder(pose)
            hand = Vec2(-0.25, -1.0) if self.time < self.duration - 0.4 else Vec2(0.75, -0.8)
            self._solve(pose, {self.hand_chain.name: shoulder + hand * self.arm_length}, skip)

    @property
    def trail_active(self) -> bool:
        return self.action is not Attack.BOULDER and super().trail_active

    def strokes(self, transforms, facing, slung=False) -> list[Stroke]:
        return super().strokes(
            transforms, facing, slung or (self.busy and self.action is Attack.BOULDER)
        )

    def _head(self, top: Vec2, along: Vec2, out: Vec2) -> list[Stroke]:
        socket = top - along * (2.5 * self.unit)

        def broaden(point: Vec2) -> Vec2:
            offset = point - socket
            return socket + along * (offset.dot(along) * 1.2) + out * (offset.dot(out) * 1.4)

        return [
            replace(
                stroke,
                start=broaden(stroke.start),
                end=broaden(stroke.end),
                width=stroke.width * 1.35,
                shape=tuple(broaden(point) for point in stroke.shape),
            )
            for stroke in super()._head(top, along, out)
        ]

    def _held(self, grip: Vec2, direction: Vec2, facing: int) -> list[Stroke]:
        return self._thicken_haft(super()._held(grip, direction, facing))

    def _slung(self, transforms: dict[str, BoneTransform], facing: int) -> list[Stroke]:
        return self._thicken_haft(super()._slung(transforms, facing))

    @staticmethod
    def _thicken_haft(strokes: list[Stroke]) -> list[Stroke]:
        return [
            replace(stroke, width=stroke.width * 1.4) if stroke.kind == "wood" else stroke
            for stroke in strokes
        ]
