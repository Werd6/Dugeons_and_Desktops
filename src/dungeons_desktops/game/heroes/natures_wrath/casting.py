"""Empty-handed casting gestures layered over the goblin gait."""

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.rig.biped import BipedLayout
from dungeons_desktops.rig.ik import solve_two_bone
from dungeons_desktops.rig.locomotion import PoseMode
from dungeons_desktops.rig.skeleton import Pose, forward_kinematics


class CastingPose:
    def __init__(self, layout: BipedLayout) -> None:
        self.layout = layout
        self.progress: float | None = None
        self.direction = Vec2(1, 0)

    def apply(self, pose: Pose, mode: PoseMode, dt: float, skip: frozenset[str]) -> None:
        if self.progress is None or mode is PoseMode.AIR:
            return
        skeleton = self.layout.skeleton
        # The left hand keeps its grip on walls and ceilings.
        arms = self.layout.arms if mode is PoseMode.WALK else (self.layout.arms[1],)
        reach = smoothstep(clamp((self.progress - 0.25) / 0.25, 0, 1))
        for chain in arms:
            if chain.name in skip:
                continue
            transforms = forward_kinematics(skeleton, pose)
            shoulder = transforms[chain.bones[0]].start
            length = sum(skeleton.bone(name).length for name in chain.bones)
            charge = Vec2(0.35, -0.65)
            release = self.direction * 0.9
            offset = charge.lerp(release, reach)
            if chain is self.layout.arms[0]:
                offset = offset * 0.8 + Vec2(0, 0.18)
            solve_two_bone(skeleton, pose, chain, shoulder + offset * length)
