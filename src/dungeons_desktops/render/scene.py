"""QPainter drawing for actors, weapons, vials, bullets and terrain surfaces.

Everything is drawn in world coordinates; callers set up the painter transform.
An `outline` color draws a darker halo under bodies so they read on any backdrop.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
)

from dungeons_desktops.core.geometry import Rect, Vec2, clamp, smoothstep
from dungeons_desktops.game.adventurers.actor import Stickman
from dungeons_desktops.game.adventurers.alchemy import Vials
from dungeons_desktops.game.adventurers.render import (
    _draw_vines,
    draw_body,  # noqa: F401 - compatibility export
    draw_stickman,
)
from dungeons_desktops.game.adventurers.spells import (
    ARROW_STUCK_TIME,
    PULSE_TIME,
    SPARK_LIFE,
    Spells,
)
from dungeons_desktops.game.defenders.chimera.actor import Chimera
from dungeons_desktops.game.defenders.displacer.actor import Displacer
from dungeons_desktops.game.defenders.displacer.render import draw_displacer
from dungeons_desktops.game.defenders.dragon.actor import Dragon
from dungeons_desktops.game.defenders.dragon.render import draw_dragon
from dungeons_desktops.game.defenders.drakes.drake import Drake
from dungeons_desktops.game.defenders.drakes.kobold import Kobold
from dungeons_desktops.game.defenders.drow.actor import Drow, Lizard
from dungeons_desktops.game.defenders.elementals.actor import Elemental
from dungeons_desktops.game.defenders.goblins.actor import Goblin
from dungeons_desktops.game.defenders.goblins.render import draw_goblin
from dungeons_desktops.game.defenders.goblins.spears import Spears
from dungeons_desktops.game.defenders.hydra.actor import Hydra
from dungeons_desktops.game.defenders.hydra.render import draw_hydra
from dungeons_desktops.game.defenders.lich.actor import Lich
from dungeons_desktops.game.defenders.lich.render import draw_lich
from dungeons_desktops.game.defenders.lich.skeletons import Skeleton
from dungeons_desktops.game.defenders.mimic.actor import Mimic
from dungeons_desktops.game.defenders.mimic.render import draw_mimic
from dungeons_desktops.game.defenders.mindflayer.actor import (
    MindFlayer,
)
from dungeons_desktops.game.defenders.mindflayer.devourer import Devourer
from dungeons_desktops.game.defenders.mindflayer.render import (
    draw_devourer,
    draw_mindflayer,
    draw_mindflayers,  # noqa: F401 - compatibility export
    draw_psionics,
)
from dungeons_desktops.game.defenders.minotaur.actor import Minotaur
from dungeons_desktops.game.defenders.minotaur.render import draw_minotaur
from dungeons_desktops.game.defenders.ooze.actor import Ooze
from dungeons_desktops.game.defenders.worm.actor import Worm
from dungeons_desktops.game.defenders.worm.render import draw_worm
from dungeons_desktops.game.effects.debris import HOLE_FADE, HOLE_LIFE, Debris, Hole
from dungeons_desktops.game.effects.fire import Burn
from dungeons_desktops.game.effects.flames import FLAME_LIFE, Flame
from dungeons_desktops.game.effects.gore import DROP_LIFE, SPLAT_LIFE, Gore
from dungeons_desktops.game.effects.projectiles import Projectiles
from dungeons_desktops.game.effects.render import (
    draw_demise_over,
    draw_demise_under,
    melted,
)
from dungeons_desktops.game.heroes.dio.render import draw_dio_effects  # noqa: F401
from dungeons_desktops.game.world.simulation import KILL_MARK_TIME, KillMark
from dungeons_desktops.navigation.terrain import Surface
from dungeons_desktops.rig.skeleton import BoneTransform

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
