"""The wizard's usual wand, held steady through a channeled sweeping ray."""

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.adventurers.weapons import Wand
from dungeons_desktops.rig.skeleton import Pose


class IggyWand(Wand):
    beam_aim: float | None = None

    def _hold(self, pose: Pose, skip: frozenset[str]) -> None:
        if self.beam_aim is None:
            super()._hold(pose, skip)
            return
        pose.angles[self.layout.torso] += 0.1
        shoulder = self._shoulder(pose)
        reach = Vec2.from_angle(self.beam_aim, self.arm_length * 0.94)
        self._solve(pose, {self.hand_chain.name: shoulder + reach}, skip)
        self.angle = self.beam_aim

    def cancel(self) -> None:
        self.beam_aim = None
        super().cancel()
