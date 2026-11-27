"""The brief, shared prayer pose used by Divine Judgement."""

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.rig.ik import solve_two_bone
from dungeons_desktops.rig.skeleton import forward_kinematics, mirror_pose


def apply_prayer_pose(actor) -> None:
    """Bring both hands together at the chest and bow the praying adventurer."""
    skeleton = actor.layout.skeleton
    facing = actor.locomotion.facing
    pose = actor.locomotion.pose
    if facing < 0:
        pose = mirror_pose(skeleton, pose)

    pose.angles[actor.layout.torso] -= 0.16
    pose.angles[actor.layout.head] += 0.28
    transforms = forward_kinematics(skeleton, pose)
    shoulder = transforms[actor.layout.torso].end
    scale = actor.layout.scale
    hands = (
        shoulder + Vec2(5.0, 8.0) * scale,
        shoulder + Vec2(4.0, 7.2) * scale,
    )
    for chain, hand in zip(actor.layout.arms, hands, strict=True):
        solve_two_bone(skeleton, pose, chain, hand)

    actor.locomotion.pose = mirror_pose(skeleton, pose) if facing < 0 else pose
