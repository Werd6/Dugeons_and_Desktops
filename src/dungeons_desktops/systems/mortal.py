"""Monster HP: what the goblins, the worm, the dragon, the mind flayer and its
intellect devourers, and the displacer beast share.

Every adventurer attack that lands takes `ADVENTURER_DAMAGE` off a monster. At 0 HP
the world moves it out of the living (`SimWorld.hurt_monster`) into `fallen`, where
it falls limp, lies a while, fades, and is gone.
"""

from __future__ import annotations

GOBLIN_HP = 5
WORM_HP = 4
DRAGON_HP = 15
MIND_FLAYER_HP = 9
DEVOURER_HP = 3
DISPLACER_HP = 14
MINOTAUR_HP = 26
LICH_HP = 6
SKELETON_HP = 2
MIMIC_HP = 8
HYDRA_HP = 20
DRAKE_HP = 4
KOBOLD_HP = 2
LIZARD_HP = 5
DROW_HP = 0
CHIMERA_HP = 22
ELEMENTAL_HP = 20
ADVENTURER_DAMAGE = 1
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
    def hp(self) -> int:
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
