"""Role-specific equipment over cold iron armor and ghost-lit skulls."""

from __future__ import annotations

import math
from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QRadialGradient

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.adventurers.render import draw_body, draw_fighter_helmet
from dungeons_desktops.game.defenders.graveknights.actor import Graveknight, GraveknightRole
from dungeons_desktops.game.defenders.legendary import LEGENDARY_GOLD
from dungeons_desktops.game.heroes.hero_fighter import render as hero_fighter
from dungeons_desktops.game.heroes.hero_sorcerer import render as hero_sorcerer
from dungeons_desktops.render.chromatic import chromatic_appearance
from dungeons_desktops.render.equipment import draw_strokes
from dungeons_desktops.render.primitives import qt, world_pen

SKIN = QColor(126, 142, 154)
FAR = QColor(67, 78, 88)
HEAD = QColor(44, 51, 59)
ARMOR_EDGE = QColor(29, 35, 43)
BREASTPLATE = QColor(166, 180, 194)
BREASTPLATE_DARK = QColor(36, 42, 54)
BREASTPLATE_SILVER = QColor(232, 240, 246)
BREASTPLATE_EDGE = QColor(12, 16, 24)
EYE = QColor(92, 235, 210)
FIGHTER_EYE = QColor(110, 255, 140)
PYRE = QColor(255, 148, 48)
PYRE_CORE = QColor(255, 236, 170)
GOLD_TRIM = QColor(214, 170, 92)
GOLD_HOT = QColor(255, 214, 120)


@chromatic_appearance
def draw_graveknight(
    painter: QPainter, knight: Graveknight, outline: QColor | None = None
) -> None:
    transforms = knight.transforms()
    facing = knight.facing
    legendary = getattr(knight, "legendary", False)
    haste = knight.ashen_haste if legendary else 0.0

    def armor(parts) -> None:
        hero_fighter.draw_breastplate(
            painter,
            knight,
            parts,
            outline=outline,
            plate=BREASTPLATE,
            plate_dark=BREASTPLATE_DARK,
            silver=GOLD_TRIM if legendary else BREASTPLATE_SILVER,
            armor_edge=BREASTPLATE_EDGE,
        )

        head = parts[knight.layout.head].end
        radius = knight.layout.head_radius
        painter.setPen(world_pen(ARMOR_EDGE if outline is None else outline, 1.0))
        painter.setBrush(HEAD)
        painter.drawEllipse(qt(head), radius, radius)
        if knight.role is GraveknightRole.FIGHTER:
            draw_fighter_helmet(painter, knight, parts)
        eye = head + Vec2(facing * radius * 0.5, -radius * 0.08)
        eye_color = FIGHTER_EYE if knight.role is GraveknightRole.FIGHTER else EYE
        if legendary:
            eye_color = QColor(
                min(255, int(eye_color.red() + 80 * haste)),
                min(255, int(eye_color.green() + 40 * haste)),
                max(0, int(eye_color.blue() - 60 * haste)),
            )
        glow = QRadialGradient(qt(eye), radius * 0.85)
        glow.setColorAt(
            0.0,
            QColor(eye_color.red(), eye_color.green(), eye_color.blue(), 150),
        )
        glow.setColorAt(
            1.0,
            QColor(eye_color.red(), eye_color.green(), eye_color.blue(), 0),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(qt(eye), radius * 0.85, radius * 0.85)
        painter.setBrush(eye_color)
        painter.drawEllipse(qt(eye), 0.8, 0.8)
        if legendary and not knight.dead:
            _draw_gold_armor(painter, knight, parts, facing, haste)

    draw_body(
        painter,
        knight,
        SKIN,
        FAR,
        HEAD,
        between=armor,
        outline=outline,
        body_width=2.2,
        show_joints=False,
    )
    strokes = knight.weapon.strokes(transforms, facing, slung=knight.dead)
    if knight.role is GraveknightRole.MAGE:
        # The Hero Sorcerer renders its focus as a floating skull rather than the
        # FireOrb base class's pink outer orb. Keep the inner casting flash.
        draw_strokes(painter, [stroke for stroke in strokes if stroke.kind != "orb"])
        if not knight.dead and knight.weapon.held:
            hero_sorcerer.draw_focus(painter, knight, transforms, outline)
    else:
        draw_strokes(painter, strokes)
    if legendary and not knight.dead and outline is None:
        _draw_weapon_fire(painter, strokes, knight.time, haste)
        _draw_ashen_embers(painter, knight, facing, haste)


def _draw_gold_armor(
    painter: QPainter,
    knight: Graveknight,
    parts,
    facing: int,
    haste: float,
) -> None:
    """Gold trim and white-hot cracks that brighten as ashen haste rises."""
    torso = parts[knight.layout.torso]
    middle = torso.start.lerp(torso.end, 0.45)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(world_pen(GOLD_HOT if haste > 0.55 else GOLD_TRIM, 1.15 + 0.55 * haste))
    painter.drawLine(qt(middle + Vec2(-2.6 * facing, -3.2)), qt(middle + Vec2(0.4 * facing, 0.4)))
    painter.drawLine(qt(middle + Vec2(0.4 * facing, 0.4)), qt(middle + Vec2(-1.4 * facing, 3.4)))
    painter.setPen(world_pen(LEGENDARY_GOLD, 0.9))
    near = "upper_arm_r" if facing > 0 else "upper_arm_l"
    far = "upper_arm_l" if facing > 0 else "upper_arm_r"
    painter.drawEllipse(qt(parts[near].start), 1.6 + haste, 1.6 + haste)
    painter.drawEllipse(qt(parts[far].start), 1.3 + 0.7 * haste, 1.3 + 0.7 * haste)
    painter.setPen(Qt.PenStyle.NoPen)
    gold = QColor(GOLD_HOT.red(), GOLD_HOT.green(), GOLD_HOT.blue(), 90 + int(80 * haste))
    painter.setBrush(gold)
    painter.drawEllipse(qt(middle), 2.2 + haste, 1.4 + 0.6 * haste)


def _draw_weapon_fire(painter: QPainter, strokes, time: float, haste: float) -> None:
    """Gold-cored fire along the weapon edge — denser and hotter with haste."""
    painter.setPen(Qt.PenStyle.NoPen)
    count = 3 + int(5 * haste)
    for stroke in strokes:
        span = stroke.end - stroke.start
        length = max(span.length(), 1.0)
        direction = span / length
        across = Vec2(-direction.y, direction.x)
        for i in range(count):
            along = (0.35 + 0.6 * i / max(count - 1, 1)) % 1.0
            flicker = 0.5 + 0.5 * math.sin(time * (14.0 + 6.0 * haste) + i * 1.7 + length)
            point = stroke.start + direction * (length * along)
            point += across * (math.sin(time * 9.0 + i * 2.1) * (0.6 + 1.2 * haste))
            point += direction * (-1.2 * flicker * (0.5 + haste))
            outer = 2.0 + 2.4 * haste * flicker
            painter.setBrush(QColor(PYRE.red(), PYRE.green(), PYRE.blue(), 120 + int(90 * haste)))
            painter.drawEllipse(qt(point), outer, outer * 0.75)
            painter.setBrush(QColor(PYRE_CORE.red(), PYRE_CORE.green(), PYRE_CORE.blue(), 200))
            painter.drawEllipse(qt(point), outer * 0.4, outer * 0.35)
            if haste > 0.35:
                painter.setBrush(
                    QColor(GOLD_HOT.red(), GOLD_HOT.green(), GOLD_HOT.blue(), 160 + int(60 * haste))
                )
                painter.drawEllipse(qt(point + direction * 0.8), 1.0 + haste, 1.0 + haste)


def _draw_ashen_embers(
    painter: QPainter, knight: Graveknight, facing: int, haste: float
) -> None:
    """Rising fire embers off the armor; more of them as possession charges burn away."""
    painter.setPen(Qt.PenStyle.NoPen)
    center = knight.center()
    embers = 4 + int(8 * haste)
    for i in range(embers):
        phase = knight.time * (3.2 + haste * 4.0) + i * 1.3
        rise = (phase * 7.0) % 18.0
        side = math.sin(phase * 1.7) * (3.0 + 4.0 * haste)
        point = center + Vec2(facing * side * 0.35 - facing * 2.0, -4.0 - rise)
        life = 1.0 - rise / 18.0
        size = (1.1 + 1.6 * haste) * (0.45 + 0.55 * life)
        painter.setBrush(QColor(PYRE.red(), PYRE.green(), PYRE.blue(), int(160 * life)))
        painter.drawEllipse(qt(point), size, size * 1.25)
        painter.setBrush(QColor(GOLD_HOT.red(), GOLD_HOT.green(), GOLD_HOT.blue(), int(200 * life)))
        painter.drawEllipse(qt(point), size * 0.45, size * 0.55)


def draw_graveknights(
    painter: QPainter,
    graveknights: Iterable[Graveknight],
    outline: QColor | None = None,
) -> None:
    for knight in graveknights:
        draw_graveknight(painter, knight, outline)
