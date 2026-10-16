"""Compatibility exports for mortal lifecycle and feature-owned HP constants."""

from __future__ import annotations

import warnings

from dungeons_desktops.game.actors.mortal import FADE_TIME, Mortal
from dungeons_desktops.game.adventurers.combat import ADVENTURER_DAMAGE
from dungeons_desktops.game.defenders.chimera.actor import CHIMERA_HP
from dungeons_desktops.game.defenders.displacer.actor import DISPLACER_HP
from dungeons_desktops.game.defenders.dragon.actor import DRAGON_HP
from dungeons_desktops.game.defenders.drakes.drake import DRAKE_HP
from dungeons_desktops.game.defenders.drakes.kobold import KOBOLD_HP
from dungeons_desktops.game.defenders.drow.actor import DROW_HP, LIZARD_HP
from dungeons_desktops.game.defenders.elementals.actor import ELEMENTAL_HP
from dungeons_desktops.game.defenders.goblins.actor import GOBLIN_HP
from dungeons_desktops.game.defenders.hydra.actor import HYDRA_HP
from dungeons_desktops.game.defenders.lich.actor import LICH_HP
from dungeons_desktops.game.defenders.lich.skeletons import SKELETON_HP
from dungeons_desktops.game.defenders.mimic.actor import MIMIC_HP
from dungeons_desktops.game.defenders.mindflayer.actor import MIND_FLAYER_HP
from dungeons_desktops.game.defenders.mindflayer.devourer import DEVOURER_HP
from dungeons_desktops.game.defenders.minotaur.actor import MINOTAUR_HP
from dungeons_desktops.game.defenders.ooze.actor import OOZE_HP
from dungeons_desktops.game.defenders.worm.actor import WORM_HP

warnings.warn(
    "dungeons_desktops.systems.mortal moved to game.actors.mortal and feature packages",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "ADVENTURER_DAMAGE", "CHIMERA_HP", "DEVOURER_HP", "DISPLACER_HP", "DRAGON_HP",
    "DRAKE_HP", "DROW_HP", "ELEMENTAL_HP", "FADE_TIME", "GOBLIN_HP", "HYDRA_HP",
    "KOBOLD_HP", "LICH_HP", "LIZARD_HP", "MIMIC_HP", "MIND_FLAYER_HP", "MINOTAUR_HP",
    "Mortal", "OOZE_HP", "SKELETON_HP", "WORM_HP",
]
