"""A compact bear assembled from broad body masses, with a curved red crest."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.heroes.natures_wrath.bear import (
    MAUL_HIT,
    MAUL_WINDUP,
    BearLeg,
    GiantBear,
)
from dungeons_desktops.game.heroes.natures_wrath.render import MOHAWK, draw_nature_magic
from dungeons_desktops.render.primitives import alpha, qt, world_pen

FUR = QColor(88, 53, 29)
FAR = QColor(76, 46, 26)
INK = QColor(24, 17, 13)


def draw_bear(painter: QPainter, bear: GiantBear, outline: QColor | None = None) -> None:
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    f = bear.facing

    def aura(front: bool) -> None:
        if bear.hero.animated:
            draw_nature_magic(
                painter,
                bear.body + Vec2(f * 6, 0),
                bear.hero.nature_time,
                bear.hero.layout.head_radius,
                x_spread=9.0,
                y_spread=4.0,
                leaves=8,
                leaf_scale=1.4,
                front=front,
            )

    aura(False)

    def at(origin: Vec2, x: float, y: float) -> Vec2:
        return origin + Vec2(f * x, y)

    def leg(part: BearLeg) -> QPainterPath:
        # A continuous taper avoids visible knee corners; the front legs are wider.
        root, middle, foot = part.root, part.knee, part.foot
        if part.front and part.near and bear.maul_time is not None:
            # The lifted paw turns with the swipe instead of keeping a planted-foot shape.
            along = (foot - root).normalized()
            side = Vec2(-along.y, along.x)
            path = QPainterPath(qt(root - side * 14))
            path.quadTo(qt(root - along * 13), qt(root + side * 14))
            path.cubicTo(qt(middle + side * 13), qt(foot + side * 10), qt(foot + side * 9))
            path.quadTo(qt(foot + along * 14), qt(foot - side * 9))
            path.cubicTo(qt(foot - side * 10), qt(middle - side * 13), qt(root - side * 14))
            path.closeSubpath()
            return path
        upper = 16 if part.front else 14
        lower = 11 if part.front else 8
        top = root.lerp(foot, 0.3)
        path = QPainterPath(qt(at(root, -upper, -2)))
        path.cubicTo(
            qt(at(top, -upper * 0.85, 0)), qt(at(middle, -lower, 0)), qt(at(foot, -lower, -5))
        )
        path.quadTo(qt(at(foot, -lower, 0)), qt(at(foot, -lower + 3, 0)))
        path.lineTo(qt(at(foot, 13, 0)))
        path.quadTo(qt(at(foot, 17, -1)), qt(at(foot, 12, -5)))
        path.lineTo(qt(at(foot, 7, -7)))
        path.cubicTo(
            qt(at(middle, lower, 0)), qt(at(top, upper * 0.85, 0)), qt(at(root, upper, -2))
        )
        path.cubicTo(
            qt(at(root, upper - 2, -14)), qt(at(root, -upper + 2, -14)), qt(at(root, -upper, -2))
        )
        path.closeSubpath()
        return path

    hip, shoulder, head = bear.hip, bear.shoulder, bear.head
    # Reference ratios: the head is roughly half the torso length and four-fifths its depth.
    # Keep the body, head and limbs as separate filled masses without decorative borders.
    body = QPainterPath(qt(at(hip, -18, -2)))
    body.cubicTo(qt(at(hip, -18, -18)), qt(at(hip, -5, -24)), qt(at(hip, 4, -21)))
    body.cubicTo(qt(at(hip, 19, -16)), qt(at(shoulder, -14, -16)), qt(at(shoulder, -7, -22)))
    body.cubicTo(qt(at(shoulder, 4, -26)), qt(at(shoulder, 17, -15)), qt(at(shoulder, 17, -1)))
    body.cubicTo(qt(at(shoulder, 18, 13)), qt(at(shoulder, 8, 21)), qt(at(shoulder, -4, 21)))
    body.cubicTo(qt(at(hip, 14, 23)), qt(at(hip, -2, 24)), qt(at(hip, -12, 15)))
    body.quadTo(qt(at(hip, -20, 10)), qt(at(hip, -18, -2)))
    body.closeSubpath()

    face = QPainterPath(qt(at(head, -18, -3)))
    face.cubicTo(qt(at(head, -19, -16)), qt(at(head, -6, -20)), qt(at(head, 5, -15)))
    face.quadTo(qt(at(head, 13, -13)), qt(at(head, 13, -7)))
    face.cubicTo(qt(at(head, 16, -4)), qt(at(head, 23, -3)), qt(at(head, 23, 2)))
    face.quadTo(qt(at(head, 24, 7)), qt(at(head, 15, 9)))
    face.cubicTo(qt(at(head, 10, 15)), qt(at(head, 7, 18)), qt(at(head, 0, 19)))
    face.cubicTo(qt(at(head, -11, 17)), qt(at(head, -18, 10)), qt(at(head, -18, -3)))
    face.closeSubpath()
    ears = QPainterPath()
    ears.addEllipse(qt(at(head, -12, -13)), 4.5, 5.0)
    ears.addEllipse(qt(at(head, 6, -14)), 3.5, 4.0)
    face = face.united(ears)
    legs = [(part, leg(part)) for part in bear.legs]

    if outline is not None:
        silhouette = body.united(face)
        for _, path in legs:
            silhouette = silhouette.united(path)
        painter.setPen(world_pen(outline, 2))
        painter.setBrush(FUR)
        painter.drawPath(silhouette)
        painter.setPen(Qt.PenStyle.NoPen)
    for part, path in legs:
        if not part.near:
            painter.setBrush(FAR)
            painter.drawPath(path)
    painter.setBrush(FUR)
    painter.drawPath(body)
    for part, path in legs:
        if part.near and not (part.front and bear.maul_time is not None):
            painter.drawPath(path)
    painter.drawPath(face)

    # A plain red oval replaces the pupil and highlight.
    eye = at(head, 7, -7)
    painter.setBrush(QColor(235, 35, 42))
    painter.drawEllipse(qt(eye), 2.6, 1.5)
    nose = QPainterPath(qt(at(head, 18, -2)))
    nose.quadTo(qt(at(head, 22, -3)), qt(at(head, 23, 0)))
    nose.quadTo(qt(at(head, 24, 3)), qt(at(head, 21, 5)))
    nose.quadTo(qt(at(head, 17, 3)), qt(at(head, 18, -2)))
    painter.setBrush(INK)
    painter.drawPath(nose)

    # One arcing fan follows the crown and curls down the back of the skull.
    sweep = bear.charge * 3
    crest = QPainterPath(qt(at(head, 7, -14)))
    crest.cubicTo(
        qt(at(head, 1 - sweep, -30)), qt(at(head, -18 - sweep, -29)), qt(at(head, -20, -8))
    )
    crest.lineTo(qt(at(head, -15, -7)))
    crest.cubicTo(
        qt(at(head, -15 - sweep, -12)), qt(at(head, -2 - sweep, -17)), qt(at(head, 7, -14))
    )
    crest.closeSubpath()
    painter.setBrush(MOHAWK)
    painter.drawPath(crest)
    # The near ear sits in front of the crest, keeping the bear silhouette readable.
    painter.setBrush(FUR)
    painter.drawEllipse(qt(at(head, -12, -13)), 4.5, 5.0)
    if bear.maul_time is not None:
        for part, path in legs:
            if part.near and part.front:
                painter.drawPath(path)
                if MAUL_WINDUP < bear.maul_time < MAUL_HIT + 0.08:
                    strength = max(0.0, 1 - abs(bear.maul_time - MAUL_HIT) / 0.15)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    for offset in (-3, 0, 3):
                        tip = part.foot + Vec2(f * 10, offset - 3)
                        streak = QPainterPath(qt(tip + Vec2(-f * 15, -18)))
                        streak.quadTo(qt(tip + Vec2(f * 2, -12)), qt(tip))
                        painter.setPen(world_pen(alpha(QColor(232, 231, 191), 150 * strength), 0.9))
                        painter.drawPath(streak)
    aura(True)
    painter.restore()
