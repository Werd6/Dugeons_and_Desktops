"""Reverse-grip daggers: a low guard, running arm swing, and alternating slashes."""

import math
from collections.abc import Callable

from dungeons_desktops.core.geometry import Vec2, clamp
from dungeons_desktops.rig.biped import BipedLayout
from dungeons_desktops.rig.equipment import Daggers, Key, Stroke, _sample
from dungeons_desktops.rig.skeleton import Pose, forward_kinematics


class SlayerDaggers(Daggers):
    name = "jagged daggers"
    GUARD = 0.18
    STAB = (
        Key(0.0, Vec2(0.32, 0.38), 2.45),
        Key(0.06, Vec2(-0.10, -0.36), 1.35, torso=-0.12),
        Key(0.16, Vec2(0.92, 0.05), 1.0, torso=0.22),
        Key(0.23, Vec2(0.63, 0.5), 1.9, torso=0.12),
        Key(0.3, Vec2(0.32, 0.38), 2.45),
    )
    THROW = (
        Key(0.0, Vec2(0.32, 0.38), 2.45),
        Key(0.12, Vec2(-0.3, -0.65), -1.9, torso=-0.12),
        Key(0.25, Vec2(0.95, -0.2), -0.1, torso=0.25),
        Key(0.5, Vec2(0.32, 0.38), 2.45),
    )

    def __init__(self, layout: BipedLayout) -> None:
        super().__init__(layout)
        self.on_attack: Callable[[], None] | None = None
        self.throwing = False
        self.blade = 10.0 * self.unit
        self.angle = self.off_angle = self.STAB[0].angle

    def start(self) -> bool:
        started = super().start()
        if started and self.on_attack is not None:
            self.on_attack()
        return started

    def _hold(self, pose: Pose, skip: frozenset[str]) -> None:
        if self.throwing:
            key = _sample(self.THROW, self.time or 0.0)
            pose.angles[self.layout.torso] += key.torso
            shoulder = self._shoulder(pose)
            self._solve(pose, {
                self.hand_chain.name: shoulder + key.hand * self.arm_length,
                self.support_chain.name: shoulder + Vec2(0.1, 0.5) * self.arm_length,
            }, skip)
            self.angle, self.off_angle = key.angle, self.STAB[0].angle
            return
        # Read the locomotion arms before posing the guard, keeping the hands'
        # counter-swing synchronized with the feet instead of freezing them.
        walking = forward_kinematics(self.layout.skeleton, pose)
        shoulder = walking[self.layout.torso].end
        times = (self.time, None if self.time is None else self.time - self.second)
        keys = tuple(self._key(time) for time in times)
        pose.angles[self.layout.torso] += self.GUARD + keys[0].torso + 0.5 * keys[1].torso
        posed_shoulder = self._shoulder(pose)
        targets = {}
        angles = []
        for index, (chain, time, key) in enumerate(zip(
            (self.hand_chain, self.support_chain), times, keys, strict=True,
        )):
            swing = clamp(
                (walking[chain.bones[-1]].end.x - shoulder.x) / self.arm_length,
                -0.65, 0.65,
            )
            # Ease out the gait during the slash and return to the current step.
            gait = 1.0
            if time is not None and 0 < time < self.STAB[-1].time:
                gait -= math.sin(math.pi * time / self.STAB[-1].time) ** 2
            offset = Vec2(0.35 * swing, 0.1 * abs(swing)) * gait
            stagger = Vec2(-0.2, 0.12) if index else Vec2(0, 0)
            targets[chain.name] = posed_shoulder + (key.hand + offset + stagger) * self.arm_length
            angles.append(key.angle + (0.25 * swing - 0.15 * index) * gait)
        self._solve(pose, targets, skip)
        self.angle, self.off_angle = angles

    def strokes(self, transforms, facing, slung=False) -> list[Stroke]:
        strokes = super().strokes(transforms, facing, slung)
        if self.throwing and self.held and (self.time is None or self.time >= 0.25):
            return strokes[:5]  # The main dagger is in flight or lodged in its target.
        return strokes

    def _dagger(self, grip: Vec2, direction: Vec2) -> list[Stroke]:
        s = self.unit
        across = Vec2(-direction.y, direction.x)

        def at(along: float, side: float) -> Vec2:
            return grip + (direction * along + across * side) * s

        # Three broad, backward-facing teeth remain readable at desktop scale.
        shape = tuple(at(x, y) for x, y in (
            (1.1, -1.2), (3.0, -2.2), (2.7, -0.65),
            (5.2, -2.0), (4.7, -0.5), (7.2, -1.7), (6.8, -0.3),
            (10.0, -0.6), (7.7, 1.1), (3.0, 1.25), (1.1, 0.85),
        ))
        return [
            Stroke(at(-2.5, 0), grip, 1.8 * s, "metal"),
            Stroke(at(-2.5, -0.6), at(-2.5, 0.6), 0.9 * s, "hilt"),
            Stroke(at(1, -2.2), at(1, 2.0), 1.2 * s, "hilt"),
            Stroke(at(1.1, 0), at(10, -0.6), 0.35 * s, "steel", shape),
            Stroke(at(2.3, 0.35), at(7.6, 0.15), 0.45 * s, "metal"),
        ]
