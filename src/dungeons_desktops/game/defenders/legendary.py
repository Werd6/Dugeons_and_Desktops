"""Shared legendary power floor applied when a defender summons in its upgraded form."""

from __future__ import annotations

from typing import Any

from PySide6.QtGui import QColor

from dungeons_desktops.game.unlocks import LEGENDARY_NAMES

LEGENDARY_HP = 1.5
"""How much tougher a legendary body is than its base form."""
LEGENDARY_DAMAGE_BONUS = 1
"""Flat damage added to legendary hits that use `legendary_damage`."""
LEGENDARY_GOLD = QColor(214, 170, 92)
"""Health-bar and accent colour for legendary forms."""


def legendary_name(kind: str) -> str:
    return LEGENDARY_NAMES.get(kind, kind.replace("_", " ").title())


def apply_legendary(body: Any, base_hp: int | None = None) -> None:
    """Mark `body` legendary and raise its `max_hp` from the class (or `base_hp`) floor."""
    body.legendary = True
    floor = type(body).max_hp if base_hp is None else base_hp
    body.max_hp = max(1, int(round(floor * LEGENDARY_HP)))
    if hasattr(body, "damage"):
        body.damage = 0


def legendary_damage(base: int, legendary: bool) -> int:
    """Outgoing hit strength, with the shared legendary bump when upgraded."""
    return base + LEGENDARY_DAMAGE_BONUS if legendary else base
