"""Outstretched arms and slow claws; one hand keeps its grip when clinging."""

import math

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.rig.biped import BipedLayout
from dungeons_desktops.rig.equipment import Weapon
from dungeons_desktops.rig.ik import solve_two_bone
from dungeons_desktops.rig.locomotion import PoseMode
from dungeons_desktops.rig.skeleton import Pose, forward_kinematics


class ZombieClaws(Weapon):
    name = "claws"
    duration = 1.0
    hit_time = 0.42

    def __init__(self, layout: BipedLayout) -> None:
        super().__init__(layout)
        self.clock = 0.0
        self._pending = False
        self.claw_direction = Vec2(1.0, 0.0)

    def cancel(self) -> None:
        super().cancel()
        self._pending = False

    def take_strike(self) -> bool:
        pending, self._pending = self._pending, False
        return pending

    def apply(self, pose: Pose, mode: PoseMode, dt: float, skip: frozenset[str]) -> None:
        self.clock += dt
        if self.time is not None and self.time < self.hit_time <= self.time + dt:
            self._pending = True
        super().apply(pose, mode, dt, skip)

    def _hold(self, pose: Pose, skip: frozenset[str]) -> None:
        sway = math.sin(self.clock * 2.6)
        lunge = 0.0 if self.time is None else math.sin(math.pi * self.time / self.duration)
        if self._clinging:
            shoulder = self._shoulder(pose)
            if self.hanging and self.support_chain.name not in skip:
                transforms = forward_kinematics(self.layout.skeleton, pose)
                support = transforms[self.support_chain.bones[-1]].end
                other = transforms[self.hand_chain.bones[-1]].end
                # If the support hand was mid-step, plant it before the other lets go.
                solve_two_bone(
                    self.layout.skeleton,
                    pose,
                    self.support_chain,
                    Vec2(support.x, min(support.y, other.y)),
                )
            self._solve(
                pose,
                {
                    self.hand_chain.name: shoulder
                    + self.claw_direction * self.arm_length * (0.7 + 0.27 * lunge)
                },
                skip,
            )
            return
        pose.angles[self.layout.torso] += 0.26 + 0.06 * sway + 0.12 * lunge
        pose.angles[self.layout.head] += 0.18
        shoulder = self._shoulder(pose)
        self._solve(
            pose,
            {
                self.support_chain.name: shoulder
                + Vec2(0.82 + 0.06 * lunge, 0.02 + 0.05 * sway) * self.arm_length,
                self.hand_chain.name: shoulder
                + Vec2(0.93, 0.23 + 0.06 * sway - 0.12 * lunge) * self.arm_length,
            },
            skip,
        )

    def strokes(self, transforms, facing, slung=False):
        return []
