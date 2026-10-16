"""Health bars, kill counter, and floating kill marks."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.game.world.simulation import KILL_MARK_TIME, KillMark
from dungeons_desktops.render.primitives import alpha, qt

KILL_MARK_TEXT = "+\N{SKULL}"
KILL_MARK_SIZE = 15
KILL_MARK_LIFT = 14.0
KILL_MARK_RISE = 22.0
KILL_MARK_COLOR = QColor(255, 236, 228)
KILL_MARK_SHADOW = QColor(0, 0, 0, 170)
COUNTER_BACK = QColor(20, 20, 26, 170)
COUNTER_TEXT = QColor(240, 232, 214)
HEALTH_BAR_HEIGHT = 20.0
SKULL = QColor(236, 230, 214)
WOUNDED = QColor(214, 128, 132)


def draw_kill_counter(painter: QPainter, kills: int, corner: Vec2, bump: float = 0.0) -> None:
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
    painter.setBrush(SKULL if bump == 0.0 else WOUNDED)
    painter.drawEllipse(qt(center), skull, skull * 0.9)
    painter.drawRoundedRect(QRectF(center.x - 4.0, center.y + 3.0, 8.0, 5.5), 1.5, 1.5)
    painter.setBrush(COUNTER_BACK.darker(150))
    for side in (-1.0, 1.0):
        painter.drawEllipse(qt(center + Vec2(2.8 * side, 0.5)), 2.0, 2.2)
    painter.drawPolygon(
        [
            qt(center + Vec2(0.0, 3.0)),
            qt(center + Vec2(-1.0, 4.6)),
            qt(center + Vec2(1.0, 4.6)),
        ]
    )
    painter.setFont(font)
    painter.setPen(COUNTER_TEXT)
    left = pad + 2 * skull + gap
    painter.drawText(QRectF(left, 0, text_width + 1.0, height), Qt.AlignmentFlag.AlignVCenter, text)
    painter.restore()


def draw_kill_marks(painter: QPainter, marks: Iterable[KillMark]) -> None:
    font = QFont(painter.font())
    font.setPixelSize(KILL_MARK_SIZE)
    font.setBold(True)
    painter.save()
    painter.setFont(font)
    for mark in marks:
        age = mark.age / KILL_MARK_TIME
        pop = 1.0 + 0.4 * max(0.0, 1.0 - age / 0.15)
        rise = KILL_MARK_RISE * smoothstep(min(1.0, age * 1.5))
        painter.save()
        painter.translate(qt(mark.point - Vec2(0.0, KILL_MARK_LIFT + rise)))
        painter.scale(pop, pop)
        painter.setOpacity(1.0 - smoothstep(clamp((age - 0.5) / 0.5, 0.0, 1.0)))
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
        painter.setBrush(alpha(color, color.alpha()))
        painter.drawRoundedRect(
            QRectF(track.x(), track.y(), max(filled, thickness), thickness),
            thickness / 2,
            thickness / 2,
        )
    painter.restore()
