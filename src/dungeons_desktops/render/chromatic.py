"""Shared cat substitutions, stone statues, and dragon-style elemental corpses."""

from __future__ import annotations

from dataclasses import dataclass
from functools import wraps

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPicture

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.effects.chromatic import RayEffect, body_center
from dungeons_desktops.game.effects.render import draw_demise_over, draw_demise_under
from dungeons_desktops.game.heroes.the_inquisitive.companion_render import draw_cat_shape
from dungeons_desktops.render.primitives import alpha, qt, world_pen
from dungeons_desktops.rig.skeleton import BoneTransform


@dataclass
class Stamp:
    image: QImage
    bounds: QRectF
    origin: Vec2


def chromatic_appearance(draw):
    """Wrap one creature's native renderer; ordinary creatures take the unchanged path."""
    @wraps(draw)
    def wrapped(painter, actor, *args, **kwargs):
        if getattr(actor, "chromatic_shattered", False):
            return
        state = getattr(actor, "chromatic_status", None)
        if state is None:
            return draw(painter, actor, *args, **kwargs)
        painter.save()
        if state.effect is RayEffect.POLYMORPH:
            delta = body_center(actor) - state.origin
            feet = Vec2(state.origin.x, max(p.y for p in state.points)) + delta
            painter.translate(qt(feet))
            painter.scale(2.2 * getattr(actor, "facing", 1), 2.2)
            draw_cat_shape(painter, state.time)
            painter.setPen(world_pen(alpha(QColor(195, 111, 255), 125), 0.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(qt(Vec2(0, -4)), 7.7, 6.4)
        else:
            if state.render_cache is None:
                state.render_cache = _capture(draw, actor, state.effect, args, kwargs)
            stamp = state.render_cache
            delta = body_center(actor) - stamp.origin
            painter.translate(qt(delta))
            if state.demise is None:
                painter.drawImage(stamp.bounds, stamp.image)
            else:
                _draw_demise(painter, stamp, state.demise)
        painter.restore()
    return wrapped


def draw_chromatic_effects(painter, effects) -> None:
    """Stone shards and dust outlive the vanished statue and its caster."""
    painter.save()
    for burst in effects.shatters:
        for mote in burst.motes:
            fade = min(1.0, (1 - mote.t) * 3)
            if mote.kind == "mist":
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(alpha(QColor(151, 151, 146), 70 * (1 - mote.t)))
                size = mote.size * (1 + mote.t)
                painter.drawEllipse(qt(mote.position), size, size * 0.7)
                continue
            corners = [mote.position + Vec2.from_angle(mote.angle + a, mote.size * r)
                       for a, r in ((0, 1), (1.5, 0.7), (3.1, 1.1), (4.8, 0.7))]
            painter.setPen(world_pen(alpha(QColor(82, 85, 91), 255 * fade), 0.5))
            painter.setBrush(alpha(QColor(159, 163, 171), 255 * fade))
            painter.drawPolygon([qt(p) for p in corners])
            painter.setPen(world_pen(alpha(QColor(212, 214, 218), 200 * fade), 0.5))
            painter.drawLine(qt(corners[0]), qt(corners[1]))
    painter.restore()


def _capture(draw, actor, effect, args, kwargs) -> Stamp:
    picture = QPicture()
    recorder = QPainter(picture)
    recorder.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw(recorder, actor, *args, **kwargs)
    recorder.end()
    bounds = QRectF(picture.boundingRect()).adjusted(-3, -3, 3, 3)
    scale = min(3.0, 1200 / max(1, bounds.width(), bounds.height()))
    image = QImage(max(1, round(bounds.width() * scale)),
                   max(1, round(bounds.height() * scale)), QImage.Format.Format_RGBA8888)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(scale, scale)
    painter.translate(-bounds.x(), -bounds.y())
    painter.drawPicture(0, 0, picture)
    painter.end()
    tint = {
        RayEffect.PETRIFY: (187, 190, 194),
        RayEffect.ACID: (168, 216, 72),
        RayEffect.ICE: (173, 229, 255),
    }[effect]
    # Qt performs these image-wide operations natively; Python pixel loops stall
    # the first frame when several large creatures become statues together.
    toned = image.convertToFormat(QImage.Format.Format_Grayscale8).convertToFormat(
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    painter = QPainter(toned)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
    painter.fillRect(toned.rect(), QColor(76, 76, 76))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
    painter.fillRect(toned.rect(), QColor(*tint))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    painter.drawImage(0, 0, image)
    painter.end()
    image = toned
    if effect is RayEffect.PETRIFY:
        painter = QPainter(image)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
        painter.scale(scale, scale)
        painter.translate(-bounds.x(), -bounds.y())
        painter.setPen(world_pen(QColor(73, 77, 85, 190), 0.6))
        for portion in (0.28, 0.55, 0.76):
            start = Vec2(bounds.x() + bounds.width() * portion, bounds.y())
            elbow = start + Vec2(-bounds.width() * 0.1, bounds.height() * 0.35)
            end = elbow + Vec2(bounds.width() * 0.07, bounds.height() * 0.22)
            painter.drawLine(qt(start), qt(elbow))
            painter.drawLine(qt(elbow), qt(end))
        painter.end()
    return Stamp(image, bounds, body_center(actor))


def _draw_demise(painter, stamp, demise):
    bounds = stamp.bounds
    top = Vec2(bounds.left() + 3, bounds.top() + 3)
    bottom = Vec2(bounds.right() - 3, bounds.bottom() - 3)
    transforms = {"body": BoneTransform(top, bottom, 0)}
    radius = max(4.5, bounds.width() * 0.18)
    draw_demise_under(painter, demise, transforms)
    if not demise.shattered:
        painter.save()
        if demise.kind == "acid":
            center = Vec2(bounds.center().x(), bottom.y)
            painter.translate(qt(center))
            painter.scale(1 + 0.4 * demise.melt, max(0.015, 1 - demise.melt))
            painter.translate(-qt(center))
        painter.drawImage(bounds, stamp.image)
        painter.restore()
    draw_demise_over(painter, demise, transforms, radius)
