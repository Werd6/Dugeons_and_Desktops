"""Procedural stick-figure body rendering shared with humanoid features."""

from __future__ import annotations

from collections.abc import Callable, Collection

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.actors.base import Actor
from dungeons_desktops.render.primitives import pen, qt
from dungeons_desktops.rig.skeleton import BoneTransform

JOINT = QColor(214, 170, 92)
LIMB_WIDTH = 3.0


def draw_body(
    painter: QPainter,
    actor: Actor,
    near: QColor,
    far: QColor,
    head_fill: QColor,
    between: Callable[[dict[str, BoneTransform]], None] | None = None,
    outline: QColor | None = None,
    hidden: Collection[str] = (),
    over_legs: Callable[[dict[str, BoneTransform]], None] | None = None,
    transforms: dict[str, BoneTransform] | None = None,
) -> dict[str, BoneTransform]:
    """Draw a biped in stable back-to-front body order."""
    layout = actor.layout
    if transforms is None:
        transforms = actor.transforms()
    shown = [bone.name for bone in layout.skeleton.bones if bone.name not in hidden]
    far_side = [name for name in shown if name.endswith("_l")]
    near_side = [name for name in shown if name.endswith("_r")]
    near_arm = [name for name in near_side if "arm" in name]
    near_leg = [name for name in near_side if name not in near_arm]
    spine = [name for name in (layout.pelvis, layout.torso) if name not in hidden]
    has_head = layout.head not in hidden
    head = transforms[layout.head]
    radius = layout.head_radius
    neck_length = head.start.distance_to(head.end) - radius
    neck_end = head.start + Vec2.from_angle(head.angle, neck_length)
    limb_width = LIMB_WIDTH * layout.scale
    joint = 1.1 * layout.scale

    if outline is not None:
        painter.setPen(pen(outline, (LIMB_WIDTH + 2.5) * layout.scale))
        for name in shown:
            if name != layout.head:
                transform = transforms[name]
                painter.drawLine(qt(transform.start), qt(transform.end))
        if has_head:
            painter.drawLine(qt(head.start), qt(neck_end))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(qt(head.end), radius, radius)

    def draw_bones(names: list[str], color: QColor) -> None:
        painter.setPen(pen(color, limb_width))
        for name in names:
            transform = transforms[name]
            painter.drawLine(qt(transform.start), qt(transform.end))

    draw_bones(far_side, far)
    draw_bones(spine, near)
    if has_head:
        painter.setPen(pen(near, limb_width))
        painter.drawLine(qt(head.start), qt(neck_end))
        painter.setBrush(head_fill)
        painter.drawEllipse(qt(head.end), radius, radius)
    if between is not None:
        between(transforms)
    draw_bones(near_leg, near)

    def draw_joints(names: list[str]) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(JOINT)
        for name in names:
            painter.drawEllipse(qt(transforms[name].start), joint, joint)

    draw_joints([name for name in shown if name not in near_arm])
    if over_legs is not None:
        over_legs(transforms)
    draw_bones(near_arm, near)
    draw_joints(near_arm)
    return transforms
