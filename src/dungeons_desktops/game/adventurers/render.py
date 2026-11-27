"""Procedural stick-figure body rendering shared with humanoid features."""

from __future__ import annotations

import math
from collections.abc import Callable, Collection, Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.actors.base import Actor
from dungeons_desktops.game.adventurers.actor import Stickman
from dungeons_desktops.game.adventurers.spells import VINE_GROW, VINE_TIME, Spells
from dungeons_desktops.game.defenders.goblins.appearance import (
    GOBLIN_FAR,
    GOBLIN_HEAD,
    GOBLIN_SKIN,
)
from dungeons_desktops.game.defenders.mimic.render import draw_lure_alert
from dungeons_desktops.game.defenders.mindflayer.render import FLAYER_SKIN, FLAYER_SKIN_FAR
from dungeons_desktops.game.effects.render import demise_colors
from dungeons_desktops.game.heroes.hero_alchemist import render as hero_alchemist
from dungeons_desktops.game.heroes.hero_cleric import render as hero_cleric
from dungeons_desktops.game.heroes.hero_fighter import render as hero_fighter
from dungeons_desktops.game.heroes.hero_sorcerer import render as hero_sorcerer
from dungeons_desktops.game.heroes.natures_wrath.bear_render import draw_bear
from dungeons_desktops.game.heroes.natures_wrath.dragon_render import draw_magma_dragon
from dungeons_desktops.game.heroes.natures_wrath.render import (
    BODY_WIDTH as NATURES_WRATH_BODY_WIDTH,
)
from dungeons_desktops.game.heroes.natures_wrath.render import (
    draw_nature_aura,
    draw_natures_wrath_cape,
    draw_natures_wrath_head,
)
from dungeons_desktops.game.heroes.the_hunter import render as hunter
from dungeons_desktops.game.heroes.the_inquisitive import appearance as iggy
from dungeons_desktops.game.heroes.the_inquisitive.companion_render import draw_cat
from dungeons_desktops.game.heroes.the_inquisitive.model import HAT_RADIUS as IGGY_HAT_RADIUS
from dungeons_desktops.game.heroes.the_mighty.model import BODY_WIDTH as MIGHTY_BODY_WIDTH
from dungeons_desktops.game.heroes.the_mighty.render import RAGE, draw_mighty_details
from dungeons_desktops.game.heroes.the_slayer import render as slayer
from dungeons_desktops.game.heroes.the_slayer.render import draw_slayer_bandana, draw_slayer_cape
from dungeons_desktops.render.chromatic import chromatic_appearance
from dungeons_desktops.render.equipment import WEAPON_COLORS, draw_strokes, draw_trail
from dungeons_desktops.render.primitives import alpha, mix, pen, qt, world_pen
from dungeons_desktops.rig.skeleton import BoneTransform

JOINT = QColor(214, 170, 92)
LIMB_WIDTH = 3.0
BACKGROUND = QColor(24, 26, 33)
GROUND = QColor(90, 96, 110)
NEAR_LIMB = QColor(236, 230, 214)
FAR_LIMB = QColor(150, 146, 136)
TARGET = QColor(110, 190, 240)
SCARF = QColor(255, 214, 234)
SCARF_EDGE = QColor(168, 52, 108)
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
CLASS_COLORS = {
    "barbarian": (QColor(238, 138, 54), QColor(160, 90, 36)),
    "hero_barbarian": (QColor(238, 138, 54), QColor(160, 90, 36)),
    "paladin": (QColor(252, 224, 92), QColor(172, 150, 58)),
    "hero_paladin": (QColor(252, 224, 92), QColor(172, 150, 58)),
    "wizard": (QColor(172, 112, 242), QColor(112, 72, 164)),
    "hero_wizard": (iggy.BODY, iggy.BODY_FAR),
    "ranger": (QColor(108, 200, 88), QColor(70, 132, 58)),
    "hero_ranger": (QColor(108, 200, 88), QColor(70, 132, 58)),
    "rogue": (QColor(206, 174, 50), QColor(138, 116, 34)),
    "hero_rogue": (slayer.BODY, slayer.BODY_FAR),
    "cleric": (QColor(244, 242, 234), QColor(170, 168, 160)),
    "hero_cleric": (QColor(255, 250, 220), QColor(210, 168, 76)),
    "alchemist": (QColor(74, 136, 240), QColor(46, 88, 164)),
    "hero_alchemist": (hero_alchemist.BODY, hero_alchemist.BODY_FAR),
    "druid": (QColor(70, 182, 160), QColor(44, 118, 104)),
    "sorcerer": (QColor(250, 116, 184), QColor(172, 62, 118)),
    "hero_sorcerer": (hero_sorcerer.BODY, hero_sorcerer.BODY_FAR),
    "fighter": (QColor(236, 64, 68), QColor(154, 38, 44)),
    "hero_fighter": (QColor(176, 188, 198), QColor(96, 108, 122)),
    "hero_druid": (GOBLIN_SKIN, GOBLIN_FAR),
}
SELECTED = QColor(120, 220, 160)
WOUNDED = QColor(230, 60, 60)
CHARRED = QColor(34, 28, 26)
CHARRED_FAR = QColor(22, 18, 17)
PSYCHIC = QColor(196, 112, 255)
BRAIN = QColor(238, 152, 176)
BRAIN_EDGE = QColor(168, 78, 108)
THRALL_TINT = 0.4


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
    body_width: float | None = None,
    head_width: float | None = None,
    show_head_base: bool = True,
    show_joints: bool = True,
    joint_color: QColor | None = None,
) -> dict[str, BoneTransform]:
    """Draw a biped; an explicit body width uses world units and scales with zoom."""
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
    limb_width = LIMB_WIDTH * layout.scale if body_width is None else body_width
    head_line_width = limb_width if head_width is None else head_width
    line_pen = pen if body_width is None else world_pen
    joint = 1.1 * layout.scale

    if outline is not None:
        painter.setPen(line_pen(outline, limb_width + 2.5 * layout.scale))
        for name in shown:
            if name != layout.head:
                transform = transforms[name]
                painter.drawLine(qt(transform.start), qt(transform.end))
        if has_head and show_head_base:
            painter.setPen(line_pen(outline, head_line_width + 2.5 * layout.scale))
            painter.drawLine(qt(head.start), qt(neck_end))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(qt(head.end), radius, radius)

    def draw_bones(names: list[str], color: QColor) -> None:
        painter.setPen(line_pen(color, limb_width))
        for name in names:
            transform = transforms[name]
            painter.drawLine(qt(transform.start), qt(transform.end))

    draw_bones(far_side, far)
    draw_bones(spine, near)
    if has_head and show_head_base:
        painter.setPen(line_pen(near, head_line_width))
        painter.drawLine(qt(head.start), qt(neck_end))
        painter.setBrush(head_fill)
        painter.drawEllipse(qt(head.end), radius, radius)
    if between is not None:
        between(transforms)
    draw_bones(near_leg, near)

    def draw_joints(names: list[str]) -> None:
        if not show_joints:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(JOINT if joint_color is None else joint_color)
        for name in names:
            painter.drawEllipse(qt(transforms[name].start), joint, joint)

    draw_joints([name for name in shown if name not in near_arm])
    if over_legs is not None:
        over_legs(transforms)
    draw_bones(near_arm, near)
    draw_joints(near_arm)
    return transforms


@chromatic_appearance
def draw_stickman(
    painter: QPainter,
    stickman: Stickman,
    selected: bool = False,
    outline: QColor | None = None,
    transforms: dict[str, BoneTransform] | None = None,
    hide: Collection[str] = (),
) -> None:
    if getattr(stickman, "is_alchemical_ooze", False):
        hero_alchemist.draw_alchemical_ooze(
            painter,
            stickman,
            SELECTED if selected else outline,
        )
        return
    shadow_clone = getattr(stickman, "is_shadow_clone", False)
    if shadow_clone and stickman.gone:
        return
    if (
        stickman.variant == "hero_rogue" and not shadow_clone and stickman.animated
        and stickman.assassinate.spinning
    ):
        return
    if stickman.variant == "hero_alchemist":
        hero_alchemist.draw_poison_clouds(painter, stickman)
    if (beast := getattr(stickman, "beast", None)) is not None:
        hero_alchemist.draw_beastform(painter, beast, SELECTED if selected else outline)
        return
    if (dragon := getattr(stickman, "dragon", None)) is not None:
        draw_magma_dragon(painter, dragon, SELECTED if selected else outline)
        return
    if (bear := getattr(stickman, "bear", None)) is not None:
        draw_bear(painter, bear, SELECTED if selected else outline)
        return
    strokes = stickman.weapon_strokes()
    held = stickman.weapon_held
    variant = stickman.variant
    hammer_away = variant == "hero_paladin" and stickman.weapon.hammer_away
    hidden = stickman.severed | set(hide)
    has = {name: name not in hidden for name in (stickman.layout.head, stickman.layout.torso)}
    nature_hero = variant == "hero_druid"
    cleric_hero = variant == "hero_cleric"
    alchemist_hero = variant == "hero_alchemist"
    sorcerer_hero = variant == "hero_sorcerer"
    if sorcerer_hero:
        hero_sorcerer.draw_blood_cloud(painter, stickman)
        hero_sorcerer.draw_corpsenado(painter, stickman)
        hero_sorcerer.draw_skeletal_grasp(painter, stickman)
    if alchemist_hero:
        if transforms is None:
            transforms = stickman.transforms()
        hero_alchemist.draw_back_gear(painter, stickman, transforms)
    if sorcerer_hero:
        if transforms is None:
            transforms = stickman.transforms()
        hero_sorcerer.draw_orbiting_skulls(
            painter,
            stickman,
            transforms,
            front=False,
            outline=SELECTED if selected else outline,
        )
    if cleric_hero:
        if transforms is None:
            transforms = stickman.transforms()
        hero_cleric.draw_souls(painter, stickman)
        hero_cleric.draw_divine_aura(painter, stickman, transforms)
        hero_cleric.draw_staff_glow(painter, stickman, transforms)
    if variant == "hero_ranger":
        hunter.draw_shot(painter, stickman)
        if has[stickman.layout.torso]:
            if transforms is None:
                transforms = stickman.transforms()
            hunter.draw_back(painter, stickman, transforms)
    if variant == "hero_wizard":
        draw_cat(painter, stickman.cat)
    if variant == "hero_rogue" and has[stickman.layout.torso]:
        if transforms is None:
            transforms = stickman.transforms()
        slayer.draw_slayer_shadow(painter, stickman, transforms)
        draw_slayer_cape(painter, stickman, transforms)
    if nature_hero:
        if transforms is None:
            transforms = stickman.transforms()
        draw_nature_aura(painter, stickman, transforms)
        if has[stickman.layout.torso]:
            draw_natures_wrath_cape(painter, stickman, transforms)
    equipment_behind = variant == "hero_fighter"
    if not held or equipment_behind:
        if equipment_behind:
            draw_trail(painter, stickman.trail)
        draw_strokes(painter, strokes[3:] if hammer_away else strokes)
    elif variant == "hero_paladin" and not hammer_away:
        draw_trail(painter, stickman.trail)
        draw_strokes(painter, strokes[:3])  # Far-hand hammer sits behind his body and shield.

    def costume(transforms) -> None:
        if variant in ("wizard", "hero_wizard") and has[stickman.layout.head]:
            _draw_hat(
                painter, stickman, transforms,
                radius=IGGY_HAT_RADIUS if variant == "hero_wizard" else None,
            )
        elif variant in ("fighter", "hero_fighter") and has[stickman.layout.head]:
            draw_fighter_helmet(painter, stickman, transforms)
        elif variant == "druid" and has[stickman.layout.head]:
            _draw_antlers(painter, stickman, transforms)
        elif variant == "hero_druid" and has[stickman.layout.head]:
            draw_natures_wrath_head(painter, stickman, transforms)
        elif variant == "hero_rogue" and has[stickman.layout.head]:
            draw_slayer_bandana(painter, stickman, transforms)
        elif variant == "hero_ranger" and has[stickman.layout.head]:
            hunter.draw_hat(painter, stickman, transforms)
        elif cleric_hero and has[stickman.layout.head]:
            hero_cleric.draw_halo(painter, stickman, transforms)
        elif alchemist_hero and has[stickman.layout.head]:
            hero_alchemist.draw_headgear(painter, stickman, transforms)
        elif sorcerer_hero and has[stickman.layout.head]:
            hero_sorcerer.draw_skull_face(
                painter,
                stickman,
                transforms,
                SELECTED if selected else outline,
            )
        if variant in ("sorcerer", "hero_sorcerer") and has[stickman.layout.torso]:
            _draw_scarf(painter, stickman, transforms)
        if stickman.thrall and has[stickman.layout.head]:
            _draw_thrall_brain(painter, stickman, transforms)

    def over_legs(transforms) -> None:
        if variant == "hero_ranger" and has[stickman.layout.torso]:
            hunter.draw_pistol(painter, stickman, transforms)
        if variant in ("cleric", "hero_cleric", "hero_wizard") and has[stickman.layout.torso]:
            _draw_robe(painter, stickman, transforms)
        if held and variant not in (
            "hero_fighter", "hero_paladin", "hero_alchemist", "hero_sorcerer",
        ):
            draw_trail(painter, stickman.trail)
            draw_strokes(painter, strokes)

    near, far = CLASS_COLORS.get(variant, (NEAR_LIMB, FAR_LIMB))
    if getattr(stickman, "is_simulacrum", False):
        near, far = iggy.COPY_BODY, iggy.COPY_FAR
    if shadow_clone:
        near, far = slayer.SHADOW, slayer.SHADOW_FAR
    if variant == "hero_barbarian":
        near = mix(near, RAGE, stickman.fury * 0.85)
        far = mix(far, RAGE.darker(160), stickman.fury * 0.85)
    if stickman.thrall:
        near, far = mix(near, FLAYER_SKIN, THRALL_TINT), mix(far, FLAYER_SKIN_FAR, THRALL_TINT)
    head = (
        GOBLIN_HEAD if variant == "hero_druid"
        else hero_sorcerer.BONE if sorcerer_hero
        else BACKGROUND
    )
    if getattr(stickman, "is_simulacrum", False):
        head = iggy.COPY_HEAD
    if shadow_clone:
        head = slayer.SHADOW_DARK
    if stickman.damage:
        hurt = 0.72 * min(1.0, stickman.damage / stickman.max_hp)
        near, far = mix(near, WOUNDED, hurt), mix(far, WOUNDED, hurt)
    if stickman.burn is not None:
        char = stickman.burn.char
        near, far = mix(near, CHARRED, char), mix(far, CHARRED_FAR, char)
        head = mix(head, CHARRED, char)
    if stickman.demise is not None:
        near, far, head = demise_colors(stickman.demise, near, far, head)
    body_width = None
    if nature_hero:
        body_width = NATURES_WRATH_BODY_WIDTH * stickman.layout.scale
    elif variant == "hero_barbarian":
        body_width = MIGHTY_BODY_WIDTH * stickman.layout.scale
    elif variant == "hero_wizard":
        body_width = iggy.BODY_WIDTH * stickman.layout.scale
    elif variant == "hero_rogue":
        body_width = slayer.BODY_WIDTH * stickman.layout.scale
    elif variant == "hero_ranger":
        body_width = hunter.BODY_WIDTH * stickman.layout.scale
    elif cleric_hero:
        body_width = hero_cleric.BODY_WIDTH * stickman.layout.scale
    elif alchemist_hero:
        body_width = hero_alchemist.BODY_WIDTH * stickman.layout.scale
    elif sorcerer_hero:
        body_width = hero_sorcerer.BODY_WIDTH * stickman.layout.scale
    elif variant == "hero_fighter":
        body_width = hero_fighter.BODY_WIDTH * stickman.layout.scale
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
        body_width=body_width,
        head_width=(body_width * 0.5 if alchemist_hero and body_width is not None else None),
        show_head_base=not sorcerer_hero,
        show_joints=not nature_hero,
        joint_color=(
            near
            if variant in (
                "hero_wizard", "hero_rogue", "hero_ranger", "hero_cleric",
                "hero_alchemist",
                "hero_sorcerer",
                "hero_fighter",
            )
            else None
        ),
    )

    if alchemist_hero:
        hero_alchemist.draw_gloves_and_tubes(painter, stickman, transforms)
        if held:
            draw_trail(painter, stickman.trail)
            draw_strokes(painter, strokes)
    elif sorcerer_hero:
        if held:
            draw_strokes(painter, [stroke for stroke in strokes if stroke.kind != "orb"])
            hero_sorcerer.draw_focus(
                painter,
                stickman,
                transforms,
                SELECTED if selected else outline,
            )
        hero_sorcerer.draw_orbiting_skulls(
            painter,
            stickman,
            transforms,
            front=True,
            outline=SELECTED if selected else outline,
        )

    if variant == "hero_fighter":
        hero_fighter.draw_armor(painter, stickman, transforms, hidden)
    elif variant == "hero_barbarian":
        draw_mighty_details(painter, stickman, transforms, hidden)
    elif variant == "hero_paladin":
        _draw_hero_armor(painter, stickman, transforms, hidden)
        if held:
            draw_strokes(painter, strokes[3:])
    elif cleric_hero:
        hero_cleric.draw_resurrection_flash(painter, stickman)

    if stickman.divine_prayer > 0.0:
        hero_cleric.draw_prayer_glow(painter, stickman, transforms)

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


def _draw_hat(
    painter: QPainter, stickman: Stickman, transforms, radius: float | None = None
) -> None:
    """A wizard's tall pointed hat, its tip flopping back, on a wide brim."""
    fill, edge, star = (
        (iggy.HAT, iggy.HAT_EDGE, iggy.HAT_STAR)
        if stickman.variant == "hero_wizard" else (HAT, HAT_EDGE, HAT_STAR)
    )
    center, up, back, r = _head_frame(stickman, transforms)
    if radius is not None:
        # Keep the brim seated on the head while preserving the full hat geometry.
        center += up * (0.55 * (r - radius))
        r = radius
    side = up.rotated(math.pi / 2)
    base = center + up * (0.7 * r)
    bend = base + up * (1.3 * r) + back * (0.25 * r)
    tip = base + up * (2.1 * r) + back * (1.1 * r)
    cone = [base - side * (0.85 * r), bend - side * (0.35 * r), tip, bend + side * (0.35 * r)]
    _polygon(painter, [*cone, base + side * (0.85 * r)], fill, edge)
    brim = center + up * (0.55 * r)
    _polygon(
        painter,
        [
            brim - side * (1.5 * r),
            brim + side * (1.5 * r),
            brim + side * (1.2 * r) + up * (0.35 * r),
            brim - side * (1.2 * r) + up * (0.35 * r),
        ],
        fill,
        edge,
    )
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(star)
    painter.drawEllipse(qt(base.lerp(bend, 0.5)), 0.22 * r, 0.22 * r)


def draw_fighter_helmet(painter: QPainter, stickman: Stickman, transforms) -> None:
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


def _draw_scarf(painter: QPainter, stickman: Stickman, transforms) -> None:
    """A neck wrap and two trailing ends, attached to the torso pose."""
    scarf, edge = (
        (hero_sorcerer.SCARF, hero_sorcerer.SCARF_EDGE)
        if stickman.variant == "hero_sorcerer"
        else (SCARF, SCARF_EDGE)
    )
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
            scarf,
            edge,
        )
    painter.setPen(world_pen(edge, r * 0.7))
    painter.drawLine(qt(neck - back * (0.5 * r)), qt(neck + back * (0.5 * r)))
    painter.setPen(world_pen(scarf, r * 0.45))
    painter.drawLine(qt(neck - back * (0.5 * r)), qt(neck + back * (0.5 * r)))


def _draw_robe(painter: QPainter, stickman: Stickman, transforms) -> None:
    """A fitted robe with a sash, stole, and flared skirt that swings with the legs."""
    fill, edge, sash = (
        (iggy.ROBE, iggy.ROBE_EDGE, iggy.ROBE_SASH)
        if stickman.variant == "hero_wizard" else (ROBE, ROBE_EDGE, ROBE_SASH)
    )
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
    painter.setPen(pen(edge, 1.0))
    painter.setBrush(fill)
    painter.drawPath(path)

    painter.setPen(world_pen(sash, 0.22 * r))
    painter.drawLine(qt(torso.end + forward * (0.2 * r)), qt(hem_middle.lerp(hem_front, 0.4)))
    painter.setPen(world_pen(sash, 0.32 * r))
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
                painter.setPen(world_pen(alpha(color, 255 * fade), 3.0 * taper + extra))
                painter.drawLine(qt(a), qt(b))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(alpha(WEAPON_COLORS["leaf"], 255 * fade))
        for i in range(2, count, 3):
            a, b = points[i], points[i + 1]
            along = (b - a).normalized()
            out = along.rotated((1 if i % 2 else -1) * math.pi / 2.6)
            leaf_at = a + out * 2.2
            painter.drawEllipse(qt(leaf_at), 1.4, 1.0)
        if vine.age < VINE_GROW + 0.15:
            tip = points[-1]
            painter.setBrush(alpha(VINE_DARK, 255 * fade))
            painter.drawEllipse(qt(tip), 1.6, 1.6)
