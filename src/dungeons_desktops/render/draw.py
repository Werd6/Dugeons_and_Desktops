"""QPainter drawing for actors, weapons, vials, bullets and terrain surfaces.

Everything is drawn in world coordinates; callers set up the painter transform.
An `outline` color draws a darker halo under bodies so they read on any backdrop.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Collection, Iterable, Sequence
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPolygonF,
    QRadialGradient,
    QTransform,
)

from dungeons_desktops.core.geometry import Rect, Vec2, clamp, smoothstep
from dungeons_desktops.game.adventurers.actor import Actor, Stickman
from dungeons_desktops.game.adventurers.alchemy import Vials
from dungeons_desktops.game.adventurers.spells import (
    ARROW_STUCK_TIME,
    PULSE_TIME,
    SPARK_LIFE,
    VINE_GROW,
    VINE_TIME,
    Spells,
)
from dungeons_desktops.game.defenders.chimera.actor import Chimera
from dungeons_desktops.game.defenders.displacer.actor import Displacer
from dungeons_desktops.game.defenders.displacer.render import draw_displacer
from dungeons_desktops.game.defenders.dragon.actor import SCALE as DRAGON_SCALE
from dungeons_desktops.game.defenders.dragon.actor import Dragon, Leg
from dungeons_desktops.game.defenders.drakes.drake import Drake
from dungeons_desktops.game.defenders.drakes.kobold import Kobold
from dungeons_desktops.game.defenders.drow.actor import Drow, Lizard
from dungeons_desktops.game.defenders.elementals.actor import Elemental
from dungeons_desktops.game.defenders.goblins.actor import Goblin
from dungeons_desktops.game.defenders.goblins.spears import Spears
from dungeons_desktops.game.defenders.hydra.actor import Hydra
from dungeons_desktops.game.defenders.hydra.render import draw_hydra
from dungeons_desktops.game.defenders.lich.actor import Lich
from dungeons_desktops.game.defenders.lich.render import draw_lich
from dungeons_desktops.game.defenders.lich.skeletons import Skeleton
from dungeons_desktops.game.defenders.mimic.actor import Mimic
from dungeons_desktops.game.defenders.mimic.render import draw_lure_alert, draw_mimic
from dungeons_desktops.game.defenders.mindflayer.actor import (
    PULSE_RADIUS,
    WAVE_TIME,
    MindFlayer,
    Power,
)
from dungeons_desktops.game.defenders.mindflayer.devourer import BODY_HEIGHT, Devourer
from dungeons_desktops.game.defenders.minotaur.actor import Minotaur
from dungeons_desktops.game.defenders.minotaur.render import draw_minotaur
from dungeons_desktops.game.defenders.ooze.actor import Ooze
from dungeons_desktops.game.defenders.worm.actor import Worm
from dungeons_desktops.game.effects.debris import HOLE_FADE, HOLE_LIFE, Debris, Hole
from dungeons_desktops.game.effects.fire import Burn
from dungeons_desktops.game.effects.flames import FLAME_LIFE, Flame
from dungeons_desktops.game.effects.gore import DROP_LIFE, SPLAT_LIFE, Gore
from dungeons_desktops.game.effects.projectiles import Projectiles
from dungeons_desktops.game.effects.render import (
    demise_colors,
    draw_breath,
    draw_demise_over,
    draw_demise_under,
    melted,
)
from dungeons_desktops.game.world.simulation import KILL_MARK_TIME, KillMark
from dungeons_desktops.navigation.terrain import Surface
from dungeons_desktops.rig.ik import two_bone_points
from dungeons_desktops.rig.skeleton import BoneTransform
from dungeons_desktops.rig.weapons import Banner, HeroTridentAndShield

BACKGROUND = QColor(24, 26, 33)
KILL_MARK_TEXT = "+\N{SKULL}"
KILL_MARK_SIZE = 15
KILL_MARK_LIFT = 14.0
"""How far above the head the "+skull" starts..."""
KILL_MARK_RISE = 22.0
"""...and how much further it drifts up."""
KILL_MARK_COLOR = QColor(255, 236, 228)
KILL_MARK_SHADOW = QColor(0, 0, 0, 170)
GROUND = QColor(90, 96, 110)
NEAR_LIMB = QColor(236, 230, 214)
FAR_LIMB = QColor(150, 146, 136)
JOINT = QColor(214, 170, 92)
TARGET = QColor(110, 190, 240)
WALK_SURFACE = QColor(110, 200, 140, 120)
CLIMB_SURFACE = QColor(230, 160, 80, 120)
WEAPON_COLORS = {
    "steel": QColor(214, 224, 238),
    "hilt": QColor(206, 160, 78),
    "wood": QColor(150, 100, 62),
    "metal": QColor(128, 134, 150),
    "flash": QColor(255, 222, 120),
    "magic": QColor(196, 120, 255),
    "orb": QColor(255, 110, 176),
    "holy": QColor(252, 250, 240),
    "string": QColor(228, 222, 204),
    "shield": QColor(52, 84, 156),
    "hero_shield": QColor(36, 48, 62),
    "hero_shield_trim": QColor(214, 226, 234),
    "hero_shield_strap": QColor(78, 88, 94),
    "hero_shield_boss": QColor(236, 224, 194),
    "divine_glow": QColor(176, 214, 255, 70),
    "divine": QColor(198, 214, 226),
    "divine_core": QColor(252, 255, 255),
    "bomb": QColor(220, 40, 52),
    "glass": QColor(235, 200, 205),
    "cork": QColor(160, 115, 70),
    "leaf": QColor(92, 170, 70),
}
MAGIC = QColor(176, 96, 255)
MAGIC_CORE = QColor(244, 226, 255)
FIRE_SPARK = QColor(255, 124, 48)
FIRE_SPARK_CORE = QColor(255, 244, 180)
SCARF = QColor(255, 214, 234)
SCARF_EDGE = QColor(168, 52, 108)
HOLY = QColor(255, 255, 248)
HAT = QColor(92, 62, 176)
HAT_EDGE = QColor(52, 32, 108)
HAT_STAR = QColor(255, 222, 96)
ANTLER = QColor(214, 192, 150)
ANTLER_EDGE = QColor(120, 96, 64)
CIRCLET = QColor(96, 150, 70)
VINE = QColor(70, 140, 56)
VINE_DARK = QColor(40, 92, 36)
ROBE = QColor(240, 238, 230)
ROBE_EDGE = QColor(176, 172, 160)
ROBE_SASH = QColor(214, 176, 86)
HERO_PLATE = QColor(118, 132, 146)
HERO_PLATE_DARK = QColor(31, 48, 44)
HERO_SILVER = QColor(214, 226, 234)
HERO_ARMOR_EDGE = QColor(22, 28, 38)
HERO_WING = QColor(214, 226, 234, 210)
HERO_WING_FAR = QColor(148, 164, 180, 160)
HERO_WING_BONE = QColor(238, 244, 248)
CLASS_COLORS = {
    "barbarian": (QColor(238, 138, 54), QColor(160, 90, 36)),
    "paladin": (QColor(252, 224, 92), QColor(172, 150, 58)),
    "wizard": (QColor(172, 112, 242), QColor(112, 72, 164)),
    "ranger": (QColor(108, 200, 88), QColor(70, 132, 58)),
    "rogue": (QColor(206, 174, 50), QColor(138, 116, 34)),
    "cleric": (QColor(244, 242, 234), QColor(170, 168, 160)),
    "alchemist": (QColor(74, 136, 240), QColor(46, 88, 164)),
    "druid": (QColor(70, 182, 160), QColor(44, 118, 104)),
    "sorcerer": (QColor(250, 116, 184), QColor(172, 62, 118)),
    "fighter": (QColor(236, 64, 68), QColor(154, 38, 44)),
    "hero_fighter": (QColor(176, 188, 198), QColor(96, 108, 122)),
}
"""Limb colors (near, far) for each adventurer class."""
SPARK_COLORS = {
    "magic": MAGIC,
    "fire": FIRE_SPARK,
    "holy": HOLY,
    "wood": QColor(150, 100, 62),
    "hit": QColor(255, 226, 170),
    "leaf": QColor(110, 190, 80),
}
SELECTED = QColor(120, 220, 160)
GOBLIN_SKIN = QColor(132, 186, 88)
GOBLIN_FAR = QColor(88, 128, 60)
GOBLIN_HEAD = QColor(58, 92, 44)
GOBLIN_EYE = QColor(250, 220, 80)
SKELETON_BONE = QColor(226, 220, 196)
SKELETON_FAR = QColor(160, 154, 134)
SKELETON_SOCKET = QColor(22, 18, 24)
SKELETON_EYE = QColor(140, 255, 140)
SKELETON_DIRT = QColor(92, 74, 56)
BANNER = QColor(150, 30, 34)
BANNER_EDGE = QColor(60, 14, 16)
WOUNDED = QColor(230, 60, 60)
VIAL_RED = QColor(220, 40, 52)
VIAL_GLASS = QColor(235, 200, 205)
VIAL_CORK = QColor(160, 115, 70)
VIAL_SCALE = 1.1
BLAST_OUTER = QColor(240, 90, 40)
BLAST_INNER = QColor(255, 220, 140)
TRAIL = QColor(190, 215, 255)
BULLET = QColor(255, 232, 160)
SPARK = QColor(255, 200, 110)
OUTLINE = QColor(20, 20, 26, 200)
WORM_SKIN = QColor(214, 128, 132)
WORM_RIDGE = QColor(160, 84, 92)
WORM_MOUTH = QColor(70, 16, 24)
WORM_TOOTH = QColor(255, 255, 255)
WORM_GHOST = QColor(214, 128, 132, 70)
WORM_GHOST_EDGE = QColor(120, 70, 60, 110)
WORM_HEAD_SCALE = 1.425
"""How much bigger the drawn head is than the body's thickest segment."""
WORM_JAW_OPEN = 0.85
WORM_JAW_STRIKE = 0.3
"""Half-angle of the jaw gap in radians: always `OPEN`, plus up to `STRIKE` mid-lunge."""
WORM_TEETH_PER_JAW = 3
BURIED_WORM_VISIBLE = False
"""True: a burrowing worm shows as a faint silhouette. False: it's invisible
underground and only appears when it breaks out of the ground."""
DIRT = QColor(132, 96, 62)
DIRT_DARK = QColor(84, 58, 36)
DIRT_LIGHT = QColor(170, 128, 86)
DIRT_SHADES = (DIRT, DIRT_DARK, DIRT_LIGHT)
DUST = QColor(196, 170, 130)
SHOCKWAVE = QColor(250, 236, 205)
HOLE = QColor(22, 14, 10)
DRAGON_SKIN = QColor(176, 46, 40)
DRAGON_FAR = QColor(118, 30, 28)
DRAGON_BELLY = QColor(232, 170, 92)
DRAGON_WING = QColor(204, 82, 58, 215)
DRAGON_WING_FAR = QColor(140, 46, 36, 200)
DRAGON_HORN = QColor(240, 226, 192)
DRAGON_TALON = QColor(58, 34, 30)
DRAGON_EYE = QColor(255, 220, 60)
DRAGON_WING_SCALE = 2.0


@dataclass(frozen=True)
class DragonPalette:
    skin: QColor
    far: QColor
    belly: QColor
    wing: QColor
    wing_far: QColor
    horn: QColor
    talon: QColor
    eye: QColor


DRAGON_PALETTES = {
    "red": DragonPalette(
        DRAGON_SKIN,
        DRAGON_FAR,
        DRAGON_BELLY,
        DRAGON_WING,
        DRAGON_WING_FAR,
        DRAGON_HORN,
        DRAGON_TALON,
        DRAGON_EYE,
    ),
    "green": DragonPalette(
        QColor(44, 132, 62),
        QColor(26, 86, 40),
        QColor(200, 216, 96),
        QColor(78, 164, 84, 215),
        QColor(34, 100, 48, 200),
        QColor(226, 218, 168),
        QColor(30, 46, 28),
        QColor(255, 226, 60),
    ),
    "blue": DragonPalette(
        QColor(36, 82, 182),
        QColor(22, 50, 120),
        QColor(178, 210, 244),
        QColor(66, 122, 216, 215),
        QColor(30, 62, 142, 200),
        QColor(236, 240, 250),
        QColor(24, 28, 52),
        QColor(196, 246, 255),
    ),
    "black": DragonPalette(
        QColor(46, 42, 54),
        QColor(24, 22, 30),
        QColor(178, 168, 142),
        QColor(86, 72, 104, 215),
        QColor(44, 36, 56, 200),
        QColor(156, 142, 116),
        QColor(12, 10, 14),
        QColor(190, 255, 90),
    ),
    "white": DragonPalette(
        QColor(232, 238, 246),
        QColor(168, 182, 204),
        QColor(204, 222, 240),
        QColor(216, 232, 248, 215),
        QColor(158, 176, 204, 200),
        QColor(178, 196, 222),
        QColor(88, 98, 120),
        QColor(96, 196, 255),
    ),
}
"""Wing size relative to the body; the folded wing grows with it."""
FLAME_HOT = QColor(255, 244, 170)
FLAME_MID = QColor(255, 150, 40)
FLAME_SMOKE = QColor(110, 60, 40)
FLAME_RED = QColor(225, 60, 25)
CHARRED = QColor(34, 28, 26)
BLOOD = QColor(200, 16, 24)
BLOOD_DARK = QColor(120, 6, 12)
CHARRED_FAR = QColor(22, 18, 17)
COUNTER_BACK = QColor(20, 20, 26, 170)
COUNTER_TEXT = QColor(240, 232, 214)
HEALTH_BAR_HEIGHT = 20.0
SKULL = QColor(236, 230, 214)
FLAYER_ROBE = QColor(98, 52, 150)
FLAYER_ROBE_EDGE = QColor(52, 24, 86)
FLAYER_TRIM = QColor(214, 176, 84)
FLAYER_SKIN = QColor(172, 146, 204)
FLAYER_SKIN_FAR = QColor(120, 98, 150)
FLAYER_SKIN_EDGE = QColor(96, 70, 128)
FLAYER_EYE = QColor(246, 242, 255)
FLAYER_CAPE = QColor(44, 20, 66)
FLAYER_CAPE_EDGE = QColor(20, 8, 32)
FLAYER_LINING = QColor(176, 34, 66)
FLAYER_SHADOW = QColor(40, 20, 70, 60)
FLAYER_TENTACLE = QColor(146, 112, 184)
FLAYER_TENTACLE_EDGE = QColor(62, 36, 92)
TENTACLE_LENGTH = 2.8
"""Face tentacles, in head radii."""
PSYCHIC = QColor(196, 112, 255)
PSYCHIC_CORE = QColor(250, 236, 255)
BRAIN = QColor(238, 152, 176)
BRAIN_EDGE = QColor(168, 78, 108)
DEVOURER_LEG = QColor(222, 186, 178)
DEVOURER_LEG_FAR = QColor(170, 130, 126)
THRALL_TINT = 0.4
"""How far a thrall's colors are pulled toward the mind flayer's skin."""

LIMB_WIDTH = 3.0


def qt(point: Vec2) -> QPointF:
    return QPointF(point.x, point.y)


def pen(color: QColor, width: float, style=Qt.PenStyle.SolidLine) -> QPen:
    """Width in screen pixels, independent of the zoom."""
    result = QPen(color, width, style, Qt.PenCapStyle.RoundCap)
    result.setCosmetic(True)
    return result


def world_pen(color: QColor, width: float) -> QPen:
    """Width in world pixels, scaled with the zoom like the props it draws."""
    return QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)


def draw_actors(
    painter: QPainter,
    goblins: Iterable[Goblin],
    stickmen: Iterable[Stickman],
    selected: Stickman | None = None,
    outline: QColor | None = None,
) -> None:
    for goblin in goblins:
        draw_goblin(painter, goblin, outline)
    for stickman in stickmen:
        painter.setOpacity(1.0 - stickman.fade)
        demise = stickman.demise
        squeeze = stickman.squeeze() if demise is None else None
        if squeeze is not None:
            _draw_swallowed(painter, stickman, squeeze, stickman is selected, outline)
        elif demise is None:
            draw_stickman(painter, stickman, stickman is selected, outline)
        else:
            transforms = melted(stickman.transforms(), demise.melt)
            draw_demise_under(painter, demise, transforms)
            hide = (stickman.layout.head,) if demise.kind == "acid" else ()
            if not demise.shattered:
                draw_stickman(painter, stickman, stickman is selected, outline, transforms, hide)
            draw_demise_over(painter, demise, transforms, stickman.layout.head_radius)
        if stickman.burn is not None:
            painter.setOpacity(1.0)
            draw_burn(painter, stickman.burn)
    painter.setOpacity(1.0)


def draw_dio_effects(
    painter: QPainter, heroes: Iterable[Stickman], outline: QColor | None = None
) -> None:
    """Hero effects that must remain visible above monsters and ordinary actors."""
    for hero in heroes:
        if hero.variant != "hero_fighter" or not hero.animated:
            continue
        weapon = hero.weapon
        if not isinstance(weapon, HeroTridentAndShield):
            continue
        phase = getattr(getattr(hero, "phase", None), "value", "")
        if phase == "throw_charge":
            charge = getattr(hero, "trident_charge", 0.0)
            center = weapon.trident_center(hero.transforms(), hero.facing)
            pulse = 1.0 + 0.12 * math.sin(charge * math.tau * 3.0)
            painter.setPen(world_pen(_alpha(HERO_SILVER, int(80 + 100 * charge)), 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(qt(center), 7.0 * pulse, 7.0 * pulse)
        thrown = getattr(hero, "thrown_trident", None)
        if thrown is not None:
            draw_strokes(
                painter,
                weapon.trident_strokes(thrown.position, thrown.direction, 1.65),
            )
            painter.setPen(world_pen(_alpha(HERO_SILVER, 120), 1.1))
            painter.drawLine(qt(thrown.position - thrown.direction * 28.0), qt(thrown.position))

        marked = getattr(hero, "marked", None)
        if marked is None and phase == "mark_cast":
            marked = getattr(hero, "target", None)
        point = hero.world.locate(marked) if marked is not None else None
        if point is not None:
            pulse = 1.0 + 0.12 * math.sin(getattr(hero, "mark_time", 0.0) * 10.0)
            radius = 7.0 * pulse
            center = point - Vec2(0.0, 16.0)
            painter.setPen(world_pen(_alpha(HERO_SILVER, 220), 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(qt(center), radius, radius * 0.45)
            painter.drawLine(qt(center - Vec2(0.0, 5.0)), qt(center + Vec2(0.0, 5.0)))
            painter.drawLine(qt(center - Vec2(3.5, 0.0)), qt(center + Vec2(3.5, 0.0)))

        shield = getattr(hero, "spectral_shield", None)
        if shield is not None:
            _draw_spectral_shield(painter, shield.position, outline)

        flash = getattr(hero, "attack_flash", None)
        if flash is not None:
            direction = Vec2(float(hero.facing), 0.0)
            across = Vec2(0.0, 1.0)
            start = hero.center() + direction * 5.0 - across * 2.0
            tip = start + direction * (20.0 if flash == "shield" else 25.0)
            painter.setPen(world_pen(QColor(218, 234, 248, 75), 4.0))
            painter.drawLine(qt(start), qt(tip))
            painter.setPen(world_pen(QColor(246, 252, 255, 220), 1.2))
            painter.drawLine(qt(start), qt(tip))
            painter.drawLine(qt(tip - direction * 5.0 + across * 3.0), qt(tip))
            painter.drawLine(qt(tip - direction * 5.0 - across * 3.0), qt(tip))


def _draw_spectral_shield(
    painter: QPainter, center: Vec2, outline: QColor | None = None
) -> None:
    shape = (
        center + Vec2(-5.2, -6.2),
        center + Vec2(5.2, -6.2),
        center + Vec2(4.8, 1.0),
        center + Vec2(0.0, 7.4),
        center + Vec2(-4.8, 1.0),
    )
    edge = outline or QColor(96, 126, 146, 190)
    painter.setPen(world_pen(edge, 1.4))
    painter.setBrush(QColor(210, 232, 248, 105))
    painter.drawPolygon([qt(point) for point in shape])
    painter.setPen(world_pen(QColor(250, 255, 255, 210), 1.0))
    painter.drawPolygon(
        [
            qt(center + Vec2(0.0, -2.4)),
            qt(center + Vec2(1.4, -0.2)),
            qt(center + Vec2(0.0, 2.2)),
            qt(center + Vec2(-1.4, -0.2)),
        ]
    )


def _draw_swallowed(
    painter: QPainter,
    stickman: Stickman,
    squeeze: tuple[Vec2, Vec2, float],
    selected: bool,
    outline: QColor | None,
) -> None:
    """Him going down a mimic's throat: shrunk toward its mouth, hidden past it."""
    mouth, up, scale = squeeze
    if scale <= 0.01:
        return
    side = Vec2(-up.y, up.x) * 400.0
    clip = QPainterPath()
    out = up * 400.0
    corners = [mouth - side, mouth + side, mouth + side + out, mouth - side + out]
    clip.addPolygon(QPolygonF([qt(p) for p in corners]))
    painter.save()
    painter.setClipPath(clip)
    painter.translate(qt(mouth))
    painter.scale(scale, scale)
    painter.translate(-qt(mouth))
    draw_stickman(painter, stickman, selected, outline)
    painter.restore()


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
    """Far limbs, spine, head, then `between` (things held in front of the body),
    the near leg, `over_legs` (clothes covering the legs), then the near arm.
    Bones named in `hidden` are left out."""
    layout = actor.layout
    if transforms is None:
        transforms = actor.transforms()
    shown = [b.name for b in layout.skeleton.bones if b.name not in hidden]
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
                t = transforms[name]
                painter.drawLine(qt(t.start), qt(t.end))
        if has_head:
            painter.drawLine(qt(head.start), qt(neck_end))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(qt(head.end), radius, radius)

    def draw_bones(names: list[str], color: QColor) -> None:
        painter.setPen(pen(color, limb_width))
        for name in names:
            t = transforms[name]
            painter.drawLine(qt(t.start), qt(t.end))

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


def draw_stickman(
    painter: QPainter,
    stickman: Stickman,
    selected: bool = False,
    outline: QColor | None = None,
    transforms: dict[str, BoneTransform] | None = None,
    hide: Collection[str] = (),
) -> None:
    strokes = stickman.weapon_strokes()
    held = stickman.weapon_held
    variant = stickman.variant
    hidden = stickman.severed | set(hide)
    has = {name: name not in hidden for name in (stickman.layout.head, stickman.layout.torso)}
    equipment_behind = variant == "hero_fighter"
    if variant == "hero_fighter":
        posed = stickman.transforms() if transforms is None else transforms
        if getattr(stickman, "wings", False):
            _draw_dio_wings(painter, stickman, posed)
    if not held or equipment_behind:
        if equipment_behind:
            draw_trail(painter, stickman.trail)
        draw_strokes(painter, strokes)

    def costume(transforms) -> None:
        if variant == "wizard" and has[stickman.layout.head]:
            _draw_hat(painter, stickman, transforms)
        elif variant == "fighter" and has[stickman.layout.head]:
            _draw_helmet(painter, stickman, transforms)
        elif variant == "druid" and has[stickman.layout.head]:
            _draw_antlers(painter, stickman, transforms)
        if variant == "sorcerer" and has[stickman.layout.torso]:
            _draw_scarf(painter, stickman, transforms)
        if stickman.thrall and has[stickman.layout.head]:
            _draw_thrall_brain(painter, stickman, transforms)

    def over_legs(transforms) -> None:
        if variant == "cleric" and has[stickman.layout.torso]:
            _draw_robe(painter, stickman, transforms)
        if held and variant != "hero_fighter":
            draw_trail(painter, stickman.trail)
            draw_strokes(painter, strokes)

    near, far = CLASS_COLORS.get(variant, (NEAR_LIMB, FAR_LIMB))
    if stickman.thrall:
        near, far = _mix(near, FLAYER_SKIN, THRALL_TINT), _mix(far, FLAYER_SKIN_FAR, THRALL_TINT)
    head = BACKGROUND
    if stickman.damage:
        hurt = 0.72 * min(1.0, stickman.damage / stickman.max_hp)
        near, far = _mix(near, WOUNDED, hurt), _mix(far, WOUNDED, hurt)
    if stickman.burn is not None:
        char = stickman.burn.char
        near, far = _mix(near, CHARRED, char), _mix(far, CHARRED_FAR, char)
        head = _mix(head, CHARRED, char)
    if stickman.demise is not None:
        near, far, head = demise_colors(stickman.demise, near, far, head)
    transforms = draw_body(
        painter,
        stickman,
        near,
        far,
        head,
        costume,
        outline=outline,
        hidden=hidden,
        over_legs=over_legs,
        transforms=transforms,
    )

    if variant == "hero_fighter":
        _draw_hero_armor(painter, stickman, transforms, hidden)
        if has[stickman.layout.head]:
            _draw_hero_helmet(painter, stickman, transforms)

    if stickman.paralysed and has[stickman.layout.head]:
        _draw_stun(painter, stickman, transforms)
    if stickman.lure is not None and stickman.animated:
        head = transforms[stickman.layout.head].end
        draw_lure_alert(painter, head, stickman.layout.head_radius, stickman.lure_age)
    if selected:
        head = transforms[stickman.layout.head].end
        top = head - Vec2(0.0, stickman.layout.head_radius + 5.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(SELECTED)
        painter.drawPolygon([qt(top), qt(top + Vec2(-3.5, -5.0)), qt(top + Vec2(3.5, -5.0))])
    if selected and stickman.limbs_draggable:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for name, tip in stickman.limb_tips().items():
            painter.setPen(pen(TARGET if name == stickman.dragging_limb else GROUND, 1.5))
            painter.drawEllipse(qt(tip), 3.5, 3.5)


def _head_frame(stickman: Stickman, transforms) -> tuple[Vec2, Vec2, Vec2, float]:
    """Head center, its up and backward directions, and its radius."""
    head = transforms[stickman.layout.head]
    up = Vec2.from_angle(head.angle)
    back = Vec2(-stickman.facing, 0.0)
    return head.end, up, back, stickman.layout.head_radius


def _draw_thrall_brain(painter: QPainter, stickman: Stickman, transforms) -> None:
    """The intellect devourer riding a thrall's skull: a pink brain on top of his head."""
    center, up, _, r = _head_frame(stickman, transforms)
    _draw_brain(painter, center + up * (0.8 * r), 1.0 * r, 0.62 * r)


def _draw_brain(
    painter: QPainter, center: Vec2, rx: float, ry: float, outline: QColor | None = None
) -> None:
    """A pink brain: two lobes split by a groove, with a few folds."""
    if outline is not None:
        painter.setPen(world_pen(outline, 1.6))
        painter.setBrush(outline)
        painter.drawEllipse(qt(center), rx, ry)
    painter.setPen(world_pen(BRAIN_EDGE, max(0.4, 0.12 * ry)))
    painter.setBrush(BRAIN)
    painter.drawEllipse(qt(center), rx, ry)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(qt(center + Vec2(0.0, -ry * 0.9)), qt(center + Vec2(0.0, ry * 0.5)))
    for side in (-1.0, 1.0):
        for k, (x, y) in enumerate(((0.45, -0.35), (0.6, 0.2))):
            fold = center + Vec2(side * x * rx, y * ry)
            arc = 0.28 * rx
            painter.drawLine(qt(fold - Vec2(arc, 0.0)), qt(fold + Vec2(0.0, -0.25 * ry * (k + 1))))
            painter.drawLine(qt(fold + Vec2(0.0, -0.25 * ry * (k + 1))), qt(fold + Vec2(arc, 0.0)))


def _draw_stun(painter: QPainter, stickman: Stickman, transforms) -> None:
    """Purple sparks circling the head of a paralysed adventurer."""
    center, up, _, r = _head_frame(stickman, transforms)
    if stickman.knocked:
        up = Vec2(0.0, -1.0)
    ring = center + up * (1.7 * r)
    spin = stickman.stun * 6.0
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(PSYCHIC)
    for k in range(3):
        angle = spin + k * math.tau / 3
        point = ring + Vec2(math.cos(angle) * 1.3 * r, math.sin(angle) * 0.4 * r)
        painter.drawEllipse(qt(point), 0.28 * r, 0.28 * r)


def _polygon(painter: QPainter, points: Iterable[Vec2], fill: QColor, edge: QColor) -> None:
    painter.setPen(pen(edge, 1.0))
    painter.setBrush(fill)
    painter.drawPolygon([qt(p) for p in points])


def _draw_hat(painter: QPainter, stickman: Stickman, transforms) -> None:
    """A wizard's tall pointed hat, its tip flopping back, on a wide brim."""
    center, up, back, r = _head_frame(stickman, transforms)
    side = up.rotated(math.pi / 2)
    base = center + up * (0.7 * r)
    bend = base + up * (1.3 * r) + back * (0.25 * r)
    tip = base + up * (2.1 * r) + back * (1.1 * r)
    cone = [base - side * (0.85 * r), bend - side * (0.35 * r), tip, bend + side * (0.35 * r)]
    _polygon(painter, [*cone, base + side * (0.85 * r)], HAT, HAT_EDGE)
    brim = center + up * (0.55 * r)
    _polygon(
        painter,
        [
            brim - side * (1.5 * r),
            brim + side * (1.5 * r),
            brim + side * (1.2 * r) + up * (0.35 * r),
            brim - side * (1.2 * r) + up * (0.35 * r),
        ],
        HAT,
        HAT_EDGE,
    )
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(HAT_STAR)
    painter.drawEllipse(qt(base.lerp(bend, 0.5)), 0.22 * r, 0.22 * r)


def _draw_helmet(painter: QPainter, stickman: Stickman, transforms) -> None:
    """A steel knight's helmet with a dark visor, brow ridge and breathing vents."""
    center, up, _, r = _head_frame(stickman, transforms)
    forward = up.rotated(math.pi / 2) * stickman.facing

    def at(x: float, y: float) -> Vec2:
        return center + forward * (x * r) + up * (y * r)

    steel = WEAPON_COLORS["steel"]
    edge = QColor(70, 78, 94)
    _polygon(
        painter,
        [
            at(-1.0, -0.8),
            at(-1.0, 0.6),
            at(-0.55, 1.05),
            at(0.45, 1.05),
            at(0.95, 0.65),
            at(1.1, -0.65),
            at(0.35, -1.05),
        ],
        WEAPON_COLORS["metal"],
        edge,
    )
    _polygon(
        painter,
        [at(0.0, 0.65), at(0.95, 0.65), at(1.1, -0.65), at(0.35, -1.05)],
        steel,
        edge,
    )
    painter.setPen(world_pen(edge, 0.28 * r))
    painter.drawLine(qt(at(-0.25, 0.2)), qt(at(0.9, 0.2)))
    painter.setPen(world_pen(steel, 0.16 * r))
    painter.drawLine(qt(at(-0.55, 0.8)), qt(at(0.55, 0.8)))
    painter.setPen(world_pen(edge, 0.13 * r))
    for x in (0.2, 0.5, 0.8):
        painter.drawLine(qt(at(x, -0.3)), qt(at(x, -0.55)))


def _draw_hero_armor(
    painter: QPainter,
    stickman: Stickman,
    transforms: dict[str, BoneTransform],
    hidden: Collection[str],
) -> None:
    """Simple fitted full plate over the existing articulated stick-figure rig."""
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
    _polygon(painter, cuirass, HERO_PLATE_DARK, HERO_ARMOR_EDGE)
    light = (
        shoulder + across * (facing * 0.08 * r),
        shoulder + across * (facing * 1.12 * r) - up * (0.05 * r),
        waist + across * (facing * 0.68 * r),
        waist + across * (facing * 0.08 * r) - up * (0.12 * r),
    )
    _polygon(painter, light, HERO_PLATE, HERO_SILVER)
    painter.setPen(world_pen(HERO_SILVER, 0.12 * r))
    painter.drawLine(
        qt(shoulder + across * (facing * 0.18 * r) - up * (0.05 * r)),
        qt(waist + across * (facing * 0.12 * r)),
    )

    for side, color in (("l", HERO_PLATE_DARK), ("r", HERO_PLATE)):
        name = f"upper_arm_{side}"
        if name in hidden:
            continue
        joint = transforms[name].start
        painter.setPen(world_pen(HERO_ARMOR_EDGE, 0.9))
        painter.setBrush(color)
        painter.drawEllipse(qt(joint), 0.62 * r, 0.42 * r)

        for bone, start_width, end_width in (
            (f"upper_arm_{side}", 0.48, 0.38),
            (f"lower_arm_{side}", 0.42, 0.30),
            (f"upper_leg_{side}", 0.58, 0.44),
            (f"lower_leg_{side}", 0.46, 0.36),
        ):
            if bone in hidden:
                continue
            segment = transforms[bone]
            along = (segment.end - segment.start).normalized()
            across_segment = along.rotated(math.pi / 2)
            plate = (
                segment.start + across_segment * (start_width * r),
                segment.end + across_segment * (end_width * r),
                segment.end - across_segment * (end_width * r),
                segment.start - across_segment * (start_width * r),
            )
            _polygon(painter, plate, color, HERO_ARMOR_EDGE)

        boot = transforms[f"lower_leg_{side}"]
        if f"lower_leg_{side}" not in hidden:
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
                HERO_ARMOR_EDGE,
            )


def _draw_dio_wings(painter: QPainter, stickman: Stickman, transforms) -> None:
    """Articulated silver angel wings unfolding and flapping behind Dio."""
    torso = transforms[stickman.layout.torso]
    root = torso.end.lerp(torso.start, 0.22)
    back = Vec2(-float(stickman.facing), 0.0)
    up = Vec2(0.0, -1.0)
    opened = clamp(getattr(stickman, "wing_open", 1.0), 0.12, 1.0)
    beat = math.sin(getattr(stickman, "flight_clock", 0.0) * 8.0)
    for far, scale in ((True, 0.78), (False, 1.0)):
        lift = (5.0 + 7.0 * opened + 3.0 * beat) * scale
        reach = (7.0 + 17.0 * opened) * scale
        base = root + back * (2.0 if far else 0.5)
        elbow = base + back * (reach * 0.42) + up * lift
        tip = base + back * reach + up * (lift * 0.45)
        lower = base + back * (reach * 0.62) - up * (5.0 * opened)
        fill = HERO_WING_FAR if far else HERO_WING
        edge = HERO_PLATE_DARK if far else HERO_ARMOR_EDGE
        _polygon(painter, (base, elbow, tip, lower), fill, edge)
        painter.setPen(world_pen(HERO_WING_BONE, 1.3 if far else 1.7))
        painter.drawPolyline([qt(base), qt(elbow), qt(tip)])
        for fraction, drop in ((0.42, 4.0), (0.62, 5.5), (0.80, 6.5)):
            feather_root = base.lerp(tip, fraction)
            feather_tip = feather_root + back * (5.0 * scale) - up * (drop * opened * scale)
            painter.setPen(world_pen(edge, 2.6 if far else 3.2))
            painter.drawLine(qt(feather_root), qt(feather_tip))
            painter.setPen(world_pen(fill, 1.5 if far else 2.0))
            painter.drawLine(qt(feather_root), qt(feather_tip))


def _draw_hero_helmet(painter: QPainter, stickman: Stickman, transforms) -> None:
    """The established Fighter helmet with Dio's silver Spartan crest."""
    center, up, _, r = _head_frame(stickman, transforms)
    forward = up.rotated(math.pi / 2) * stickman.facing

    def at(x: float, y: float) -> Vec2:
        return center + forward * (x * r) + up * (y * r)

    crest = (
        at(-0.96, 0.82),
        at(-1.12, 1.48),
        at(-0.82, 1.98),
        at(-0.22, 2.14),
        at(0.38, 1.94),
        at(0.76, 1.46),
        at(0.66, 0.92),
        at(0.22, 1.12),
        at(-0.42, 1.18),
    )
    _polygon(painter, crest, HERO_SILVER, HERO_ARMOR_EDGE)
    _draw_helmet(painter, stickman, transforms)


def _draw_scarf(painter: QPainter, stickman: Stickman, transforms) -> None:
    """A pale pink neck wrap and two trailing ends, attached to the torso pose."""
    torso = transforms[stickman.layout.torso]
    neck = torso.end
    down = (torso.start - neck).normalized()
    back = Vec2(-stickman.facing, 0.0)
    r = stickman.layout.head_radius
    flutter = math.sin(getattr(stickman.weapon, "clock", 0.0) * 5.0) * 0.25 * r
    for length, drop in ((2.3, 0.6), (1.6, 1.15)):
        tip = neck + back * (length * r) + down * (drop * r + flutter)
        _polygon(
            painter,
            [neck, neck + down * (0.45 * r), tip + down * (0.4 * r), tip - back * (0.25 * r), tip],
            SCARF,
            SCARF_EDGE,
        )
    painter.setPen(world_pen(SCARF_EDGE, r * 0.7))
    painter.drawLine(qt(neck - back * (0.5 * r)), qt(neck + back * (0.5 * r)))
    painter.setPen(world_pen(SCARF, r * 0.45))
    painter.drawLine(qt(neck - back * (0.5 * r)), qt(neck + back * (0.5 * r)))


def _draw_robe(painter: QPainter, stickman: Stickman, transforms) -> None:
    """A cleric's white robe: fitted at the shoulders, belted with a gold sash, and a
    skirt that flares to mid-shin and swings with the legs. A gold stole runs down
    the front."""
    layout = stickman.layout
    r = layout.head_radius
    torso = transforms[layout.torso]
    down = (torso.start - torso.end).normalized()
    forward = down.rotated(math.pi / 2)
    if forward.x * stickman.facing < 0:
        forward = -forward
    hems = [
        transforms[f"lower_leg_{side}"].start.lerp(transforms[f"lower_leg_{side}"].end, 0.75)
        for side in ("l", "r")
    ]
    hem_back, hem_front = sorted(hems, key=lambda point: point.dot(forward))
    hem_front += forward * (1.05 * r)
    hem_back -= forward * (1.05 * r)
    waist = torso.start - down * (0.15 * r)
    hem_middle = hem_front.lerp(hem_back, 0.5) + down * (0.3 * r)

    def flare(top: Vec2, bottom: Vec2, side: Vec2) -> Vec2:
        return top.lerp(bottom, 0.5) + side * (0.2 * r)

    path = QPainterPath(qt(torso.end - forward * (0.45 * r)))
    path.quadTo(qt(torso.end - down * (0.15 * r)), qt(torso.end + forward * (0.45 * r)))
    path.lineTo(qt(waist + forward * (0.45 * r)))
    path.quadTo(qt(flare(waist + forward * (0.45 * r), hem_front, forward)), qt(hem_front))
    path.quadTo(qt(hem_middle), qt(hem_back))
    path.quadTo(
        qt(flare(waist - forward * (0.45 * r), hem_back, -forward)),
        qt(waist - forward * (0.45 * r)),
    )
    path.closeSubpath()
    painter.setPen(pen(ROBE_EDGE, 1.0))
    painter.setBrush(ROBE)
    painter.drawPath(path)

    painter.setPen(world_pen(ROBE_SASH, 0.22 * r))
    painter.drawLine(qt(torso.end + forward * (0.2 * r)), qt(hem_middle.lerp(hem_front, 0.4)))
    painter.setPen(world_pen(ROBE_SASH, 0.32 * r))
    painter.drawLine(qt(waist - forward * (0.6 * r)), qt(waist + forward * (0.6 * r)))


def _draw_antlers(painter: QPainter, stickman: Stickman, transforms) -> None:
    """A druid's crown: a leafy green circlet with a pair of elk antlers rising from it,
    each a curving beam with tines off its front."""
    center, up, back, head = _head_frame(stickman, transforms)
    side = up.rotated(math.pi / 2)
    band = center + up * (0.62 * head)
    r = 0.62 * head
    for spread, width in ((-1.0, 0.85), (1.0, 1.0)):
        root = band + side * (spread * 0.35 * head)
        out = side * spread
        beam = [
            root,
            root + up * (0.9 * r) + out * (0.35 * r) + back * (0.15 * r),
            root + up * (1.7 * r) + out * (0.95 * r) + back * (0.35 * r),
            root + up * (2.3 * r) + out * (1.7 * r) + back * (0.3 * r),
        ]
        tines = [
            (beam[1], beam[1] + up * (0.75 * r) - out * (0.15 * r)),
            (beam[2], beam[2] + up * (0.8 * r) - out * (0.1 * r)),
            (beam[2].lerp(beam[3], 0.5), beam[2].lerp(beam[3], 0.5) + up * (0.6 * r)),
        ]
        for color, extra in ((ANTLER_EDGE, 0.16 * head), (ANTLER, 0.0)):
            painter.setPen(world_pen(color, width * 0.24 * head + extra))
            for a, b in zip(beam, beam[1:], strict=False):
                painter.drawLine(qt(a), qt(b))
            painter.setPen(world_pen(color, width * 0.17 * head + extra))
            for a, b in tines:
                painter.drawLine(qt(a), qt(b))
    painter.setPen(world_pen(CIRCLET, 0.28 * head))
    painter.drawLine(qt(band - side * (0.85 * head)), qt(band + side * (0.85 * head)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(WEAPON_COLORS["leaf"])
    for k in (-0.5, 0.0, 0.5):
        leaf = band + side * (k * head) + up * (0.12 * head)
        painter.drawEllipse(qt(leaf), 0.18 * head, 0.13 * head)


def _draw_vines(painter: QPainter, spells: Spells) -> None:
    for vine in spells.vines:
        points = vine.path()
        fade = min(1.0, (VINE_TIME - vine.age) / 0.25)
        count = len(points) - 1
        for color, extra in ((VINE_DARK, 1.0), (VINE, 0.0)):
            for i, (a, b) in enumerate(zip(points, points[1:], strict=False)):
                taper = 1.0 - 0.7 * i / count
                painter.setPen(world_pen(_alpha(color, 255 * fade), 3.0 * taper + extra))
                painter.drawLine(qt(a), qt(b))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_alpha(WEAPON_COLORS["leaf"], 255 * fade))
        for i in range(2, count, 3):
            a, b = points[i], points[i + 1]
            along = (b - a).normalized()
            out = along.rotated((1 if i % 2 else -1) * math.pi / 2.6)
            leaf_at = a + out * 2.2
            painter.drawEllipse(qt(leaf_at), 1.4, 1.0)
        if vine.age < VINE_GROW + 0.15:
            tip = points[-1]
            painter.setBrush(_alpha(VINE_DARK, 255 * fade))
            painter.drawEllipse(qt(tip), 1.6, 1.6)


def draw_spells(painter: QPainter, spells: Spells) -> None:
    """Vines, heal pulses, arrows, magic missile darts with their trails, and sparks."""
    _draw_vines(painter, spells)
    for pulse in spells.pulses:
        t = pulse.age / PULSE_TIME
        radius = pulse.radius * smoothstep(min(1.0, t * 1.4))
        painter.setPen(pen(_alpha(HOLY, 230 * (1.0 - t)), 1.0 + 2.5 * (1.0 - t)))
        painter.setBrush(_alpha(HOLY, 50 * (1.0 - t)))
        painter.drawEllipse(qt(pulse.center), radius, radius)
    for arrow in spells.arrows:
        fade = 1.0
        if arrow.stuck is not None:
            fade = clamp((ARROW_STUCK_TIME - arrow.stuck) / 0.5, 0.0, 1.0)
        along = arrow.velocity.normalized() if arrow.stuck is None else arrow.heading
        tail = arrow.position - along * 8.0
        painter.setPen(world_pen(_alpha(WEAPON_COLORS["wood"], 255 * fade), 0.9))
        painter.drawLine(qt(tail), qt(arrow.position))
        painter.setPen(world_pen(_alpha(WEAPON_COLORS["steel"], 255 * fade), 1.6))
        painter.drawLine(qt(arrow.position - along * 1.5), qt(arrow.position))
        painter.setPen(world_pen(_alpha(HOLY, 220 * fade), 1.2))
        painter.drawLine(qt(tail), qt(tail + along * 2.0))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for missile in spells.missiles:
        color = FIRE_SPARK if missile.kind == "fire" else MAGIC
        core = FIRE_SPARK_CORE if missile.kind == "fire" else MAGIC_CORE
        for trail in missile.darts:
            for i, (a, b) in enumerate(zip(trail, trail[1:], strict=False)):
                strength = (i + 1) / len(trail)
                painter.setPen(world_pen(_alpha(color, 200 * strength), 0.6 + 1.6 * strength))
                painter.drawLine(qt(a), qt(b))
            head = trail[-1]
            heading = (head - trail[-2]).normalized() if len(trail) > 1 else Vec2(1.0, 0.0)
            side = heading.rotated(math.pi / 2)
            dart = [
                head + heading * 2.6,
                head + side * 1.1,
                head - heading * 1.8,
                head - side * 1.1,
            ]
            painter.setPen(pen(color, 1.0))
            painter.setBrush(core)
            painter.drawPolygon([qt(p) for p in dart])
            painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(Qt.PenStyle.NoPen)
    for spark in spells.sparks:
        t = spark.age / SPARK_LIFE
        painter.setBrush(_alpha(SPARK_COLORS[spark.color], 240 * (1.0 - t)))
        painter.drawEllipse(qt(spark.position), 1.3 * (1.0 - 0.5 * t), 1.3 * (1.0 - 0.5 * t))


def draw_burn(painter: QPainter, burn: Burn) -> None:
    """Flames rising off a burning body: little tongues that cool from a yellow core
    through orange and red into thin smoke."""
    painter.setPen(Qt.PenStyle.NoPen)
    for ember in burn.embers:
        t = ember.age / ember.life
        r = ember.size * (1.0 - 0.5 * t)
        base = ember.position
        if t < 0.7:
            color = _mix(FLAME_MID, FLAME_RED, t / 0.7)
            alpha = 230 * (1.0 - 0.4 * t / 0.7)
        else:
            color, alpha = FLAME_SMOKE, 120 * (1.0 - t) / 0.3
        tip = base + Vec2(-ember.velocity.x * 0.04, -2.6 * r)
        tongue = [
            base + Vec2(-r, 0.0),
            base + Vec2(-0.6 * r, 0.8 * r),
            base + Vec2(0.6 * r, 0.8 * r),
            base + Vec2(r, 0.0),
            tip,
        ]
        painter.setBrush(_alpha(color, alpha))
        painter.drawPolygon([qt(point) for point in tongue])
        if t < 0.35:
            painter.setBrush(_alpha(FLAME_HOT, 230 * (1.0 - t / 0.35)))
            painter.drawEllipse(qt(base + Vec2(0.0, -0.2 * r)), 0.45 * r, 0.6 * r)


def draw_gore(painter: QPainter, gore: Gore) -> None:
    """Splats flattened on whatever they hit, then flying droplets stretched along
    their motion."""
    painter.setPen(Qt.PenStyle.NoPen)
    for splat in gore.splats:
        fade = 1.0 - max(0.0, (splat.age - 0.6 * SPLAT_LIFE) / (0.4 * SPLAT_LIFE))
        painter.setBrush(_alpha(BLOOD_DARK, 220 * fade))
        center = splat.position - Vec2(0.0, splat.width * 0.15)
        painter.drawEllipse(qt(center), splat.width, splat.width * 0.3)
    for drop in gore.drops:
        fade = 1.0 - drop.age / DROP_LIFE
        painter.setBrush(_alpha(BLOOD, 240 * fade))
        streak = drop.velocity * 0.012
        tail = drop.position - streak
        size = drop.size
        side = Vec2(-streak.y, streak.x).normalized() * (size * 0.8)
        painter.drawPolygon([qt(drop.position + side), qt(tail), qt(drop.position - side)])
        painter.drawEllipse(qt(drop.position), size, size)


def draw_goblin(painter: QPainter, goblin: Goblin, outline: QColor | None = None) -> None:
    facing = goblin.facing
    radius = goblin.layout.head_radius
    s = goblin.layout.scale

    def ear(transforms) -> None:
        center = transforms[goblin.layout.head].end
        back = -facing
        points = [
            center + Vec2(back * 0.5 * radius, -0.7 * radius),
            center + Vec2(back * (radius + 8.0 * s), -1.1 * radius),
            center + Vec2(back * 0.9 * radius, 0.1 * radius),
        ]
        painter.setPen(pen(GOBLIN_SKIN, max(0.6, 1.5 * s)))
        painter.setBrush(GOBLIN_HEAD)
        painter.drawPolygon([qt(p) for p in points])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(GOBLIN_EYE)
        eye = max(0.6, 1.5 * s)
        painter.drawEllipse(qt(center + Vec2(facing * 0.45 * radius, -0.15 * radius)), eye, eye)
        painter.setPen(pen(GOBLIN_SKIN, max(0.5, 1.2 * s)))
        mouth = center + Vec2(facing * 0.35 * radius, 0.4 * radius)
        painter.drawLine(qt(mouth), qt(mouth + Vec2(facing * 3.0, -0.8) * s))
        if held:
            draw_strokes(painter, strokes)
            if isinstance(weapon, Banner):
                _draw_banner_cloth(painter, weapon, transforms, facing)

    weapon = goblin.weapon
    strokes = weapon.strokes(goblin.transforms(), facing)
    held = weapon.held
    if not held:
        if isinstance(weapon, Banner):
            _draw_banner_cloth(painter, weapon, goblin.transforms(), facing)
        draw_strokes(painter, strokes)
    draw_body(painter, goblin, GOBLIN_SKIN, GOBLIN_FAR, GOBLIN_HEAD, ear, outline=outline)


def draw_skeletons(
    painter: QPainter, skeletons: Iterable[Skeleton], outline: QColor | None = None
) -> None:
    for skeleton in skeletons:
        draw_skeleton(painter, skeleton, outline)


def draw_skeleton(painter: QPainter, skeleton: Skeleton, outline: QColor | None = None) -> None:
    """Bare bones: knobbly limbs, a ribcage, a skull with green pinpoint eyes. Rising,
    it claws its way up out of the ground it stands on."""
    layout = skeleton.layout
    transforms = skeleton.transforms()
    facing = skeleton.facing
    rise = smoothstep(clamp(skeleton.rising, 0.0, 1.0))
    painter.save()
    if rise < 1.0:
        ground = skeleton.contact()
        _draw_dirt(painter, ground, skeleton.risen)
        painter.setClipRect(QRectF(ground.x - 60.0, ground.y - 200.0, 120.0, 200.0))
        painter.translate(0.0, (1.0 - rise) * 46.0)
    head = transforms[layout.head]
    radius = layout.head_radius
    names = [b.name for b in layout.skeleton.bones if b.name != layout.head]
    far = [n for n in names if n.endswith("_l")]
    near = [n for n in names if not n.endswith("_l") and n not in (layout.torso, layout.pelvis)]
    spine = [layout.pelvis, layout.torso]
    if outline is not None:
        painter.setPen(pen(outline, 3.6))
        for name in names:
            painter.drawLine(qt(transforms[name].start), qt(transforms[name].end))
        painter.setBrush(outline)
        painter.drawEllipse(qt(head.end), radius + 1.2, radius + 1.2)
    weapon = skeleton.weapon
    strokes = weapon.strokes(transforms, facing)
    if not weapon.held:
        draw_strokes(painter, strokes)
    _draw_bones(painter, transforms, far, SKELETON_FAR)
    _draw_ribs(painter, transforms[layout.torso], facing)
    _draw_bones(painter, transforms, spine, SKELETON_BONE, knobs=False)
    _draw_skull(painter, head.end, radius, facing, skeleton.dead)
    if weapon.held:
        draw_strokes(painter, strokes)
    _draw_bones(painter, transforms, near, SKELETON_BONE)
    painter.restore()


def _draw_bones(
    painter: QPainter,
    transforms: dict[str, BoneTransform],
    names: Iterable[str],
    color: QColor,
    knobs: bool = True,
) -> None:
    for name in names:
        t = transforms[name]
        painter.setPen(pen(color, 1.3))
        painter.drawLine(qt(t.start), qt(t.end))
        if knobs:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(qt(t.start), 1.0, 1.0)
            painter.drawEllipse(qt(t.end), 0.9, 0.9)


def _draw_ribs(painter: QPainter, torso: BoneTransform, facing: int) -> None:
    along = torso.end - torso.start
    length = along.length()
    if length < 1e-6:
        return
    up = along * (1.0 / length)
    side = Vec2(-up.y, up.x) * (1.0 if side_sign(up, facing) else -1.0)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(pen(SKELETON_BONE, 0.9))
    for share, width in ((0.45, 3.2), (0.62, 3.8), (0.79, 3.4)):
        middle = torso.start + along * share
        path = QPainterPath(qt(middle - side * width))
        path.quadTo(qt(middle + up * 1.6), qt(middle + side * width))
        painter.drawPath(path)
    hip = torso.start
    painter.setPen(pen(SKELETON_BONE, 1.0))
    painter.drawLine(qt(hip - side * 2.6), qt(hip + side * 2.6))


def side_sign(up: Vec2, facing: int) -> bool:
    return (Vec2(-up.y, up.x).x >= 0.0) == (facing > 0)


def _draw_skull(painter: QPainter, center: Vec2, radius: float, facing: int, dead: bool) -> None:
    f = float(facing)
    painter.setPen(pen(SKELETON_FAR, 0.7))
    painter.setBrush(SKELETON_BONE)
    painter.drawEllipse(qt(center + Vec2(-0.1 * f * radius, -0.05 * radius)), radius, radius * 0.95)
    jaw = QRectF(
        center.x + f * 0.05 * radius - 0.55 * radius,
        center.y + 0.55 * radius,
        1.1 * radius,
        0.55 * radius,
    )
    painter.drawRoundedRect(jaw, 1.0, 1.0)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(SKELETON_SOCKET)
    eye = center + Vec2(f * 0.42 * radius, -0.05 * radius)
    painter.drawEllipse(qt(eye), 0.32 * radius, 0.36 * radius)
    painter.drawEllipse(qt(eye + Vec2(-f * 0.55 * radius, 0.0)), 0.22 * radius, 0.32 * radius)
    painter.drawEllipse(
        qt(center + Vec2(f * 0.62 * radius, 0.38 * radius)), 0.12 * radius, 0.16 * radius
    )
    painter.setPen(pen(SKELETON_SOCKET, 0.5))
    for k in range(3):
        x = center.x + f * (0.05 + 0.22 * k) * radius
        painter.drawLine(QPointF(x, center.y + 0.6 * radius), QPointF(x, center.y + 1.0 * radius))
    if not dead:
        glow = QRadialGradient(qt(eye), radius * 0.9)
        glow.setColorAt(0.0, QColor(110, 255, 140, 150))
        glow.setColorAt(1.0, QColor(110, 255, 140, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(qt(eye), radius * 0.9, radius * 0.9)
        painter.setBrush(SKELETON_EYE)
        painter.drawEllipse(qt(eye), 0.13 * radius + 0.3, 0.13 * radius + 0.3)


def _draw_dirt(painter: QPainter, ground: Vec2, age: float) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    fade = max(0.0, 1.0 - age / 1.4)
    painter.setBrush(_alpha(SKELETON_DIRT, 200 * fade))
    painter.drawEllipse(QRectF(ground.x - 11.0, ground.y - 2.0, 22.0, 4.0))
    for k in range(6):
        t = (age * 1.6 + k * 0.17) % 1.0
        x = ground.x + (k - 2.5) * 3.5 + math.sin(k * 7.0) * 2.0
        y = ground.y - 14.0 * t * (1.0 - t) * 4.0 * 0.5
        painter.setBrush(_alpha(SKELETON_DIRT if k % 2 else SKELETON_FAR, 220 * fade * (1.0 - t)))
        painter.drawEllipse(QPointF(x, y), 0.9, 0.9)


def _draw_banner_cloth(
    painter: QPainter, banner: Banner, transforms: dict[str, BoneTransform], facing: int
) -> None:
    """A ragged war flag streaming back from the top of the pole, rippling."""
    top, up = banner.top(transforms, facing)
    s = banner.scale
    back = Vec2(-facing * 1.0, 0.0)
    width, height = 26.0 * s, 16.0 * s
    clock = banner.clock
    upper, lower = [], []
    for k in range(5):
        t = k / 4
        wave = math.sin(clock * 9.0 - t * 4.0) * 2.5 * s * t
        along = top + back * (width * t)
        upper.append(along + Vec2(0.0, wave))
        lower.append(along + Vec2(0.0, height * (1.0 - 0.25 * t) + wave))
    lower[-1] = lower[-1] + back * (-4.0 * s) + Vec2(0.0, -height * 0.3)
    painter.setPen(world_pen(BANNER_EDGE, 0.8 * s * 3.0))
    painter.setBrush(BANNER)
    painter.drawPolygon([qt(p) for p in upper + lower[::-1]])
    middle = top + back * (width * 0.4) + Vec2(0.0, height * 0.45)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(GOBLIN_EYE)
    painter.drawEllipse(qt(middle), 3.0 * s, 3.0 * s)
    painter.setBrush(BANNER_EDGE)
    painter.drawEllipse(qt(middle), 1.2 * s, 1.8 * s)


def draw_spears(painter: QPainter, spears: Spears) -> None:
    for spear in spears.spears:
        alpha = 255 * (1.0 - spear.fade)
        direction = Vec2.from_angle(spear.angle + spear.quiver)
        tip = spear.position
        butt = tip - direction * spear.length
        head = tip - direction * (spear.length * 0.2)
        painter.setPen(world_pen(_alpha(WEAPON_COLORS["wood"], alpha), 1.2))
        painter.drawLine(qt(butt), qt(head))
        painter.setPen(world_pen(_alpha(WEAPON_COLORS["steel"], alpha), 2.0))
        painter.drawLine(qt(head), qt(tip))


def draw_vial(painter: QPainter, center: Vec2, angle: float) -> None:
    s = VIAL_SCALE
    neck = Vec2.from_angle(angle) * s
    painter.setPen(world_pen(VIAL_GLASS, 1.0 * s))
    painter.setBrush(VIAL_RED)
    painter.drawEllipse(qt(center), 2.8 * s, 2.8 * s)
    painter.setPen(world_pen(VIAL_GLASS, 1.6 * s))
    painter.drawLine(qt(center + neck * 2.6), qt(center + neck * 4.6))
    painter.setPen(world_pen(VIAL_CORK, 1.8 * s))
    painter.drawLine(qt(center + neck * 4.6), qt(center + neck * 5.8))


def draw_vials(painter: QPainter, vials: Vials) -> None:
    for vial in vials.flying:
        draw_vial(painter, vial.position, vial.spin)
    for explosion in vials.explosions:
        t = explosion.age / vials.explosion_time
        fade = 1.0 - t
        outer = QColor(BLAST_OUTER)
        outer.setAlpha(int(170 * fade))
        inner = QColor(BLAST_INNER)
        inner.setAlpha(int(230 * fade * fade))
        radius = explosion.radius * (0.35 + 0.65 * smoothstep(min(1.0, t * 2.2)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(outer)
        painter.drawEllipse(qt(explosion.center), radius, radius)
        painter.setBrush(inner)
        painter.drawEllipse(qt(explosion.center), radius * 0.55, radius * 0.55)
        painter.setPen(world_pen(outer, 1.5))
        for k in range(8):
            ray = Vec2.from_angle(0.3 + k * 0.785, 1.0)
            painter.drawLine(
                qt(explosion.center + ray * radius * 0.9),
                qt(explosion.center + ray * radius * (1.1 + 0.4 * t)),
            )


def draw_strokes(painter: QPainter, strokes) -> None:
    for stroke in strokes:
        color = WEAPON_COLORS[stroke.kind]
        painter.setPen(world_pen(color, stroke.width))
        if stroke.shape:
            painter.setBrush(color)
            painter.drawPolygon([qt(p) for p in stroke.shape])
            painter.setBrush(Qt.BrushStyle.NoBrush)
        else:
            painter.drawLine(qt(stroke.start), qt(stroke.end))


def draw_trail(painter: QPainter, trail: list[Vec2]) -> None:
    for i, (a, b) in enumerate(zip(trail, trail[1:], strict=False)):
        color = QColor(TRAIL)
        color.setAlpha(int(200 * (i + 1) / len(trail)))
        painter.setPen(world_pen(color, 1.0 + 2.0 * (i + 1) / len(trail)))
        painter.drawLine(qt(a), qt(b))


def draw_projectiles(painter: QPainter, projectiles: Projectiles) -> None:
    painter.setPen(world_pen(BULLET, 1.5))
    for bullet in projectiles.bullets:
        tail = bullet.position - bullet.velocity.normalized() * 6.0
        painter.drawLine(qt(tail), qt(bullet.position))
    for spark in projectiles.sparks:
        t = spark.age / projectiles.spark_life
        color = QColor(SPARK)
        color.setAlpha(int(255 * (1.0 - t)))
        painter.setPen(world_pen(color, 1.2))
        size = 2.0 + 5.0 * t
        for k in range(4):
            ray = Vec2.from_angle(0.6 + k * 1.5708, size)
            painter.drawLine(qt(spark.position + ray * 0.4), qt(spark.position + ray))


def _alpha(color: QColor, alpha: float) -> QColor:
    result = QColor(color)
    result.setAlpha(max(0, min(255, int(alpha))))
    return result


def draw_worm(painter: QPainter, worm: Worm, outline: QColor | None = None) -> None:
    """Buried segments are a faint silhouette (or hidden, see `BURIED_WORM_VISIBLE`);
    exposed ones are solid."""
    points = worm.points
    buried = [worm.buried(p) for p in points]
    runs: list[list[Vec2]] = []
    for i in range(len(points) - 1):
        if BURIED_WORM_VISIBLE and buried[i] and buried[i + 1]:
            if not runs or runs[-1][-1] != points[i]:
                runs.append([points[i]])
            runs[-1].append(points[i + 1])
    stroker = QPainterPathStroker()
    stroker.setWidth(2.0 * worm.radius(len(points) // 3))
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(world_pen(WORM_GHOST_EDGE, 1.0))
    painter.setBrush(WORM_GHOST)
    for run in runs:
        path = QPainterPath(qt(run[0]))
        for point in run[1:]:
            path.lineTo(qt(point))
        shape = stroker.createStroke(path).simplified()
        painter.drawPath(shape)

    exposed = [i for i in range(len(points) - 1, 0, -1) if not (buried[i] and buried[i - 1])]
    if outline is not None:
        for i in exposed:
            painter.setPen(world_pen(outline, 2.0 * worm.radius(i) + 2.0))
            painter.drawLine(qt(points[i]), qt(points[i - 1]))
    for i in exposed:
        painter.setPen(world_pen(WORM_SKIN, 2.0 * worm.radius(i)))
        painter.drawLine(qt(points[i]), qt(points[i - 1]))
    painter.setPen(world_pen(WORM_RIDGE, 0.8))
    for i in exposed:
        if i % 2 == 0:
            along = (points[i - 1] - points[i]).normalized()
            across = Vec2(-along.y, along.x) * (worm.radius(i) * 0.85)
            painter.drawLine(qt(points[i] + across), qt(points[i] - across))

    head = worm.head
    radius = worm.radius(0)
    if buried[0]:
        if not BURIED_WORM_VISIBLE:
            return
        painter.setPen(world_pen(WORM_GHOST_EDGE, 1.0))
        painter.setBrush(WORM_GHOST)
        painter.drawEllipse(qt(head + Vec2.from_angle(worm.heading, 1.5)), radius, radius)
        return
    _draw_worm_head(painter, head, worm.heading, radius * WORM_HEAD_SCALE, worm.mouth, outline)


def _draw_worm_head(
    painter: QPainter,
    center: Vec2,
    heading: float,
    radius: float,
    mouth: float,
    outline: QColor | None,
) -> None:
    """A head with a gaping jaw cut into its front, always open and lined with white
    triangle teeth; `mouth` (0..1) opens it wider for a strike."""
    half = WORM_JAW_OPEN + WORM_JAW_STRIKE * mouth
    forward = Vec2.from_angle(heading)
    hinge = center - forward * (radius * 0.3)

    def rim(angle: float, scale: float = 1.0) -> Vec2:
        return center + Vec2.from_angle(angle, radius * scale)

    steps = 28
    around = [rim(heading + half + (math.tau - 2 * half) * k / steps) for k in range(steps + 1)]
    skull = [qt(hinge), *(qt(p) for p in around)]
    if outline is not None:
        painter.setPen(world_pen(outline, 2.0))
        painter.setBrush(outline)
        painter.drawPolygon(skull)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(WORM_SKIN)
    painter.drawPolygon(skull)

    throat = [rim(heading - half + 2 * half * k / 10, 0.8) for k in range(11)]
    painter.setBrush(WORM_MOUTH)
    painter.drawPolygon([qt(hinge), *(qt(p) for p in throat)])
    gums = [qt(hinge), qt(rim(heading + half)), qt(rim(heading - half))]
    painter.setPen(world_pen(WORM_MOUTH, 1.2))
    painter.drawPolyline([gums[1], gums[0], gums[2]])
    painter.setPen(Qt.PenStyle.NoPen)

    painter.setBrush(WORM_TOOTH)
    for side in (-1.0, 1.0):
        tip = rim(heading + side * half)
        edge = tip - hinge
        along = edge.normalized()
        inward = (forward - along * forward.dot(along)).normalized()
        count = WORM_TEETH_PER_JAW
        width = edge.length() * 0.7 / count
        for k in range(count):
            base = hinge + edge * (0.3 + 0.7 * (k + 0.5) / count)
            length = width * (1.0 + 0.5 * k / max(1, count - 1))
            painter.drawPolygon(
                [
                    qt(base - along * (width / 2)),
                    qt(base + along * (width / 2)),
                    qt(base + inward * length + along * (width * 0.15)),
                ]
            )


def _clip_to(boxes: Iterable[Rect]) -> QPainterPath:
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.WindingFill)
    for box in boxes:
        path.addRect(QRectF(box.x, box.y, box.width, box.height))
    return path


def draw_holes(painter: QPainter, debris: Debris, boxes: Sequence[Rect]) -> None:
    """Holes torn in the windows: a jagged dark pit with a ring of churned dirt,
    showing only on the window it was torn in."""
    painter.setPen(Qt.PenStyle.NoPen)
    for hole in debris.holes:
        ground = hole.ground(boxes)
        if ground is None:
            continue
        fade = min(1.0, (HOLE_LIFE - hole.age) / HOLE_FADE)
        opened = smoothstep(min(1.0, hole.age * 6.0))
        painter.save()
        painter.setClipPath(_clip_to([ground]))
        radius = hole.radius * opened
        painter.setBrush(_alpha(DIRT, 235 * fade))
        painter.drawPolygon(_hole_edge(hole, radius * 1.35))
        painter.setBrush(_alpha(DIRT_DARK, 245 * fade))
        painter.drawPolygon(_hole_edge(hole, radius * 1.1))
        painter.setBrush(_alpha(HOLE, 250 * fade))
        painter.drawPolygon(_hole_edge(hole, radius * 0.85))
        painter.restore()


def _hole_edge(hole: Hole, radius: float) -> list[QPointF]:
    count = len(hole.outline)
    return [
        qt(hole.center + Vec2.from_angle(math.tau * k / count, r * radius))
        for k, r in enumerate(hole.outline)
    ]


def draw_debris(painter: QPainter, debris: Debris, ground: Sequence[Rect] = ()) -> None:
    """Dust, impact rings and flying dirt. Cracks only show on `ground` (the windows
    and the bottom border)."""
    painter.setPen(Qt.PenStyle.NoPen)
    for puff in debris.puffs:
        t = puff.age / puff.life
        radius = puff.radius * (1.0 + 1.6 * smoothstep(t))
        painter.setBrush(_alpha(DUST, 110 * (1.0 - t) ** 1.5))
        painter.drawEllipse(qt(puff.position), radius, radius)

    painter.setBrush(Qt.BrushStyle.NoBrush)
    for ring in debris.rings:
        t = ring.age / ring.life
        center = ring.center
        shock = min(1.0, t * 4.0)
        if shock < 1.0:
            radius = ring.radius * (0.4 + 1.4 * smoothstep(shock))
            painter.setPen(world_pen(_alpha(SHOCKWAVE, 230 * (1.0 - shock)), 3.0 * (1.0 - shock)))
            painter.drawEllipse(qt(center), radius, radius * 0.7)
        swell = min(1.0, t * 3.0)
        radius = ring.radius * (0.5 + 0.8 * smoothstep(swell))
        painter.setPen(world_pen(_alpha(DUST, 200 * (1.0 - swell)), 2.5))
        painter.drawEllipse(qt(center), radius, radius * 0.75)
        if not ground or not ring.cracks:
            continue
        crack_fade = 1.0 - smoothstep(max(0.0, (t - 0.5) / 0.5))
        grow = smoothstep(min(1.0, t * 8.0))
        painter.save()
        painter.setClipPath(_clip_to(ground))
        painter.setPen(world_pen(_alpha(DIRT_DARK, 240 * crack_fade), 1.3))
        for crack in ring.cracks:
            path = QPainterPath(qt(center + crack[0] * ring.radius))
            for point in crack[1:]:
                path.lineTo(qt(center + point * (ring.radius * grow)))
            painter.drawPath(path)
        painter.restore()

    painter.setPen(Qt.PenStyle.NoPen)
    for particle in debris.particles:
        fade = 1.0 - particle.age / particle.life
        painter.setBrush(_alpha(DIRT_SHADES[particle.shade], 255 * min(1.0, fade * 2.0)))
        size = particle.size
        if particle.chunk:
            corners = [
                particle.position + Vec2.from_angle(particle.angle + k, size * r)
                for k, r in ((0.0, 1.0), (1.7, 0.75), (3.0, 0.95), (4.6, 0.7))
            ]
            painter.drawPolygon([qt(c) for c in corners])
        else:
            painter.drawEllipse(qt(particle.position), size, size)


def draw_surfaces(painter: QPainter, surfaces: Iterable[Surface]) -> None:
    for surface in surfaces:
        color = WALK_SURFACE if surface.walkable else CLIMB_SURFACE
        painter.setPen(pen(color, 3))
        if surface.walkable:
            painter.drawLine(qt(surface.start), qt(surface.end))
        elif surface.hanging:
            grip = Vec2(0.0, surface.grip + 3.0)
            painter.drawLine(
                qt(Vec2(surface.start.x, 0.0) + grip), qt(Vec2(surface.end.x, 0.0) + grip)
            )
        else:
            offset = surface.normal * 3.0
            painter.drawLine(
                qt(surface.lip + offset), qt(Vec2(surface.start.x, surface.wall_bottom) + offset)
            )
            painter.setPen(pen(color, 1.5, Qt.PenStyle.DotLine))
            painter.drawLine(
                qt(Vec2(surface.start.x, surface.wall_bottom) + offset), qt(surface.end + offset)
            )


def draw_kill_counter(painter: QPainter, kills: int, corner: Vec2, bump: float = 0.0) -> None:
    """A small skull-and-number pill whose bottom-right corner sits at `corner`.
    `bump` (1 just after a kill, decaying to 0) briefly enlarges it."""
    font = QFont(painter.font())
    font.setPixelSize(13)
    font.setBold(True)
    text = str(kills)
    text_width = QFontMetricsF(font).horizontalAdvance(text)
    height, skull, gap, pad = 24.0, 7.0, 6.0, 9.0
    width = pad + 2 * skull + gap + text_width + pad

    painter.save()
    painter.translate(corner.x - width / 2, corner.y - height / 2)
    painter.scale(1.0 + 0.25 * bump, 1.0 + 0.25 * bump)
    painter.translate(-width / 2, -height / 2)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(COUNTER_BACK)
    painter.drawRoundedRect(QRectF(0, 0, width, height), height / 2, height / 2)

    center = Vec2(pad + skull, height / 2 - 1.0)
    painter.setBrush(_alpha(SKULL, 255) if bump == 0.0 else _alpha(WORM_SKIN, 255))
    painter.drawEllipse(qt(center), skull, skull * 0.9)
    painter.drawRoundedRect(QRectF(center.x - 4.0, center.y + 3.0, 8.0, 5.5), 1.5, 1.5)
    painter.setBrush(COUNTER_BACK.darker(150))
    for side in (-1.0, 1.0):
        painter.drawEllipse(qt(center + Vec2(2.8 * side, 0.5)), 2.0, 2.2)
    painter.drawPolygon(
        [qt(center + Vec2(0.0, 3.0)), qt(center + Vec2(-1.0, 4.6)), qt(center + Vec2(1.0, 4.6))]
    )

    painter.setFont(font)
    painter.setPen(COUNTER_TEXT)
    left = pad + 2 * skull + gap
    painter.drawText(QRectF(left, 0, text_width + 1.0, height), Qt.AlignmentFlag.AlignVCenter, text)
    painter.restore()


def draw_kill_marks(painter: QPainter, marks: Iterable[KillMark]) -> None:
    """Each "+skull" pops up above a fallen adventurer's head, drifts up and fades."""
    font = QFont(painter.font())
    font.setPixelSize(KILL_MARK_SIZE)
    font.setBold(True)
    painter.save()
    painter.setFont(font)
    for mark in marks:
        t = mark.age / KILL_MARK_TIME
        pop = 1.0 + 0.4 * max(0.0, 1.0 - t / 0.15)
        rise = KILL_MARK_RISE * smoothstep(min(1.0, t * 1.5))
        painter.save()
        painter.translate(qt(mark.point - Vec2(0.0, KILL_MARK_LIFT + rise)))
        painter.scale(pop, pop)
        painter.setOpacity(1.0 - smoothstep(clamp((t - 0.5) / 0.5, 0.0, 1.0)))
        box = QRectF(-40.0, -KILL_MARK_SIZE, 80.0, 2.0 * KILL_MARK_SIZE)
        center = Qt.AlignmentFlag.AlignCenter
        painter.setPen(KILL_MARK_SHADOW)
        painter.drawText(box.translated(1.0, 1.0), center, KILL_MARK_TEXT)
        painter.setPen(KILL_MARK_COLOR)
        painter.drawText(box, center, KILL_MARK_TEXT)
        painter.restore()
    painter.restore()


def draw_health_bar(
    painter: QPainter, fraction: float, corner: Vec2, color: QColor, label: str = ""
) -> None:
    """A pill like the kill counter's, bottom-right corner at `corner`: `label`, then a
    bar filled to `fraction` in `color`."""
    font = QFont(painter.font())
    font.setPixelSize(11)
    font.setBold(True)
    label_width = QFontMetricsF(font).horizontalAdvance(label) if label else 0.0
    height, pad, gap, bar, thickness = HEALTH_BAR_HEIGHT, 9.0, 6.0, 84.0, 7.0
    width = pad + label_width + (gap if label else 0.0) + bar + pad

    painter.save()
    painter.translate(corner.x - width, corner.y - height)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(COUNTER_BACK)
    painter.drawRoundedRect(QRectF(0, 0, width, height), height / 2, height / 2)
    if label:
        painter.setFont(font)
        painter.setPen(COUNTER_TEXT)
        painter.drawText(
            QRectF(pad, 0, label_width + 1.0, height), Qt.AlignmentFlag.AlignVCenter, label
        )
    track = QRectF(width - pad - bar, (height - thickness) / 2, bar, thickness)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(COUNTER_BACK.darker(170))
    painter.drawRoundedRect(track, thickness / 2, thickness / 2)
    filled = clamp(fraction, 0.0, 1.0) * bar
    if filled > 0.0:
        painter.setBrush(color)
        painter.drawRoundedRect(
            QRectF(track.x(), track.y(), max(filled, thickness), thickness),
            thickness / 2,
            thickness / 2,
        )
    painter.restore()


def draw_fallen(
    painter: QPainter,
    fallen: Iterable[
        Goblin
        | Chimera
        | Elemental
        | Worm
        | Dragon
        | Drake
        | Kobold
        | MindFlayer
        | Devourer
        | Displacer
        | Minotaur
        | Ooze
        | Lich
        | Mimic
        | Hydra
    ],
    outline: QColor | None = None,
) -> None:
    """Dead monsters, fading out."""
    for body in fallen:
        painter.setOpacity(1.0 - body.fade)
        if isinstance(body, Skeleton):
            draw_skeleton(painter, body, outline)
        elif isinstance(body, Drow):
            from dungeons_desktops.game.defenders.drow.render import draw_drow_on_foot

            draw_drow_on_foot(painter, body, outline)
        elif isinstance(body, Lizard):
            from dungeons_desktops.game.defenders.drow.render import draw_lizard

            draw_lizard(painter, body, outline)
        elif isinstance(body, Chimera):
            from dungeons_desktops.game.defenders.chimera.render import draw_chimera

            draw_chimera(painter, body, outline)
            draw_fire(painter, body.flames)
        elif isinstance(body, Elemental):
            from dungeons_desktops.game.defenders.elementals.render import draw_elemental

            draw_elemental(painter, body, outline)
        elif isinstance(body, Goblin):
            draw_goblin(painter, body, outline)
        elif isinstance(body, Worm):
            draw_worm(painter, body, outline)
        elif isinstance(body, MindFlayer):
            draw_mindflayer(painter, body, outline)
        elif isinstance(body, Devourer):
            draw_devourer(painter, body, outline)
        elif isinstance(body, Displacer):
            draw_displacer(painter, body, outline)
        elif isinstance(body, Minotaur):
            draw_minotaur(painter, body, outline)
        elif isinstance(body, Ooze):
            from dungeons_desktops.game.defenders.ooze.render import draw_ooze

            draw_ooze(painter, body, outline)
        elif isinstance(body, Lich):
            draw_lich(painter, body, outline)
        elif isinstance(body, Mimic):
            draw_mimic(painter, body, outline)
        elif isinstance(body, Hydra):
            draw_hydra(painter, body, outline)
        elif isinstance(body, Drake):
            from dungeons_desktops.game.defenders.drakes.render import draw_drake

            draw_drake(painter, body, outline)
        elif isinstance(body, Kobold):
            from dungeons_desktops.game.defenders.drakes.render import draw_kobold

            draw_kobold(painter, body, outline)
        else:
            draw_dragon(painter, body, outline)
    painter.setOpacity(1.0)
    draw_psionics(painter, [b for b in fallen if isinstance(b, MindFlayer)])


def draw_minotaurs(
    painter: QPainter, minotaurs: Iterable[Minotaur], outline: QColor | None = None
) -> None:
    for minotaur in minotaurs:
        draw_minotaur(painter, minotaur, outline)


def draw_displacers(
    painter: QPainter, displacers: Iterable[Displacer], outline: QColor | None = None
) -> None:
    for displacer in displacers:
        draw_displacer(painter, displacer, outline)


def draw_mindflayers(
    painter: QPainter,
    flayers: Iterable[MindFlayer],
    devourers: Iterable[Devourer],
    outline: QColor | None = None,
) -> None:
    for devourer in devourers:
        draw_devourer(painter, devourer, outline)
    flayers = list(flayers)
    for flayer in flayers:
        draw_mindflayer(painter, flayer, outline)
    draw_psionics(painter, flayers)


def draw_mindflayer(painter: QPainter, flayer: MindFlayer, outline: QColor | None = None) -> None:
    """Back to front: the cape streaming behind it, the high flared collar, the far
    arm, the purple robe (it has no legs to speak of), the bulbous head with blank
    eyes, the face tentacles (writhing, or wrapped round a victim's head mid-grab),
    then the near arm."""
    layout = flayer.layout
    t = flayer.transforms()
    r = layout.head_radius
    facing = flayer.facing
    limb = LIMB_WIDTH * layout.scale
    torso = t[layout.torso]
    down = (torso.start - torso.end).normalized()
    up = -down
    side = Vec2(-down.y, down.x)
    back = Vec2(-facing, 0.0)
    neck, waist = torso.end, torso.start
    hem = waist + down * (layout.leg_length * 0.95)
    time = flayer.float_time
    edge_pen = world_pen(outline, 2.0) if outline is not None else pen(FLAYER_ROBE_EDGE, 1.0)

    def arm(name: str, color: QColor) -> None:
        bones = (t[f"upper_arm_{name}"], t[f"lower_arm_{name}"])
        if outline is not None:
            painter.setPen(pen(outline, limb + 2.5 * layout.scale))
            for bone in bones:
                painter.drawLine(qt(bone.start), qt(bone.end))
        painter.setPen(world_pen(FLAYER_ROBE_EDGE, limb * 1.35))
        painter.drawLine(qt(bones[0].start), qt(bones[0].end))
        painter.setPen(world_pen(FLAYER_ROBE, limb))
        painter.drawLine(qt(bones[0].start), qt(bones[0].end))
        painter.setPen(world_pen(color, limb * 0.8))
        painter.drawLine(qt(bones[1].start), qt(bones[1].end))

    follower = flayer.follower
    if not flayer.dead and not follower.in_transition:
        ground = follower.current_anchor().surface
        if ground.walkable:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(FLAYER_SHADOW)
            painter.drawEllipse(qt(Vec2(flayer.feet.x, ground.start.y)), 1.6 * r, 0.4 * r)
    _draw_cape(painter, flayer, neck, hem, down, back, r, outline)
    collar = [
        neck + back * (0.1 * r) + down * (0.35 * r),
        neck + back * (2.3 * r) + up * (1.6 * r),
        neck + back * (1.7 * r) + up * (2.4 * r),
        neck + back * (1.5 * r) + up * (3.5 * r),
        neck + back * (0.8 * r) + up * (2.6 * r),
        neck + back * (0.2 * r) + up * (3.1 * r),
        neck - back * (0.3 * r) + up * (1.2 * r),
    ]
    painter.setPen(world_pen(outline, 2.0) if outline is not None else pen(FLAYER_CAPE_EDGE, 1.0))
    painter.setBrush(FLAYER_CAPE)
    painter.drawPolygon([qt(p) for p in collar])
    lining = [neck.lerp(p, 0.78) for p in collar]
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(FLAYER_LINING)
    painter.drawPolygon([qt(p) for p in lining])

    arm("l", FLAYER_SKIN_FAR)
    flutter = side * (math.sin(time * 2.0) * 0.12 * r)
    robe = [
        neck + side * (0.65 * r),
        waist + side * (1.0 * r),
        hem + side * (1.45 * r) + flutter,
        hem + side * (0.5 * r) + down * (0.3 * r) + flutter,
        hem - side * (0.5 * r) + down * (0.15 * r) + flutter,
        hem - side * (1.45 * r) + flutter,
        waist - side * (1.0 * r),
        neck - side * (0.65 * r),
    ]
    painter.setPen(edge_pen)
    painter.setBrush(FLAYER_ROBE)
    painter.drawPolygon([qt(p) for p in robe])
    painter.setPen(world_pen(FLAYER_TRIM, 0.22 * r))
    painter.drawLine(qt(neck + down * (0.2 * r)), qt(hem + down * (0.2 * r)))
    painter.setPen(world_pen(FLAYER_TRIM, 0.3 * r))
    painter.drawLine(qt(waist - side * (0.95 * r)), qt(waist + side * (0.95 * r)))

    head = t[layout.head]
    center = head.end
    head_up = Vec2.from_angle(head.angle)
    forward = head_up.rotated(facing * math.pi / 2)
    dome = center - forward * (0.45 * r) + head_up * (0.35 * r)
    if outline is not None:
        painter.setPen(world_pen(outline, 2.0))
        painter.setBrush(outline)
        painter.drawEllipse(qt(dome), 1.1 * r, 1.1 * r)
        painter.drawEllipse(qt(center), r, r)
    painter.setPen(pen(FLAYER_SKIN_EDGE, 1.0))
    painter.setBrush(FLAYER_SKIN)
    painter.drawEllipse(qt(dome), 1.1 * r, 1.1 * r)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(qt(center), r, r)
    painter.setPen(world_pen(FLAYER_SKIN_EDGE, 0.12 * r))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for k in (-1.0, 1.0):
        vein = dome + head_up * (0.3 * r) + forward * (k * 0.3 * r)
        painter.drawLine(qt(vein), qt(vein - forward * (0.35 * r) + head_up * (0.3 * r)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(PSYCHIC if flayer.power is not None else FLAYER_EYE)
    eye = center + forward * (0.45 * r) + head_up * (0.15 * r)
    painter.drawEllipse(qt(eye), 0.34 * r, 0.22 * r)
    _draw_tentacles(painter, flayer, center, head_up, forward, r, outline)
    arm("r", FLAYER_SKIN)


def _draw_cape(
    painter: QPainter,
    flayer: MindFlayer,
    neck: Vec2,
    hem: Vec2,
    down: Vec2,
    back: Vec2,
    r: float,
    outline: QColor | None,
) -> None:
    """A long cape from the shoulders, trailing away from the way it's floating (and
    settling behind it when it stops), its crimson lining showing at the turned hem."""
    drift = flayer.drift if not flayer.dead else Vec2(0.0, 0.0)
    trail = drift * -0.25
    if trail.length() > 2.6 * r:
        trail = trail.normalized() * (2.6 * r)
    time = flayer.float_time
    billow = min(1.0, drift.length() / 30.0)
    wave = math.sin(time * (2.0 + 4.0 * billow)) * (0.25 + 0.5 * billow) * r
    length = hem.distance_to(neck) + 0.6 * r
    shoulder = neck + back * (0.3 * r) + down * (0.25 * r)
    front = neck - back * (0.3 * r) + down * (0.25 * r)
    inner = neck + down * length + back * (0.9 * r) + trail * 0.7 + down * (wave * 0.3)
    outer = neck + down * (length * 0.97) + back * (2.9 * r) + trail * 1.2 + down * wave
    belly = neck + down * (length * 0.45) + back * (2.6 * r + 0.4 * wave) + trail * 0.5
    cape = QPainterPath(qt(front))
    cape.lineTo(qt(shoulder))
    cape.quadTo(qt(belly), qt(outer))
    cape.quadTo(qt(outer.lerp(inner, 0.5) + down * (0.6 * r)), qt(inner))
    cape.lineTo(qt(front))
    painter.setPen(world_pen(outline, 2.0) if outline is not None else pen(FLAYER_CAPE_EDGE, 1.0))
    painter.setBrush(FLAYER_CAPE)
    painter.drawPath(cape)
    lining = QPainterPath(qt(outer))
    lining.quadTo(qt(outer.lerp(inner, 0.5) + down * (0.6 * r)), qt(inner))
    lining.quadTo(qt(outer.lerp(inner, 0.5) - down * (0.35 * r)), qt(outer))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(FLAYER_LINING)
    painter.drawPath(lining)


def _draw_tentacles(
    painter: QPainter,
    flayer: MindFlayer,
    center: Vec2,
    up: Vec2,
    forward: Vec2,
    r: float,
    outline: QColor | None = None,
) -> None:
    """Four thick face tentacles, two-toned and curling at the tips, always writhing.
    Mid-grab they reach out and wrap round the victim's head."""
    base = center + forward * (0.5 * r) - up * (0.5 * r)
    reach = flayer.grab_reach
    victim = flayer.victim if reach > 0.0 else None
    held = None
    if victim is not None:
        held = victim.transforms()[victim.layout.head].end, victim.layout.head_radius
    down = -up
    length = TENTACLE_LENGTH * r
    count = 9
    time = flayer.float_time
    for i, spread in enumerate((0.36, -0.12, 0.12, -0.36)):
        root = base + forward * (spread * r)
        curl = 1.5 if i % 2 == 0 else -1.2
        angle = 0.15 + spread * 0.5
        point = root
        points = [root]
        for k in range(1, count + 1):
            u = k / count
            writhe = math.sin(time * 3.4 + i * 1.7 + u * 5.0) * 0.45 * u
            flick = math.sin(time * 7.0 + i * 2.3) * 0.6 * u**4
            angle_k = angle + writhe + curl * u**3 + flick
            direction = down * math.cos(angle_k) + forward * math.sin(angle_k)
            point = point + direction * (length / count)
            points.append(point)
        if held is not None:
            head, radius = held
            toward = (head - root).normalized()
            approach = head - toward * (radius * 1.05)
            start = math.atan2(approach.y - head.y, approach.x - head.x) + (0.35 * spread / 0.36)
            sweep = (1.0 if i % 2 == 0 else -1.0) * math.pi * 1.25
            wrap = radius * (1.05 + 0.12 * (i % 2))
            gripping = []
            for k in range(count + 1):
                u = k / count
                if u <= 0.5:
                    spot = root.lerp(approach, u / 0.5) + down * (
                        math.sin(u * math.pi * 2) * 0.3 * r
                    )
                else:
                    a = start + sweep * (u - 0.5) / 0.5
                    spot = head + Vec2(math.cos(a), math.sin(a)) * wrap
                gripping.append(spot)
            points = [p.lerp(g, smoothstep(reach)) for p, g in zip(points, gripping, strict=True)]
        widths = [(0.62 - 0.47 * k / count) * r for k in range(count)]
        if outline is not None:
            for k in range(count):
                painter.setPen(world_pen(outline, widths[k] + 2.0))
                painter.drawLine(qt(points[k]), qt(points[k + 1]))
        for k in range(count):
            painter.setPen(world_pen(FLAYER_TENTACLE_EDGE, widths[k] + 0.3 * r))
            painter.drawLine(qt(points[k]), qt(points[k + 1]))
        for k in range(count):
            painter.setPen(world_pen(FLAYER_SKIN if i < 2 else FLAYER_TENTACLE, widths[k]))
            painter.drawLine(qt(points[k]), qt(points[k + 1]))


def draw_psionics(painter: QPainter, flayers: Iterable[MindFlayer]) -> None:
    """Mind blast bolts, pulse rings, and the glow of a power being summoned."""
    for flayer in flayers:
        if flayer.power in (Power.BLAST, Power.PULSE) and not flayer.dead:
            charge = min(1.0, flayer.power_time / 0.45)
            point = flayer.mouth() if flayer.power is Power.BLAST else flayer.center()
            size = (3.0 if flayer.power is Power.BLAST else 9.0) * (0.4 + charge)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_alpha(PSYCHIC, 90 * charge))
            painter.drawEllipse(qt(point), size, size)
        for bolt in flayer.bolts:
            wobble = 1.0 + 0.25 * math.sin(bolt.age * 30.0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_alpha(PSYCHIC, 110))
            painter.drawEllipse(qt(bolt.position), 5.0 * wobble, 5.0 * wobble)
            painter.setBrush(PSYCHIC_CORE)
            painter.drawEllipse(qt(bolt.position), 2.0, 2.0)
            painter.setPen(world_pen(_alpha(PSYCHIC, 180), 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(qt(bolt.position), 7.0 * wobble, 4.0 * wobble)
        for wave in flayer.waves:
            u = wave.age / WAVE_TIME
            radius = PULSE_RADIUS * smoothstep(min(1.0, u * 1.3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(world_pen(_alpha(PSYCHIC, 230 * (1.0 - u)), 1.0 + 3.0 * (1.0 - u)))
            painter.drawEllipse(qt(wave.center), radius, radius * 0.8)
            painter.setPen(world_pen(_alpha(PSYCHIC_CORE, 160 * (1.0 - u)), 1.0))
            painter.drawEllipse(qt(wave.center), radius * 0.8, radius * 0.64)


def draw_devourer(painter: QPainter, devourer: Devourer, outline: QColor | None = None) -> None:
    """A brain scuttling on four clawed legs, feet on whatever surface it's crawling on
    (sideways up a window's side, upside down under it); flipped over, legs up, once
    dead."""
    up, forward, feet = devourer.up, devourer.forward, devourer.position
    painter.save()
    painter.setTransform(
        QTransform(forward.x, forward.y, -up.x, -up.y, feet.x, feet.y), combine=True
    )
    center = Vec2(0.0, -BODY_HEIGHT)
    lying = devourer.dead and not devourer.airborne
    legs = []
    for front in (True, False):
        for near, offset in ((False, 0.5), (True, 0.0)):
            direction = 1.0 if front else -1.0
            hip = center + Vec2(direction * 3.0, 1.5 if not lying else -1.0)
            if lying:
                foot = hip + Vec2(direction * 2.5, -6.0 - (1.0 if near else 0.0))
                knee = hip.lerp(foot, 0.5) + Vec2(direction * 2.4, 0.0)
            elif devourer.airborne:
                foot = hip + Vec2(direction * 4.5, 3.0)
                knee = hip.lerp(foot, 0.5) + Vec2(direction * 0.5, -2.0)
            else:
                cycle = (devourer.phase + offset + (0.25 if front else 0.0)) * math.tau
                swing = math.sin(cycle) * 1.8
                lift = max(0.0, math.cos(cycle)) * 1.4
                foot = Vec2(hip.x + direction * 3.0 + swing, -lift)
                knee = hip.lerp(foot, 0.5) + Vec2(direction * 2.2, -3.0)
            legs.append((near, hip, knee, foot, direction))
    if outline is not None:
        painter.setPen(pen(outline, 3.2))
        for _, hip, knee, foot, _ in legs:
            painter.drawPolyline([qt(hip), qt(knee), qt(foot)])

    def draw_legs(side: bool) -> None:
        for near, hip, knee, foot, direction in legs:
            if near is not side:
                continue
            claw = foot + Vec2(direction * 1.4, -0.5)
            painter.setPen(world_pen(BRAIN_EDGE, 1.7))
            painter.drawPolyline([qt(hip), qt(knee), qt(foot), qt(claw)])
            painter.setPen(world_pen(DEVOURER_LEG if near else DEVOURER_LEG_FAR, 0.9))
            painter.drawPolyline([qt(hip), qt(knee), qt(foot), qt(claw)])

    draw_legs(False)
    _draw_brain(painter, center, 6.0, 4.2, outline)
    draw_legs(True)
    painter.restore()


def draw_dragon(painter: QPainter, dragon: Dragon, outline: QColor | None = None) -> None:
    """Far wing and legs, tail, body, neck and head, near legs, near wing, then fire."""
    s = DRAGON_SCALE
    p = DRAGON_PALETTES.get(dragon.variant, DRAGON_PALETTES["red"])
    near = [_dragon_limb(dragon, leg) for leg in dragon.legs if leg.near]
    far = [_dragon_limb(dragon, leg) for leg in dragon.legs if not leg.near]
    tail = dragon.tail
    widths = [7.0 * s * (1.0 - i / len(tail)) + 1.2 * s for i in range(len(tail))]
    hip, shoulder = dragon.hip, dragon.shoulder

    def strokes(color: QColor, grow: float) -> None:
        for limb in far + near:
            limb.stroke(painter, color, grow)
        for i in range(len(tail) - 1):
            painter.setPen(world_pen(color, widths[i] + grow))
            painter.drawLine(qt(tail[i]), qt(tail[i + 1]))
        painter.setPen(world_pen(color, 13.0 * s + grow))
        painter.drawLine(qt(hip), qt(shoulder))
        painter.setPen(world_pen(color, 6.5 * s + grow))
        painter.drawLine(qt(dragon.neck_base), qt(dragon.head))

    _draw_wing(painter, dragon, near=False)
    if outline is not None:
        strokes(outline, 2.0)
    for leg in far:
        _draw_dragon_leg(painter, leg, p.far, s, p.talon)
    for i in range(len(tail) - 1):
        painter.setPen(world_pen(p.skin, widths[i]))
        painter.drawLine(qt(tail[i]), qt(tail[i + 1]))
    tip, before = tail[-1], tail[-2]
    along = (tip - before).normalized()
    across = Vec2(-along.y, along.x) * (4.5 * s)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(p.skin)
    painter.drawPolygon([qt(tip + across), qt(tip + along * (9.0 * s)), qt(tip - across)])

    painter.setPen(world_pen(p.skin, 13.0 * s))
    painter.drawLine(qt(hip), qt(shoulder))
    belly = dragon.local(Vec2(0.0, 3.5 * s))
    painter.setPen(world_pen(p.belly, 5.0 * s))
    painter.drawLine(qt(hip + belly + dragon.forward * 3.0), qt(shoulder + belly))
    painter.setPen(world_pen(p.far, 1.2 * s))
    for k in range(1, 6):
        spine = hip.lerp(shoulder, k / 6.0) + dragon.local(Vec2(0.0, -6.0 * s))
        painter.drawLine(qt(spine), qt(spine + dragon.local(Vec2(-1.5, -2.5) * s)))

    painter.setPen(world_pen(p.skin, 6.5 * s))
    painter.drawLine(qt(dragon.neck_base), qt(dragon.head))
    _draw_dragon_head(painter, dragon, s)

    for leg in near:
        _draw_dragon_leg(painter, leg, p.skin, s, p.talon)
    _draw_wing(painter, dragon, near=True)
    draw_flames(painter, dragon)


@dataclass
class DragonLimb:
    joints: list[Vec2]
    widths: list[float]
    toes: list[tuple[Vec2, Vec2, Vec2]]
    """Base, tip and talon direction, dew claw first, nearest toe last."""
    muscle: float
    """Width of the thigh or upper arm where it meets the body, tapering to the knee."""

    def stroke(self, painter: QPainter, color: QColor, grow: float) -> None:
        root, knee = self.joints[0], self.joints[1]
        along = knee - root
        if along.length() > 1e-6:
            side = along.normalized().rotated(math.pi / 2)
            steps = [k / 6 for k in range(7)]
            half = [
                (
                    self.widths[0]
                    + (self.muscle - self.widths[0])
                    * (1.0 - smoothstep(clamp((u - 0.25) / 0.75, 0.0, 1.0)))
                    + grow
                )
                / 2
                for u in steps
            ]
            outline = [root + along * u + side * h for u, h in zip(steps, half, strict=True)]
            outline += [
                root + along * u - side * h
                for u, h in reversed(list(zip(steps, half, strict=True)))
            ]
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawPolygon([qt(p) for p in outline])
            painter.drawEllipse(qt(root), half[0], half[0])
            painter.restore()
        for i, width in enumerate(self.widths):
            painter.setPen(world_pen(color, width + grow))
            painter.drawLine(qt(self.joints[i]), qt(self.joints[i + 1]))
        painter.setPen(world_pen(color, 1.4 * DRAGON_SCALE + grow * 0.6))
        for base, tip, _ in self.toes:
            painter.drawLine(qt(base), qt(tip))


def _blend_angle(a: float, b: float, t: float) -> float:
    return a + math.remainder(b - a, math.tau) * t


def _dragon_limb(dragon: Dragon, leg: Leg) -> DragonLimb:
    """Hip or shoulder, knee or elbow, hock or wrist, ankle, all ending on the sim's foot
    point. Hind legs stand digitigrade on a raked metatarsus with the hock kicked back;
    front legs bring the elbow back over a short sloped wrist. The toes lie flat with
    the outline resting on the surface and curl under as the foot lifts."""
    s = DRAGON_SCALE
    facing = dragon.facing
    lift = smoothstep(leg.lift)
    root, foot = leg.root, leg.foot
    thigh, shin, ankle_bone = (8.5, 9.0, 6.0) if not leg.front else (9.0, 9.0, 3.5)
    rake = 0.5 if not leg.front else 0.3

    up = Vec2(0.0, -1.0)
    reach = root - foot
    rise = up.rotated(-facing * rake).angle()
    if reach.length() > 1e-6:
        rise = _blend_angle(rise, reach.angle(), lift)
    rise_dir = Vec2.from_angle(rise)
    hang = (-rise_dir).angle() - facing * 0.6
    toe_angle = _blend_angle(0.0 if facing > 0 else math.pi, hang, lift)
    toe = Vec2.from_angle(toe_angle)
    normal = toe.rotated(-facing * math.pi / 2)

    ankle = foot + normal * (2.8 * s) - toe * (0.6 * s)
    hock = ankle + rise_dir * (ankle_bone * s)
    stretch = max(1.0, hock.distance_to(root) / (0.97 * (thigh + shin) * s))
    bend = -facing if leg.front else facing
    _, knee, hock = two_bone_points(root, thigh * s * stretch, shin * s * stretch, hock, bend)

    size = (0.85 if leg.front else 1.0) * s
    base = foot + normal * (1.3 * s)
    toes = []
    for spread, length in ((-0.42, 3.0), (-0.2, 3.7), (0.0, 4.5)):
        reach_dir = toe.rotated(facing * spread * (1.0 - 0.6 * lift))
        tip = base + reach_dir * (length * size * (1.0 - 0.35 * lift))
        toes.append((base, tip, reach_dir.rotated(facing * (0.4 + 0.8 * lift))))
    dew = (-toe).rotated(facing * (0.6 - 1.1 * lift))
    dew_tip = base + dew * (1.9 * size)
    toes.insert(0, (base, dew_tip, dew.rotated(-facing * 0.8)))
    widths = (4.8, 4.4, 3.6) if not leg.front else (4.4, 4.2, 3.6)
    muscle = 8.2 if not leg.front else 7.0
    return DragonLimb([root, knee, hock, ankle], [w * s for w in widths], toes, muscle * s)


def _draw_dragon_leg(
    painter: QPainter, limb: DragonLimb, color: QColor, s: float, talon: QColor
) -> None:
    limb.stroke(painter, color, 0.0)
    shade = color.darker(125)
    for i, (base, tip, _) in enumerate(limb.toes):
        painter.setPen(world_pen(shade if i < 3 else color, 1.4 * s))
        painter.drawLine(qt(base), qt(tip))
    painter.setPen(world_pen(talon, 1.1 * s))
    for _, tip, hook in limb.toes:
        painter.drawLine(qt(tip), qt(tip + hook * (1.5 * s)))


def _draw_dragon_head(painter: QPainter, dragon: Dragon, s: float) -> None:
    head, angle = dragon.head, dragon.head_angle
    forward = Vec2.from_angle(angle)
    up = forward.rotated(-dragon.facing * math.pi / 2)
    jaw = dragon.jaw
    p = DRAGON_PALETTES.get(dragon.variant, DRAGON_PALETTES["red"])

    def at(x: float, y: float) -> Vec2:
        return head + forward * (x * s) - up * (y * s)

    variant = dragon.variant
    if variant == "green":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(p.far)
        for x in (-1.0, -3.5):
            painter.drawPolygon([qt(at(x, -4.0)), qt(at(x - 2.6, -6.3)), qt(at(x - 1.6, -3.6))])
    elif variant not in ("blue", "black"):
        painter.setPen(world_pen(p.horn, 1.6 * s))
        painter.drawLine(qt(at(-2.0, -3.5)), qt(at(-8.0, -8.0)))
        painter.drawLine(qt(at(0.0, -4.0)), qt(at(-4.5, -9.0)))

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(p.skin)
    upper = [at(-4.5, -4.0), at(3.0, -4.5), at(10.0, -1.5), at(10.0, 0.5), at(-4.5, 1.5)]
    open_by = 0.55 * jaw * dragon.facing
    hinge = at(-2.5, 1.0)

    def jaw_point(x: float, y: float) -> Vec2:
        return hinge + (at(x, y) - hinge).rotated(open_by)

    lower = [jaw_point(-4.0, 1.0), jaw_point(9.0, 1.0), jaw_point(8.0, 3.0), jaw_point(-3.0, 4.5)]
    if jaw > 0.05:
        painter.setBrush(WORM_MOUTH)
        painter.drawPolygon([qt(hinge), qt(at(9.0, 0.5)), qt(jaw_point(8.5, 1.5))])
        painter.setBrush(WORM_TOOTH)
        for x in (3.0, 6.0, 8.5):
            painter.drawPolygon([qt(at(x - 1.0, 0.5)), qt(at(x + 0.6, 0.5)), qt(at(x, 2.0))])
    painter.setBrush(p.skin)
    painter.drawPolygon([qt(point) for point in upper])
    painter.setBrush(p.belly)
    painter.drawPolygon([qt(point) for point in lower])
    painter.setBrush(p.eye)
    painter.drawEllipse(qt(at(1.5, -1.8)), 1.3 * s, 1.0 * s)
    painter.setBrush(OUTLINE)
    painter.drawEllipse(qt(at(9.0, -0.8)), 0.6 * s, 0.6 * s)
    if variant == "green":
        _draw_horn(painter, [at(6.6, -2.4), at(8.4, -7.6), at(10.0, -1.4)], p, s)
    elif variant == "blue":
        _draw_horn(painter, [at(-0.6, -3.6), at(5.0, -13.0), at(3.0, -4.2)], p, s, ridges=3)
    elif variant == "black":
        _draw_ram_horn(painter, at, p, s)


def _draw_horn(
    painter: QPainter, points: list[Vec2], p: DragonPalette, s: float, ridges: int = 0
) -> None:
    """A tapering horn: `points` are base back, tip, base front."""
    back, tip, front = points
    painter.setPen(world_pen(p.horn.darker(150), 0.5 * s))
    painter.setBrush(p.horn)
    painter.drawPolygon([qt(back), qt(tip), qt(front)])
    painter.setPen(world_pen(p.horn.darker(135), 0.45 * s))
    for k in range(1, ridges + 1):
        t = k / (ridges + 1)
        painter.drawLine(qt(back.lerp(tip, t)), qt(front.lerp(tip, t + 0.08)))


def _draw_ram_horn(
    painter: QPainter, at: Callable[[float, float], Vec2], p: DragonPalette, s: float
) -> None:
    """A ram's horn curling back, down and round on the side of the head."""
    steps = 22
    points, widths = [], []
    for k in range(steps + 1):
        t = k / steps
        turn = -math.pi / 2 - t * 1.75 * math.pi
        radius = 4.6 - 3.2 * t
        points.append(at(-3.6 + radius * math.cos(turn) - 0.6 * t, -2.2 + radius * math.sin(turn)))
        widths.append((2.6 - 1.7 * t) * s)
    for color, grow in ((p.horn.darker(170), 0.9 * s), (p.horn, 0.0)):
        for k in range(steps):
            painter.setPen(world_pen(color, widths[k] + grow))
            painter.drawLine(qt(points[k]), qt(points[k + 1]))
    painter.setPen(world_pen(p.horn.darker(140), 0.4 * s))
    for k in range(2, steps - 2, 3):
        across = (points[k + 1] - points[k]).normalized().rotated(math.pi / 2) * (widths[k] * 0.5)
        painter.drawLine(qt(points[k] - across), qt(points[k] + across))


def _draw_wing(painter: QPainter, dragon: Dragon, near: bool) -> None:
    s = DRAGON_SCALE * DRAGON_WING_SCALE * (1.0 if near else 0.85)
    p = DRAGON_PALETTES.get(dragon.variant, DRAGON_PALETTES["red"])
    root = dragon.shoulder + dragon.local(Vec2(-1.0 if near else 1.0, -5.0) * DRAGON_SCALE)

    if dragon.flying:
        # The wing beats up and down around the body's long axis, so seen from the
        # side its span shrinks to a sliver as it swings out toward the viewer.
        beat = dragon.flap + (0.0 if near else 0.25)
        arm = 0.35 + 1.05 * math.cos(beat)
        hand = 0.35 + 1.25 * math.cos(beat - 0.9)
        sweep = -2.0 * math.sin(beat)
        elbow = root + dragon.local(Vec2(1.0 + sweep, -16.0 * math.sin(arm)) * s)
        tip = elbow + dragon.local(Vec2(-12.0 + 2.0 * sweep, -24.0 * math.sin(hand)) * s)
        trailing = elbow + dragon.local(Vec2(-21.0, -13.0 * math.sin(hand)) * s)
        back = root + dragon.local(Vec2(-17.0, 2.0) * s)
    else:
        elbow = root + dragon.local(Vec2(-5.0, -7.0) * s)
        tip = root + dragon.local(Vec2(-19.0, -4.0) * s)
        trailing = root + dragon.local(Vec2(-15.0, -1.0) * s)
        back = root + dragon.local(Vec2(-9.0, 0.0) * s)

    def notch(a: Vec2, b: Vec2) -> Vec2:
        return a.lerp(b, 0.5).lerp(elbow, 0.22)

    painter.setPen(world_pen(p.far if near else OUTLINE, 1.2 * s))
    painter.setBrush(p.wing if near else p.wing_far)
    outline = [root, elbow, tip, notch(tip, trailing), trailing, notch(trailing, back), back]
    painter.drawPolygon([qt(point) for point in outline])
    painter.setPen(world_pen(p.skin if near else p.far, 2.0 * s))
    painter.drawPolyline([qt(root), qt(elbow), qt(tip)])
    painter.setPen(world_pen(p.far, 0.8 * s))
    painter.drawLine(qt(elbow), qt(trailing))


def draw_flames(painter: QPainter, dragon: Dragon) -> None:
    if dragon.variant != "red":
        draw_breath(painter, dragon)
        return
    draw_fire(painter, dragon.flames)


def draw_fire(painter: QPainter, flames: Iterable[Flame]) -> None:
    """Flames going from white-hot through orange to smoke as they age."""
    painter.setPen(Qt.PenStyle.NoPen)
    for flame in flames:
        t = flame.age / FLAME_LIFE
        radius = flame.radius
        if t < 0.55:
            color = _mix(FLAME_HOT, FLAME_MID, t / 0.55)
        else:
            color = _mix(FLAME_MID, FLAME_SMOKE, (t - 0.55) / 0.45)
        painter.setBrush(_alpha(color, 230 * (1.0 - t) ** 0.8))
        painter.drawEllipse(qt(flame.position), radius, radius)
        if t < 0.35:
            painter.setBrush(_alpha(FLAME_HOT, 200 * (1.0 - t / 0.35)))
            painter.drawEllipse(qt(flame.position), radius * 0.45, radius * 0.45)


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    t = clamp(t, 0.0, 1.0)
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
    )
