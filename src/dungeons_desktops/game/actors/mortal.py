"""Shared mortal lifecycle and corpse fading."""

from __future__ import annotations

FADE_TIME = 0.5


class Mortal:
    """HP and the fade-out after death. Subclasses set `max_hp` and how long the body
    `linger`s, and implement `die` and `update_dead`."""

    max_hp = 1
    linger = 3.0
    """Seconds a body lies there before it starts fading."""
    damage = 0
    dead = False
    down_time = 0.0

    @property
    def hp(self) -> float:
        return max(0, self.max_hp - self.damage)

    @property
    def fade(self) -> float:
        """0 while alive or freshly dead; rises to 1 as the body fades out."""
        if not self.dead:
            return 0.0
        return min(1.0, max(0.0, (self.down_time - self.linger) / FADE_TIME))

    @property
    def gone(self) -> bool:
        return self.dead and self.down_time >= self.linger + FADE_TIME
