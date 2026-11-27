"""The cleric hero's white-gold staff topped by a radiant sun."""

import math

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.rig.equipment import CLINGING, HolyStaff, Stroke
from dungeons_desktops.rig.ik import solve_two_bone
from dungeons_desktops.rig.locomotion import PoseMode
from dungeons_desktops.rig.skeleton import Pose, forward_kinematics


class SunStaff(HolyStaff):
    name = "sun staff"

    def begin_channel(self) -> bool:
        """Hold the raised casting pose until Divine Judgement finishes."""
        self.duration = 10_000.0
        return self.start()

    def end_channel(self) -> None:
        self.cancel()
        self.duration = HolyStaff.duration

    def apply(
        self, pose: Pose, mode: PoseMode, dt: float, skip: frozenset[str]
    ) -> None:
        support = None
        if mode in CLINGING and self.support_chain.name not in skip:
            support = forward_kinematics(self.layout.skeleton, pose)[
                self.support_chain.bones[-1]
            ].end
        super().apply(pose, mode, dt, skip)
        if support is not None:
            solve_two_bone(self.layout.skeleton, pose, self.support_chain, support)

    def _staff(self, butt: Vec2, direction: Vec2) -> list[Stroke]:
        s = self.unit
        top = butt + direction * self.length
        across = direction.rotated(math.pi / 2)

        def radial(angle: float, radius: float) -> Vec2:
            return top + (direction * math.cos(angle) + across * math.sin(angle)) * radius * s

        glow = Stroke(top, top, 14.0 * s, "sun_glow")
        shaft = Stroke(butt, top - direction * (4.5 * s), 2.0 * s, "sun_wood")
        collar = Stroke(
            top - direction * (7.0 * s),
            top - direction * (3.5 * s),
            3.2 * s,
            "sun_gold",
        )
        rays = [
            Stroke(radial(angle, 5.0), radial(angle, 9.0 if index % 2 == 0 else 7.5),
                   1.25 * s, "sun_gold")
            for index in range(12)
            for angle in (index * math.tau / 12,)
        ]
        disc = tuple(radial(index * math.tau / 16, 4.6) for index in range(16))
        core = tuple(radial(index * math.tau / 12, 2.6) for index in range(12))
        return [
            shaft,
            collar,
            glow,
            *rays,
            Stroke(top, top, 0.5 * s, "sun_gold", disc),
            Stroke(top, top, 0.4 * s, "sun_core", core),
        ]

    def sun_center(self, transforms, facing: int) -> Vec2:
        if self.held:
            return self.top(transforms, facing)
        low, high = self._back_line(transforms, facing, 6.0 * self.unit, 0.0)
        return low + (high - low).normalized() * self.length
