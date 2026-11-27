"""Full plate and spectral combat effects for The Soulforger."""

from __future__ import annotations

import math
from collections.abc import Collection, Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.actors.base import Actor
from dungeons_desktops.game.adventurers.actor import Stickman
from dungeons_desktops.game.heroes.hero_fighter.weapon import (
    SoulforgedTridentAndShield,
)
from dungeons_desktops.render.equipment import draw_strokes
from dungeons_desktops.render.primitives import alpha, qt, world_pen
from dungeons_desktops.rig.skeleton import BoneTransform

BODY_WIDTH = 5.0
PLATE = QColor(118, 132, 146)
PLATE_DARK = QColor(31, 48, 44)
SILVER = QColor(214, 226, 234)
ARMOR_EDGE = QColor(22, 28, 38)


def draw_hero_fighter_effects(
    painter: QPainter, heroes: Iterable[Stickman], outline: QColor | None = None
) -> None:
    for hero in heroes:
        if hero.variant != "hero_fighter":
            continue
        weapon = hero.weapon
        if not isinstance(weapon, SoulforgedTridentAndShield):
            continue
        for trident in getattr(hero, "spectral_tridents", ()):
            draw_strokes(
                painter,
                weapon.trident_strokes(trident.position, trident.direction, 1.2),
            )
            painter.setPen(world_pen(alpha(SILVER, 105), 1.1))
            painter.drawLine(
                qt(trident.position - trident.direction * 24.0), qt(trident.position)
            )

        shield = getattr(hero, "spectral_shield", None)
        if shield is not None:
            _draw_spectral_shield(painter, shield.position, outline)

        if not hero.animated:
            continue
        marked = getattr(hero, "marked", None)
        action = getattr(getattr(hero, "action", None), "value", "")
        if marked is None and action == "mark":
            marked = getattr(hero, "action_target", None)
        point = hero.world.locate(marked) if marked is not None else None
        if point is not None:
            pulse = 1.0 + 0.1 * math.sin(getattr(hero, "effect_time", 0.0) * 10.0)
            _draw_death_mark(painter, point - Vec2(0.0, 16.0), pulse)

        flash = getattr(hero, "attack_flash", None)
        if flash is not None:
            direction = Vec2(float(hero.facing), 0.0)
            across = Vec2(0.0, 1.0)
            start = hero.center() + direction * 5.0 - across * 2.0
            tip = start + direction * (25.0 if flash == "trident" else 20.0)
            painter.setPen(world_pen(QColor(218, 234, 248, 75), 4.0))
            painter.drawLine(qt(start), qt(tip))
            painter.setPen(world_pen(QColor(246, 252, 255, 220), 1.2))
            painter.drawLine(qt(start), qt(tip))


def draw_breastplate(
    painter: QPainter,
    stickman: Actor,
    transforms: dict[str, BoneTransform],
    hidden: Collection[str] = (),
    outline: QColor | None = None,
    *,
    plate: QColor = PLATE,
    plate_dark: QColor = PLATE_DARK,
    silver: QColor = SILVER,
    armor_edge: QColor = ARMOR_EDGE,
) -> None:
    """The Soulforger's fitted cuirass, reusable without the rest of his full plate."""
    layout = stickman.layout
    r = layout.head_radius
    if layout.torso in hidden:
        return
    torso = transforms[layout.torso]
    up = (torso.end - torso.start).normalized()
    across = up.rotated(math.pi / 2)
    shoulder, waist = torso.end, torso.start
    facing = 1.0 if across.x * stickman.facing >= 0 else -1.0

    cuirass = (
        shoulder + across * (1.28 * r) - up * (0.12 * r),
        shoulder + across * (1.05 * r) + up * (0.35 * r),
        shoulder - across * (0.95 * r) + up * (0.28 * r),
        shoulder - across * (1.22 * r) - up * (0.18 * r),
        waist - across * (0.72 * r) + up * (0.08 * r),
        waist - across * (0.18 * r) - up * (0.22 * r),
        waist + across * (0.22 * r) - up * (0.22 * r),
        waist + across * (0.78 * r) + up * (0.08 * r),
    )
    edge = armor_edge if outline is None else outline
    highlight = silver if outline is None else outline
    _polygon(painter, cuirass, plate_dark, edge)
    light = (
        shoulder + across * (facing * 0.08 * r),
        shoulder + across * (facing * 1.12 * r) - up * (0.05 * r),
        waist + across * (facing * 0.68 * r),
        waist + across * (facing * 0.08 * r) - up * (0.12 * r),
    )
    _polygon(painter, light, plate, highlight)
    painter.setPen(world_pen(highlight, 0.12 * r))
    painter.drawLine(
        qt(shoulder + across * (facing * 0.18 * r) - up * (0.05 * r)),
        qt(waist + across * (facing * 0.12 * r)),
    )


def draw_armor(
    painter: QPainter,
    stickman: Stickman,
    transforms: dict[str, BoneTransform],
    hidden: Collection[str],
) -> None:
    """Fitted full plate over the ordinary Fighter skeleton and gait."""
    layout = stickman.layout
    r = layout.head_radius
    if layout.torso in hidden:
        return
    draw_breastplate(painter, stickman, transforms, hidden)

    for side, color in (("l", PLATE_DARK), ("r", PLATE)):
        upper_arm = f"upper_arm_{side}"
        if upper_arm not in hidden:
            painter.setPen(world_pen(ARMOR_EDGE, 0.9))
            painter.setBrush(color)
            painter.drawEllipse(qt(transforms[upper_arm].start), 0.62 * r, 0.42 * r)
        for bone, start_width, end_width in (
            (upper_arm, 0.48, 0.38),
            (f"lower_arm_{side}", 0.42, 0.30),
            (f"upper_leg_{side}", 0.58, 0.44),
            (f"lower_leg_{side}", 0.46, 0.36),
        ):
            if bone in hidden:
                continue
            segment = transforms[bone]
            along = (segment.end - segment.start).normalized()
            side_vector = along.rotated(math.pi / 2)
            _polygon(
                painter,
                (
                    segment.start + side_vector * (start_width * r),
                    segment.end + side_vector * (end_width * r),
                    segment.end - side_vector * (end_width * r),
                    segment.start - side_vector * (start_width * r),
                ),
                color,
                ARMOR_EDGE,
            )
        lower_leg = f"lower_leg_{side}"
        if lower_leg in hidden:
            continue
        boot = transforms[lower_leg]
        along = (boot.end - boot.start).normalized()
        toe = Vec2(float(stickman.facing), 0.0)
        ankle = boot.end - along * (0.38 * r)
        _polygon(
            painter,
            (
                ankle - toe * (0.22 * r),
                boot.end + toe * (0.72 * r),
                boot.end + Vec2(0.0, 0.34 * r) - toe * (0.18 * r),
                ankle + Vec2(0.0, 0.22 * r) - toe * (0.30 * r),
            ),
            color,
            ARMOR_EDGE,
        )


def _draw_death_mark(painter: QPainter, center: Vec2, pulse: float) -> None:
    radius = 7.0 * pulse
    painter.setPen(world_pen(alpha(SILVER, 225), 1.25))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(qt(center), radius, radius * 0.45)
    painter.drawLine(qt(center - Vec2(0.0, 5.0)), qt(center + Vec2(0.0, 5.0)))
    painter.drawLine(qt(center - Vec2(3.5, 0.0)), qt(center + Vec2(3.5, 0.0)))


def _draw_spectral_shield(
    painter: QPainter, center: Vec2, outline: QColor | None
) -> None:
    shape = (
        center + Vec2(-5.2, -6.2),
        center + Vec2(5.2, -6.2),
        center + Vec2(4.8, 1.0),
        center + Vec2(0.0, 7.4),
        center + Vec2(-4.8, 1.0),
    )
    painter.setPen(world_pen(outline or QColor(96, 126, 146, 190), 1.4))
    painter.setBrush(QColor(210, 232, 248, 105))
    painter.drawPolygon([qt(point) for point in shape])


def _polygon(
    painter: QPainter, points: tuple[Vec2, ...], fill: QColor, edge: QColor
) -> None:
    painter.setPen(world_pen(edge, 1.0))
    painter.setBrush(fill)
    painter.drawPolygon([qt(point) for point in points])
